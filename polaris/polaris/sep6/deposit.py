from typing import Dict, Tuple

from django.utils.translation import gettext as _
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from stellar_sdk.keypair import Keypair
from stellar_sdk.memo import IdMemo, HashMemo, TextMemo
from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError, MemoInvalidException

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.locale.utils import validate_language, activate_lang_for_request
from polaris.utils import render_error_response, Logger, create_transaction_id
from polaris.sep6.utils import validate_403_response
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
    if "error" in args:
        return args["error"]
    args["account_id"] = account

    # All request arguments are validated in parse_request_args()
    # except 'type'. An invalid 'type' is the only reason
    # process_sep6_request() should throw an exception.
    try:
        integration_response = rdi.process_sep6_request(args)
    except ValueError:
        return render_error_response(_("invalid 'type'"))

    try:
        response, status_code = validate_response(args, integration_response)
    except (ValueError, KeyError):
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    if status_code == 200:
        transaction_id = create_transaction_id()
        Transaction.objects.create(
            id=transaction_id,
            stellar_account=account,
            asset=args["asset"],
            kind=Transaction.KIND.deposit,
            status=Transaction.STATUS.pending_user_transfer_start,
            deposit_memo=args["memo"],
            deposit_memo_type=args["memo_type"] or Transaction.MEMO_TYPES.text,
            to_address=account,
            protocol=Transaction.PROTOCOL.sep6,
        )
        logger.info(f"Created deposit transaction {transaction_id}")

    return Response(response, status=status_code)


def validate_response(args: Dict, integration_response: Dict) -> Tuple[Dict, int]:
    """
    Validate /deposit response returned from integration function
    """
    account = args["account_id"]
    asset = args["asset"]
    if "type" in integration_response:
        return validate_403_response(account, integration_response), 403

    response = {
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "how": integration_response["how"],
    }
    if not isinstance(response["how"], str):
        logger.error("Invalid 'how' returned from process_sep6_request()")
        raise ValueError()

    if calculate_fee == registered_fee_func:
        # Polaris user has not replaced default fee function, so fee_fixed
        # and fee_percent are still used.
        response.update(
            fee_fixed=round(asset.deposit_fee_fixed, asset.significant_decimals),
            fee_percent=asset.deposit_fee_percent,
        )

    if "extra_info" in integration_response:
        response["extra_info"] = integration_response["extra_info"]
        if not isinstance(response["extra_info"], dict):
            logger.error("Invalid 'extra_info' returned from process_sep6_request()")
            raise ValueError()

    return response, 200


def parse_request_args(request: Request) -> Dict:
    asset = Asset.objects.filter(
        code=request.GET.get("asset_code"), sep6_enabled=True, deposit_enabled=True
    ).first()
    if not asset:
        return {"error": render_error_response(_("invalid 'asset_code'"))}
    elif asset.code not in settings.ASSETS:
        return {
            "error": render_error_response(_("unsupported asset type: %s") % asset.code)
        }

    lang = request.GET.get("lang")
    if lang:
        err_resp = validate_language(lang)
        if err_resp:
            return {"error": err_resp}
        activate_lang_for_request(lang)

    try:
        kp = Keypair.from_public_key(request.GET.get("account_id"))
    except (ValueError, TypeError, Ed25519PublicKeyInvalidError):
        return {"error": _("invalid 'account_id'")}

    memo = None
    memo_type = request.GET.get("memo_type")
    if memo_type and memo_type not in Transaction.MEMO_TYPES:
        return {"error": render_error_response(_("invalid 'memo_type'"))}

    try:
        if memo_type == Transaction.MEMO_TYPES.id:
            memo = IdMemo(int(request.GET.get("memo"))).memo_id
        elif memo_type == Transaction.MEMO_TYPES.hash:
            memo = HashMemo(request.GET.get("memo")).memo_hash
        elif memo_type == Transaction.MEMO_TYPES.text:
            memo = TextMemo(request.GET.get("memo")).memo_text
    except MemoInvalidException:
        return {"error": _("Invalid 'memo' for 'memo_type'")}

    return {
        "asset": asset,
        "account_id": kp.public_key,
        "memo_type": memo_type,
        "memo": memo,
        "type": request.GET.get("type"),
    }
