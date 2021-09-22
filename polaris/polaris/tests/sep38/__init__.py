import unittest
from unittest import mock

from polaris.tests.sep38.data import noop_decor


class BaseSep38Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mock.patch("rest_framework.decorators.api_view", noop_decor).start()
        mock.patch("rest_framework.decorators.renderer_classes", noop_decor).start()
        mock.patch("rest_framework.decorators.parser_classes", noop_decor).start()
        mock.patch("polaris.sep24.utils.check_authentication", noop_decor).start()

        # Mock all external calls
        cls.mock_error = mock.patch("polaris.utils.render_error_response").start()
        cls.mock_get_stellar_asset = mock.patch(
            "polaris.sep38.utils.get_stellar_asset"
        ).start()
        cls.mock_get_offchain_asset = mock.patch(
            "polaris.sep38.utils.get_offchain_asset"
        ).start()
        cls.mock_get_exchange_pair = mock.patch(
            "polaris.sep38.utils.get_exchange_pair"
        ).start()
        cls.mock_get_quote_by_id = mock.patch(
            "polaris.sep38.utils.get_quote_by_id"
        ).start()
        cls.mock_list_stellar_assets = mock.patch(
            "polaris.sep38.utils.list_stellar_assets"
        ).start()
        cls.mock_list_offchain_assets = mock.patch(
            "polaris.sep38.utils.list_offchain_assets"
        ).start()
        cls.mock_list_exchange_pairs = mock.patch(
            "polaris.sep38.utils.list_exchange_pairs"
        ).start()

    @classmethod
    def tearDownClass(cls):
        mock.patch.stopall()

    def setUp(self):
        self.mock_error.reset_mock()
        self.mock_get_stellar_asset.reset_mock()
        self.mock_get_offchain_asset.reset_mock()
        self.mock_get_exchange_pair.reset_mock()
        self.mock_get_quote_by_id.reset_mock()
        self.mock_list_stellar_assets.reset_mock()
        self.mock_list_offchain_assets.reset_mock()
        self.mock_list_exchange_pairs.reset_mock()
