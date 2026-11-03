"""Retailer boundary. No outbound requests or affiliate tracking by default."""
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

@dataclass(frozen=True)
class ShoppingLink:
    url: str
    affiliate: bool = False
    disclosure: str = 'Regular retailer link. No affiliate commission is currently earned.'

class AffiliateProvider(Protocol):
    """An approved provider receives product URLs only, never family data.

    Implement retailer-required attribution and disclosures here after approval.
    Never accept arbitrary redirect destinations or append child identifiers.
    """
    def build_link(self, product_url: str) -> ShoppingLink: ...

class Retailer:
    def __init__(self, domain, label):
        self.domain, self.label = domain, label
        self.affiliate_provider = None

    def shopping_link(self, url):
        return self.affiliate_provider.build_link(url) if self.affiliate_provider else ShoppingLink(url)

RETAILERS = {r.domain: r for r in [Retailer('amazon.com', 'Amazon'), Retailer('walmart.com', 'Walmart'), Retailer('target.com', 'Target')]}

def normalize_product_url(raw):
    """Discard tracking query strings, fragments, and embedded credentials."""
    parsed = urlsplit(raw)
    host = (parsed.hostname or '').lower()
    domain = host.removeprefix('www.')
    if parsed.scheme != 'https' or domain not in RETAILERS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Use an HTTPS Amazon.com, Walmart.com, or Target.com product link.')
    path = parsed.path
    # Product pages only; reject redirect, search, and arbitrary retailer routes.
    import re
    patterns = {'amazon.com': r'/(?:[^/]+/)?(?:dp|gp/product)/[A-Za-z0-9]+/?',
                'walmart.com': r'/ip/(?:[^/]+/)?[0-9]+/?',
                'target.com': r'/p/(?:[^/]+/)?-/A-[0-9]+/?'}
    pattern = patterns[domain]
    if not re.fullmatch(pattern, path):
        raise ValueError('Paste a direct product page link.')
    return domain, urlunsplit(('https', 'www.' + domain, path, '', ''))
