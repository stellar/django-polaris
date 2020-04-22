from typing import Dict


class CustomerIntegration:
    def more_info(self, account):
        pass

    def put(self, params: Dict):
        pass

    def delete(self, account: str):
        pass


registered_customer_integration = CustomerIntegration()
