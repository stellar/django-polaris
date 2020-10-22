"""This module defines helpers for various endpoints."""
import json
import codecs
import datetime
import uuid
import base64
from decimal import Decimal
from typing import Optional, Tuple, Union
from logging import getLogger as get_logger, LoggerAdapter

from django.utils.translation import gettext
from rest_framework import status
from rest_framework.response import Response
from stellar_sdk import TransactionEnvelope, TextMemo, IdMemo, HashMemo, Asset, Claimant
from stellar_sdk.transaction_builder import TransactionBuilder
from stellar_sdk.exceptions import (
    BaseHorizonError,
    NotFoundError,
    BadRequestError,
    BadSignatureError,
    SignatureExistError,
)
from stellar_sdk.xdr import StellarXDR_const as const
from stellar_sdk.xdr.StellarXDR_type import TransactionResult
from stellar_sdk.account import Account, Thresholds
from stellar_sdk.sep.stellar_web_authentication import _verify_te_signed_by_account_id
from stellar_sdk.sep.exceptions import InvalidSep10ChallengeError
from stellar_sdk.keypair import Keypair

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
        resp_data["template_name"] = "polaris/error.html"
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
            gettext("the specified operation is not available for '%s'") % asset.code,
            content_type=content_type,
        )
    elif not (min_amount <= amount <= max_amount):
        return render_error_response(
            gettext("Asset amount must be within bounds [%(min)s, %(max)s]")
            % {
                "min": round(min_amount, asset.significant_decimals),
                "max": round(max_amount, asset.significant_decimals),
            },
            content_type=content_type,
        )


def create_stellar_deposit(transaction: Transaction) -> bool:
    """
    Create and submit the Stellar transaction for the deposit.
    The Transaction `pending_anchor` when the task is called from `poll_pending_deposits()`.
    """
    if transaction.status != Transaction.STATUS.pending_anchor:
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

    try:
        _, created, pending_trust = get_or_create_transaction_destination_account(
            transaction
        )
    except RuntimeError as e:
        transaction.status = Transaction.STATUS.error
        transaction.status_message = str(e)
        transaction.save()
        logger.error(transaction.status_message)
        return False
    if created or pending_trust:
        # the account is pending_trust for the asset to be received
        if pending_trust and transaction.status != Transaction.STATUS.pending_trust:
            transaction.status = Transaction.STATUS.pending_trust
            transaction.save()

    # if the distribution account's master signer's weight is great or equal to the its
    # medium threshold, verify the transaction is signed by it's channel account
    master_signer = None
    if transaction.asset.distribution_account_master_signer:
        master_signer = transaction.asset.distribution_account_master_signer
    thresholds = transaction.asset.distribution_account_thresholds
    if not (master_signer and master_signer["weight"] >= thresholds["med_threshold"]):
        multisig = True
        envelope = TransactionEnvelope.from_xdr(
            transaction.envelope_xdr, settings.STELLAR_NETWORK_PASSPHRASE
        )
        try:
            _verify_te_signed_by_account_id(envelope, transaction.channel_account)
        except InvalidSep10ChallengeError:
            transaction.status = Transaction.STATUS.error
            transaction.status_message = gettext(
                "Multisig transaction's envelope was not signed by channel account"
            )
            transaction.save()
            return False
    # otherwise, create the envelope and sign it with the distribution account's secret
    else:
        multisig = False
        distribution_acc, _ = get_account_obj(
            Keypair.from_public_key(transaction.asset.distribution_account)
        )
        envelope = create_transaction_envelope(transaction, distribution_acc)
        envelope.sign(transaction.asset.distribution_seed)
        transaction.envelope_xdr = envelope.to_xdr()

    try:
        return submit_stellar_deposit(transaction, multisig=multisig)
    except RuntimeError as e:
        transaction.status_message = str(e)
        transaction.status = Transaction.STATUS.error
        transaction.save()
        logger.error(transaction.status_message)
        return False


def handle_bad_signatures_error(e, transaction, multisig=False):
    err_msg = (
        f"Horizon returned a {e.__class__.__name__} on transaction "
        f"{transaction.id} submission."
    )
    logger.error(err_msg)
    logger.error(
        f"Transaction {transaction.id} envelope XDR: {transaction.envelope_xdr}"
    )
    logger.error(f"Transaction {transaction.id} result XDR: {e.result_xdr}")
    if multisig:
        logger.error(
            f"Resetting the Transaction.envelope_xdr for {transaction.id}, "
            "updating Transaction.pending_signatures to True"
        )
        channel_account, _ = get_account_obj(
            Keypair.from_public_key(transaction.channel_account)
        )
        transaction.envelope_xdr = create_transaction_envelope(
            transaction, channel_account
        ).to_xdr()
        transaction.pending_signatures = True
        transaction.status = Transaction.STATUS.pending_anchor = True
    else:
        transaction.status = Transaction.STATUS.error
        transaction.status_message = (
            f"Horizon returned a {e.__class__.__name__} on transaction "
            f"{transaction.id} submission"
        )
    transaction.save()


def submit_stellar_deposit(transaction, multisig=False) -> bool:
    claimable = (
        True if transaction.status == Transaction.STATUS.pending_trust else False
    )
    transaction.status = Transaction.STATUS.pending_stellar
    transaction.save()
    logger.info(f"Transaction {transaction.id} now pending_stellar")
    envelope = TransactionEnvelope.from_xdr(
        transaction.envelope_xdr, settings.STELLAR_NETWORK_PASSPHRASE
    )
    try:
        response = settings.HORIZON_SERVER.submit_transaction(envelope)
    except BaseHorizonError as e:
        logger.info(e.__class__.__name__)
        tx_result = TransactionResult.from_xdr(e.result_xdr)
        op_results = tx_result.result.results
        if isinstance(e, BadRequestError):
            if op_results[0].code == -1:  # Bad Auth
                handle_bad_signatures_error(e, transaction, multisig=multisig)
                return False  # handle_bad_signatures_error() saves transaction
            else:
                transaction.status = Transaction.STATUS.error
                transaction.status_message = (
                    f"tx failed with codes: {op_results}. Result XDR: {e.result_xdr}"
                )
        elif op_results[0].tr.paymentResult.code == const.PAYMENT_NO_TRUST:
            transaction.status = Transaction.STATUS.pending_trust
            transaction.status_message = (
                "trustline error when submitting transaction to horizon"
            )
        else:
            raise RuntimeError(
                "Unable to submit payment to horizon, "
                f"non-trustline failure: {e.message}"
            )
        transaction.save()
        logger.error(transaction.status_message)
        return False

    if not response.get("successful"):
        transaction_result = TransactionResult.from_xdr(response["result_xdr"])
        raise RuntimeError(
            "Stellar transaction failed when submitted to horizon: "
            f"{transaction_result.result.results}"
        )
    transaction.claimable_balance_id = get_balance_id(response) if claimable else None
    transaction.paging_token = response["paging_token"]
    transaction.stellar_transaction_id = response["id"]
    transaction.status = Transaction.STATUS.completed
    transaction.completed_at = datetime.datetime.now(datetime.timezone.utc)
    transaction.status_eta = 0
    transaction.amount_out = round(
        Decimal(transaction.amount_in) - Decimal(transaction.amount_fee),
        transaction.asset.significant_decimals,
    )
    transaction.save()
    logger.info(f"Transaction {transaction.id} completed.")
    return True


def load_account(resp):
    sequence = int(resp["sequence"])
    thresholds = Thresholds(
        resp["thresholds"]["low_threshold"],
        resp["thresholds"]["med_threshold"],
        resp["thresholds"]["high_threshold"],
    )
    account = Account(account_id=resp["account_id"], sequence=sequence)
    account.signers = resp["signers"]
    account.thresholds = thresholds
    return account


def get_account_obj(kp):
    try:
        json_resp = (
            settings.HORIZON_SERVER.accounts()
            .account_id(account_id=kp.public_key)
            .call()
        )
    except NotFoundError:
        raise RuntimeError(f"account {kp.public_key} does not exist")
    else:
        return load_account(json_resp), json_resp


def has_trustline(transaction, json_resp):
    pending_trust = True
    for balance in json_resp["balances"]:
        if balance.get("asset_type") == "native":
            continue
        asset_code = balance["asset_code"]
        asset_issuer = balance["asset_issuer"]
        if (
            transaction.asset.code == asset_code
            and transaction.asset.issuer == asset_issuer
        ):
            pending_trust = False
            break
    return pending_trust


def get_or_create_transaction_destination_account(
    transaction,
) -> Tuple[Optional[Account], bool, bool]:
    """
    Returns the stellar_sdk.account.Account for which this transaction's payment will be sent to as
    as well as whether or not the account was created as a result of calling this function.

    If the account exists, the function simply returns the account and False.

    If the account doesn't exist, Polaris must create the account using an account provided by the
    anchor. Polaris can use the distribution account of the anchored asset or a channel account if
    the asset's distribution account requires non-master signatures.

    If the transacted asset's distribution account does not require non-master signatures, Polaris
    can create the destination account using the distribution account. On successful creation,
    this function will return the account and True. On failure, a RuntimeError exception is raised.

    If the transacted asset's distribution account does require non-master signatures, the anchor
    should save a keypair of a pre-existing Stellar account to use as the channel account via
    DepositIntegration.create_channel_account().

    This channel account must only be used as the source account for transactions related to the
    ``Transaction`` object passed. It also must not be used to submit transactions by any service
    other than Polaris. If it is, the outstanding transactions will be invalidated due to bad
    sequence numbers. Finally, the channel accounts must have a master signer with a weight greater
    than or equal to the medium threshold for the account.

    After the transaction for creating the destination account has been submitted to the stellar network
    and the transaction has been created, this function will return the account and True. If the
    transaction was not submitted successfully, a RuntimeError exception will be raised.
    """
    try:
        account, json_resp = get_account_obj(
            Keypair.from_public_key(transaction.stellar_account)
        )
        return account, False, has_trustline(transaction, json_resp)
    except RuntimeError:
        master_signer = None
        if transaction.asset.distribution_account_master_signer:
            master_signer = transaction.asset.distribution_account_master_signer
        thresholds = transaction.asset.distribution_account_thresholds
        if master_signer and master_signer["weight"] >= thresholds["med_threshold"]:
            source_account_kp = Keypair.from_secret(transaction.asset.distribution_seed)
            source_account, _ = get_account_obj(source_account_kp)
        else:
            from polaris.integrations import registered_deposit_integration as rdi

            rdi.create_channel_account(transaction)
            source_account_kp = Keypair.from_secret(transaction.channel_seed)
            source_account, _ = get_account_obj(source_account_kp)

        base_fee = settings.HORIZON_SERVER.fetch_base_fee()
        builder = TransactionBuilder(
            source_account=source_account,
            network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
            base_fee=base_fee,
        )
        transaction_envelope = builder.append_create_account_op(
            destination=transaction.stellar_account,
            starting_balance=settings.ACCOUNT_STARTING_BALANCE,
        ).build()
        transaction_envelope.sign(source_account_kp)

        try:
            settings.HORIZON_SERVER.submit_transaction(transaction_envelope)
        except BaseHorizonError as submit_exc:  # pragma: no cover
            raise RuntimeError(
                "Horizon error when submitting create account to horizon: "
                f"{submit_exc.message}"
            )

        transaction.status = Transaction.STATUS.pending_trust
        transaction.save()
        logger.info(
            f"Transaction {transaction.id} is now pending_trust of destination account"
        )
        account, json_resp = get_account_obj(
            Keypair.from_public_key(transaction.stellar_account)
        )
        return account, True, has_trustline(transaction, json_resp)
    except BaseHorizonError as e:
        raise RuntimeError(f"Horizon error when loading stellar account: {e.message}")


def create_transaction_envelope(transaction, source_account) -> TransactionEnvelope:
    payment_amount = round(
        Decimal(transaction.amount_in) - Decimal(transaction.amount_fee),
        transaction.asset.significant_decimals,
    )
    memo = make_memo(transaction.memo, transaction.memo_type)
    base_fee = settings.HORIZON_SERVER.fetch_base_fee()
    builder = TransactionBuilder(
        source_account=source_account,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        base_fee=base_fee,
    )
    if transaction.status == Transaction.STATUS.pending_trust:
        claimant = Claimant(destination=transaction.stellar_account)
        asset = Asset(code=transaction.asset.code, issuer=transaction.asset.issuer)
        builder.append_create_claimable_balance_op(
            claimants=[claimant],
            asset=asset,
            amount=str(payment_amount),
            source=transaction.asset.distribution_account,
        )
    else:
        builder.append_payment_op(
            destination=transaction.stellar_account,
            asset_code=transaction.asset.code,
            asset_issuer=transaction.asset.issuer,
            amount=str(payment_amount),
            source=transaction.asset.distribution_account,
        )
    if memo:
        builder.add_memo(memo)
    return builder.build()


def get_balance_id(response):
    """
    Pulls claimable balance ID from horizon responses.

    When called we decode and read the result_xdr from the horizon response.
    If any of the operations is a createClaimableBalanceResult we
    decode the Base64 representation of the balanceID xdr.
    After the fact we encode the result to hex.

    The hex representation of the balanceID is important because its the
    representation required to query and claim claimableBalances.

    :param
        response: the response from horizon

    :return:
        hex representation of the balanceID
        or
        None (if no createClaimableBalanceResult operation is found)
    """
    result_xdr = response["result_xdr"]
    tr_xdr = TransactionResult.from_xdr(result_xdr)
    for tr in tr_xdr.result.results:
        if hasattr(tr.tr, "createClaimableBalanceResult"):
            cbr_xdr = base64.b64decode(
                tr.tr.createClaimableBalanceResult.balanceID.to_xdr()
            )
            return cbr_xdr.hex()
    return None


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


def make_memo(memo: str, memo_type: str) -> Optional[Union[TextMemo, HashMemo, IdMemo]]:
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
