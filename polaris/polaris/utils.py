"""This module defines helpers for various endpoints."""
import logging
import codecs
import datetime

from rest_framework import status
from rest_framework.response import Response
from stellar_sdk.transaction_builder import TransactionBuilder
from stellar_sdk.exceptions import BaseHorizonError
from stellar_sdk.xdr.StellarXDR_type import TransactionResult

from polaris import settings
from polaris.models import Transaction


TRUSTLINE_FAILURE_XDR = "AAAAAAAAAGT/////AAAAAQAAAAAAAAAB////+gAAAAA="
SUCCESS_XDR = "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA="


class Logger:
    """
    Additional log message pre-processing.

    Right now this class allows loggers to be defined with additional
    meta-data that can be used to pre-process log statements. This
    could be done using a logging.Handler.
    """

    def __init__(self, namespace):
        self.logger = logging.getLogger("polaris")
        self.namespace = namespace

    def fmt(self, msg):
        return f'{self.namespace}: "{msg}"'

    # typical logging.Logger mock methods

    def debug(self, msg):
        self.logger.debug(self.fmt(msg))

    def info(self, msg):
        self.logger.info(self.fmt(msg))

    def warning(self, msg):
        self.logger.warning(self.fmt(msg))

    def error(self, msg):
        self.logger.error(self.fmt(msg))

    def critical(self, msg):
        self.logger.critical(self.fmt(msg))

    def exception(self, msg):
        self.logger.exception(self.fmt(msg))


logger = Logger(__name__)


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


def format_memo_horizon(memo):
    """
    Formats a hex memo, as in the Transaction model, to match
    the base64 Horizon response.
    """
    return (codecs.encode(codecs.decode(memo, "hex"), "base64").decode("utf-8")).strip()


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

    transaction_envelope = builder.append_payment_op(
        destination=stellar_account,
        asset_code=asset.code,
        asset_issuer=asset.issuer,
        amount=str(payment_amount),
    ).build()
    transaction_envelope.sign(asset.distribution_seed)
    try:
        response = server.submit_transaction(transaction_envelope)
    # Functional errors at this stage are Horizon errors.
    except BaseHorizonError as exception:
        if TRUSTLINE_FAILURE_XDR not in exception.result_xdr:  # pragma: no cover
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

    if response["result_xdr"] != SUCCESS_XDR:  # pragma: no cover
        transaction_result = TransactionResult.from_xdr(response["result_xdr"])
        msg = (
            "Stellar transaction failed when submitted to horizon: "
            f"{transaction_result.result}"
        )
        logger.error(msg)
        transaction.status_message = msg
        transaction.status = Transaction.STATUS.error
        transaction.save()
        return False

    transaction.paging_token = response["paging_token"]
    transaction.stellar_transaction_id = response["hash"]
    transaction.status = Transaction.STATUS.completed
    transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
    transaction.status_eta = 0  # No more status change.
    transaction.amount_out = payment_amount
    transaction.save()
    logger.info(f"Transaction {transaction.id} completed.")
    return True


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
        sep9_args[field] = args.get(field)
    return sep9_args
