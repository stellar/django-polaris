from typing import Dict, Optional
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from polaris.utils import getLogger

from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from rest_framework.parsers import JSONParser

from polaris.locale.utils import _is_supported_language, activate_lang_for_request
from polaris.sep10.utils import validate_sep10_token
from polaris.models import Transaction, Asset
from polaris.integrations import registered_sep31_receiver_integration
from polaris.sep31.serializers import SEP31TransactionSerializer
from polaris.utils import (
    render_error_response,
    create_transaction_id,
    memo_hex_to_base64,
    validate_patch_request_fields,
)


logger = getLogger(__name__)


class TransactionsAPIView(APIView):
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    @staticmethod
    @validate_sep10_token()
    def get(
        account: str,
        _client_domain: Optional[str],
        _request: Request,
        transaction_id: str = None,
    ) -> Response:
        if not transaction_id:
            return render_error_response(
                _("GET requests must include a transaction ID in the URI"),
            )
        elif not registered_sep31_receiver_integration.valid_sending_anchor(account):
            return render_error_response(_("invalid sending account."), status_code=403)
        elif not transaction_id:
            return render_error_response(_("missing 'id' in URI"))
        try:
            t = Transaction.objects.filter(
                id=transaction_id, stellar_account=account,
            ).first()
        except ValidationError:  # bad id parameter
            return render_error_response(_("transaction not found"), status_code=404)
        if not t:
            return render_error_response(_("transaction not found"), status_code=404)
        return Response({"transaction": SEP31TransactionSerializer(t).data})

    @staticmethod
    @validate_sep10_token()
    def patch(
        account: str,
        _client_domain: Optional[str],
        request: Request,
        transaction_id: str = None,
    ) -> Response:
        if not registered_sep31_receiver_integration.valid_sending_anchor(account):
            return render_error_response(_("invalid sending account"), status_code=403)
        try:
            transaction = Transaction.objects.filter(
                id=transaction_id,
                stellar_account=account,
                protocol=Transaction.PROTOCOL.sep31,
            ).get()
        except (ValidationError, ObjectDoesNotExist):
            return render_error_response(_("transaction not found"), status_code=404)
        if transaction.status != Transaction.STATUS.pending_transaction_info_update:
            return render_error_response(_("update not required"))
        try:
            validate_patch_request_fields(request.data.get("fields"), transaction)
            registered_sep31_receiver_integration.process_patch_request(
                params=request.data.get("fields"), transaction=transaction,
            )
        except ValueError as e:
            return render_error_response(str(e))
        except RuntimeError as e:
            logger.exception(str(e))
            return render_error_response(
                _("unable to process request"), status_code=500
            )
        transaction.status = Transaction.STATUS.pending_receiver
        transaction.required_info_updates = None
        transaction.required_info_message = None
        transaction.save()
        return Response(status=200)

    @staticmethod
    @validate_sep10_token()
    def post(
        account: str, client_domain: Optional[str], request: Request, **kwargs,
    ):
        if kwargs:
            return render_error_response(
                _("POST requests should not specify subresources in the URI")
            )
        elif not registered_sep31_receiver_integration.valid_sending_anchor(account):
            return render_error_response("invalid sending account", status_code=403)

        try:
            params = validate_post_request(request)
        except ValueError as e:
            return render_error_response(str(e))

        # validate fields separately since error responses need different format
        missing_fields = validate_post_fields(
            params.get("fields"), params.get("asset"), params.get("lang")
        )
        if missing_fields:
            return Response(
                {"error": "transaction_info_needed", "fields": missing_fields},
                status=400,
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
            kind=Transaction.KIND.send,
            status=Transaction.STATUS.pending_sender,
            stellar_account=account,
            asset=params["asset"],
            amount_in=params["amount"],
            memo=transaction_memo,
            memo_type=Transaction.MEMO_TYPES.hash,
            receiving_anchor_account=params["asset"].distribution_account,
            client_domain=client_domain,
        )

        error_data = registered_sep31_receiver_integration.process_post_request(
            params, transaction
        )
        try:
            response_data = process_post_response(error_data, transaction)
        except ValueError as e:
            logger.error(str(e))
            return render_error_response(
                _("unable to process the request"), status_code=500
            )
        else:
            transaction.save()

        return Response(response_data, status=400 if "error" in response_data else 201)


def validate_post_request(request: Request) -> Dict:
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


def validate_post_fields(
    passed_fields: Dict, asset: Asset, lang: Optional[str]
) -> Dict:
    missing_fields = defaultdict(dict)
    expected_fields = registered_sep31_receiver_integration.info(asset, lang).get(
        "fields", {}
    )
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


def process_post_response(error_data: Dict, transaction: Transaction) -> Dict:
    if not error_data:
        response_data = {
            "id": transaction.id,
            "stellar_account_id": transaction.asset.distribution_account,
            "stellar_memo": transaction.memo,
            "stellar_memo_type": transaction.memo_type,
        }
    else:
        if Transaction.objects.filter(id=transaction.id).exists():
            raise ValueError(f"transactions should not be created on bad requests")
        elif error_data["error"] == "transaction_info_needed":
            if not isinstance(error_data.get("fields"), dict):
                raise ValueError("'fields' must serialize to a JSON object")
            validate_post_fields_needed(error_data.get("fields"), transaction.asset)
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


def validate_post_fields_needed(response_fields: Dict, asset: Asset):
    expected_fields = registered_sep31_receiver_integration.info(asset).get(
        "fields", {}
    )
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
