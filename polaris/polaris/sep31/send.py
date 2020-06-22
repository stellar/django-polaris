from typing import Dict, Optional
from decimal import Decimal, InvalidOperation
from collections import defaultdict

from django.utils.translation import gettext as _
from django.core.validators import URLValidator, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer

from polaris.utils import (
    SEP_9_FIELDS,
    render_error_response,
    Logger,
    create_transaction_id,
    memo_hex_to_base64,
)
from polaris.locale.utils import _is_supported_language, activate_lang_for_request
from polaris.models import Transaction, Asset
from polaris.sep10.utils import validate_sep10_token
from polaris.integrations import registered_send_integration
from polaris.sep31.info import validate_info_fields

logger = Logger(__name__)


@api_view(["POST"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token("sep31")
def send(account: str, request: Request) -> Response:
    print(request.data)
    if not registered_send_integration.valid_sending_anchor(account):
        return render_error_response("invalid sending account", status_code=401)

    try:
        params = validate_send_request(request)
    except ValueError as e:
        return render_error_response(str(e))

    # validate fields separately since error responses need different format
    missing_fields = validate_fields(
        params.get("fields"), params.get("asset"), params.get("lang")
    )
    if missing_fields:
        return Response({"error": "customer_info_needed", "fields": missing_fields})

    transaction_id = create_transaction_id()
    # create memo
    transaction_id_hex = transaction_id.hex
    padded_hex_memo = "0" * (64 - len(transaction_id_hex)) + transaction_id_hex
    transaction_memo = memo_hex_to_base64(padded_hex_memo)
    # create transaction object without saving to the DB
    transaction = Transaction(
        id=transaction_id,
        protocol=Transaction.PROTOCOL.sep31,
        kind="send",
        status=Transaction.STATUS.pending_sender,
        stellar_account=account,
        asset=params["asset"],
        amount_in=params["amount"],
        send_memo=transaction_memo,
        send_memo_type=Transaction.MEMO_TYPES.hash,
        send_anchor_account=params["asset"].distribution_account,
        send_callback_url=params.get("callback"),
    )

    # The anchor should validate and process the parameters from the request and return
    # the data to be included in the response.
    #
    # If the anchor returns an error response, the transaction will not be created.
    #
    # If the anchor returns a success response, the anchor also must link the transaction
    # passed to the user specified by params["receiver"] using their own data model.
    response_data = registered_send_integration.process_send_request(
        params, transaction.id
    )
    try:
        response_data = process_send_response(response_data, transaction)
    except ValueError as e:
        logger.error(str(e))
        return render_error_response(
            _("unable to process the request"), status_code=500
        )
    else:
        transaction.save()

    return Response(response_data, status=400 if "error" in response_data else 200)


def validate_send_request(request: Request) -> Dict:
    asset_args = {"code": request.data.get("asset_code")}
    if request.data.get("asset_issuer"):
        asset_args["issuer"] = request.data.get("asset_issuer")
    asset = Asset.objects.filter(**asset_args).first()
    if not (asset and asset.sep31_enabled):
        raise ValueError(_("invalid 'asset_code' and 'asset_issuer'"))
    try:
        amount = round(Decimal(request.data.get("amount")), asset.significant_decimals)
    except InvalidOperation:
        raise ValueError(_("invalid 'amount'"))
    if asset.send_min_amount > amount or amount > asset.send_max_amount:
        raise ValueError(_("invalid 'amount'"))
    lang = request.data.get("lang")
    if lang:
        if not _is_supported_language(lang):
            raise ValueError("unsupported 'lang'")
        activate_lang_for_request(lang)
    receiver_info = request.data.get("require_receiver_info")
    if receiver_info and not all(f in SEP_9_FIELDS for f in receiver_info):
        raise ValueError(_("unrecognized fields in 'require_receiver_info'"))
    callback = request.data.get("callback")
    if callback:
        try:
            URLValidator(["https"])(callback)
        except ValidationError:
            raise ValidationError(_("invalid 'callback'"))
    return {
        "asset": asset,
        "amount": amount,
        "lang": lang,
        "receiver_info": receiver_info,
        # fields are validated in validate_fields()
        "fields": request.data.get("fields"),
        "callback": callback,
    }


def validate_fields(passed_fields: Dict, asset: Asset, lang: Optional[str]) -> Dict:
    print(passed_fields)
    missing_fields = defaultdict(dict)
    expected_fields = registered_send_integration.info(asset, lang)
    for category, fields in expected_fields.items():
        if category not in passed_fields:
            missing_fields[category] = fields
            continue
        for field, info in fields.items():
            if info.get("optional"):
                continue
            try:
                passed_fields[category][field]
            except KeyError:
                missing_fields[category][field] = info
                continue
    return missing_fields


def process_send_response(response_data: Dict, transaction: Transaction) -> Dict:
    if not response_data or "error" not in response_data:
        new_response_data = {
            "id": transaction.id,
            "stellar_account_id": transaction.asset.distribution_account,
            "stellar_memo": transaction.send_memo,
            "stellar_memo_type": transaction.send_memo_type,
        }
        if response_data:
            new_response_data["receiver_info"] = response_data

    else:
        if Transaction.objects.filter(id=transaction.id).exists():
            raise ValueError(
                f"transaction with ID {transaction.id} must be created by Polaris"
            )
        elif response_data["error"] == "customer_info_needed":
            validate_info_fields(response_data.get("fields"))
            if len(response_data) > 2:
                raise ValueError(
                    "extra fields returned in customer_info_needed response"
                )
        elif not isinstance(response_data["error"], str):
            raise ValueError("'error' must be a string")
        new_response_data = response_data

    return new_response_data
