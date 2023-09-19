from decimal import Decimal, DecimalException
from typing import Dict, Tuple

from django.utils.translation import gettext as _
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from stellar_sdk import Keypair
from stellar_sdk.strkey import StrKey
from stellar_sdk.exceptions import (
    MemoInvalidException,
    Ed25519PublicKeyInvalidError,
    MuxedEd25519AccountInvalidError
)

from polaris import settings
from polaris.utils import (
    getLogger,
    render_error_response,
    create_transaction_id,
    extract_sep9_fields,
    make_memo,
    get_quote_and_offchain_destination_asset,
    validate_account_and_memo,
)
from polaris.sep6.utils import validate_403_response
from polaris.sep10.token import SEP10Token
from polaris.sep10.utils import validate_sep10_token
from polaris.shared.endpoints import SEP6_MORE_INFO_PATH
from polaris.locale.utils import (
    activate_lang_for_request,
    validate_or_use_default_language,
)
from polaris.models import Asset, Transaction, Quote
from polaris.integrations import (
    registered_withdrawal_integration as rwi,
    registered_fee_func,
    calculate_fee,
    registered_custody_integration as rci,
)

logger = getLogger(__name__)


@api_view(["GET"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def withdraw(token: SEP10Token, request: Request) -> Response:
    return withdraw_logic(token=token, request=request, exchange=False)


@api_view(["GET"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def withdraw_exchange(token: SEP10Token, request: Request) -> Response:
    return withdraw_logic(token=token, request=request, exchange=True)


def withdraw_logic(token: SEP10Token, request: Request, exchange: bool):
    args = parse_request_args(token, request, exchange)
    if "error" in args:
        return args["error"]

    transaction_id = create_transaction_id()
    transaction = Transaction(
        id=transaction_id,
        stellar_account=token.account,
        muxed_account=token.muxed_account,
        account_memo=token.memo,
        asset=args["source_asset" if exchange else "asset"],
        amount_in=args["amount"],
        amount_expected=args["amount"],
        quote=args["quote"],
        kind=getattr(
            Transaction.KIND, "withdrawal-exchange" if exchange else "withdrawal"
        ),
        status=Transaction.STATUS.pending_user_transfer_start,
        protocol=Transaction.PROTOCOL.sep6,
        more_info_url=request.build_absolute_uri(
            f"{SEP6_MORE_INFO_PATH}?id={transaction_id}"
        ),
        on_change_callback=args["on_change_callback"],
        client_domain=token.client_domain,
        from_address=args.get("account"),
    )

    try:
        integration_response = rwi.process_sep6_request(
            token=token, request=request, params=args, transaction=transaction
        )
    except ValueError as e:
        return render_error_response(str(e))
    try:
        response_attrs, status_code = validate_response(
            token=token,
            request=request,
            args=args,
            integration_response=integration_response,
            transaction=transaction,
            exchange=exchange,
        )
    except ValueError as e:
        logger.error(str(e))
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    if status_code != 200:
        if Transaction.objects.filter(id=transaction.id).exists():
            logger.error("Do not save transaction objects for invalid SEP-6 requests")
            return render_error_response(
                _("unable to process the request"), status_code=500
            )
        return Response(response_attrs, status=status_code)

    try:
        receiving_account, memo_str, memo_type = validate_account_and_memo(
            *rci.get_receiving_account_and_memo(
                request=request, transaction=transaction
            )
        )
    except ValueError:
        logger.exception(
            "CustodyIntegration.get_receiving_account_and_memo() returned invalid values"
        )
        return render_error_response(
            _("unable to process the request"), status_code=500
        )
    transaction.receiving_anchor_account = receiving_account
    transaction.memo = memo_str
    transaction.memo_type = memo_type
    response_attrs["memo"] = transaction.memo
    response_attrs["memo_type"] = transaction.memo_type
    logger.info(f"Created withdraw transaction {transaction.id}")
    if exchange:
        transaction.quote.save()
    transaction.save()

    return Response(
        {
            "id": transaction.id,
            "account_id": transaction.receiving_anchor_account,
            **response_attrs,
        },
        status=status_code,
    )


def parse_request_args(
    token: SEP10Token, request: Request, exchange: bool = False
) -> Dict:
    lang = validate_or_use_default_language(request.GET.get("lang"))
    activate_lang_for_request(lang)

    account = request.GET.get("account")
    if account and account.startswith("M"):
        try:
            StrKey.decode_muxed_account(account)
        except (MuxedEd25519AccountInvalidError, ValueError):
            return {"error": render_error_response(_("invalid 'account'"))}
    elif account:
        try:
            Keypair.from_public_key(account)
        except Ed25519PublicKeyInvalidError:
            return {"error": render_error_response(_("invalid 'account'"))}

    if exchange:
        if not request.GET.get("source_asset"):
            return {
                "error": render_error_response(_("'destination_asset' is required"))
            }
        parts = request.GET.get("source_asset").split(":")
        if len(parts) != 3 or parts[0] != "stellar":
            return {"error": render_error_response(_("invalid 'source_asset'"))}
        asset_query_args = {"code": parts[1], "issuer": parts[2]}
    else:
        asset_query_args = {"code": request.GET.get("asset_code")}

    asset = Asset.objects.filter(
        sep6_enabled=True, withdrawal_enabled=True, **asset_query_args
    ).first()
    if not asset:
        return {
            "error": render_error_response(_("invalid 'asset_code' or 'source_asset'"))
        }

    memo_type = request.GET.get("memo_type")
    if memo_type and memo_type not in Transaction.MEMO_TYPES:
        return {"error": render_error_response(_("invalid 'memo_type'"))}

    try:
        make_memo(request.GET.get("memo"), memo_type)
    except (ValueError, TypeError, MemoInvalidException):
        return {"error": render_error_response(_("invalid 'memo' for 'memo_type'"))}

    if not request.GET.get("type"):
        return {"error": render_error_response(_("'type' is required"))}
    if not request.GET.get("dest"):
        return {"error": render_error_response(_("'dest' is required"))}

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
            amount = round(Decimal(amount), asset.significant_decimals)
        except DecimalException:
            return {"error": render_error_response(_("invalid 'amount'"))}
        min_amount = round(asset.withdrawal_min_amount, asset.significant_decimals)
        max_amount = round(asset.withdrawal_max_amount, asset.significant_decimals)
        if not (min_amount <= amount <= max_amount):
            return {
                "error": render_error_response(
                    _("'amount' must be within [%s, %s]") % (min_amount, min_amount)
                )
            }

    try:
        quote, destination_asset = get_quote_and_offchain_destination_asset(
            token=token,
            quote_id=request.GET.get("quote_id"),
            destination_asset_str=request.GET.get("destination_asset"),
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

    args = {
        "account": request.GET.get("account"),
        "source_asset" if exchange else "asset": asset,
        "memo_type": memo_type,
        "memo": request.GET.get("memo"),
        "lang": lang,
        "type": request.GET.get("type"),
        "dest": request.GET.get("dest"),
        "dest_extra": request.GET.get("dest_extra"),
        "on_change_callback": on_change_callback,
        "amount": amount,
        "country_code": request.GET.get("country_code"),
        "quote": quote,
        "destination_asset": destination_asset,
        **extract_sep9_fields(request.GET),
    }

    # add remaining extra params, it's on the anchor to validate them
    for param, value in request.GET.items():
        if param not in args:
            args[param] = value

    return args


def validate_response(
    token: SEP10Token,
    request: Request,
    args: Dict,
    integration_response: Dict,
    transaction: Transaction,
    exchange: bool = False,
) -> Tuple[Dict, int]:
    if "type" in integration_response:
        return (
            validate_403_response(token, request, integration_response, transaction),
            403,
        )

    asset = args["source_asset" if exchange else "asset"]
    response_attrs = {}
    if "min_amount" in integration_response:
        response_attrs["min_amount"] = integration_response["min_amount"]
        if type(integration_response["min_amount"]) not in [Decimal, int, float]:
            raise ValueError(
                "Invalid 'min_amount' type returned from process_sep6_request()"
            )
        elif integration_response["min_amount"] < 0:
            raise ValueError(
                "Invalid 'min_amount' returned from process_sep6_request()"
            )
    elif (
        transaction.asset.withdrawal_min_amount
        > getattr(Asset, "_meta").get_field("withdrawal_min_amount").default
    ):
        response_attrs["min_amount"] = round(
            transaction.asset.withdrawal_min_amount,
            transaction.asset.significant_decimals,
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
        response_attrs["max_amount"] = integration_response["max_amount"]
    elif (
        transaction.asset.withdrawal_max_amount
        < getattr(Asset, "_meta").get_field("withdrawal_max_amount").default
    ):
        response_attrs["max_amount"] = round(
            transaction.asset.withdrawal_max_amount,
            transaction.asset.significant_decimals,
        )

    if "fee_fixed" in integration_response or "fee_percent" in integration_response:
        if "fee_fixed" in integration_response:
            response_attrs["fee_fixed"] = integration_response["fee_fixed"]
        if "fee_percent" in integration_response:
            response_attrs["fee_percent"] = integration_response["fee_percent"]
    elif calculate_fee == registered_fee_func and not exchange:
        # return the fixed and percentage fee rates if the registered fee function
        # has not been implemented AND the request was not for the `/withdraw-exchange`
        # endpoint.
        if asset.withdrawal_fee_fixed is not None:
            response_attrs["fee_fixed"] = round(
                asset.withdrawal_fee_fixed, asset.significant_decimals
            )
        if asset.withdrawal_fee_percent is not None:
            response_attrs["fee_percent"] = round(
                asset.withdrawal_fee_percent, asset.significant_decimals
            )

    if "extra_info" in integration_response:
        if not isinstance(integration_response["extra_info"], dict):
            raise ValueError("invalid 'extra_info' returned from integration")
        response_attrs["extra_info"] = integration_response["extra_info"]

    return response_attrs, 200
