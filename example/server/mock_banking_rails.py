from uuid import uuid4
from decimal import Decimal
from polaris.models import Transaction


class RailsAccount:
    def __init__(self, account_id: str):
        self.id = account_id


class RailsTransaction:
    def __init__(self, to_account: RailsAccount, amount: Decimal, memo: str):
        self.id = str(uuid4())
        self.to_account = to_account
        self.from_account = RailsAccount(str(uuid4()))
        self.amount = amount
        self.status = "complete"
        self.memo = memo


class RailsClient:
    def __init__(self, account_id):
        self.account = RailsAccount(account_id)

    def get_deposit(self, memo):
        """
        A fake banking rails function for retrieving a RailsTransaction object.

        When a deposit is initiated by making a POST /deposit/interactive call,
        we (the anchor) display instructions with a fake `memo` string that the
        user would (in theory) use when making the deposit to the anchor's
        account. This `memo` is saved to Transaction.external_extra.

        Then, when polling the bank for new deposits into the anchor's account,
        we identify a Transaction database object using the memo originally
        displayed to the user.

        This is intended to be an example for how a real anchor would poll the
        anchors bank and identify a deposit from a particular user.
        """
        transaction = Transaction.objects.filter(
            external_extra=memo,
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start,
        ).first()
        if transaction:
            return RailsTransaction(self.account, transaction.amount_in, memo)
        else:
            return None

    def send_funds(self, from_account: RailsAccount, to_account: str, amount: Decimal):
        """
        A fake function to symbolize sending money from an anchor's bank
        account to the user's bank account.
        """
        pass
