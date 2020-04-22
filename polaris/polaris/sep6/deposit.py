from typing import Dict, Tuple

from django.utils.translation import gettext as _
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer

from polaris.models import Asset, Transaction
from polaris.locale.utils import validate_language, activate_lang_for_request
from polaris.utils import render_error_response, Logger, create_transaction_id
from polaris.sep10.utils import validate_sep10_token
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_fee_func,
    calculate_fee,
)


logger = Logger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@validate_sep10_token("sep6")
def deposit(account: str, request: Request) -> Response:
    args = parse_request_args(request)
    if args["error"]:
        return args["error"]
    elif account != args["account"]:
        return render_error_response(
            _("The account specified does not match authorization token"),
            status_code=403,
        )

    bad_integration_error = render_error_response(
        _("Unable to process the request"), status_code=500
    )
    integration_response = rdi.process_sep6_request(args)
    try:
        response, status_code = validate_response(args["asset"], integration_response)
    except ValueError:
        return bad_integration_error

    if status_code == 200:
        transaction_id = create_transaction_id()
        Transaction.objects.create(
            id=transaction_id,
            stellar_account=account,
            asset=args["asset"],
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start,
            deposit_memo=args["memo"],
            deposit_memo_type=args["memo_type"],
        )
        logger.info(f"Created deposit transaction {transaction_id}")

    return Response(response, status=status_code)


def validate_response(asset: Asset, integration_response: Dict) -> Tuple[Dict, int]:
    """
    Validate /deposit response returned from integration function
    """
    statuses = ["pending", "denied"]
    types = ["customer_info_status", "non_interactive_customer_info_needed"]
    if "type" in integration_response:
        status = 403
        response = {"type": integration_response["type"]}
        if response["type"] not in types:
            logger.error("Invalid 'type' returned from process_sep6_request()")
            raise ValueError()

        elif response["type"] == types[0]:
            if integration_response.get("status") not in statuses:
                logger.error("Invalid 'status' returned from process_sep6_request()")
                raise ValueError()
            response["status"] = integration_response["status"]
            if "more_info_url" in integration_response:
                response["more_info_url"] = integration_response["more_info_url"]
            elif "eta" in integration_response:
                response["eta"] = integration_response["eta"]

        elif "fields" not in integration_response:
            logger.error(f"Missing 'fields' for {types[1]}")
            raise ValueError()

        else:
            response["fields"] = integration_response["fields"]

    else:
        status = 200
        response = {
            "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
            "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
            "how": integration_response.get("how"),
        }
        if calculate_fee == registered_fee_func:
            # Polaris user has not replaced default fee function, so fee_fixed
            # and fee_percent are still used.
            response.update(
                fee_fixed=round(asset.deposit_fee_fixed, asset.significant_decimals),
                fee_percent=asset.deposit_fee_percent,
            )
        if "extra_info" in integration_response:
            response["extra_info"] = integration_response["extra_info"]

    return response, status


def parse_request_args(request: Request) -> Dict:
    asset = Asset.objects.filter(
        code=request.GET.get("asset_code"), sep6_enabled=True, deposit_enabled=True
    ).first()
    if not asset:
        return {"error": render_error_response(_("invalid 'asset_code'"))}

    lang = request.GET.get("lang")
    if lang:
        err_resp = validate_language(lang)
        if err_resp:
            return {"error": err_resp}
        activate_lang_for_request(lang)

    account = request.GET.get("account_id")
    if not account:
        return {"error": "'account_id' not specified"}

    memo_type = request.GET.get("memo_type")
    if memo_type not in Transaction.MEMO_TYPES:
        return {"error": render_error_response(_("invalid 'memo_type'"))}

    return {
        "asset": asset,
        "account": account,
        "memo_type": memo_type,
        "memo": request.GET.get("memo"),
        "type": request.GET.get("type"),
    }
