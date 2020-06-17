from typing import List
from django.db.models import QuerySet

from polaris.models import Transaction


class RailsIntegration:
    """
    A container class for functions that access off-chain rails, such banking
    accounts or other crypto networks. Currently only contains
    poll_pending_transfers() but others will be added.
    """

    def poll_pending_transfers(self, transactions: QuerySet) -> List[Transaction]:
        pass

    # TODO: move DepositIntegration.poll_pending_deposits here
    # DepositIntegration and WithdrawalIntegration should only contain functions
    # that are needed by unilateral transaction SEPs, such as SEP6 and SEP24.
    # poll_pending_deposits() is a function that could be used by bilateral
    # transaction SEPs (like SEP31) that need to watch for incoming deposits
    # to their accounts.
    #
    # Polaris should have designed all rails-related functions to be separate
    # from the type of transaction being processed, since now it would be a bad
    # design decision to have SEP31 (bilateral payment) anchors use
    # DepositIntegration and WithdrawalIntegration.
    #
    # For example, both SEP31 and SEP6/24 anchors need to poll their bank/off-chain
    # transfers (off-chain payments to users after receiving stellar funds).
    # The difference is that SEP31 anchors are sending funds to a user
    # who did not deposit funds into the anchor's stellar account, whereas SEP6/24
    # anchors are. Polaris could've added a poll_pending_transfers function to
    # both SendIntegration and WithdrawalIntegration, but it is probably better to
    # allow the anchor to connect to their off-chain rails once for all pending
    # transfers than twice for payments and withdrawals.
    #
    # WithdrawalIntegration.process_withdrawal() as well as
    # SendIntegration.process_payment() may also be moved (and maybe combined) here
    # in the future, since they are rails-related functions and are for very similar
    # purposes.
    #
    # For now, I want to avoid breaking changes and introduce SEP31 support without
    # changing the interface for other SEPs.


registered_rails_integration = RailsIntegration()
