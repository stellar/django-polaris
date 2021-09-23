from unittest import mock
from unittest.mock import patch, MagicMock

import pytest
from django.core.exceptions import ValidationError

from polaris.tests.sep38 import BaseSep38Tests


class TestQuote(BaseSep38Tests):
    @classmethod
    def setUpClass(cls):
        cls.mock_get_significant_decimals = mock.patch(
            "polaris.sep38.utils.get_significant_decimals"
        ).start()
        BaseSep38Tests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        BaseSep38Tests.tearDownClass()

    def tearDown(self) -> None:
        super().tearDown()
        self.mock_get_significant_decimals.reset_mock()

    def test_validate_quote_request(self):
        test_data = {
            "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
            "buy_asset": "iso4217:USD",
            "sell_amount": "10",
            "buy_amount": None,
            "expire_after": "2021-10-01 10:00:00",
        }
        # Happy path
        from polaris.sep38.quote import validate_quote_request

        validate_quote_request(test_data)

        test_data.update(
            {
                "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
                "buy_asset": "iso4217:USD",
                "sell_amount": "10",
                "buy_amount": "10",
            }
        )
        with pytest.raises(ValidationError):
            validate_quote_request(test_data)

        test_data.update(
            {
                "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
                "buy_asset": "iso4217:USD",
                "sell_amount": None,
                "buy_amount": None,
            }
        )
        with pytest.raises(ValidationError):
            validate_quote_request(test_data)

        test_data.update(
            {
                "sell_asset": None,
                "buy_asset": "iso4217:USD",
                "sell_amount": "10",
                "buy_amount": None,
            }
        )
        with pytest.raises(ValidationError):
            validate_quote_request(test_data)

        test_data.update(
            {
                "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
                "buy_asset": None,
                "sell_amount": "10",
                "buy_amount": None,
            }
        )
        with pytest.raises(ValidationError):
            validate_quote_request(test_data)

        # Test invalid date string
        test_data.update(
            {
                "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
                "buy_asset": "iso4217:USD",
                "sell_amount": None,
                "buy_amount": "10",
                "expire_after": "abc",
            }
        )
        with pytest.raises(ValueError):
            validate_quote_request(test_data)

    def test_get_quote(self):
        from polaris.models import Quote

        mock_request = MagicMock()
        test_quote = Quote()
        # Happy path
        self.mock_get_quote_by_id.return_value = test_quote
        from polaris.sep38.quote import QuoteAPIView

        QuoteAPIView.get(mock_request, "1234")
        self.mock_get_quote_by_id.assert_called_with("1234")
        assert self.mock_error.call_count == 0

        self.mock_get_quote_by_id.side_effect = ValueError("")
        QuoteAPIView.get(mock_request, "1234")
        assert self.mock_error.call_count == 1

    @patch("polaris.integrations.registered_quote_integration.post_quote")
    @patch("polaris.sep38.quote.validate_quote_request")
    def test_post_quote_error(
        self, mock_validate_quote_request: MagicMock, mock_rqi_post_quote: MagicMock
    ):
        mock_validate_quote_request.side_effect = ValidationError("")
        mock_request = MagicMock()

        from polaris.sep38.quote import QuoteAPIView

        QuoteAPIView.post(mock_request)
        self.mock_error.assert_called_once()

        self.mock_error.reset_mock()
        mock_validate_quote_request.side_effect = None
        self.mock_get_exchange_pair.side_effect = ValueError("")
        QuoteAPIView.post(mock_request)
        self.mock_error.assert_called_once()

        # Test None exchange pair should result in error
        self.mock_error.reset_mock()
        self.mock_get_exchange_pair.side_effect = None
        self.mock_get_exchange_pair.return_value = None
        QuoteAPIView.post(mock_request)
        self.mock_error.assert_called_once()

        # Test None rqi.post_quote should result in error
        from polaris.models import ExchangePair

        self.mock_error.reset_mock()
        self.mock_get_exchange_pair.side_effect = None
        ep = ExchangePair()
        ep.__dict__.update(
            {
                "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
                "buy_asset": "iso4217:NGN",
            }
        )
        self.mock_get_exchange_pair.return_value = ep
        mock_rqi_post_quote.return_value = None
        QuoteAPIView.post(mock_request)
        self.mock_error.assert_called_once()

    @patch("polaris.integrations.registered_quote_integration.post_quote")
    @patch("polaris.sep38.quote.validate_quote_request")
    @patch("polaris.models.Quote.save")
    def test_post_quote_ok(
        self,
        mock_quote_save: MagicMock,
        mock_validate_quote_request: MagicMock,
        mock_rqi_post_quote: MagicMock,
    ):
        mock_request = MagicMock()
        test_request = {
            "sell_asset": "iso4217:NGN",
            "buy_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
            "sell_amount": 10,
            "expire_after": "2021-10-01T10:00:00",
            "sell_delivery_method": "cash",
            "buy_delivery_method": "cash",
            "country_code": "USA",
        }

        test_quote_result = {
            "sell_asset": "iso4217:NGN",
            "buy_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
            "sell_amount": "10",
            "buy_amount": None,
            "requested_expire_after": "2021-10-01T10:00:00",
            "sell_delivery_method": "cash",
            "buy_delivery_method": "cash",
            "country_code": "USA",
            "price": "0.5",
        }

        # Test with sell_amount
        from polaris.models import Quote

        test_quote = Quote()
        test_quote.__dict__.update(test_quote_result)

        # Test with sell_amount
        from polaris.models import Quote

        test_quote = Quote()
        test_quote.__dict__.update(test_quote_result)

        from polaris.models import ExchangePair

        ep = ExchangePair()
        ep.__dict__.update(
            {
                "sell_asset": "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
                "buy_asset": "iso4217:NGN",
            }
        )
        self.mock_get_exchange_pair.return_value = ep

        mock_quote_save.reset_mock()
        self.mock_get_exchange_pair.side_effect = None
        self.mock_get_exchange_pair.return_value = ep
        self.mock_get_significant_decimals.return_value = 2
        mock_rqi_post_quote.return_value = test_quote
        mock_validate_quote_request.return_value = test_request
        from polaris.sep38.quote import QuoteAPIView

        QuoteAPIView.post(mock_request)
        mock_quote_save.assert_called_once()
        saved_quote = mock_quote_save.call_args[0][0]
        assert float(saved_quote.sell_amount) / float(saved_quote.buy_amount) == float(
            saved_quote.price
        )

        # Test with buy amount
        mock_quote_save.reset_mock()
        test_quote.__dict__.update({"sell_amount": None, "buy_amount": "10"})
        QuoteAPIView.post(mock_request)
        mock_quote_save.assert_called_once()
        saved_quote = mock_quote_save.call_args[0][0]
        assert float(saved_quote.sell_amount) / float(saved_quote.buy_amount) == float(
            saved_quote.price
        )
