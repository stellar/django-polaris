from unittest.mock import patch, MagicMock

from rest_framework import status

from polaris.tests.sep38 import BaseSep38Tests
from polaris.tests.sep38.data import get_mock_offchain_assets, get_mock_stellar_assets


class TestInfo(BaseSep38Tests):
    @classmethod
    def setUpClass(cls):
        BaseSep38Tests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        BaseSep38Tests.tearDownClass()

    def tearDown(self) -> None:
        super().tearDown()

    def test_info(self):
        from polaris.sep38.info import info

        self.mock_list_stellar_assets.return_value = get_mock_stellar_assets()
        self.mock_list_offchain_assets.return_value = get_mock_offchain_assets()
        mock_request = MagicMock()
        info(mock_request)
        assert self.mock_error.call_count == 0
