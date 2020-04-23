import pytest
import json
from unittest.mock import patch, Mock

from polaris.management.commands.poll_pending_deposits import Command, rdi, logger
from polaris.utils import create_stellar_deposit
from polaris.tests.conftest import STELLAR_ACCOUNT_1_SEED
from polaris.management.commands.poll_pending_deposits import execute_deposit
from polaris.models import Transaction
from polaris.tests.helpers import mock_load_not_exist_account, sep10
from polaris.tests.sep24.test_deposit import DEPOSIT_PATH, HORIZON_SUCCESS_RESPONSE

test_module = "polaris.management.commands.poll_pending_deposits"


@pytest.mark.django_db
@patch(f"{test_module}.create_stellar_deposit", return_value=True)
def test_poll_pending_deposits_success(client, acc1_usd_deposit_transaction_factory):
    transaction = acc1_usd_deposit_transaction_factory()
    rdi.poll_pending_deposits = Mock(return_value=[transaction])
    Command.execute_deposits()
    transaction.refresh_from_db()
    assert transaction.status == Transaction.STATUS.pending_anchor
    assert transaction.status_eta == 5


@pytest.mark.django_db
def test_poll_pending_deposits_bad_integration(
    client,
    acc1_usd_deposit_transaction_factory,
    acc1_usd_withdrawal_transaction_factory,
):
    # execute_deposits() queries for pending deposits
    acc1_usd_deposit_transaction_factory()
    # integration returns withdraw transaction
    withdrawal_transaction = acc1_usd_withdrawal_transaction_factory()
    rdi.poll_pending_deposits = Mock(return_value=[withdrawal_transaction])
    # error message is logged
    logger.error = Mock()

    Command.execute_deposits()

    logger.error.assert_called_with("Transaction not a deposit")

    # Change kind, add bad status
    withdrawal_transaction.kind = Transaction.KIND.deposit
    withdrawal_transaction.status = Transaction.STATUS.completed
    logger.error.reset_mock()

    Command.execute_deposits()

    logger.error.assert_called_with(
        f"Unexpected transaction status: {withdrawal_transaction.status}, expecting "
        f"{Transaction.STATUS.pending_user_transfer_start}"
    )


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.load_account", side_effect=mock_load_not_exist_account
)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    return_value=HORIZON_SUCCESS_RESPONSE,
)
def test_deposit_stellar_no_account(
    mock_load_account, mock_base_fee, client, acc1_usd_deposit_transaction_factory,
):
    """
    `create_stellar_deposit` sets the transaction with the provided `transaction_id` to
    status `pending_trust` if the provided transaction's `stellar_account` does not
    exist yet. This condition is mocked by throwing an error when attempting to load
    information for the provided account.
    Normally, this function creates the account. We have mocked out that functionality,
    as it relies on network calls to Horizon.
    """
    del mock_load_account, mock_base_fee, client
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    create_stellar_deposit(deposit.id)
    assert (
        Transaction.objects.get(id=deposit.id).status
        == Transaction.STATUS.pending_trust
    )


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    return_value=HORIZON_SUCCESS_RESPONSE,
)
def test_deposit_stellar_success(
    mock_submit, mock_base_fee, client, acc1_usd_deposit_transaction_factory,
):
    """
    `create_stellar_deposit` succeeds if the provided transaction's `stellar_account`
    has a trustline to the issuer for its `asset`, and the Stellar transaction completes
    successfully. All of these conditions and actions are mocked in this test to avoid
    network calls.
    """
    del mock_submit, mock_base_fee, client
    deposit = acc1_usd_deposit_transaction_factory()
    deposit.status = Transaction.STATUS.pending_anchor
    deposit.save()
    create_stellar_deposit(deposit.id)
    assert Transaction.objects.get(id=deposit.id).status == Transaction.STATUS.completed


@pytest.mark.django_db
@patch("stellar_sdk.server.Server.fetch_base_fee", return_value=100)
@patch(
    "stellar_sdk.server.Server.submit_transaction",
    return_value=HORIZON_SUCCESS_RESPONSE,
)
def test_deposit_interactive_confirm_success(
    mock_submit, mock_base_fee, client, acc1_usd_deposit_transaction_factory,
):
    """
    `GET /deposit` and `GET /transactions/deposit/webapp` succeed with valid `account`
    and `asset_code`.
    """
    del mock_submit, mock_base_fee
    deposit = acc1_usd_deposit_transaction_factory()

    encoded_jwt = sep10(client, deposit.stellar_account, STELLAR_ACCOUNT_1_SEED)
    header = {"HTTP_AUTHORIZATION": f"Bearer {encoded_jwt}"}

    response = client.post(
        DEPOSIT_PATH,
        {"asset_code": "USD", "account": deposit.stellar_account},
        follow=True,
        **header,
    )
    content = json.loads(response.content)
    assert response.status_code == 200
    assert content["type"] == "interactive_customer_info_needed"

    transaction_id = content["id"]
    url = content["url"]
    # Authenticate session
    response = client.get(url)
    assert response.status_code == 200
    assert client.session["authenticated"] is True

    amount = 20
    url, args_str = url.split("?")
    response = client.post(url + "/submit?" + args_str, {"amount": amount})
    assert response.status_code == 302
    assert (
        Transaction.objects.get(id=transaction_id).status
        == Transaction.STATUS.pending_user_transfer_start
    )

    transaction = Transaction.objects.get(id=transaction_id)
    execute_deposit(transaction)

    # We've mocked submit_transaction, but the status should be marked as
    # completed after executing the function above.
    transaction.refresh_from_db()
    assert float(transaction.amount_in) == amount
    assert transaction.status == Transaction.STATUS.completed
