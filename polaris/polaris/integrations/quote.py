from typing import List

from polaris.models import Quote


class GetPricesResponse:
    asset = "",
    price = "",
    decimals = 0


class GetPriceResponse:
    price = "",
    sell_amount = "",
    buy_amount = ""


class SEP38AnchorIntegration:
    """
    The container class for SEP38 integrations

    The list of the offline assets supported by the anchor should be returned.

    The returned dictionary should contains the following attributes specified at:
    https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#get-info

    If there is no Offchain assets, an empty list is expected.

    """

    def get_prices(self,
                   sell_asset: str,
                   sell_amount: str,
                   sell_delivery_method: str = None,
                   buy_delivery_method: str = None,
                   country_code: str = None) -> List[GetPricesResponse]:
        pass

    def get_price(self,
                  sell_asset: str,
                  buy_asset: str,
                  sell_amount: str = None,
                  buy_amount: str = None
                  ) -> GetPriceResponse:
        pass

    def post_quote(self, quote: Quote):
        pass


registered_quote_integration = SEP38AnchorIntegration()
