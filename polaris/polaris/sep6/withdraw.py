from decimal import Decimal, DecimalException
from typing import Dict, Tuple, Optional

from django.utils.translation import gettext as _
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from stellar_sdk.exceptions import MemoInvalidException

from polaris import settings
from polaris.utils import (
    getLogger,
    render_error_response,
    create_transaction_id,
    extract_sep9_fields,
    make_memo,
    memo_hex_to_base64,
)
from polaris.sep6.utils import validate_403_response
from polaris.sep10.utils import validate_sep10_token
from polaris.shared.endpoints import SEP6_MORE_INFO_PATH
from polaris.locale.utils import validate_language, activate_lang_for_request
from polaris.models import Asset, Transaction
from polaris.integrations import (
    registered_withdrawal_integration as rwi,
    registered_fee_func,
    calculate_fee,
)

logger = getLogger(__name__)


@api_view(["GET"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token()
def withdraw(account: str, client_domain: Optional[str], request: Request,) -> Response:
    args = parse_request_args(request)
    if "error" in args:
        return args["error"]
    args["account"] = account

    transaction_id = create_transaction_id()
    transaction_id_hex = transaction_id.hex
    padded_hex_memo = "0" * (64 - len(transaction_id_hex)) + transaction_id_hex
    transaction_memo = memo_hex_to_base64(padded_hex_memo)
    transaction = Transaction(
        id=transaction_id,
        stellar_account=account,
        asset=args["asset"],
        kind=Transaction.KIND.withdrawal,
        status=Transaction.STATUS.pending_user_transfer_start,
        receiving_anchor_account=args["asset"].distribution_account,
        memo=transaction_memo,
        memo_type=Transaction.MEMO_TYPES.hash,
        protocol=Transaction.PROTOCOL.sep6,
        more_info_url=request.build_absolute_uri(
            f"{SEP6_MORE_INFO_PATH}?id={transaction_id}"
        ),
        on_change_callback=args["on_change_callback"],
        client_domain=client_domain,
    )

    # All request arguments are validated in parse_request_args()
    # except 'type', 'dest', and 'dest_extra'. Since Polaris doesn't know
    # which argument was invalid, the anchor is responsible for raising
    # an exception with a translated message.
    try:
        integration_response = rwi.process_sep6_request(args, transaction)
    except ValueError as e:
        return render_error_response(str(e))
    try:
        response, status_code = validate_response(
            args, integration_response, transaction
        )
    except ValueError as e:
        logger.error(str(e))
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    if status_code == 200:
        response["memo"] = transaction.memo
        response["memo_type"] = transaction.memo_type
        logger.info(f"Created withdraw transaction {transaction.id}")
        transaction.save()
    elif Transaction.objects.filter(id=transaction.id).exists():
        logger.error("Do not save transaction objects for invalid SEP-6 requests")
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    return Response(response, status=status_code)


def parse_request_args(request: Request) -> Dict:
    asset = Asset.objects.filter(
        code=request.GET.get("asset_code"), sep6_enabled=True, withdrawal_enabled=True
    ).first()
    if not asset:
        return {"error": render_error_response(_("invalid 'asset_code'"))}

    lang = request.GET.get("lang")
    if lang:
        err_resp = validate_language(lang)
        if err_resp:
            return {"error": err_resp}
        activate_lang_for_request(lang)

    memo_type = request.GET.get("memo_type")
    if memo_type and memo_type not in Transaction.MEMO_TYPES:
        return {"error": render_error_response(_("invalid 'memo_type'"))}

    try:
        make_memo(request.GET.get("memo"), memo_type)
    except (ValueError, MemoInvalidException):
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

    args = {
        "asset": asset,
        "memo_type": memo_type,
        "memo": request.GET.get("memo"),
        "lang": request.GET.get("lang"),
        "type": request.GET.get("type"),
        "dest": request.GET.get("dest"),
        "dest_extra": request.GET.get("dest_extra"),
        "on_change_callback": on_change_callback,
        "amount": amount,
        "country_code": request.GET.get("country_code"),
        **extract_sep9_fields(request.GET),
    }

    # add remaining extra params, it's on the anchor to validate them
    for param, value in request.GET.items():
        if param not in args:
            args[param] = value

    return args


def validate_response(
    args: Dict, integration_response: Dict, transaction: Transaction
) -> Tuple[Dict, int]:
    if "type" in integration_response:
        return validate_403_response(integration_response, transaction), 403

    asset = args["asset"]
    response = {
        "account_id": asset.distribution_account,
        "id": transaction.id,
    }
    if "min_amount" in integration_response:
        response["min_amount"] = integration_response["min_amount"]
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
        > Asset._meta.get_field("withdrawal_min_amount").default
    ):
        response["min_amount"] = round(
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
        response["max_amount"] = integration_response["max_amount"]
    elif (
        transaction.asset.withdrawal_max_amount
        < Asset._meta.get_field("withdrawal_max_amount").default
    ):
        response["max_amount"] = round(
            transaction.asset.withdrawal_max_amount,
            transaction.asset.significant_decimals,
        )

    if calculate_fee == registered_fee_func:
        # Polaris user has not replaced default fee function, so fee_fixed
        # and fee_percent are still used.
        response.update(
            fee_fixed=round(asset.withdrawal_fee_fixed, asset.significant_decimals),
            fee_percent=asset.withdrawal_fee_percent,
        )

    if "extra_info" in integration_response:
        if not isinstance(integration_response["extra_info"], dict):
            raise ValueError("invalid 'extra_info' returned from integration")
        response["extra_info"] = integration_response["extra_info"]

    return response, 200
