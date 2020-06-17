from typing import Dict

from polaris.models import Asset, Transaction


class SendIntegration:
    """
    The container class for SEP31 integrations
    """

    def info(self, asset: Asset, lang: str = None) -> Dict:
        pass

    def process_send_request(self, params: Dict, transaction_id: str) -> Dict:
        pass

    def process_update_request(self, params: Dict, transaction: Transaction):
        pass

    def process_payment(self, transaction: Transaction):
        pass

    def valid_sending_anchor(self, public_key: str) -> bool:
        pass


registered_send_integration = SendIntegration()
