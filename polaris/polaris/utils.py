"""This module defines helpers for various endpoints."""
import codecs
import datetime
import uuid
from typing import Optional
from logging import getLogger as get_logger, LoggerAdapter

from django.utils.translation import gettext as _
from django.conf import settings as django_settings
from rest_framework import status
from rest_framework.response import Response
from stellar_sdk.transaction_builder import TransactionBuilder
from stellar_sdk.exceptions import BaseHorizonError
from stellar_sdk.xdr import StellarXDR_const as const
from stellar_sdk.xdr.StellarXDR_type import TransactionResult
from stellar_sdk import Memo, TextMemo, IdMemo, HashMemo

from polaris import settings
from polaris.models import Transaction


class PolarisLoggerAdapter(LoggerAdapter):
    def process(self, msg, kwargs):
        return f"{self.extra['python_path']}: {msg}", kwargs


def getLogger(name):
    return PolarisLoggerAdapter(get_logger(name), extra={"python_path": name})


logger = getLogger(__name__)


def render_error_response(
    description: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    content_type: str = "application/json",
) -> Response:
    """
    Renders an error response in Django.

    Currently supports HTML or JSON responses.
    """
    resp_data = {
        "data": {"error": description},
        "status": status_code,
        "content_type": content_type,
    }
    if content_type == "text/html":
        resp_data["data"]["status_code"] = status_code
        resp_data["template_name"] = "error.html"
    return Response(**resp_data)


def memo_hex_to_base64(memo):
    """
    Formats a hex memo, as in the Transaction model, to match
    the base64 Horizon response.
    """
    return (codecs.encode(codecs.decode(memo, "hex"), "base64").decode("utf-8")).strip()


def memo_base64_to_hex(memo):
    return (
        codecs.encode(codecs.decode(memo.encode(), "base64"), "hex").decode("utf-8")
    ).strip()


def create_transaction_id():
    """Creates a unique UUID for a Transaction, via checking existing entries."""
    while True:
        transaction_id = uuid.uuid4()
        if not Transaction.objects.filter(id=transaction_id).exists():
            break
    return transaction_id


def verify_valid_asset_operation(
    asset, amount, op_type, content_type="application/json"
) -> Optional[Response]:
    enabled = getattr(asset, f"{op_type}_enabled")
    min_amount = getattr(asset, f"{op_type}_min_amount")
    max_amount = getattr(asset, f"{op_type}_max_amount")
    if not enabled:
        return render_error_response(
            _("the specified operation is not available for '%s'") % asset.code,
            content_type=content_type,
        )
    elif not (min_amount <= amount <= max_amount):
        return render_error_response(
            _("Asset amount must be within bounds [%(min)s, %(max)s]")
            % {
                "min": round(min_amount, asset.significant_decimals),
                "max": round(max_amount, asset.significant_decimals),
            },
            content_type=content_type,
        )


def create_stellar_deposit(transaction_id: str) -> bool:
    """
    Create and submit the Stellar transaction for the deposit.

    :returns a boolean indicating whether or not the deposit was successfully
        completed. One reason a transaction may not be completed is if a
        trustline must be established. The transaction's status will be set as
        ``pending_stellar`` and the status_message will be populated
        with a description of the problem encountered.
    :raises ValueError: the transaction has an unexpected status
    """
    transaction = Transaction.objects.get(id=transaction_id)

    # We check the Transaction status to avoid double submission of a Stellar
    # transaction. The Transaction can be either `pending_anchor` if the task
    # is called from `poll_pending_deposits()` or `pending_trust` if called
    # from the `check_trustlines()`.
    if transaction.status not in [
        Transaction.STATUS.pending_anchor,
        Transaction.STATUS.pending_trust,
    ]:
        raise ValueError(
            f"unexpected transaction status {transaction.status} for "
            "create_stellar_deposit",
        )
    elif transaction.amount_in is None or transaction.amount_fee is None:
        transaction.status = Transaction.STATUS.error
        transaction.status_message = (
            "`amount_in` and `amount_fee` must be populated, skipping transaction"
        )
        transaction.save()
        raise ValueError(transaction.status_message)
    transaction.status = Transaction.STATUS.pending_stellar
    transaction.save()
    logger.info(f"Transaction {transaction_id} now pending_stellar")

    # We can assume transaction has valid stellar_account, amount_in, and asset
    # because this task is only called after those parameters are validated.
    stellar_account = transaction.stellar_account
    payment_amount = round(
        transaction.amount_in - transaction.amount_fee,
        transaction.asset.significant_decimals,
    )
    asset = transaction.asset
    memo = make_memo(transaction.memo, transaction.memo_type)

    # If the given Stellar account does not exist, create
    # the account with at least enough XLM for the minimum
    # reserve and a trust line (recommended 2.01 XLM), update
    # the transaction in our internal database, and return.

    server = settings.HORIZON_SERVER
    starting_balance = settings.ACCOUNT_STARTING_BALANCE
    server_account = server.load_account(asset.distribution_account)
    base_fee = server.fetch_base_fee()
    builder = TransactionBuilder(
        source_account=server_account,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        base_fee=base_fee,
    )
    try:
        server.load_account(stellar_account)
    except BaseHorizonError as address_exc:
        # 404 code corresponds to Resource Missing.
        if address_exc.status != 404:  # pragma: no cover
            msg = (
                "Horizon error when loading stellar account: " f"{address_exc.message}"
            )
            logger.error(msg)
            transaction.status_message = msg
            transaction.status = Transaction.STATUS.error
            transaction.save()
            return False

        logger.info(f"Stellar account {stellar_account} does not exist. Creating.")
        transaction_envelope = builder.append_create_account_op(
            destination=stellar_account,
            starting_balance=starting_balance,
            source=asset.distribution_account,
        ).build()
        transaction_envelope.sign(asset.distribution_seed)
        try:
            server.submit_transaction(transaction_envelope)
        except BaseHorizonError as submit_exc:  # pragma: no cover
            msg = (
                "Horizon error when submitting create account to horizon: "
                f"{submit_exc.message}"
            )
            logger.error(msg)
            transaction.status_message = msg
            transaction.status = Transaction.STATUS.error
            transaction.save()
            return False

        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        logger.info(f"Transaction for account {stellar_account} now pending_trust.")
        return False

    # If the account does exist, deposit the desired amount of the given
    # asset via a Stellar payment. If that payment succeeds, we update the
    # transaction to completed at the current time. If it fails due to a
    # trustline error, we update the database accordingly. Else, we do not update.

    builder.append_payment_op(
        destination=stellar_account,
        asset_code=asset.code,
        asset_issuer=asset.issuer,
        amount=str(payment_amount),
    )
    if memo:
        builder.add_memo(memo)
    transaction_envelope = builder.build()
    transaction_envelope.sign(asset.distribution_seed)
    try:
        response = server.submit_transaction(transaction_envelope)
    # Functional errors at this stage are Horizon errors.
    except BaseHorizonError as exception:
        tx_result = TransactionResult.from_xdr(exception.result_xdr)
        op_result = tx_result.result.results[0]
        if op_result.tr.paymentResult.code != const.PAYMENT_NO_TRUST:
            msg = (
                "Unable to submit payment to horizon, "
                f"non-trustline failure: {exception.message}"
            )
            logger.error(msg)
            transaction.status_message = msg
            transaction.status = Transaction.STATUS.error
            transaction.save()
            return False
        msg = "trustline error when submitting transaction to horizon"
        logger.error(msg)
        transaction.status_message = msg
        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        return False

    if not response.get("successful"):
        transaction_result = TransactionResult.from_xdr(response["result_xdr"])
        msg = (
            "Stellar transaction failed when submitted to horizon: "
            f"{transaction_result.result.results}"
        )
        logger.error(msg)
        transaction.status_message = msg
        transaction.status = Transaction.STATUS.error
        transaction.save()
        return False

    transaction.paging_token = response["paging_token"]
    transaction.stellar_transaction_id = response["id"]
    transaction.status = Transaction.STATUS.completed
    transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
    transaction.status_eta = 0  # No more status change.
    transaction.amount_out = payment_amount
    transaction.save()
    logger.info(f"Transaction {transaction.id} completed.")
    return True


def memo_str(memo: str, memo_type: str) -> Optional[str]:
    memo = make_memo(memo, memo_type)
    if not memo:
        return memo
    if isinstance(memo, IdMemo):
        return str(memo.memo_id)
    elif isinstance(memo, HashMemo):
        return memo_hex_to_base64(memo.memo_hash.hex())
    else:
        return memo.memo_text.decode()


def make_memo(memo: str, memo_type: str) -> Optional[Memo]:
    if not memo:
        return None
    if memo_type == Transaction.MEMO_TYPES.id:
        return IdMemo(int(memo))
    elif memo_type == Transaction.MEMO_TYPES.hash:
        return HashMemo(memo_base64_to_hex(memo))
    elif memo_type == Transaction.MEMO_TYPES.text:
        return TextMemo(memo)
    else:
        raise ValueError()


SEP_9_FIELDS = {
    "family_name",
    "last_name",
    "given_name",
    "first_name",
    "additional_name",
    "address_country_code",
    "state_or_province",
    "city",
    "postal_code",
    "address",
    "mobile_number",
    "email_address",
    "birth_date",
    "birth_place",
    "birth_country_code",
    "bank_account_number",
    "bank_number",
    "bank_phone_number",
    "tax_id",
    "tax_id_name",
    "occupation",
    "employer_name",
    "employer_address",
    "language_code",
    "id_type",
    "id_country_code",
    "id_issue_date",
    "id_expiration_date",
    "id_number",
    "photo_id_front",
    "photo_id_back",
    "notary_approval_of_photo_id",
    "ip_address",
    "photo_proof_residence",
    "organization.name",
    "organization.VAT_number",
    "organization.registration_number",
    "organization.registered_address",
    "organization.number_of_shareholders",
    "organization.shareholder_name",
    "organization.photo_incorporation_doc",
    "organization.photo_proof_adress",
    "organization.address_country_code",
    "organization.state_or_province",
    "organization.city",
    "organization.postal_code",
    "organization.director_name",
    "organization.website",
    "organization.email",
    "organization.phone",
}


def extract_sep9_fields(args):
    sep9_args = {}
    for field in SEP_9_FIELDS:
        if field in args:
            sep9_args[field] = args.get(field)
    return sep9_args


def check_config():
    from polaris.sep24.utils import check_sep24_config

    if not hasattr(django_settings, "POLARIS_ACTIVE_SEPS"):
        raise AttributeError(
            "POLARIS_ACTIVE_SEPS must be defined in your django settings file."
        )

    check_middleware()
    check_protocol()
    if "sep-24" in django_settings.POLARIS_ACTIVE_SEPS:
        check_sep24_config()


def check_middleware():
    err_msg = "{} is not installed in settings.MIDDLEWARE"
    cors_middleware_path = "corsheaders.middleware.CorsMiddleware"
    if cors_middleware_path not in django_settings.MIDDLEWARE:
        raise ValueError(err_msg.format(cors_middleware_path))


def check_protocol():
    if settings.LOCAL_MODE:
        logger.warning(
            "Polaris is in local mode. This makes the SEP-24 interactive flow "
            "insecure and should only be used for local development."
        )
    if not (settings.LOCAL_MODE or getattr(django_settings, "SECURE_SSL_REDIRECT")):
        logger.warning(
            "SECURE_SSL_REDIRECT is required to redirect HTTP traffic to HTTPS"
        )
    if getattr(django_settings, "SECURE_PROXY_SSL_HEADER"):
        logger.warning(
            "SECURE_PROXY_SSL_HEADER should only be set if Polaris is "
            "running behind an HTTPS reverse proxy."
        )
