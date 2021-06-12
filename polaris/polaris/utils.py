"""This module defines helpers for various endpoints."""
import json
import codecs
import uuid
from typing import Optional, Union, Tuple, Dict
from logging import getLogger as get_logger, LoggerAdapter

from django.utils.translation import gettext
from rest_framework import status
from rest_framework.response import Response
from stellar_sdk import TextMemo, IdMemo, HashMemo
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.account import Account, Thresholds
from stellar_sdk import Memo
from requests import Response as RequestsResponse, RequestException, post

from polaris import settings
from polaris.models import Transaction
from polaris.shared.serializers import TransactionSerializer


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


def is_pending_trust(transaction, json_resp):
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


def memo_str(memo: Optional[Memo]) -> Tuple[Optional[str], Optional[str]]:
    if not memo:
        return memo, None
    if isinstance(memo, IdMemo):
        return str(memo.memo_id), Transaction.MEMO_TYPES.id
    elif isinstance(memo, HashMemo):
        return memo_hex_to_base64(memo.memo_hash.hex()), Transaction.MEMO_TYPES.hash
    elif isinstance(memo, TextMemo):
        return memo.memo_text.decode(), Transaction.MEMO_TYPES.text
    else:
        raise ValueError()


def make_memo(memo: str, memo_type: str) -> Optional[Union[TextMemo, HashMemo, IdMemo]]:
    if not (memo or memo_type):
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
    "bank_branch_number",
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
    "organization.photo_proof_address",
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


def make_on_change_callback(
    transaction: Transaction, timeout: Optional[int] = None
) -> RequestsResponse:
    """
    Makes a POST request to `transaction.on_change_callback`, a URL
    provided by the client. The request will time out in
    ``settings.CALLBACK_REQUEST_TIMEOUT`` seconds if _timeout_ is not specified.

    The client is responsible for providing a publicly-accessible URL that
    responds within the timeout period. Polaris will continue processing
    `transaction` regardless of the result of this request.

    :raises: A ``requests.RequestException`` subclass or ``ValueError``
    :returns: The ``requests.Response`` object for the request
    """
    if (
        not transaction.on_change_callback
        or transaction.on_change_callback.lower() == "postmessage"
    ):
        raise ValueError("invalid or missing on_change_callback")
    if not timeout:
        timeout = settings.CALLBACK_REQUEST_TIMEOUT
    return post(
        url=transaction.on_change_callback,
        json=TransactionSerializer(transaction).data,
        timeout=timeout,
    )


def maybe_make_callback(transaction: Transaction, timeout: Optional[int] = None):
    """
    Makes the on_change_callback request if present on the transaciton and
    potentially logs an error. Use this function only if the response to the
    callback is irrelevant for your use case.
    """
    if (
        transaction.on_change_callback
        and transaction.on_change_callback.lower() != "postmessage"
    ):
        try:
            callback_resp = make_on_change_callback(transaction, timeout=timeout)
        except RequestException as e:
            logger.error(f"Callback request raised {e.__class__.__name__}: {str(e)}")
        else:
            if not callback_resp.ok:
                logger.error(f"Callback request returned {callback_resp.status_code}")


def validate_patch_request_fields(fields: Dict, transaction: Transaction):
    try:
        required_info_updates = json.loads(transaction.required_info_updates)
    except (ValueError, TypeError):
        raise RuntimeError(
            "expected json-encoded string from transaction.required_info_update"
        )
    for category, expected_fields in required_info_updates.items():
        if category not in fields:
            raise ValueError(gettext("missing %s fields") % category)
        elif not isinstance(fields[category], dict):
            raise ValueError(
                gettext("invalid type for %s, must be an object") % category
            )
        for field in expected_fields:
            if field not in fields[category]:
                raise ValueError(
                    gettext("missing %(field)s in %(category)s")
                    % {"field": field, "category": category}
                )
