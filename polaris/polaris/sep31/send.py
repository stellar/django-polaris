from typing import Dict, Optional
from decimal import Decimal, InvalidOperation
from collections import defaultdict

from django.utils.translation import gettext as _
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

logger = Logger(__name__)


@api_view(["POST"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token("sep31")
def send(account: str, request: Request) -> Response:
    if not registered_send_integration.valid_sending_anchor(account):
        return render_error_response("invalid sending account", status_code=403)

    try:
        params = validate_send_request(request)
    except ValueError as e:
        return render_error_response(str(e))

    # validate fields separately since error responses need different format
    missing_fields = validate_fields(
        params.get("fields"), params.get("asset"), params.get("lang")
    )
    if missing_fields:
        return Response(
            {"error": "transaction_info_needed", "fields": missing_fields}, status=400
        )

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
    )

    # The anchor should validate and process the parameters from the request and return
    # the data to be included in the response.
    #
    # If the anchor returns an error response, the transaction will not be created.
    #
    # If the anchor returns a success response, the anchor also must link the transaction
    # passed to the user specified by params["receiver"] using their own data model.
    error_data = registered_send_integration.process_send_request(
        params, transaction.id
    )
    try:
        response_data = process_send_response(error_data, transaction)
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
    except (InvalidOperation, TypeError):
        raise ValueError(_("invalid 'amount'"))
    if asset.send_min_amount > amount or amount > asset.send_max_amount:
        raise ValueError(_("invalid 'amount'"))
    lang = request.data.get("lang")
    if lang:
        if not _is_supported_language(lang):
            raise ValueError("unsupported 'lang'")
        activate_lang_for_request(lang)
    if not isinstance(request.data.get("fields"), dict):
        raise ValueError(_("'fields' must serialize to a JSON object"))
    elif len(request.data["fields"]) not in [0, 1]:
        raise ValueError("'fields' should only have one key, 'transaction'")
    elif request.data["fields"] and not isinstance(
        request.data["fields"].get("transaction"), dict
    ):
        raise ValueError(_("'transaction' value in 'fields' must be a dict"))
    if not (
        type(request.data.get("sender_id")) in [str, type(None)]
        and type(request.data.get("receiver_id")) in [str, type(None)]
    ):
        raise ValueError(_("'sender_id' and 'receiver_id' values must be strings"))
    return {
        "asset": asset,
        "amount": amount,
        "lang": lang,
        # fields are validated in validate_fields()
        "sender_id": request.data.get("sender_id"),
        "receiver_id": request.data.get("receiver_id"),
        "fields": request.data.get("fields"),
    }


def validate_fields(passed_fields: Dict, asset: Asset, lang: Optional[str]) -> Dict:
    missing_fields = defaultdict(dict)
    expected_fields = registered_send_integration.info(asset, lang).get("fields", {})
    if "transaction" not in expected_fields:
        return {}
    elif "transaction" not in passed_fields:
        missing_fields["transaction"] = expected_fields["transaction"]
        return missing_fields
    for field, info in expected_fields["transaction"].items():
        if info.get("optional"):
            continue
        elif field not in passed_fields["transaction"]:
            missing_fields["transaction"][field] = info
    return dict(missing_fields)


def process_send_response(error_data: Dict, transaction: Transaction) -> Dict:
    if not error_data:
        response_data = {
            "id": transaction.id,
            "stellar_account_id": transaction.asset.distribution_account,
            "stellar_memo": transaction.send_memo,
            "stellar_memo_type": transaction.send_memo_type,
        }
    else:
        if Transaction.objects.filter(id=transaction.id).exists():
            raise ValueError(f"transactions should not be created on bad requests")
        elif error_data["error"] == "transaction_info_needed":
            if not isinstance(error_data.get("fields"), dict):
                raise ValueError("'fields' must serialize to a JSON object")
            validate_fields_needed(error_data.get("fields"), transaction.asset)
            if len(error_data) > 2:
                raise ValueError(
                    "extra fields returned in customer_info_needed response"
                )
        elif error_data["error"] == "customer_info_needed":
            if ("type" in error_data and len(error_data) > 2) or (
                "type" not in error_data and len(error_data) > 1
            ):
                raise ValueError(
                    "extra fields returned in transaction_info_needed response"
                )
            elif type(error_data.get("type")) not in [None, str]:
                raise ValueError("invalid value for 'type' key")
        elif not isinstance(error_data["error"], str):
            raise ValueError("'error' must be a string")
        response_data = error_data

    return response_data


def validate_fields_needed(response_fields: Dict, asset: Asset):
    expected_fields = registered_send_integration.info(asset).get("fields", {})
    if "transaction" not in response_fields:
        raise ValueError("unrecognized category of fields in response")
    if not isinstance(response_fields["transaction"], dict):
        raise ValueError("'transaction' value must be a dict")
    for field, value in response_fields["transaction"].items():
        if field not in expected_fields["transaction"]:
            raise ValueError(f"unrecognized field in 'transaction' object")
        elif not (
            isinstance(response_fields["transaction"][field], dict)
            and response_fields["transaction"][field].get("description")
        ):
            raise ValueError(f"field value must be a dict with a description")
