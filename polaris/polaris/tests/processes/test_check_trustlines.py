import pytest
from unittest.mock import patch, Mock

from polaris.tests.conftest import USD_ISSUER_ACCOUNT
from polaris.models import Transaction
from polaris.tests.conftest import STELLAR_ACCOUNT_1
from polaris.management.commands.check_trustlines import Command as CheckTrustlinesCMD


mock_server = Mock(
    accounts=Mock(
        return_value=Mock(
            account_id=Mock(
                return_value=Mock(
                    call=Mock(
                        return_value={
                            "id": 1,
                            "sequence": 1,
                            "balances": [
                                {
                                    "asset_code": "USD",
                                    "asset_issuer": USD_ISSUER_ACCOUNT,
                                }
                            ],
                            "thresholds": {
                                "low_threshold": 1,
                                "med_threshold": 1,
                                "high_threshold": 1,
                            },
                            "signers": [{"key": STELLAR_ACCOUNT_1, "weight": 1}],
                        }
                    )
                )
            )
        )
    )
)


@pytest.mark.django_db
@patch("polaris.management.commands.check_trustlines.create_stellar_deposit")
@patch(
    "polaris.management.commands.check_trustlines.settings.HORIZON_SERVER", mock_server
)
def test_deposit_check_trustlines_success(acc1_usd_deposit_transaction_factory):
    """
    Creates a transaction with status `pending_trust` and checks that
    `check_trustlines` changes its status to `completed`. All the necessary
    functionality and conditions are mocked for determinism.
    """
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_trust
    deposit.save()
    deposit.refresh_from_db = Mock()
    CheckTrustlinesCMD.check_trustlines()
    assert deposit.refresh_from_db.was_called
