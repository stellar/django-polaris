from polaris.models import Transaction


class CustodyIntegration:
    def get_distribution_account(self) -> str:
        pass

    def submit_transaction(self, transaction: Transaction) -> dict:
        pass
