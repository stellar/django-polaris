import unittest
from unittest.mock import patch, MagicMock

import pytest

from polaris.models import OffChainAsset


def _compare_asset(a1: dict, a2: OffChainAsset) -> bool:
    assert a1.get("asset") == f"{a2.schema}:{a2.identifier}"
    assert "".join(a1.get("country_codes")) == a2.country_codes


class TestQuote(unittest.TestCase):
    @pytest.mark.django_db
    def test_list_stellar_assets(self):
        from polaris.sep38.utils import list_stellar_assets

        list_stellar_assets()

    @pytest.mark.django_db
    @patch("polaris.sep38.utils.DeliveryMethod.objects.filter")
    @patch("polaris.sep38.utils.OffChainAsset.objects.all")
    def test_list_offchain_assets(
        self,
        mock_offchain_assets_all: MagicMock,
        mock_sell_method: MagicMock,
        mock_buy_method: MagicMock,
    ):
        from polaris.sep38.utils import list_offchain_assets
        from polaris.tests.sep38.data import get_mock_offchain_assets
        from polaris.tests.sep38.data import get_mock_buy_delivery_methods
        from polaris.tests.sep38.data import get_mock_sell_delivery_methods

        mock_offchain_assets_all.return_value = get_mock_offchain_assets()
        mock_buy_method.return_value = get_mock_buy_delivery_methods()
        mock_sell_method.return_value = get_mock_sell_delivery_methods()

        mock_offchain_assets = get_mock_offchain_assets()
        result = list_offchain_assets()
        assert len(result) == len(mock_offchain_assets)
        for idx, _ in enumerate(result):
            _compare_asset(result[idx], mock_offchain_assets[idx])

    @pytest.mark.django_db
    def test_list_exchange_pairs(self):
        from polaris.sep38.utils import list_exchange_pairs

        list_exchange_pairs(
            "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
            "iso4217:USD",
        )

    @pytest.mark.django_db
    def test_get_offchain_asset(self):
        from polaris.sep38.utils import get_offchain_asset

        with pytest.raises(Exception):
            get_offchain_asset("iso4217:USD")

    @pytest.mark.django_db
    def test_get_stellar_asset(self):
        from polaris.sep38.utils import get_stellar_asset

        with pytest.raises(Exception):
            get_stellar_asset(
                "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B"
            )

    @pytest.mark.django_db
    @patch("polaris.models.DeliveryMethod")
    def test_get_buy_delivery_methods(self, _):
        from polaris.sep38.utils import get_buy_delivery_methods
        from polaris.models import OffChainAsset

        get_buy_delivery_methods(OffChainAsset())

    @pytest.mark.django_db
    def test_get_sell_delivery_methods(self):
        from polaris.sep38.utils import get_sell_delivery_methods
        from polaris.models import OffChainAsset

        get_sell_delivery_methods(OffChainAsset())

    @pytest.mark.django_db
    def test_is_stellar_asset(self):
        from polaris.sep38.utils import is_stellar_asset

        assert is_stellar_asset(
            "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B"
        )
        assert is_stellar_asset(
            "stellar:USDC:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B"
        )
        assert not is_stellar_asset(
            "stel:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B"
        )
        assert not is_stellar_asset("iso4217:USD")

    @pytest.mark.django_db
    @patch("polaris.sep38.utils.get_stellar_asset")
    @patch("polaris.sep38.utils.get_offchain_asset")
    def test_get_significant_decimals(
        self, mock_get_offchain_asset, mock_get_stellar_asset
    ):
        from polaris.sep38.utils import get_significant_decimals

        get_significant_decimals(
            "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B"
        )
        mock_get_stellar_asset.assert_called_once()
        get_significant_decimals("iso4217:USD")
        mock_get_offchain_asset.assert_called_once()

    @pytest.mark.django_db
    @pytest.mark.django_db
    def test_get_quote_by_id(self):
        from polaris.sep38.utils import get_quote_by_id

        with pytest.raises(Exception):
            get_quote_by_id("1234")

    @pytest.mark.django_db
    def test_get_exchange_pair(self):
        from polaris.sep38.utils import get_exchange_pair

        with pytest.raises(Exception):
            get_exchange_pair(
                "iso4217:USD",
                "stellar:SRT:GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
            )
