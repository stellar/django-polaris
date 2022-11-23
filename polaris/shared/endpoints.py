import json
from decimal import Decimal, DecimalException

from django.urls import reverse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import gettext as _
from django.conf import settings as django_settings

from polaris.locale.utils import (
    activate_lang_for_request,
    validate_or_use_default_language,
)
from polaris import settings as polaris_settings
from polaris.templates import Template
from polaris.utils import render_error_response, getLogger
from polaris.models import Transaction, Asset, OffChainAsset
from polaris.integrations import registered_fee_func
from polaris.sep24.utils import verify_valid_asset_operation, get_timezone_utc_offset
from polaris.shared.serializers import TransactionSerializer
from polaris.integrations import (
    registered_deposit_integration as rdi,
    registered_withdrawal_integration as rwi,
)
from polaris.sep10.utils import SEP10Token


logger = getLogger(__name__)
SEP6_MORE_INFO_PATH = "/sep6/transaction/more_info"


def more_info(request: Request, sep6: bool = False) -> Response:
    try:
        transaction = _get_transaction_from_request(request, sep6=sep6)
    except (AttributeError, ValidationError) as exc:
        return render_error_response(str(exc), as_html=True)
    except ObjectDoesNotExist:
        return render_error_response(
            _("transaction not found"),
            status_code=status.HTTP_404_NOT_FOUND,
            as_html=True,
        )

    current_offset = get_timezone_utc_offset(
        request.session.get("timezone") or django_settings.TIME_ZONE
    )
    # persists the session, generating r.session.session_key
    #
    # this session key is passed to the rendered views and
    # used in client-side JavaScript in requests to the server
    if request.session.is_empty():
        request.session["authenticated"] = False
    else:
        request.session.modified = True
    if not request.session.session_key:
        request.session.create()
    serializer = TransactionSerializer(
        transaction, context={"request": request, "sep6": sep6}
    )
    tx_json = json.dumps({"transaction": serializer.data})
    context = {
        "tx_json": tx_json,
        "amount_in_asset": transaction.asset.asset_identification_format,
        "amount_out_asset": transaction.asset.asset_identification_format,
        "amount_in": serializer.data.get("amount_in"),
        "amount_out": serializer.data.get("amount_out"),
        "amount_fee": serializer.data.get("amount_fee"),
        "amount_in_symbol": transaction.asset.symbol,
        "amount_fee_symbol": transaction.asset.symbol,
        "amount_out_symbol": transaction.asset.symbol,
        "amount_in_significant_decimals": transaction.asset.significant_decimals,
        "amount_fee_significant_decimals": transaction.asset.significant_decimals,
        "amount_out_significant_decimals": transaction.asset.significant_decimals,
        "transaction": transaction,
        "asset": transaction.asset,
        "offchain_asset": None,
        "price": None,
        "price_inversion": None,
        "price_inversion_significant_decimals": None,
        "exchange_amount": None,
        "exchanged_amount": None,
        "current_offset": current_offset,
        "timezone_endpoint": reverse("tzinfo"),
        "session_id": request.session.session_key,
    }
    if transaction.quote:
        if "deposit" in transaction.kind:
            scheme, identifier = transaction.quote.sell_asset.split(":")
        else:
            scheme, identifier = transaction.quote.buy_asset.split(":")
        offchain_asset = OffChainAsset.objects.get(scheme=scheme, identifier=identifier)
        if "deposit" in transaction.kind:
            context.update(
                **{
                    "amount_in_asset": offchain_asset.asset_identification_format,
                    "amount_in_symbol": offchain_asset.symbol,
                    "amount_in_significant_decimals": offchain_asset.significant_decimals,
                }
            )
        else:
            context.update(
                **{
                    "amount_out_asset": offchain_asset.asset_identification_format,
                    "amount_out_symbol": offchain_asset.symbol,
                    "amount_out_significant_decimals": offchain_asset.significant_decimals,
                }
            )
        if transaction.fee_asset == offchain_asset.asset_identification_format:
            context.update(
                **{
                    "amount_fee_symbol": offchain_asset.symbol,
                    "amount_fee_significant_decimals": offchain_asset.significant_decimals,
                }
            )
        price_inversion = 1 / transaction.quote.price
        price_inversion_sd = min(
            transaction.asset.significant_decimals, offchain_asset.significant_decimals
        )
        while (
            calc_amount_out_with_price_inversion(
                transaction, price_inversion, price_inversion_sd, context
            )
            != transaction.amount_out
            and price_inversion_sd < 7
        ):
            price_inversion_sd += 1
        if (
            transaction.fee_asset == offchain_asset.asset_identification_format
            and "deposit" in transaction.kind
        ) or (
            transaction.fee_asset == transaction.asset.asset_identification_format
            and "withdrawal" in transaction.kind
        ):
            context["exchange_amount"] = transaction.amount_in - transaction.amount_fee
        else:
            context["exchanged_amount"] = round(
                transaction.amount_in * price_inversion,
                context["amount_out_significant_decimals"],
            )
        context.update(
            **{
                "offchain_asset": offchain_asset,
                "price": transaction.quote.price,
                "price_inversion": round(
                    1 / transaction.quote.price, price_inversion_sd
                ),
                "price_inversion_significant_decimals": price_inversion_sd,
            }
        )

    integration_class = rdi if "deposit" in transaction.kind else rwi
    try:
        content_from_anchor = (
            integration_class.content_for_template(
                request=request,
                template=Template.MORE_INFO,
                transaction=transaction,
            )
            or {}
        )
    except NotImplementedError:
        content_from_anchor = {}

    context.update(content_from_anchor)

    # more_info.html will update the 'callback' parameter value to 'success' after
    # making the callback. If the page is then reloaded, the callback is not included
    # in the rendering context, ensuring only one successful callback request is made.
    callback = request.GET.get("callback")
    if callback and callback != "success":
        context["callback"] = callback

    return Response(
        context,
        template_name=content_from_anchor.get(
            "template_name", "polaris/more_info.html"
        ),
    )


def calc_amount_out_with_price_inversion(
    transaction: Transaction,
    price_inversion: Decimal,
    price_inversion_significant_decimals: int,
    context: dict,
):
    if (
        transaction.fee_asset == transaction.asset.asset_identification_format
        and "deposit" not in transaction.kind
    ) or (
        transaction.fee_asset != transaction.asset.asset_identification_format
        and "deposit" in transaction.kind
    ):
        return round(
            round(price_inversion, price_inversion_significant_decimals)
            * (transaction.amount_in - transaction.amount_fee),
            context["amount_out_significant_decimals"],
        )
    else:
        return round(
            round(price_inversion, price_inversion_significant_decimals)
            * transaction.amount_in
            - transaction.amount_fee,
            context["amount_out_significant_decimals"],
        )


def transactions_request(
    request: Request,
    token: SEP10Token,
    sep6: bool = False,
) -> Response:
    activate_lang_for_request(validate_or_use_default_language(request.GET.get("lang")))

    try:
        limit = _validate_limit(request.GET.get("limit"))
    except ValueError:
        return render_error_response(
            "invalid limit", status_code=status.HTTP_400_BAD_REQUEST
        )

    protocol_filter = {"sep6_enabled": True} if sep6 else {"sep24_enabled": True}
    if not request.GET.get("asset_code"):
        return render_error_response("asset_code is required")
    elif not Asset.objects.filter(
        code=request.GET.get("asset_code"), **protocol_filter
    ).exists():
        return render_error_response("invalid asset_code")

    translation_dict = {
        "asset_code": "asset__code",
        "no_older_than": "started_at__gte",
        "kind": "kind",
    }

    qset_filter = _compute_qset_filters(request.GET, translation_dict)
    qset_filter["stellar_account"] = token.account
    qset_filter["muxed_account"] = token.muxed_account
    qset_filter["account_memo"] = token.memo

    # Since the Transaction IDs are UUIDs, rather than in the chronological
    # order of their creation, we map the paging ID (if provided) to the
    # started_at field of a Transaction.
    paging_id = request.GET.get("paging_id")
    if paging_id:
        try:
            start_transaction = Transaction.objects.get(id=paging_id)
        except ObjectDoesNotExist:
            return render_error_response(
                "invalid paging_id", status_code=status.HTTP_400_BAD_REQUEST
            )
        qset_filter["started_at__lt"] = start_transaction.started_at

    protocol = Transaction.PROTOCOL.sep6 if sep6 else Transaction.PROTOCOL.sep24
    transactions_qset = Transaction.objects.filter(protocol=protocol, **qset_filter)
    if limit:
        transactions_qset = transactions_qset[:limit]

    serializer = TransactionSerializer(
        transactions_qset,
        many=True,
        context={"request": request, "same_asset": True, "sep6": sep6},
    )

    return Response({"transactions": serializer.data})


def transaction_request(
    request: Request,
    token: SEP10Token,
    sep6: bool = False,
) -> Response:
    activate_lang_for_request(validate_or_use_default_language(request.GET.get("lang")))
    try:
        request_transaction = _get_transaction_from_request(
            request,
            token=token,
            sep6=sep6,
        )
    except (AttributeError, ValidationError) as exc:
        return render_error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
    except ObjectDoesNotExist:
        return render_error_response(
            "transaction not found", status_code=status.HTTP_404_NOT_FOUND
        )
    serializer = TransactionSerializer(
        request_transaction,
        context={"request": request, "sep6": sep6},
    )
    return Response({"transaction": serializer.data})


def fee(request: Request, sep6: bool = False) -> Response:
    """
    Definition of the /fee endpoint, in accordance with SEP-0024.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#fee
    """
    deposit_op = polaris_settings.OPERATION_DEPOSIT
    withdrawal_op = polaris_settings.OPERATION_WITHDRAWAL

    operation = request.GET.get("operation")
    op_type = request.GET.get("type")
    asset_code = request.GET.get("asset_code")
    amount_str = request.GET.get("amount")

    # Verify that the asset code exists in our database:
    protocol_filter = {"sep6_enabled": True} if sep6 else {"sep24_enabled": True}
    asset = Asset.objects.filter(code=asset_code, **protocol_filter).first()
    if not asset_code or not asset:
        return render_error_response("invalid 'asset_code'")

    # Verify that amount is provided, and that can be parsed into a decimal:
    try:
        amount = Decimal(amount_str)
    except (DecimalException, TypeError):
        return render_error_response("invalid 'amount'")

    error_resp = None
    # Verify that the requested operation is valid:
    if operation not in (deposit_op, withdrawal_op):
        error_resp = render_error_response(
            f"'operation' should be either '{deposit_op}' or '{withdrawal_op}'"
        )
    # Verify asset is enabled and within the specified limits
    elif operation == deposit_op:
        error_resp = verify_valid_asset_operation(
            asset, amount, Transaction.KIND.deposit
        )
    elif operation == withdrawal_op:
        error_resp = verify_valid_asset_operation(
            asset, amount, Transaction.KIND.withdrawal
        )

    if error_resp:
        return error_resp

    try:
        fee_amount = registered_fee_func(
            request=request,
            fee_params={
                "operation": operation,
                "type": op_type,
                "asset_code": asset_code,
                "amount": amount,
            },
        )
    except ValueError:
        return render_error_response(
            _("unable to calculate fees for the requested asset")
        )

    return Response({"fee": fee_amount})


def _validate_limit(limit):
    if not limit:
        return limit
    limit = int(limit)
    if limit < 1:
        raise ValueError
    return limit


def _compute_qset_filters(req_params, translation_dict):
    """
    _compute_qset_filters translates the keys of req_params to the keys of translation_dict.
    If the key isn't present in filters_dict, it is discarded.
    """
    return {
        translation_dict[rp]: req_params[rp]
        for rp in filter(lambda i: i in translation_dict, req_params.keys())
    }


def _get_transaction_from_request(
    request,
    token: SEP10Token = None,
    sep6: bool = False,
):
    translation_dict = {
        "id": "id",
        "stellar_transaction_id": "stellar_transaction_id",
        "external_transaction_id": "external_transaction_id",
    }

    qset_filter = _compute_qset_filters(request.GET, translation_dict)
    if not qset_filter:
        raise AttributeError(
            _(
                "at least one of id, stellar_transaction_id, or "
                "external_transaction_id must be provided"
            )
        )

    if token:
        qset_filter["stellar_account"] = token.account
        qset_filter["muxed_account"] = token.muxed_account
        qset_filter["account_memo"] = token.memo

    protocol = Transaction.PROTOCOL.sep6 if sep6 else Transaction.PROTOCOL.sep24
    return Transaction.objects.get(protocol=protocol, **qset_filter)
