from typing import List

from polaris.models import Quote


class SEP38AnchorIntegration:
    """
    The container class for SEP38 integrations
    """

    def get_prices(
        self,
        sell_asset: str,
        sell_amount: str,
        sell_delivery_method: str = None,
        buy_delivery_method: str = None,
        country_code: str = None,
        *args,
        **kwargs
    ) -> List[dict]:
        pass

    def get_price(
        self,
        sell_asset: str,
        buy_asset: str,
        sell_amount: str = None,
        buy_amount: str = None,
        sell_delivery_method: str = None,
        buy_delivery_method: str = None,
        country_code: str = None,
        *args,
        **kwargs
    ) -> dict:
        pass

    def post_quote(self, quote: Quote, *args, **kwargs):
        pass


registered_quote_integration = SEP38AnchorIntegration()
