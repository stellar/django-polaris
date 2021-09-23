# Test coverage class
from polaris.tests.sep38 import BaseSep38Tests


class TestUrls(BaseSep38Tests):
    @classmethod
    def setUpClass(cls):
        BaseSep38Tests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        BaseSep38Tests.tearDownClass()

    def test_urls(self):
        from polaris.sep38.urls import urlpatterns

        for _ in urlpatterns:
            pass

    def test_cover_integration(self):
        from polaris.integrations import SEP38AnchorIntegration

        sep38 = SEP38AnchorIntegration()
        sep38.get_prices("", "")
        sep38.get_price("", "")
        sep38.post_quote(None)
