from decimal import Decimal, DecimalException
from typing import Dict, Tuple

from django.utils.translation import gettext as _
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, renderer_classes, parser_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import APIException
from stellar_sdk.strkey import StrKey
from stellar_sdk import Keypair
from stellar_sdk.exceptions import (
    MemoInvalidException,
    Ed25519PublicKeyInvalidError,
    MuxedEd25519AccountInvalidError
)

from polaris import settings
from polaris.models import Asset, Transaction, Quote
from polaris.locale.utils import (
    activate_lang_for_request,
    validate_or_use_default_language,
)
from polaris.utils import (
    getLogger,
    render_error_response,
    create_transaction_id,
    extract_sep9_fields,
    make_memo,
    get_account_obj,
    get_quote_and_offchain_source_asset,
)
from polaris.shared.endpoints import SEP6_MORE_INFO_PATH
from polaris.sep6.utils import validate_403_response
from polaris.sep10.utils import validate_sep10_token
from polaris.sep10.token import SEP10Token
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_custody_integration as rci,
    registered_fee_func,
    calculate_fee,
)

logger = getLogger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@validate_sep10_token()
def deposit(token: SEP10Token, request: Request) -> Response:
    return deposit_logic(token=token, request=request, exchange=False)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@validate_sep10_token()
def deposit_exchange(token: SEP10Token, request: Request) -> Response:
    return deposit_logic(token=token, request=request, exchange=True)


def deposit_logic(token: SEP10Token, request: Request, exchange: bool) -> Response:
    args = parse_request_args(token, request, exchange)
    if "error" in args:
        return args["error"]

    transaction_id = create_transaction_id()
    transaction = Transaction(
        id=transaction_id,
        stellar_account=token.account,
        muxed_account=token.muxed_account,
        account_memo=token.memo,
        asset=args["destination_asset" if exchange else "asset"],
        amount_in=args.get("amount"),
        amount_expected=args.get("amount"),
        quote=args["quote"],
        kind=getattr(Transaction.KIND, "deposit-exchange" if exchange else "deposit"),
        status=Transaction.STATUS.pending_user_transfer_start,
        memo=args["memo"],
        memo_type=args["memo_type"] or Transaction.MEMO_TYPES.text,
        to_address=args["account"],
        protocol=Transaction.PROTOCOL.sep6,
        more_info_url=request.build_absolute_uri(
            f"{SEP6_MORE_INFO_PATH}?id={transaction_id}"
        ),
        claimable_balance_supported=args["claimable_balance_supported"],
        on_change_callback=args["on_change_callback"],
        client_domain=token.client_domain,
    )

    try:
        integration_response = rdi.process_sep6_request(
            token=token, request=request, params=args, transaction=transaction
        )
    except ValueError as e:
        return render_error_response(str(e))
    except APIException as e:
        return render_error_response(str(e), status_code=e.status_code)

    try:
        response, status_code = validate_response(
            token, request, args, integration_response, transaction, exchange
        )
    except (ValueError, KeyError) as e:
        logger.error(str(e))
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    if status_code == 200:
        logger.info(f"Created deposit transaction {transaction.id}")
        if transaction.quote:
            transaction.quote.save()
        transaction.save()
    elif Transaction.objects.filter(id=transaction.id).exists():
        logger.error("Do not save transaction objects for invalid SEP-6 requests")
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    return Response(response, status=status_code)


def validate_response(
    token: SEP10Token,
    request: Request,
    args: Dict,
    integration_response: Dict,
    transaction: Transaction,
    exchange: bool,
) -> Tuple[Dict, int]:
    """
    Validate /deposit response returned from integration function
    """
    if "type" in integration_response:
        return (
            validate_403_response(token, request, integration_response, transaction),
            403,
        )

    asset = args["destination_asset" if exchange else "asset"]
    if not (
        "how" in integration_response and isinstance(integration_response["how"], str)
    ):
        raise ValueError("Invalid 'how' returned from process_sep6_request()")
    response = {
        "how": integration_response["how"],
        "id": transaction.id,
    }
    if "min_amount" in integration_response:
        if type(integration_response["min_amount"]) not in [Decimal, int, float]:
            raise ValueError(
                "Invalid 'min_amount' type returned from process_sep6_request()"
            )
        elif integration_response["min_amount"] < 0:
            raise ValueError(
                "Invalid 'min_amount' returned from process_sep6_request()"
            )
        response["min_amount"] = integration_response["min_amount"]
    elif (
        transaction.asset.deposit_min_amount
        > getattr(Asset, "_meta").get_field("deposit_min_amount").default
    ):
        response["min_amount"] = round(
            transaction.asset.deposit_min_amount, transaction.asset.significant_decimals
        )
    if "max_amount" in integration_response:
        if type(integration_response["max_amount"]) not in [Decimal, int, float]:
            raise ValueError(
                "Invalid 'max_amount' type returned from process_sep6_request()"
            )
        elif integration_response["max_amount"] < 0:
            raise ValueError(
                "Invalid 'max_amount' returned from process_sep6_request()"
            )
        response["max_amount"] = integration_response["max_amount"]
    elif (
        transaction.asset.deposit_max_amount
        < getattr(Asset, "_meta").get_field("deposit_max_amount").default
    ):
        response["max_amount"] = round(
            transaction.asset.deposit_max_amount, transaction.asset.significant_decimals
        )

    if calculate_fee == registered_fee_func and not exchange:
        # return the fixed and percentage fee rates if the registered fee function
        # has not been implemented AND the request was not for the `/deposit-exchange`
        # endpoint.
        if asset.deposit_fee_fixed is not None:
            response["fee_fixed"] = round(
                asset.deposit_fee_fixed, asset.significant_decimals
            )
        if asset.deposit_fee_percent is not None:
            response["fee_percent"] = round(
                asset.deposit_fee_percent, asset.significant_decimals
            )

    if "extra_info" in integration_response:
        response["extra_info"] = integration_response["extra_info"]
        if not isinstance(response["extra_info"], dict):
            raise ValueError(
                "Invalid 'extra_info' returned from process_sep6_request()"
            )

    return response, 200


def parse_request_args(
    token: SEP10Token, request: Request, exchange: bool = False
) -> Dict:
    lang = validate_or_use_default_language(request.GET.get("lang"))
    activate_lang_for_request(lang)

    account = request.GET.get("account")
    if account.startswith("M"):
        try:
            StrKey.decode_muxed_account(account)
        except (MuxedEd25519AccountInvalidError, ValueError):
            return {"error": render_error_response(_("invalid 'account'"))}
    else:
        try:
            Keypair.from_public_key(account)
        except Ed25519PublicKeyInvalidError:
            return {"error": render_error_response(_("invalid 'account'"))}

    if exchange:
        if not request.GET.get("destination_asset"):
            return {
                "error": render_error_response(_("'destination_asset' is required"))
            }
        parts = request.GET.get("destination_asset").split(":")
        if len(parts) != 3 or parts[0] != "stellar":
            return {"error": render_error_response(_("invalid 'destination_asset'"))}
        asset_query_args = {"code": parts[1], "issuer": parts[2]}
    else:
        asset_query_args = {"code": request.GET.get("asset_code")}

    asset = Asset.objects.filter(
        sep6_enabled=True, deposit_enabled=True, **asset_query_args
    ).first()
    if not asset:
        return {
            "error": render_error_response(
                _("asset not found using 'asset_code' or 'destination_asset'")
            )
        }

    memo_type = request.GET.get("memo_type")
    if memo_type and memo_type not in Transaction.MEMO_TYPES:
        return {"error": render_error_response(_("invalid 'memo_type'"))}

    try:
        make_memo(request.GET.get("memo"), memo_type)
    except (ValueError, TypeError, MemoInvalidException):
        return {"error": render_error_response(_("invalid 'memo' for 'memo_type'"))}

    claimable_balance_supported = request.GET.get(
        "claimable_balance_supported", ""
    ).lower()
    if claimable_balance_supported not in ["", "true", "false"]:
        return {
            "error": render_error_response(
                _("'claimable_balance_supported' value must be 'true' or 'false'")
            )
        }
    else:
        claimable_balance_supported = claimable_balance_supported == "true"

    on_change_callback = request.GET.get("on_change_callback")
    if on_change_callback and on_change_callback.lower() != "postmessage":
        schemes = ["https"] if not settings.LOCAL_MODE else ["https", "http"]
        try:
            URLValidator(schemes=schemes)(on_change_callback)
        except ValidationError:
            return {"error": render_error_response(_("invalid callback URL provided"))}
        if any(
            domain in on_change_callback
            for domain in settings.CALLBACK_REQUEST_DOMAIN_DENYLIST
        ):
            on_change_callback = None

    amount = request.GET.get("amount")
    if exchange and not amount:
        return {"error": render_error_response(_("'amount' is required"))}
    if amount:
        try:
            amount = Decimal(amount)
        except DecimalException:
            return {"error": render_error_response(_("invalid 'amount'"))}
        if not exchange:
            # Polaris cannot validate the amounts of the off-chain asset, because the minumum and
            # maximum limits saved to the database are for amounts of the Stellar asset. So, we
            # only perform this validation if exchange=False.
            amount = round(amount, asset.significant_decimals)
            min_amount = round(asset.deposit_min_amount, asset.significant_decimals)
            max_amount = round(asset.deposit_max_amount, asset.significant_decimals)
            if not (min_amount <= amount <= max_amount):
                return {
                    "error": render_error_response(
                        _("'amount' must be within [%s, %s]") % (min_amount, max_amount)
                    )
                }

    try:
        quote, source_asset = get_quote_and_offchain_source_asset(
            token=token,
            quote_id=request.GET.get("quote_id"),
            source_asset_str=request.GET.get("source_asset"),
            asset=asset,
            amount=amount,
        )
    except ValueError as e:
        return {"error": render_error_response(str(e))}

    if (
        quote
        and quote.type == Quote.TYPE.firm
        and Transaction.objects.filter(quote=quote).exists()
    ):
        return {
            "error": render_error_response(
                _("quote has already been used in a transaction")
            )
        }

    if not rci.account_creation_supported:
        if account.startswith("M"):
            stellar_account = StrKey.decode_muxed_account(account).ed25519
        else:
            stellar_account = account
        try:
            get_account_obj(Keypair.from_public_key(stellar_account))
        except RuntimeError:
            return {
                "error": render_error_response(
                    _("public key 'account' must be a funded Stellar account")
                )
            }

    args = {
        "account": request.GET.get("account"),
        "destination_asset" if exchange else "asset": asset,
        "memo_type": memo_type,
        "memo": request.GET.get("memo"),
        "lang": lang,
        "type": request.GET.get("type"),
        "claimable_balance_supported": claimable_balance_supported,
        "on_change_callback": on_change_callback,
        "country_code": request.GET.get("country_code"),
        "amount": amount,
        "quote": quote,
        "source_asset": source_asset,
        **extract_sep9_fields(request.GET),
    }

    # add remaining extra params, it's on the anchor to validate them
    for param, value in request.GET.items():
        if param not in args:
            args[param] = value

    return args
