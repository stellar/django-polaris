"""This module defines helpers for various endpoints."""
import base64
import json
import codecs
import time
from urllib.parse import urlparse
import uuid
from datetime import datetime, timezone
from logging import getLogger
from typing import Optional, Union, Tuple, Dict
from decimal import Decimal

import aiohttp
from django.utils.translation import gettext as _
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext
from rest_framework import status
from rest_framework.response import Response
from stellar_sdk import (
    TransactionBuilder,
    TransactionEnvelope,
    Asset as StellarAsset,
    Claimant,
    TextMemo,
    IdMemo,
    HashMemo,
    Keypair,
)
from stellar_sdk.exceptions import (
    NotFoundError,
    Ed25519PublicKeyInvalidError,
    MemoInvalidException,
)
from stellar_sdk.account import Account
from stellar_sdk import Memo
from requests import Response as RequestsResponse, RequestException, post
from aiohttp import ClientResponse

from polaris import settings
from polaris.models import Transaction, Asset, Quote, OffChainAsset, ExchangePair
from polaris.sep10.token import SEP10Token
from polaris.sep38.utils import asset_id_to_kwargs
from polaris.shared.serializers import TransactionSerializer


logger = getLogger(__name__)


def render_error_response(
    description: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    as_html: bool = False,
) -> Response:
    """
    Renders an error response in Django.

    Currently supports HTML or JSON responses.
    """
    resp_data = {"data": {"error": description}, "status": status_code}
    if as_html:
        resp_data["data"]["status_code"] = str(status_code)
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
    asset, amount, op_type, as_html=False
) -> Optional[Response]:
    enabled = getattr(asset, f"{op_type}_enabled")
    min_amount = getattr(asset, f"{op_type}_min_amount")
    max_amount = getattr(asset, f"{op_type}_max_amount")
    if not enabled:
        return render_error_response(
            gettext("the specified operation is not available for '%s'") % asset.code,
            as_html=as_html,
        )
    elif not (min_amount <= amount <= max_amount):
        return render_error_response(
            gettext("Asset amount must be within bounds [%(min)s, %(max)s]")
            % {
                "min": round(min_amount, asset.significant_decimals),
                "max": round(max_amount, asset.significant_decimals),
            },
            as_html=as_html,
        )


def load_account(resp):
    sequence = int(resp["sequence"])
    account = Account(account=resp["account_id"], sequence=sequence, raw_data=resp)
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


async def get_account_obj_async(kp, server):
    try:
        json_resp = await server.accounts().account_id(account_id=kp.public_key).call()
    except NotFoundError:
        raise RuntimeError(f"account {kp.public_key} does not exist")
    else:
        return load_account(json_resp), json_resp


def is_pending_trust(transaction, json_resp):
    pending_trust = True
    for balance in json_resp["balances"]:
        if balance.get("asset_type") in ["native", "liquidity_pool_shares"]:
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


def make_memo(
    memo: Optional[str], memo_type: Optional[str]
) -> Optional[Union[TextMemo, HashMemo, IdMemo]]:
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


def validate_account_and_memo(account: str, memo: str):
    if not (isinstance(account, str) and isinstance(memo, str)):
        raise ValueError("invalid public key or memo type, expected strings")
    try:
        Keypair.from_public_key(account)
    except Ed25519PublicKeyInvalidError:
        raise ValueError("invalid public key")
    try:
        IdMemo(int(memo))
    except (ValueError, MemoInvalidException):
        pass
    else:
        return account, memo, Transaction.MEMO_TYPES.id
    try:
        HashMemo(memo_base64_to_hex(memo))
    except (ValueError, MemoInvalidException):
        pass
    else:
        return account, memo, Transaction.MEMO_TYPES.hash
    try:
        TextMemo(memo)
    except MemoInvalidException:
        raise ValueError("invalid memo")
    else:
        return account, memo, Transaction.MEMO_TYPES.text


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
    "bank_account_type",
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
    "sex",
    "proof_of_income",
    "proof_of_liveness",
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

def compute_callback_signature(callback_url: str, callback_body: str) -> str:
    callback_time = int(time.time())
    sig_payload = f"{callback_time}.{urlparse(callback_url).netloc}.{callback_body}"
    signature = base64.b64encode(Keypair.from_secret(settings.SIGNING_SEED).sign(sig_payload.encode())).decode()
    return f"t={callback_time}, s={signature}"

def make_on_change_callback(
    transaction: Transaction, timeout: Optional[int] = None
) -> Optional[RequestsResponse]:
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
    callback_body = json.dumps({"transaction": TransactionSerializer(transaction).data})
    try:
        signature_header_value = compute_callback_signature(transaction.on_change_callback, callback_body)
    except ValueError:  # 
        logger.error(f"unable to parse host of transaction.on_change_callback for transaction {transaction.id}")
        return None
    headers = {
        "Signature": signature_header_value,
        "Content-Type": "application/json"
    }
    return post(
        url=transaction.on_change_callback,
        data=callback_body.encode(),
        timeout=timeout,
        headers=headers
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
            if callback_resp and not callback_resp.ok:
                logger.error(f"Callback request returned {callback_resp.status_code}")


async def make_on_change_callback_async(
    transaction: Transaction, timeout: Optional[int] = None
) -> Optional[ClientResponse]:
    if (
        not transaction.on_change_callback
        or transaction.on_change_callback.lower() == "postmessage"
    ):
        raise ValueError("invalid or missing on_change_callback")
    if not timeout:
        timeout = settings.CALLBACK_REQUEST_TIMEOUT
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    callback_body = json.dumps({"transaction": TransactionSerializer(transaction).data})
    try:
        signature_header_value = compute_callback_signature(transaction.on_change_callback, callback_body)
    except ValueError:  # 
        logger.error(f"unable to parse host of transaction.on_change_callback for transaction {transaction.id}")
        return None
    headers = {
        "Signature": signature_header_value,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession(timeout=timeout_obj) as session:
        return await session.post(
            url=transaction.on_change_callback,
            data=callback_body.encode(),
            timeout=timeout,
            headers=headers
        )


async def maybe_make_callback_async(
    transaction: Transaction, timeout: Optional[int] = None
):
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
            callback_resp = await make_on_change_callback_async(
                transaction, timeout=timeout
            )
        except RequestException as e:
            logger.error(f"Callback request raised {e.__class__.__name__}: {str(e)}")
        else:
            if callback_resp and not callback_resp.ok:
                logger.error(f"Callback request returned {callback_resp.status}")


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


def create_deposit_envelope(
    transaction, source_account, use_claimable_balance, base_fee
) -> TransactionEnvelope:
    if transaction.amount_out:
        payment_amount = transaction.amount_out
    elif transaction.quote:
        raise RuntimeError(
            f"transaction {transaction.id} uses a quote but does not have "
            "amount_out assigned"
        )
    else:
        payment_amount = round(
            Decimal(transaction.amount_in) - Decimal(transaction.amount_fee),
            transaction.asset.significant_decimals,
        )
    builder = TransactionBuilder(
        source_account=source_account,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        base_fee=base_fee,
    )
    asset = StellarAsset(code=transaction.asset.code, issuer=transaction.asset.issuer)
    if use_claimable_balance:
        claimant = Claimant(destination=transaction.to_address)
        builder.append_create_claimable_balance_op(
            claimants=[claimant],
            asset=asset,
            amount=str(payment_amount),
            source=transaction.asset.distribution_account,
        )
    else:
        builder.append_payment_op(
            destination=transaction.to_address,
            asset=asset,
            amount=str(payment_amount),
            source=transaction.asset.distribution_account,
        )
    if transaction.memo:
        builder.add_memo(make_memo(transaction.memo, transaction.memo_type))
    return builder.build()


def get_quote_and_offchain_destination_asset(
    token: SEP10Token,
    quote_id: str,
    destination_asset_str: str,
    asset: Asset,
    amount: Decimal,
) -> Tuple[Optional[Quote], Optional[OffChainAsset]]:
    quote = None
    destination_asset = None
    if quote_id:
        if "sep-38" not in settings.ACTIVE_SEPS or not asset.sep38_enabled:
            raise ValueError(_("quotes are not supported"))
        if not destination_asset_str:
            raise ValueError(
                _("'destination_asset' must be provided if 'quote_id' is provided")
            )
        try:
            quote = Quote.objects.get(
                id=quote_id,
                stellar_account=token.account,
                account_memo=token.memo,
                muxed_account=token.muxed_account,
                type=Quote.TYPE.firm,
            )
        except ObjectDoesNotExist:
            raise ValueError(_("quote not found"))
        if quote.expires_at < datetime.now(timezone.utc):
            raise ValueError(_("quote has expired"))
        if quote.sell_asset != asset.asset_identification_format:
            raise ValueError(
                _(
                    "quote 'sell_asset' does not match 'asset_code' and 'asset_issuer' parameters"
                )
            )
        if quote.buy_asset != destination_asset_str:
            raise ValueError(
                _("quote 'buy_asset' does not match 'destination_asset' parameter")
            )
        if quote.sell_amount != amount:
            raise ValueError(_("quote amount does not match 'amount' parameter"))
        try:
            destination_asset = OffChainAsset.objects.get(
                **asset_id_to_kwargs(destination_asset_str)
            )
        except (ValueError, TypeError, ObjectDoesNotExist):
            raise ValueError(_("invalid 'destination_asset'"))
    elif destination_asset_str:
        if "sep-38" not in settings.ACTIVE_SEPS or not asset.sep38_enabled:
            raise ValueError(_("quotes are not supported"))
        if not ExchangePair.objects.filter(
            sell_asset=asset.asset_identification_format,
            buy_asset=destination_asset_str,
        ).exists():
            raise ValueError(
                _("unsupported 'destination_asset' for 'asset_code' and 'asset_issuer'")
            )
        try:
            destination_asset = OffChainAsset.objects.get(
                **asset_id_to_kwargs(destination_asset_str)
            )
        except (ValueError, TypeError, ObjectDoesNotExist):
            raise ValueError(_("invalid 'destination_asset'"))
        quote = Quote(
            id=str(uuid.uuid4()),
            type=Quote.TYPE.indicative,
            stellar_account=token.account,
            account_memo=token.memo,
            muxed_account=token.muxed_account,
            sell_asset=asset.asset_identification_format,
            buy_asset=destination_asset_str,
            sell_amount=amount,
        )
    return quote, destination_asset


def get_quote_and_offchain_source_asset(
    token: SEP10Token,
    quote_id: str,
    source_asset_str: str,
    asset: Asset,
    amount: Decimal,
) -> Tuple[Optional[Quote], Optional[OffChainAsset]]:
    quote = None
    source_asset = None
    if quote_id:
        if "sep-38" not in settings.ACTIVE_SEPS or not asset.sep38_enabled:
            raise ValueError(_("quotes are not supported"))
        if not source_asset_str:
            raise ValueError(
                _("'source_asset' must be provided if 'quote_id' is provided")
            )
        try:
            quote = Quote.objects.get(
                id=quote_id,
                stellar_account=token.account,
                account_memo=token.memo,
                muxed_account=token.muxed_account,
                type=Quote.TYPE.firm,
            )
        except ObjectDoesNotExist:
            raise ValueError(_("quote not found"))
        if quote.expires_at < datetime.now(timezone.utc):
            raise ValueError(_("quote has expired"))
        if quote.buy_asset != asset.asset_identification_format:
            raise ValueError(
                _(
                    "quote 'buy_asset' does not match 'asset_code' and 'asset_issuer' parameters"
                )
            )
        if quote.sell_asset != source_asset_str:
            raise ValueError(
                _("quote 'sell_asset' does not match 'source_asset' parameter")
            )
        if quote.sell_amount != amount:
            raise ValueError(_("quote amount does not match 'amount' parameter"))
        try:
            source_asset = OffChainAsset.objects.get(
                **asset_id_to_kwargs(source_asset_str)
            )
        except (ValueError, TypeError, ObjectDoesNotExist):
            raise ValueError(_("invalid 'source_asset'"))
    elif source_asset_str:
        if "sep-38" not in settings.ACTIVE_SEPS or not asset.sep38_enabled:
            raise ValueError(_("quotes are not supported"))
        if not ExchangePair.objects.filter(
            sell_asset=source_asset_str, buy_asset=asset.asset_identification_format
        ).exists():
            raise ValueError(
                _("unsupported 'source_asset' for 'asset_code' and 'asset_issuer'")
            )
        try:
            source_asset = OffChainAsset.objects.get(
                **asset_id_to_kwargs(source_asset_str)
            )
        except (ValueError, TypeError, ObjectDoesNotExist):
            raise ValueError(_("invalid 'source_asset'"))
        quote = Quote(
            id=str(uuid.uuid4()),
            type=Quote.TYPE.indicative,
            stellar_account=token.account,
            account_memo=token.memo,
            muxed_account=token.muxed_account,
            buy_asset=asset.asset_identification_format,
            sell_asset=source_asset_str,
            sell_amount=amount,
        )
    return quote, source_asset
