from unittest.mock import patch, MagicMock

import pytest
from django.core.exceptions import ValidationError
from rest_framework import status

from polaris.tests.sep38 import BaseSep38Tests
from polaris.tests.sep38.data import get_mock_stellar_assets, get_mock_offchain_assets


class TestPrices(BaseSep38Tests):
    @classmethod
    def setUpClass(cls):
        BaseSep38Tests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        BaseSep38Tests.tearDownClass()

    def test_validate_asset(self):
        mock_stellar_asset = get_mock_stellar_assets()[0]
        mock_offchain_asset = get_mock_offchain_assets()[0]

        self.mock_get_stellar_asset.return_value = mock_stellar_asset
        self.mock_get_offchain_asset.return_value = mock_offchain_asset

        from polaris.sep38.prices import _validate_asset

        with pytest.raises(ValidationError):
            _validate_asset(None)

        self.mock_get_stellar_asset.reset_mock()
        self.mock_get_offchain_asset.reset_mock()
        _validate_asset(
            f"stellar:{mock_stellar_asset.code}:{mock_stellar_asset.issuer}"
        )
        assert self.mock_get_stellar_asset.call_count == 1
        assert not self.mock_get_offchain_asset.called

        self.mock_get_stellar_asset.reset_mock()
        self.mock_get_offchain_asset.reset_mock()
        self.mock_get_stellar_asset.side_effect = ValueError()
        with pytest.raises(ValidationError):
            _validate_asset(
                f"stellar:{mock_stellar_asset.code}:{mock_stellar_asset.issuer}"
            )
        assert self.mock_get_stellar_asset.call_count == 1
        assert not self.mock_get_offchain_asset.called

        self.mock_get_stellar_asset.reset_mock()
        self.mock_get_offchain_asset.reset_mock()
        self.mock_get_offchain_asset.side_effect = ValueError()
        with pytest.raises(ValidationError):
            _validate_asset("iso4217:USD")
        assert self.mock_get_offchain_asset.call_count == 1
        assert not self.mock_get_stellar_asset.called

    def test_validate_prices_request(self):
        self.mock_get_stellar_asset.side_effect = None

        test_data = {
            "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B"
        }

        from polaris.sep38.prices import _validate_prices_request

        with pytest.raises(ValidationError):
            _validate_prices_request(test_data)

    @patch("polaris.sep38.prices._validate_asset")
    @patch("polaris.integrations.registered_quote_integration.get_prices")
    @patch("polaris.sep38.prices._validate_prices_request")
    def test_get_prices(self, mock_validate_prices_request, mock_rqi_get_prices, _):
        from polaris.sep38.prices import get_prices

        mock_request = MagicMock()
        mock_rqi_get_prices.return_value = []
        get_prices(mock_request)

        rr = {"asset": "", "price": "", "decimals": 0}
        mock_rqi_get_prices.return_value = [rr]
        response = get_prices(mock_request)
        assert len(response.data) == 1

        self.mock_error.reset_mock()
        mock_validate_prices_request.side_effect = ValidationError("")
        get_prices(mock_request)
        assert self.mock_error.call_count == 1
        assert (
            self.mock_error.call_args[1]["status_code"] == status.HTTP_400_BAD_REQUEST
        )

    @patch("polaris.sep38.prices._validate_price_request")
    @patch("polaris.integrations.registered_quote_integration.get_price")
    def test_get_price(self, mock_rqi_get_price, mock_validate_price_request):
        mock_request = MagicMock()

        mock_rqi_get_price.return_value = {
            "price": "10.012",
            "sell_amount": "10",
        }
        from polaris.sep38.prices import get_price

        get_price(mock_request)

        # Test ValidationError handling
        mock_validate_price_request.side_effect = ValueError("")
        get_price(mock_request)
        assert self.mock_error.call_count == 1
        assert (
            self.mock_error.call_args[1]["status_code"] == status.HTTP_400_BAD_REQUEST
        )

        self.mock_error.reset_mock()
        mock_validate_price_request.side_effect = ValueError("")
        mock_rqi_get_price.side_effect = ValueError("")
        get_price(mock_request)
        assert self.mock_error.call_count == 1
        assert (
            self.mock_error.call_args[1]["status_code"] == status.HTTP_400_BAD_REQUEST
        )

    @patch("polaris.sep38.prices._validate_asset")
    def test_validate_price_request(self, mock_validate_asset):
        from polaris.sep38.prices import _validate_price_request

        test_data = {
            "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
            "buy_asset": "iso4217:USD",
        }

        # Make sure no ValidateError is caught and done nothing
        mock_validate_asset.side_effect = ValidationError("")
        with pytest.raises(ValidationError):
            _validate_price_request(test_data)

        # Test if "sell_amount" and "buy_amount" are handled properly
        mock_validate_asset.side_effect = None
        test_data.update({"sell_amount": "10", "buy_amount": None})
        self.mock_list_exchange_pairs.return_value = [{}]
        _validate_price_request(test_data)

        test_data.update({"sell_amount": None, "buy_amount": None})
        with pytest.raises(ValueError):
            _validate_price_request(test_data)

        test_data.update({"sell_amount": "10", "buy_amount": "10"})
        with pytest.raises(ValueError):
            _validate_price_request(test_data)

        # Test if exchange pair matches are handled properly
        with pytest.raises(ValueError):
            self.mock_list_exchange_pairs.return_value = [{}, {}]
            _validate_price_request(test_data)

        with pytest.raises(ValueError):
            self.mock_list_exchange_pairs.return_value = []
            _validate_price_request(test_data)
