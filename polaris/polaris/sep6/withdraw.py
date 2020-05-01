from typing import Dict, Tuple

from django.utils.translation import gettext as _
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from stellar_sdk.exceptions import MemoInvalidException

from polaris import settings
from polaris.utils import (
    Logger,
    render_error_response,
    create_transaction_id,
    extract_sep9_fields,
    memo_str,
)
from polaris.sep6.utils import validate_403_response
from polaris.sep10.utils import validate_sep10_token
from polaris.locale.utils import validate_language, activate_lang_for_request
from polaris.models import Asset, Transaction
from polaris.integrations import (
    registered_withdrawal_integration as rwi,
    registered_fee_func,
    calculate_fee,
)


logger = Logger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep6")
def withdraw(account: str, request: Request) -> Response:
    args = parse_request_args(request)
    if "error" in args:
        return args["error"]
    args["account"] = account

    # All request arguments are validated in parse_request_args()
    # except 'type', 'dest', and 'dest_extra'. Since Polaris doesn't know
    # which argument was invalid, the anchor is responsible for raising
    # an exception with a translated message.
    try:
        integration_response = rwi.process_sep6_request(args)
    except ValueError as e:
        return render_error_response(str(e))
    try:
        response, status_code = validate_response(args, integration_response)
    except ValueError:
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    if status_code == 200:
        transaction_id = create_transaction_id()
        Transaction.objects.create(
            id=transaction_id,
            stellar_account=account,
            asset=args["asset"],
            kind=Transaction.KIND.withdrawal,
            status=Transaction.STATUS.pending_user_transfer_start,
            withdraw_anchor_account=args["asset"].distribution_account,
            withdraw_memo=args["memo"],
            withdraw_memo_type=args["memo_type"] or Transaction.MEMO_TYPES.text,
            protocol=Transaction.PROTOCOL.sep6,
        )
        logger.info(f"Created withdraw transaction {transaction_id}")

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
        memo = memo_str(request.GET.get("memo"), memo_type)
    except (ValueError, MemoInvalidException):
        return {"error": render_error_response(_("invalid 'memo' for 'memo_type'"))}

    if not request.GET.get("type"):
        return {"error": render_error_response(_("'type' is required"))}
    if not request.GET.get("dest"):
        return {"error": render_error_response(_("'dest' is required"))}

    return {
        "asset": asset,
        "memo_type": memo_type,
        "memo": memo,
        "lang": request.GET.get("lang"),
        "type": request.GET.get("type"),
        "dest": request.GET.get("dest"),
        "dest_extra": request.GET.get("dest_extra"),
        **extract_sep9_fields(request.GET),
    }


def validate_response(args: Dict, integration_response: Dict) -> Tuple[Dict, int]:
    account = args["account"]
    asset = args["asset"]
    if "type" in integration_response:
        return validate_403_response(account, integration_response), 403

    response = {
        "account_id": asset.distribution_account,
        "min_amount": round(asset.withdrawal_min_amount, asset.significant_decimals),
        "max_amount": round(asset.withdrawal_max_amount, asset.significant_decimals),
    }

    if calculate_fee == registered_fee_func:
        # Polaris user has not replaced default fee function, so fee_fixed
        # and fee_percent are still used.
        response.update(
            fee_fixed=round(asset.withdrawal_fee_fixed, asset.significant_decimals),
            fee_percent=asset.withdrawal_fee_percent,
        )

    if "extra_info" in integration_response:
        if not isinstance(integration_response["extra_info"], dict):
            logger.info("invalid 'extra_info' returned from integration")
            raise ValueError()
        response["extra_info"] = integration_response["extra_info"]

    if args["memo_type"]:
        response["memo_type"] = args["memo_type"]
        response["memo"] = args["memo"]

    return response, 200
