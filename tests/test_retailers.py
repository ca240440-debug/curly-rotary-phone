import unittest
from retailers import RETAILERS, ShoppingLink, normalize_product_url

class RetailerTests(unittest.TestCase):
    def test_normal_links_strip_tracking(self):
        domain, url = normalize_product_url('https://www.walmart.com/ip/toy/12345?affiliate=old#details')
        self.assertEqual(url, 'https://www.walmart.com/ip/toy/12345')
        self.assertFalse(RETAILERS[domain].shopping_link(url).affiliate)

    def test_reject_unsafe_destinations(self):
        for url in ['javascript:alert(1)', 'https://amazon.com.evil.test/dp/A',
                    'https://user:pass@amazon.com/dp/A', 'https://amazon.com:444/dp/A',
                    'https://amazon.com/redirect?url=evil', 'https://www.walmart.com/search?q=toy']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_product_url(url)

    def test_affiliate_provider_is_replaceable_and_receives_only_url(self):
        class ApprovedTestProvider:
            def build_link(self, product_url):
                return ShoppingLink(product_url + '?example=test', True, 'Test affiliate disclosure')
        retailer = RETAILERS['amazon.com']
        try:
            retailer.affiliate_provider = ApprovedTestProvider()
            link = retailer.shopping_link('https://www.amazon.com/dp/A')
            self.assertTrue(link.affiliate)
            self.assertEqual(link.disclosure, 'Test affiliate disclosure')
        finally:
            retailer.affiliate_provider = None
