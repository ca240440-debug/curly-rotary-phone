"""Single-family local prototype. Child projections never serialize purchase rows."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from retailers import RETAILERS, normalize_product_url
from catalog import INTEGRATIONS, seed_samples
from recommendations import RATINGS, suggested_defaults, permitted, recommendation

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('WISHLIST_DATA', str(ROOT / '.local')))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'wishes.db'
APP_ORIGINS = set(filter(None, os.environ.get('WISHNEST_APP_ORIGINS', '').split(',')))
CONSENT_VERSION = 'family-controls-v3'
PRIORITIES = ('Must Have', 'Would Love', 'Nice to Have')
sessions = {}
attempts = {}
lock = threading.Lock()


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA secure_delete=ON')
    db.execute('PRAGMA foreign_keys=ON')
    return db


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def money(value):
    if value is None or value == '':
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 <= amount <= 100000 or amount.as_tuple().exponent < -2:
            raise ValueError('Use a price from 0 to 100000 with at most two decimal places.')
        return int(amount * 100)
    except InvalidOperation:
        raise ValueError('Enter a valid price.')


def dollars(cents):
    return None if cents is None else cents / 100


def text(value, maximum=150):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError('Enter a name within the length limit.')
    return value.strip()


def boolean(value):
    if type(value) is not bool:
        raise ValueError('Permissions and statuses must be true or false.')
    return int(value)


def consented(db):
    row = db.execute("SELECT value FROM settings WHERE key='consent'").fetchone()
    return row is not None and row['value'] == CONSENT_VERSION


def pin_hash(pin, salt):
    return hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS profiles (
          id INTEGER PRIMARY KEY, nickname TEXT NOT NULL, code_hash TEXT,
          show_prices INTEGER NOT NULL DEFAULT 0, show_budget INTEGER NOT NULL DEFAULT 0,
          show_links INTEGER NOT NULL DEFAULT 0, budget_cents INTEGER);
        CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS offers (
          id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
          retailer TEXT NOT NULL, url TEXT NOT NULL, price_cents INTEGER,
          source TEXT NOT NULL DEFAULT 'manual', observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(product_id, retailer));
        CREATE TABLE IF NOT EXISTS offer_prices (
          id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id),
          price_cents INTEGER, source TEXT, observed_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS wishes (
          id INTEGER PRIMARY KEY, name TEXT, child TEXT, retailer TEXT, url TEXT,
          price REAL, target REAL, purchased INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS prices (
          id INTEGER PRIMARY KEY, wish_id INTEGER, price REAL, recorded TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        product_columns = {r['name'] for r in db.execute('PRAGMA table_info(products)')}
        for name, kind in [('category',"TEXT NOT NULL DEFAULT 'Family Finds'"),
                           ('image_key',"TEXT NOT NULL DEFAULT 'gift'"),
                           ('source_kind',"TEXT NOT NULL DEFAULT 'manual'"), ('external_id','TEXT')]:
            if name not in product_columns:
                db.execute('ALTER TABLE products ADD COLUMN ' + name + ' ' + kind)
        for table, fields in {
            'products': [('media_type',"TEXT NOT NULL DEFAULT 'general'"), ('content_rating','TEXT'),
                ('rating_verified','INTEGER NOT NULL DEFAULT 0'), ('rating_source','TEXT'),
                ('recommended_age_min','INTEGER'), ('mandatory_restriction',"TEXT NOT NULL DEFAULT ''")],
            'profiles': [('child_age','INTEGER'), ('use_age_recommendations','INTEGER NOT NULL DEFAULT 1'),
                ('allowed_categories',"TEXT NOT NULL DEFAULT 'null'"),
                ('allowed_ratings',"TEXT NOT NULL DEFAULT '[\"E\",\"E10+\"]'"),
                ('allow_unverified_games','INTEGER NOT NULL DEFAULT 0'),
                ('require_approval','INTEGER NOT NULL DEFAULT 0')],
            'wishes': [('review_state',"TEXT NOT NULL DEFAULT 'approved'")]
        }.items():
            existing = {r['name'] for r in db.execute('PRAGMA table_info(' + table + ')')}
            for name, kind in fields:
                if name not in existing:
                    db.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + name + ' ' + kind)
        columns = {r['name'] for r in db.execute('PRAGMA table_info(wishes)')}
        for name, kind in [('profile_id','INTEGER'), ('product_id','INTEGER'),
                           ('priority',"TEXT NOT NULL DEFAULT 'Would Love'"),
                           ('reserved','INTEGER NOT NULL DEFAULT 0'), ('actual_paid_cents','INTEGER'),
                           ('reference_cents','INTEGER')]:
            if name not in columns:
                db.execute('ALTER TABLE wishes ADD COLUMN ' + name + ' ' + kind)
        # Preserve legacy lists, grouped by nickname. Adult must issue child codes.
        for row in db.execute('SELECT * FROM wishes WHERE profile_id IS NULL').fetchall():
            nickname = row['child'] or 'My wishes'
            profile = db.execute('SELECT id FROM profiles WHERE nickname=?', (nickname,)).fetchone()
            profile_id = profile['id'] if profile else db.execute('INSERT INTO profiles(nickname) VALUES (?)', (nickname,)).lastrowid
            product_id = db.execute('INSERT INTO products(name) VALUES (?)', (row['name'],)).lastrowid
            db.execute('UPDATE wishes SET profile_id=?, product_id=? WHERE id=?', (profile_id, product_id, row['id']))
            if row['url']:
                try:
                    retailer, url = normalize_product_url(row['url'])
                    db.execute('INSERT INTO offers(product_id,retailer,url,price_cents) VALUES (?,?,?,?)',
                               (product_id, retailer, url, money(row['price'])))
                except ValueError:
                    pass  # Keep original legacy fields for the parent; never follow invalid URLs.
        if os.environ.get('WISHNEST_SAMPLE_PRODUCTS', '1') != '0':
            seed_samples(db)


initialize()


def profile_public(row):
    result = {'id':row['id'], 'nickname':row['nickname'], 'permissions':{
        'prices':bool(row['show_prices']), 'budget':bool(row['show_budget']), 'links':bool(row['show_links'])}}
    if row['show_budget']:
        result['budget'] = dollars(row['budget_cents'])
    return result


def product_public(db, row, profile=None):
    """Only catalog fields; no private wish state or history enters this function."""
    show_prices = profile is None or profile['show_prices']
    show_links = profile is None or profile['show_links']
    item = {'id':row['id'], 'name':row['name'], 'category':row['category'],
            'image':'/images/' + row['image_key'] + '.svg', 'source_kind':row['source_kind'],
            'media_type':row['media_type'], 'content_rating':row['content_rating'],
            'rating_verified':bool(row['rating_verified']), 'rating_source':row['rating_source'] if row['rating_verified'] else None,
            'source_label':'Sample product · illustrative prices' if row['source_kind'] == 'sample' else 'Family entry · manually recorded', 'offers':[]}
    if profile is not None:
        item['recommendation'] = recommendation(row, profile)
    else:
        item['recommended_age_min'] = row['recommended_age_min']
        item['mandatory_restriction'] = row['mandatory_restriction']
    for offer in db.execute('SELECT * FROM offers WHERE product_id=? ORDER BY retailer', (row['id'],)):
        out = {'id':offer['id'], 'retailer':offer['retailer']}
        if show_prices:
            out.update(price=dollars(offer['price_cents']), source=offer['source'], observed_at=offer['observed_at'])
        if show_links and offer['url']:
            if profile is None:
                link = RETAILERS[offer['retailer']].shopping_link(offer['url'])
                out.update(url=link.url, product_url=offer['url'], affiliate=link.affiliate, disclosure=link.disclosure)
            else:
                # Child browsing always gets plain links, never affiliate tracking.
                out.update(url=offer['url'], affiliate=False, disclosure='External retailer. No checkout is available in this app.')
        item['offers'].append(out)
    return item


def list_price(db, product_id):
    return db.execute('SELECT MIN(price_cents) FROM offers WHERE product_id=?', (product_id,)).fetchone()[0]


def child_wishes(db, profile):
    items, total, unknown = [], 0, 0
    for row in db.execute("SELECT id,name,product_id,priority FROM wishes WHERE profile_id=? AND review_state='approved' ORDER BY id DESC", (profile['id'],)):
        item = {'id':row['id'], 'name':row['name'], 'priority':row['priority']}
        price = list_price(db, row['product_id'])
        total += price or 0
        unknown += price is None
        product = db.execute('SELECT * FROM products WHERE id=?', (row['product_id'],)).fetchone()
        if not permitted(product, profile):
            item['name'] = 'Item hidden by parent settings'
            item['product'] = {'id':product['id'], 'name':item['name'], 'category':'Hidden', 'image':'/images/gift.svg', 'offers':[], 'source_kind':'hidden', 'source_label':'Hidden by current parent settings'}
            if profile['show_prices']:
                item['value'] = None
            total -= price or 0
            unknown += price is not None
            items.append(item)
            continue
        item['product'] = product_public(db, product, profile)
        if profile['show_prices']:
            item['value'] = dollars(price)
        items.append(item)
    result = {'profile':profile_public(profile), 'wishes':items}
    # Monetary totals would defeat hiding prices; both permissions are required.
    if profile['show_prices']:
        result['summary'] = {'total':dollars(total), 'unpriced_items':unknown, 'sample_items':sum(item['product']['source_kind'] == 'sample' for item in items)}
        if profile['show_budget']:
            result['summary'].update(budget=dollars(profile['budget_cents']),
                remaining=dollars(None if profile['budget_cents'] is None else profile['budget_cents'] - total))
    return result


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def headers_common(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        origin = self.headers.get('Origin')
        if origin in APP_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def respond(self, status, value):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.headers_common()
        self.end_headers()
        self.wfile.write(json.dumps(value).encode())

    def token(self):
        return self.headers.get('Authorization', '').removeprefix('Bearer ')

    def identity(self):
        with lock:
            session = sessions.get(self.token())
            if not session or session['expires'] < time.time():
                sessions.pop(self.token(), None)
                raise APIError(401, 'Sign in again.')
            return session

    def parent(self):
        if self.identity()['role'] != 'parent':
            raise APIError(403, 'Parent access required.')

    def child(self, db):
        identity = self.identity()
        if identity['role'] != 'child':
            raise APIError(403, 'Use a child profile session.')
        if not consented(db):
            raise APIError(403, 'A parent must enable wish lists first.')
        profile = db.execute('SELECT * FROM profiles WHERE id=?', (identity['profile_id'],)).fetchone()
        if not profile:
            raise APIError(401, 'Profile unavailable.')
        return profile

    def login(self, role, profile_id=None):
        token = secrets.token_urlsafe(32)
        with lock:
            sessions[token] = {'role':role, 'profile_id':profile_id,
                               'expires':time.time() + (3600 if role == 'parent' else 28800)}
        return {'token':token, 'role':role}

    def throttle(self):
        key = self.client_address[0]
        with lock:
            recent = [t for t in attempts.get(key, []) if t > time.time() - 60]
            if len(recent) >= 15:
                raise APIError(429, 'Too many sign-in attempts. Wait one minute.')
            attempts[key] = recent + [time.time()]

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path.startswith('/api/'):
                with connect() as db:
                    return self.respond(200, self.get_api(path, db))
            files = {'/share':('index.html','text/html'), '/manifest.webmanifest':('manifest.webmanifest','application/manifest+json'), '/sw.js':('sw.js','text/javascript'), '/runtime.js':('runtime.js','text/javascript'), '/':('index.html','text/html'), '/app.js':('app.js','text/javascript'), '/style.css':('style.css','text/css')}
            for image in ['gift','rocket','art','headphones','telescope','book','board','game','camera','icon']:
                files['/images/' + image + '.svg'] = ('images/' + image + '.svg','image/svg+xml')
            if path not in files:
                raise APIError(404, 'Not found.')
            name, mime = files[path]
            self.send_response(200)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.headers_common()
            self.end_headers()
            self.wfile.write((ROOT / 'public' / name).read_bytes())
        except APIError as e:
            self.respond(e.status, {'error':e.message})

    def get_api(self, path, db):
        if path == '/api/status':
            return {'configured':db.execute("SELECT 1 FROM settings WHERE key='pin'").fetchone() is not None}
        if path == '/api/wishes':
            return child_wishes(db, self.child(db))
        if path == '/api/catalog':
            profile = self.child(db)
            products = [r for r in db.execute('SELECT * FROM products ORDER BY id DESC') if permitted(r,profile)]
            if profile['use_age_recommendations'] and profile['child_age'] is not None:
                products.sort(key=lambda r: r['recommended_age_min'] is not None and r['recommended_age_min'] > profile['child_age'])
            return [product_public(db, r, profile) for r in products]
        if path == '/api/requests':
            profile = self.child(db)
            requests = []
            for row in db.execute("SELECT w.id,w.name,w.review_state,w.product_id FROM wishes w WHERE profile_id=? AND review_state!='approved'",(profile['id'],)):
                product = db.execute('SELECT * FROM products WHERE id=?',(row['product_id'],)).fetchone()
                requests.append({'id':row['id'],'name':row['name'] if permitted(product,profile) else 'Item hidden by parent settings','approval':row['review_state'], 'product_id':row['product_id']})
            return requests
        self.parent()
        if path == '/api/integrations':
            return INTEGRATIONS
        if path == '/api/privacy':
            return {'consented':consented(db), 'version':CONSENT_VERSION}
        if path == '/api/profiles':
            return [{'id':r['id'], 'nickname':r['nickname'], 'show_prices':bool(r['show_prices']),
                     'show_budget':bool(r['show_budget']), 'show_links':bool(r['show_links']),
                     'budget':dollars(r['budget_cents']), 'child_age':r['child_age'],
                     'use_age_recommendations':bool(r['use_age_recommendations']),
                     'allowed_categories':json.loads(r['allowed_categories']), 'allowed_ratings':json.loads(r['allowed_ratings']),
                     'allow_unverified_games':bool(r['allow_unverified_games']), 'require_approval':bool(r['require_approval'])} for r in db.execute('SELECT * FROM profiles')]
        if path == '/api/parent/catalog':
            return [product_public(db, r) for r in db.execute('SELECT * FROM products ORDER BY id DESC')]
        if path == '/api/parent':
            items = []
            for row in db.execute('SELECT w.*,p.nickname FROM wishes w JOIN profiles p ON p.id=w.profile_id ORDER BY w.id DESC'):
                price = list_price(db, row['product_id'])
                item = {k:row[k] for k in ('id','name','profile_id','nickname','priority','purchased','reserved','target','review_state')}
                item.update(value=dollars(price), actual_paid=dollars(row['actual_paid_cents']),
                            reference_price=dollars(row['reference_cents']),
                            savings=dollars(None if row['actual_paid_cents'] is None or row['reference_cents'] is None else row['reference_cents'] - row['actual_paid_cents']))
                product = db.execute('SELECT * FROM products WHERE id=?', (row['product_id'],)).fetchone()
                item['product'] = product_public(db, product)
                items.append(item)
            return items
        raise APIError(404, 'Not found.')

    def do_OPTIONS(self):
        if self.headers.get('Origin') not in APP_ORIGINS:
            return self.respond(403, {'error':'Origin not permitted.'})
        self.send_response(204)
        self.headers_common()
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization')
        self.end_headers()

    def do_POST(self):
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise APIError(415, 'JSON required.')
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', '') and origin not in APP_ORIGINS:
                raise APIError(403, 'Cross-origin requests are not allowed.')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16384:
                raise ValueError('Invalid request size.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('JSON object required.')
            with connect() as db:
                status, result = self.post_api(urlsplit(self.path).path, data, db)
            # Commit before reporting success to avoid an immediate next-request race.
            self.respond(status, result)
        except APIError as e:
            self.respond(e.status, {'error':e.message})
        except (ValueError, TypeError, KeyError, OverflowError) as e:
            self.respond(400, {'error':str(e) or 'Check your entries.'})
        except sqlite3.IntegrityError:
            self.respond(409, {'error':'This record conflicts with an existing item.'})

    def post_api(self, path, data, db):
        if path == '/api/unlock':
            self.throttle()
            pin = text(data.get('pin'), 200)
            row = db.execute("SELECT value FROM settings WHERE key='pin'").fetchone()
            if row is None:
                if len(pin) < 8:
                    raise ValueError('Choose a passphrase with at least eight characters.')
                salt = secrets.token_hex(16)
                db.execute("INSERT INTO settings VALUES ('pin',?)", (salt + ':' + pin_hash(pin, salt),))
            else:
                salt, expected = row['value'].split(':')
                if not hmac.compare_digest(expected, pin_hash(pin, salt)):
                    raise APIError(403, 'Incorrect parent passphrase.')
            return 200, self.login('parent')
        if path == '/api/child-login':
            self.throttle()
            if not consented(db):
                raise APIError(403, 'A parent must enable wish lists first.')
            code = text(data.get('code'), 100)
            profile = db.execute('SELECT id FROM profiles WHERE code_hash=?', (digest(code),)).fetchone()
            if not profile:
                raise APIError(403, 'Invalid profile code.')
            return 200, self.login('child', profile['id'])
        if path == '/api/logout':
            with lock:
                sessions.pop(self.token(), None)
            return 200, {'ok':True}
        if path in ('/api/wishes', '/api/priority'):
            profile = self.child(db)
            allowed = {'product_id','name','priority'} if path == '/api/wishes' else {'id','priority'}
            if set(data) - allowed:
                raise APIError(403, 'This action is not allowed in a child session.')
            priority = data.get('priority', 'Would Love')
            if priority not in PRIORITIES:
                raise ValueError('Choose Must Have, Would Love, or Nice to Have.')
            if path == '/api/priority':
                cursor = db.execute('UPDATE wishes SET priority=? WHERE id=? AND profile_id=?', (priority, int(data['id']), profile['id']))
                if not cursor.rowcount:
                    raise APIError(404, 'Wish not found.')
                return 200, {'ok':True}
            if data.get('product_id') is not None:
                product = db.execute('SELECT * FROM products WHERE id=?', (int(data['product_id']),)).fetchone()
                if not product or not permitted(product,profile):
                    raise APIError(404, 'Product unavailable under parent or mandatory eligibility settings.')
                if db.execute('SELECT id FROM wishes WHERE profile_id=? AND product_id=?', (profile['id'], product['id'])).fetchone():
                    raise APIError(409, 'This product is already on your list.')
                product_id, name = product['id'], product['name']
            else:
                name = text(data.get('name'))
                if json.loads(profile['allowed_categories']) is not None and 'Family Finds' not in json.loads(profile['allowed_categories']):
                    raise APIError(403, 'Custom ideas are not enabled in the selected categories.')
                product_id = db.execute('INSERT INTO products(name) VALUES (?)', (name,)).lastrowid
            state = 'pending' if profile['require_approval'] else 'approved'
            wish_id = db.execute('INSERT INTO wishes(name,child,profile_id,product_id,priority,review_state) VALUES (?,?,?,?,?,?)',
                                (name, profile['nickname'], profile['id'], product_id, priority, state)).lastrowid
            return (202 if state == 'pending' else 201), {'id':wish_id, 'approval':state}
        self.parent()
        if path == '/api/consent':
            if data.get('accepted') is not True:
                raise ValueError('Explicit permission is required.')
            db.execute("INSERT OR REPLACE INTO settings VALUES ('consent',?)", (CONSENT_VERSION,))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('consent_at',datetime('now'))")
            return 200, {'ok':True}
        if path == '/api/delete-family':
            if data.get('confirmation') != 'DELETE':
                raise ValueError('Deletion confirmation required.')
            for table in ('prices','offer_prices','offers','wishes','products','profiles'):
                db.execute('DELETE FROM ' + table)
            db.execute("DELETE FROM settings WHERE key IN ('consent','consent_at')")
            with lock:
                for key in list(sessions):
                    if sessions[key]['role'] == 'child':
                        del sessions[key]
            return 200, {'ok':True}
        if path == '/api/profiles':
            if not consented(db):
                raise APIError(403, 'Grant parental permission before creating profiles.')
            nickname = text(data.get('nickname'), 60)
            profile_id = data.get('id')
            existing = db.execute('SELECT * FROM profiles WHERE id=?',(int(profile_id),)).fetchone() if profile_id is not None else None
            if profile_id is not None and existing is None:
                raise APIError(404, 'Profile not found.')
            age = data.get('child_age', existing['child_age'] if existing else None)
            if age in (None,''):
                age = None
            elif type(age) is not int or not 0 <= age <= 17:
                raise ValueError('Optional age must be an integer from 0 to 17. Do not enter a birth date.')
            defaults = suggested_defaults(age)
            permissions = [boolean(data.get(k, bool(existing[k]) if existing else defaults[k])) for k in ('show_prices','show_budget','show_links')]
            budget = money(data.get('budget', dollars(existing['budget_cents']) if existing else None))
            categories = data.get('allowed_categories',json.loads(existing['allowed_categories']) if existing else None)
            if categories is not None and (not isinstance(categories,list) or len(categories)>30 or any(not isinstance(c,str) or not c or len(c)>80 for c in categories)):
                raise ValueError('Choose valid product categories.')
            ratings = data.get('allowed_ratings',json.loads(existing['allowed_ratings']) if existing else suggested_defaults(age)['allowed_ratings'])
            if not isinstance(ratings,list) or any(r not in RATINGS for r in ratings):
                raise ValueError('Choose valid ESRB rating permissions.')
            advanced = [age, boolean(data.get('use_age_recommendations',bool(existing['use_age_recommendations']) if existing else True)),
                json.dumps(categories), json.dumps(ratings),
                boolean(data.get('allow_unverified_games',bool(existing['allow_unverified_games']) if existing else False)),
                boolean(data.get('require_approval',bool(existing['require_approval']) if existing else defaults['require_approval']))]
            if existing is None:
                code = secrets.token_urlsafe(18)
                profile_id = db.execute('INSERT INTO profiles(nickname,code_hash,show_prices,show_budget,show_links,budget_cents) VALUES (?,?,?,?,?,?)',
                    (nickname, digest(code), *permissions, budget)).lastrowid
            else:
                db.execute('UPDATE profiles SET nickname=?,show_prices=?,show_budget=?,show_links=?,budget_cents=? WHERE id=?',
                           (nickname,*permissions,budget,profile_id))
            db.execute('UPDATE profiles SET child_age=?,use_age_recommendations=?,allowed_categories=?,allowed_ratings=?,allow_unverified_games=?,require_approval=? WHERE id=?',(*advanced,profile_id))
            return (201, {'id':profile_id,'code':code}) if existing is None else (200,{'ok':True})
        if path == '/api/profile-code':
            profile_id, code = int(data['id']), secrets.token_urlsafe(18)
            if not db.execute('UPDATE profiles SET code_hash=? WHERE id=?', (digest(code), profile_id)).rowcount:
                raise APIError(404, 'Profile not found.')
            with lock:
                for key in list(sessions):
                    if sessions[key]['role'] == 'child' and sessions[key]['profile_id'] == profile_id:
                        del sessions[key]
            return 200, {'code':code}
        if path == '/api/import-link':
            name = text(data.get('name'))
            retailer, url = normalize_product_url(text(data.get('url'),2000))
            price = money(data.get('price'))
            product_id = db.execute('INSERT INTO products(name) VALUES (?)',(name,)).lastrowid
            db.execute("INSERT INTO offers(product_id,retailer,url,price_cents,source) VALUES (?,?,?,?,'manual')",(product_id,retailer,url,price))
            return 201, {'id':product_id}
        if path == '/api/products':
            name = text(data.get('name'))
            return 201, {'id':db.execute('INSERT INTO products(name) VALUES (?)', (name,)).lastrowid}
        if path == '/api/product-settings':
            if set(data) - {'id','category','media_type','content_rating','recommended_age_min'}:
                raise ValueError('Verification and mandatory restrictions are managed by trusted policy/data sources.')
            product = db.execute('SELECT * FROM products WHERE id=?',(int(data['id']),)).fetchone()
            if not product:
                raise APIError(404,'Product not found.')
            if product['source_kind'] == 'sample':
                raise APIError(409,'Sample metadata is illustrative and cannot be edited.')
            category = text(data.get('category'),80)
            media = data.get('media_type','general')
            if media not in ('general','video_game'):
                raise ValueError('Choose general or video_game.')
            rating = data.get('content_rating') or None
            if rating is not None and rating not in RATINGS:
                raise ValueError('Choose a valid ESRB rating or leave unrated.')
            minimum = data.get('recommended_age_min')
            if minimum is not None and (type(minimum) is not int or not 0 <= minimum <= 18):
                raise ValueError('Suggested minimum age must be 0–18 or blank.')
            db.execute('UPDATE products SET category=?,media_type=?,content_rating=?,recommended_age_min=?,rating_verified=0,rating_source=NULL WHERE id=?',
                       (category,media,rating,minimum,product['id']))
            return 200, {'ok':True}
        if path == '/api/offers':
            product_id = int(data['product_id'])
            product = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
            if not product:
                raise APIError(404, 'Product not found.')
            if product['source_kind'] == 'sample':
                raise APIError(409, 'Sample offers are illustrative. Create a family product for a real link.')
            retailer, url = normalize_product_url(text(data.get('url'), 2000))
            price = money(data.get('price'))
            db.execute('''INSERT INTO offers(product_id,retailer,url,price_cents) VALUES (?,?,?,?)
                ON CONFLICT(product_id,retailer) DO UPDATE SET url=excluded.url,price_cents=excluded.price_cents,
                source='manual',observed_at=CURRENT_TIMESTAMP''', (product_id, retailer, url, price))
            offer_id = db.execute('SELECT id FROM offers WHERE product_id=? AND retailer=?', (product_id, retailer)).fetchone()['id']
            db.execute("INSERT INTO offer_prices(offer_id,price_cents,source) VALUES (?,?,'manual')", (offer_id, price))
            return 200, {'ok':True}
        if path == '/api/update':
            allowed = {'id','purchased','reserved','actual_paid','reference_price','target','review_state'}
            if set(data) - allowed:
                raise ValueError('Use the public product editor to change displayed prices or links.')
            row = db.execute('SELECT * FROM wishes WHERE id=?', (int(data['id']),)).fetchone()
            if not row:
                raise APIError(404, 'Wish not found.')
            if 'review_state' in data:
                if data['review_state'] not in ('approved','declined'):
                    raise ValueError('Choose approved or declined for a wish request.')
                db.execute('UPDATE wishes SET review_state=? WHERE id=?',(data['review_state'],row['id']))
            for key in ('purchased','reserved'):
                if key in data:
                    db.execute('UPDATE wishes SET ' + key + '=? WHERE id=?', (boolean(data[key]), row['id']))
            for key, column in [('actual_paid','actual_paid_cents'), ('reference_price','reference_cents')]:
                if key in data:
                    db.execute('UPDATE wishes SET ' + column + '=? WHERE id=?', (money(data[key]), row['id']))
            if 'actual_paid' in data and data['actual_paid'] not in (None,'') and row['reference_cents'] is None and 'reference_price' not in data:
                db.execute('UPDATE wishes SET reference_cents=? WHERE id=?', (list_price(db, row['product_id']), row['id']))
            if 'target' in data:
                db.execute('UPDATE wishes SET target=? WHERE id=?', (dollars(money(data['target'])), row['id']))
            return 200, {'ok':True}
        raise APIError(404, 'Not found.')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8000'))
    print(f'WishNest running on port {port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
