from typing import Dict
from decimal import Decimal

from django.utils.translation import gettext as _
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer

from polaris.utils import (
    render_error_response,
    Logger,
    create_transaction_id,
    memo_hex_to_base64,
)
from polaris.models import Transaction, Asset
from polaris.sep10.utils import validate_sep10_token
from polaris.integrations import registered_send_integration
from polaris.sep31.info import validate_integration

logger = Logger(__name__)


@api_view(["POST"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token("sep31")
def send(account: str, request: Request) -> Response:
    if not registered_send_integration.valid_sending_anchor(account):
        return render_error_response("Invalid sending account.", status_code=401)
    try:
        params = validate_send_request(request)
    except ValueError as e:
        return render_error_response(str(e))

    asset = Asset.objects.first(code=params.get("asset_code"))
    if not asset:
        return render_error_response(_("invalid asset_code and asset_issuer"))
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
        asset=asset,
        amount_in=Decimal(params.get("amount")),
        from_address=account,
        send_memo=transaction_memo,
        send_memo_type=Transaction.MEMO_TYPES.hash,
    )

    # The anchor should validate and process the parameters from the request, calculate the
    # fee for the transaction, and return the data to be included in the response.
    #
    # If the anchor returns an error response, the transaction will not be created.
    #
    # If the anchor returns a success response, the anchor also must link the transaction
    # passed to the user specified by params["receiver"]. They can do this by assigning
    # Transaction.to_address or using their own data model.
    response_data = registered_send_integration.process_send_request(
        params, transaction
    )
    try:
        validate_send_response(response_data, transaction)
    except ValueError as e:
        logger.error(str(e))
        return render_error_response(
            _("unable to process the request"), status_code=500
        )

    return Response(response_data, status=400 if "error" in response_data else 200)


def validate_send_request(request: Request) -> Dict:
    pass


def validate_send_response(response_data: Dict, transaction: Transaction):
    if "error" not in response_data:
        if not Transaction.objects.first(id=transaction.id):
            transaction.save()
        response_data.update(
            id=transaction.id,
            stellar_account_id=transaction.asset.distribution_account,
            stellar_memo=transaction.send_memo,
            stellar_memo_type=transaction.send_memo_type,
        )
        if ("receiver_info" in response_data and len(response_data) > 5) or (
            "receiver_info" not in response_data and len(response_data) > 4
        ):
            raise ValueError(
                "invalid response arguments returned from process_send_request()"
            )
    elif response_data["error"] == "customer_info_needed":
        validate_integration(response_data.get("fields"))
        if len(response_data) > 2:
            raise ValueError("extra fields returned in customer_info_needed response")
    elif len(response_data) > 1:
        raise ValueError("extra fields returned in generic error response")
