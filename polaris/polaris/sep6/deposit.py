from decimal import Decimal, DecimalException
from typing import Dict, Tuple, Optional

from django.utils.translation import gettext as _
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, renderer_classes, parser_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import APIException
from stellar_sdk.exceptions import MemoInvalidException

from polaris import settings
from polaris.models import Asset, Transaction
from polaris.locale.utils import validate_language, activate_lang_for_request
from polaris.utils import (
    getLogger,
    render_error_response,
    create_transaction_id,
    extract_sep9_fields,
    make_memo,
)
from polaris.shared.endpoints import SEP6_MORE_INFO_PATH
from polaris.sep6.utils import validate_403_response
from polaris.sep10.utils import validate_sep10_token
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_fee_func,
    calculate_fee,
)


logger = getLogger(__name__)


@api_view(["GET"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@validate_sep10_token()
def deposit(account: str, client_domain: Optional[str], request: Request,) -> Response:
    args = parse_request_args(request)
    if "error" in args:
        return args["error"]
    args["account"] = account

    transaction_id = create_transaction_id()
    transaction = Transaction(
        id=transaction_id,
        stellar_account=account,
        asset=args["asset"],
        kind=Transaction.KIND.deposit,
        status=Transaction.STATUS.pending_user_transfer_start,
        memo=args["memo"],
        memo_type=args["memo_type"] or Transaction.MEMO_TYPES.text,
        to_address=account,
        protocol=Transaction.PROTOCOL.sep6,
        more_info_url=request.build_absolute_uri(
            f"{SEP6_MORE_INFO_PATH}?id={transaction_id}"
        ),
        claimable_balance_supported=args["claimable_balance_supported"],
        on_change_callback=args["on_change_callback"],
        client_domain=client_domain,
    )

    try:
        integration_response = rdi.process_sep6_request(args, transaction)
    except ValueError as e:
        return render_error_response(str(e))
    except APIException as e:
        return render_error_response(str(e), status_code=e.status_code)

    try:
        response, status_code = validate_response(
            args, integration_response, transaction
        )
    except (ValueError, KeyError) as e:
        logger.error(str(e))
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    if status_code == 200:
        logger.info(f"Created deposit transaction {transaction.id}")
        transaction.save()
    elif Transaction.objects.filter(id=transaction.id).exists():
        logger.error("Do not save transaction objects for invalid SEP-6 requests")
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    return Response(response, status=status_code)


def validate_response(
    args: Dict, integration_response: Dict, transaction: Transaction
) -> Tuple[Dict, int]:
    """
    Validate /deposit response returned from integration function
    """
    if "type" in integration_response:
        return validate_403_response(integration_response, transaction), 403

    asset = args["asset"]
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
        > Asset._meta.get_field("deposit_min_amount").default
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
        < Asset._meta.get_field("deposit_max_amount").default
    ):
        response["max_amount"] = round(
            transaction.asset.deposit_max_amount, transaction.asset.significant_decimals
        )

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
            raise ValueError(
                "Invalid 'extra_info' returned from process_sep6_request()"
            )

    return response, 200


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

    memo_type = request.GET.get("memo_type")
    if memo_type and memo_type not in Transaction.MEMO_TYPES:
        return {"error": render_error_response(_("invalid 'memo_type'"))}

    try:
        make_memo(request.GET.get("memo"), memo_type)
    except (ValueError, MemoInvalidException):
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
    if amount:
        try:
            amount = round(Decimal(amount), asset.significant_decimals)
        except DecimalException:
            return {"error": render_error_response(_("invalid 'amount'"))}
        min_amount = round(asset.deposit_min_amount, asset.significant_decimals)
        max_amount = round(asset.deposit_max_amount, asset.significant_decimals)
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
        "lang": lang,
        "type": request.GET.get("type"),
        "claimable_balance_supported": claimable_balance_supported,
        "on_change_callback": on_change_callback,
        "country_code": request.GET.get("country_code"),
        "amount": amount,
        **extract_sep9_fields(request.GET),
    }

    # add remaining extra params, it's on the anchor to validate them
    for param, value in request.GET.items():
        if param not in args:
            args[param] = value

    return args
