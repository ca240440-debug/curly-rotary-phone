import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.process = None
        self.start()
        self.addCleanup(self.stop)
        self.parent = self.call('unlock', {'pin':'private-parent-passphrase'})[1]['token']
        self.call('consent', {'accepted':True}, self.parent)

    def start(self):
        self.process = subprocess.Popen([sys.executable, str(ROOT / 'server.py')],
            env={**os.environ, 'WISHLIST_DATA':self.temp.name, 'PORT':str(self.port), 'WISHNEST_SAMPLE_PRODUCTS':getattr(self,'sample_products','0')},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            if self.process.poll() is not None:
                self.fail(self.process.stderr.read().decode())
            try:
                urlopen(f'http://127.0.0.1:{self.port}/api/status', timeout=.2).close()
                return
            except OSError:
                time.sleep(.03)
        self.fail('Server failed to start')

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process.stderr.close()
            self.process = None

    def call(self, path, data=None, token=''):
        request = Request(f'http://127.0.0.1:{self.port}/api/' + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json', 'Authorization':'Bearer ' + token})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def profile(self, nickname='Star', **overrides):
        data = dict(nickname=nickname, show_prices=True, show_budget=True, show_links=True, budget=100, require_approval=False)
        data.update(overrides)
        status, profile = self.call('profiles', data, self.parent)
        self.assertEqual(status, 201, profile)
        status, session = self.call('child-login', {'code':profile['code']})
        self.assertEqual(status, 200, session)
        return profile['id'], session['token'], profile['code']

    def product(self, price=50):
        status, product = self.call('products', {'name':'Building blocks'}, self.parent)
        self.assertEqual(status, 201)
        self.offer(product['id'], price)
        return product['id']

    def offer(self, product_id, price, walmart=False):
        url = 'https://www.walmart.com/ip/toy/1234' if walmart else 'https://www.amazon.com/dp/ABC123?tag=old&kid=Star'
        status, result = self.call('offers', {'product_id':product_id, 'url':url, 'price':price}, self.parent)
        self.assertEqual(status, 200, result)

    def wish(self, child, product_id):
        status, result = self.call('wishes', {'product_id':product_id, 'priority':'Must Have'}, child)
        self.assertEqual(status, 201, result)
        return result['id']

    def view(self, child):
        status, result = self.call('wishes', token=child)
        self.assertEqual(status, 200, result)
        return result

    def test_budget_comparison_priorities_and_public_price_changes(self):
        _, child, _ = self.profile()
        product = self.product(55.25)
        self.offer(product, 40.10, walmart=True)
        wish = self.wish(child, product)
        view = self.view(child)
        self.assertEqual(view['summary'], {'total':40.1, 'unpriced_items':0,'sample_items':0,'budget':100,'remaining':59.9})
        self.assertEqual(len(view['wishes'][0]['product']['offers']), 2)
        self.assertEqual(view['wishes'][0]['priority'], 'Must Have')
        self.assertEqual(self.call('priority', {'id':wish,'priority':'Nice to Have'}, child)[0], 200)
        self.assertEqual(self.call('priority', {'id':wish,'priority':'Invalid'}, child)[0], 400)
        self.assertEqual(self.call('wishes', {'product_id':product}, child)[0], 409)
        self.offer(product, 120, walmart=True)
        self.offer(product, 110)
        self.assertEqual(self.view(child)['summary']['remaining'], -10)
        self.call('wishes', {'name':'A surprise idea'}, child)
        self.assertEqual(self.view(child)['summary']['unpriced_items'], 1)

    def test_private_purchase_updates_leave_entire_child_responses_identical(self):
        _, child, _ = self.profile()
        product = self.product()
        wish = self.wish(child, product)
        before = self.view(child)
        catalog_before = self.call('catalog', token=child)[1]
        for data in [dict(purchased=True), dict(reserved=True), dict(actual_paid=25, target=30), dict(reference_price=60)]:
            status, result = self.call('update', {'id':wish, **data}, self.parent)
            self.assertEqual(status, 200, result)
            self.assertEqual(self.view(child), before)
            self.assertEqual(self.call('catalog', token=child)[1], catalog_before)
        private = self.call('parent', token=self.parent)[1][0]
        self.assertEqual(private['actual_paid'], 25)
        self.assertEqual(private['savings'], 35)
        self.assertEqual(private['reserved'], 1)
        self.assertEqual(private['purchased'], 1)
        self.offer(product, 35)
        self.assertEqual(self.view(child)['summary']['total'], 35)
        self.assertEqual(len(self.view(child)['wishes']), 1)
        private = self.call('parent', token=self.parent)[1][0]
        self.assertEqual(private['actual_paid'], 25)
        self.assertEqual(private['savings'], 35)

    def test_permissions_are_enforced_server_side_and_live(self):
        profile_id, child, _ = self.profile(show_prices=False, show_budget=False, show_links=False)
        product = self.product()
        self.wish(child, product)
        view = self.view(child)
        self.assertNotIn('summary', view)
        self.assertNotIn('value', view['wishes'][0])
        self.assertNotIn('budget', view['profile'])
        for offer in [view['wishes'][0]['product']['offers'][0], self.call('catalog', token=child)[1][0]['offers'][0]]:
            self.assertEqual(set(offer), {'id','retailer'})
        self.assertEqual(self.call('profiles', {'id':profile_id,'nickname':'Star','show_prices':True,'show_budget':True,'show_links':True,'budget':0}, self.parent)[0],200)
        view = self.view(child)
        self.assertEqual(view['summary']['remaining'], -50)
        self.assertEqual(view['wishes'][0]['product']['offers'][0]['url'], 'https://www.amazon.com/dp/ABC123')
        self.assertFalse(view['wishes'][0]['product']['offers'][0]['affiliate'])
        self.assertEqual(self.call('profiles', {'id':profile_id,'nickname':'Star','show_prices':False,'show_budget':True,'budget':75}, self.parent)[0],200)
        budget_only = self.view(child)
        self.assertEqual(budget_only['profile']['budget'],75)
        self.assertNotIn('summary',budget_only)
        self.assertNotIn('value',budget_only['wishes'][0])
        self.call('profiles', {'id':profile_id,'nickname':'Star','show_prices':False,'show_budget':False,'show_links':True}, self.parent)
        self.assertNotIn('price', self.call('catalog', token=child)[1][0]['offers'][0])
        self.assertIn('url', self.call('catalog', token=child)[1][0]['offers'][0])

    def test_all_permission_combinations_and_optional_budget(self):
        import itertools
        profile_id, child, _ = self.profile()
        self.wish(child, self.product(12.34))
        for prices, budget, links in itertools.product([False,True], repeat=3):
            with self.subTest(prices=prices,budget=budget,links=links):
                self.assertEqual(self.call('profiles', {'id':profile_id,'nickname':'Star',
                    'show_prices':prices,'show_budget':budget,'show_links':links,'budget':None}, self.parent)[0],200)
                view = self.view(child)
                self.assertEqual('summary' in view,prices)
                self.assertEqual('budget' in view['profile'],budget)
                self.assertEqual('value' in view['wishes'][0],prices)
                offer = view['wishes'][0]['product']['offers'][0]
                self.assertEqual('price' in offer,prices)
                self.assertEqual('url' in offer,links)
                if prices:
                    self.assertEqual('remaining' in view['summary'],budget)
                    if budget:
                        self.assertIsNone(view['summary']['remaining'])
                        self.assertIsNone(view['summary']['budget'])

    def test_child_and_anonymous_access_cannot_escalate_or_cross_profiles(self):
        _, child, _ = self.profile()
        _, sibling, _ = self.profile('Moon')
        product = self.product()
        wish = self.wish(child, product)
        self.assertEqual(self.view(sibling)['wishes'], [])
        self.assertEqual(self.call('priority', {'id':wish,'priority':'Nice to Have'}, sibling)[0],404)
        for path in ['profiles','privacy','parent','parent/catalog']:
            self.assertEqual(self.call(path, token=child)[0],403)
            self.assertEqual(self.call(path)[0],401)
        for path, body in [('update',{'id':wish,'purchased':True}), ('offers',{'product_id':product,'price':1}), ('profiles',{'nickname':'Hacked'}), ('profile-code',{'id':1}), ('consent',{'accepted':True}), ('delete-family',{'confirmation':'DELETE'}), ('products',{'name':'Hacked'})]:
            self.assertEqual(self.call(path, body, child)[0],403)
        for key in ['actual_paid','purchased','reserved','profile_id','price','url','target','reference_price']:
            self.assertEqual(self.call('wishes', {'name':'Hacked',key:1}, child)[0],403)
        self.assertEqual(self.call('wishes')[0],401)
        self.assertEqual(self.call('catalog')[0],401)
        self.assertEqual(self.call('wishes', {'name':'Anonymous'})[0],401)

    def test_access_code_rotation_and_restart_persistence(self):
        profile_id, child, code = self.profile()
        wish = self.wish(child, self.product())
        self.call('update', {'id':wish,'purchased':True,'actual_paid':30}, self.parent)
        status, rotated = self.call('profile-code', {'id':profile_id}, self.parent)
        self.assertEqual(status,200)
        self.assertEqual(self.call('wishes', token=child)[0],401)
        self.assertEqual(self.call('child-login', {'code':code})[0],403)
        self.stop(); self.start()
        self.assertEqual(self.call('parent', token=self.parent)[0],401)
        self.parent = self.call('unlock', {'pin':'private-parent-passphrase'})[1]['token']
        child = self.call('child-login', {'code':rotated['code']})[1]['token']
        self.assertEqual(len(self.view(child)['wishes']),1)
        self.assertEqual(self.call('parent', token=self.parent)[1][0]['actual_paid'],30)
        self.call('logout', {}, child)
        self.assertEqual(self.call('wishes', token=child)[0],401)

    def test_consent_deletion_and_no_public_profile_directory(self):
        _, child, code = self.profile()
        self.wish(child, self.product())
        self.assertEqual(self.call('delete-family', {'confirmation':'DELETE'}, self.parent)[0],200)
        self.assertEqual(self.call('wishes', token=child)[0],401)
        self.assertEqual(self.call('child-login', {'code':code})[0],403)
        self.assertEqual(self.call('parent', token=self.parent)[1],[])
        self.assertEqual(self.call('profiles', token=self.parent)[1],[])
        self.assertEqual(self.call('parent/catalog', token=self.parent)[1],[])
        self.assertFalse(self.call('privacy', token=self.parent)[1]['consented'])
        self.assertEqual(self.call('profiles', {'nickname':'New'}, self.parent)[0],403)
        self.assertEqual(self.call('consent', {'accepted':False}, self.parent)[0],400)

    def test_money_validation_and_atomic_private_updates(self):
        _, child, _ = self.profile()
        wish = self.wish(child, self.product(0))
        self.assertEqual(self.view(child)['summary']['total'],0)
        for value in [-1, 1.001, 'NaN', 'Infinity', 100001, True]:
            self.assertEqual(self.call('update', {'id':wish,'purchased':True,'actual_paid':value}, self.parent)[0],400)
            self.assertFalse(self.call('parent', token=self.parent)[1][0]['purchased'])
        self.assertEqual(self.call('update', {'id':wish,'reserved':'yes'}, self.parent)[0],400)
        self.assertEqual(self.call('update', {'id':wish,'actual_paid':0}, self.parent)[0],200)
        self.assertEqual(self.call('parent', token=self.parent)[1][0]['actual_paid'],0)

    def test_parent_can_allow_m_rated_game_for_twelve_year_old(self):
        profile_id, child, _ = self.profile(child_age=12,allowed_ratings=['E'],allow_unverified_games=True)
        game = self.product(49.99)
        settings = {'id':game,'category':'Video Games','media_type':'video_game','content_rating':'M','recommended_age_min':17}
        self.assertEqual(self.call('product-settings',settings,self.parent)[0],200)
        self.assertEqual(self.call('catalog',token=child)[1],[])
        self.assertEqual(self.call('wishes',{'product_id':game},child)[0],404)
        self.assertEqual(self.call('profiles',{'id':profile_id,'nickname':'Star','allowed_ratings':['E','M']},self.parent)[0],200)
        catalog = self.call('catalog',token=child)[1]
        self.assertEqual(catalog[0]['content_rating'],'M')
        self.assertFalse(catalog[0]['rating_verified'])
        self.assertIn('Outside your age suggestions',catalog[0]['recommendation'])
        self.wish(child,game)
        self.assertEqual(self.call('profiles',{'id':profile_id,'nickname':'Star','use_age_recommendations':False},self.parent)[0],200)
        self.assertEqual(self.call('catalog',token=child)[1][0]['recommendation'],'Explore this idea')
        # A trusted eligibility restriction cannot be removed through preferences.
        with sqlite3.connect(Path(self.temp.name)/'wishes.db') as db:
            db.execute("UPDATE products SET mandatory_restriction='region_or_retailer_not_eligible' WHERE id=?",(game,))
        self.assertEqual(self.call('catalog',token=child)[1],[])
        self.assertEqual(self.view(child)['wishes'][0]['name'],'Item hidden by parent settings')
        self.assertEqual(self.call('product-settings',{**settings,'mandatory_restriction':''},self.parent)[0],400)

    def test_categories_unverified_ratings_and_wish_approval(self):
        profile_id, child, _ = self.profile(require_approval=True,allowed_categories=['Family Finds'])
        product = self.product()
        status, request = self.call('wishes',{'product_id':product},child)
        self.assertEqual(status,202)
        self.assertEqual(self.view(child)['wishes'],[])
        self.assertEqual(self.view(child)['summary']['total'],0)
        self.assertEqual(self.call('requests',token=child)[1][0]['approval'],'pending')
        self.assertEqual(self.call('update',{'id':request['id'],'review_state':'approved'},child)[0],403)
        self.assertEqual(self.call('update',{'id':request['id'],'review_state':'approved'},self.parent)[0],200)
        self.assertEqual(len(self.view(child)['wishes']),1)
        self.assertEqual(self.call('requests',token=child)[1],[])
        before = self.view(child)
        self.call('update',{'id':request['id'],'purchased':True,'reserved':True,'actual_paid':20},self.parent)
        self.assertEqual(self.view(child),before)
        self.call('product-settings',{'id':product,'category':'Video Games','media_type':'video_game','content_rating':'E','recommended_age_min':6},self.parent)
        self.assertEqual(self.call('catalog',token=child)[1],[])
        self.call('profiles',{'id':profile_id,'nickname':'Star','allowed_categories':['Video Games'],'allow_unverified_games':True},self.parent)
        self.assertEqual(len(self.call('catalog',token=child)[1]),1)
        self.call('profiles',{'id':profile_id,'nickname':'Star','allow_unverified_games':False},self.parent)
        self.assertEqual(self.call('catalog',token=child)[1],[])
        # Trusted-provider verification is read-only to parent and child clients.
        with sqlite3.connect(Path(self.temp.name)/'wishes.db') as db:
            db.execute("UPDATE products SET rating_verified=1,rating_source='Authorized test fixture' WHERE id=?",(product,))
        verified = self.call('catalog',token=child)[1][0]
        self.assertTrue(verified['rating_verified'])
        self.assertEqual(verified['rating_source'],'Authorized test fixture')
        self.assertEqual(self.call('product-settings',{'id':product,'category':'Video Games','rating_verified':True},self.parent)[0],400)
        self.assertEqual(self.call('profiles',{'id':profile_id,'nickname':'Star','allowed_ratings':['AO']},self.parent)[0],400)
        self.assertEqual(self.call('profiles',{'id':profile_id,'nickname':'Star','child_age':12.5},self.parent)[0],400)

    def test_sample_catalog_is_labeled_local_and_never_has_checkout(self):
        self.stop()
        self.sample_products = '1'
        self.start()
        self.parent = self.call('unlock',{'pin':'private-parent-passphrase'})[1]['token']
        _, child, _ = self.profile(child_age=12,allowed_ratings=['E','E10+','T','M'],allow_unverified_games=True)
        catalog = self.call('catalog',token=child)[1]
        self.assertEqual(len(catalog),11)
        for product in catalog:
            self.assertEqual(product['source_kind'],'sample')
            self.assertIn('illustrative',product['source_label'])
            self.assertTrue(product['image'].startswith('/images/'))
            for offer in product['offers']:
                self.assertEqual(offer['source'],'sample')
                self.assertNotIn('url',offer)
        mature = next(p for p in catalog if p['content_rating'] == 'M')
        self.assertFalse(mature['rating_verified'])
        self.wish(child,mature['id'])
        self.assertEqual(self.view(child)['summary']['sample_items'],1)
        self.assertEqual(self.call('offers',{'product_id':mature['id'],'url':'https://www.amazon.com/dp/SAMPLE','price':2},self.parent)[0],409)
        self.call('delete-family',{'confirmation':'DELETE'},self.parent)
        self.stop(); self.start()
        self.parent = self.call('unlock',{'pin':'private-parent-passphrase'})[1]['token']
        self.assertEqual(self.call('parent/catalog',token=self.parent)[1],[])

    def test_shared_manual_link_import_requires_parent(self):
        _, child, _ = self.profile()
        data={'name':'Imported idea','url':'https://www.target.com/p/idea/-/A-123?tracking=old','price':12.99}
        self.assertEqual(self.call('import-link',data,child)[0],403)
        self.assertEqual(self.call('import-link',data)[0],401)
        self.assertEqual(self.call('import-link',data,self.parent)[0],201)
        offer=self.call('catalog',token=child)[1][0]['offers'][0]
        self.assertEqual(offer['url'],'https://www.target.com/p/idea/-/A-123')
        self.assertEqual(offer['price'],12.99)
        self.assertEqual(self.call('import-link',{**data,'url':'https://evil.test/product'},self.parent)[0],400)

    def test_legacy_migration_preserves_wishes_and_purchase_privacy(self):
        self.stop()
        with sqlite3.connect(Path(self.temp.name) / 'wishes.db') as db:
            db.execute("INSERT INTO wishes(name,child,url,price,purchased) VALUES ('Legacy train','Old nickname','https://www.amazon.com/dp/LEGACY',45,1)")
        self.start()
        self.parent = self.call('unlock', {'pin':'private-parent-passphrase'})[1]['token']
        private = self.call('parent', token=self.parent)[1][0]
        self.assertEqual(private['purchased'],1)
        self.assertEqual(private['value'],45)
        profile_id = self.call('profiles', token=self.parent)[1][0]['id']
        code = self.call('profile-code', {'id':profile_id}, self.parent)[1]['code']
        child = self.call('child-login', {'code':code})[1]['token']
        wish = self.view(child)['wishes'][0]
        self.assertEqual(wish['name'],'Legacy train')
        self.assertEqual(set(wish), {'id','name','priority','product'})

if __name__ == '__main__':
    unittest.main()
