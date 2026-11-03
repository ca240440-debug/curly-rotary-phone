"""Unified catalog contracts. No retailer network access is enabled.

Approved ingestion adapters may implement CatalogProvider later. Providers must
respect image rights, price freshness, caching, rate limits and child-directed
use restrictions. Search terms remain local in the MVP.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

@dataclass(frozen=True)
class CatalogOffer:
    retailer: str
    external_product_id: str
    price: Decimal | None
    currency: str
    product_url: str
    observed_at: datetime

@dataclass(frozen=True)
class CatalogProduct:
    source_id: str
    name: str
    category: str
    licensed_image_reference: str
    offers: tuple[CatalogOffer, ...]
    recommended_age_min: int | None = None
    content_rating: str | None = None
    rating_verified: bool = False
    rating_source: str | None = None
    mandatory_restriction: str = ''

class CatalogProvider(Protocol):
    def search(self, query: str, category: str | None = None) -> list[CatalogProduct]: ...

# Deliberately disabled until contractual/API access and permitted use are verified.
INTEGRATIONS = [
    {'retailer':'Amazon', 'status':'not_connected', 'reason':'Approved product-data access required.'},
    {'retailer':'Walmart', 'status':'not_connected', 'reason':'Approved partner access required.'},
    {'retailer':'Target', 'status':'not_connected', 'reason':'Approved partner or authorized feed required.'},
]

SAMPLES = [
    ('rocket-kit', 'Build-a-Rocket Kit', 'Building & STEM', 'rocket', [('amazon.com',3499),('walmart.com',3299)]),
    ('art-studio', 'Rainbow Art Studio', 'Arts & Crafts', 'art', [('walmart.com',2499),('target.com',2799)]),
    ('headphones', 'Cozy Wireless Headphones', 'Tech & Gaming', 'headphones', [('amazon.com',4999),('target.com',5499)]),
    ('telescope', 'Backyard Star Explorer', 'Building & STEM', 'telescope', [('walmart.com',6999),('target.com',7499)]),
    ('adventure-book', 'The Winter Adventure Book', 'Books & Stories', 'book', [('amazon.com',1299),('target.com',1499)]),
    ('skateboard', 'Weekend Cruiser Board', 'Outdoors & Sports', 'board', [('walmart.com',3999),('target.com',4499)]),
    ('game-night', 'Family Game Night', 'Games & Puzzles', 'game', [('amazon.com',1999),('walmart.com',1799)]),
    ('camera', 'Pocket Adventure Camera', 'Tech & Gaming', 'camera', [('amazon.com',5999),('target.com',6499)]),
    ('cosmic-racing', 'Cosmic Kart Racers (Demo Game)', 'Video Games', 'game', [('amazon.com',2999),('walmart.com',2799)]),
    ('space-quest', 'Orbit Quest (Demo Game)', 'Video Games', 'game', [('target.com',3999)]),
    ('night-quest', 'Shadow Quest (Demo Game)', 'Video Games', 'game', [('amazon.com',4999)]),
]

def seed_samples(db):
    if db.execute("SELECT 1 FROM settings WHERE key='sample_catalog_v2'").fetchone():
        return
    for source_id, name, category, image, offers in SAMPLES:
        existing = db.execute("SELECT id FROM products WHERE external_id=? AND source_kind='sample'",(source_id,)).fetchone()
        if existing:
            continue
        product_id = db.execute('INSERT INTO products(name,category,image_key,source_kind,external_id) VALUES (?,?,?,?,?)',
                                (name, category, image, 'sample', source_id)).lastrowid
        rating = {'cosmic-racing':'E10+', 'space-quest':'T', 'night-quest':'M'}.get(source_id)
        minimum = {'rocket-kit':8, 'art-studio':5, 'headphones':10, 'telescope':8, 'adventure-book':7, 'skateboard':10, 'game-night':6, 'camera':10, 'cosmic-racing':10, 'space-quest':13, 'night-quest':17}[source_id]
        db.execute('UPDATE products SET recommended_age_min=?,media_type=?,content_rating=? WHERE id=?',(minimum, 'video_game' if rating else 'general', rating, product_id))
        for retailer, cents in offers:
            # Sample comparisons never invent real retailer inventory or checkout URLs.
            db.execute("INSERT INTO offers(product_id,retailer,url,price_cents,source) VALUES (?,?,'',?,'sample')", (product_id,retailer,cents))
    db.execute("INSERT INTO settings VALUES ('sample_catalog_v2','seeded')")
