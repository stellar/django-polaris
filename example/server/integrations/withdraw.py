from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Dict, List

from django import forms
from django.utils.translation import gettext as _
from rest_framework.request import Request

from polaris.integrations import WithdrawalIntegration, calculate_fee
from polaris.models import Transaction, Asset, Quote, OffChainAsset
from polaris.sep10.token import SEP10Token
from polaris.templates import Template
from polaris.utils import getLogger
from polaris import settings
from .mock_exchange import get_mock_firm_exchange_price

from ..forms import WithdrawForm, SelectAssetForm, ConfirmationForm
from .sep24_kyc import SEP24KYC
from ..models import PolarisStellarAccount, PolarisUserTransaction


logger = getLogger(__name__)


class MyWithdrawalIntegration(WithdrawalIntegration):
    def form_for_transaction(
        self,
        request: Request,
        transaction: Transaction,
        post_data=None,
        amount=None,
        *args,
        **kwargs,
    ) -> Optional[forms.Form]:
        kyc_form, content = SEP24KYC.check_kyc(transaction, post_data=post_data)
        if kyc_form:  # we don't have KYC info on this account (& memo)
            return kyc_form
        if content:  # the user hasn't confirmed their email (or skip confirmation)
            return None
        elif not transaction.amount_in:  # the user hasn't entered the amount to provide
            if post_data:
                return WithdrawForm(transaction, post_data)
            else:
                return WithdrawForm(transaction, initial={"amount": amount})
        if not transaction.fee_asset:  # the user hasn't selected the asset to receive
            if post_data:
                return SelectAssetForm(post_data)
            else:
                return SelectAssetForm()
        else:  # we have to check if we require the user to confirm the exchange rate
            transaction_extra = PolarisUserTransaction.objects.get(
                transaction_id=transaction.id
            )
            if (
                transaction_extra.requires_confirmation
                and not transaction_extra.confirmed
            ):
                return (
                    ConfirmationForm(post_data)
                    if post_data is not None
                    else ConfirmationForm()
                )
            else:  # we're done
                return None

    def content_for_template(
        self,
        request: Request,
        template: Template,
        form: Optional[forms.Form] = None,
        transaction: Optional[Transaction] = None,
        *args,
        **kwargs,
    ) -> Optional[Dict]:
        na, content = SEP24KYC.check_kyc(transaction)
        if content:
            return content
        elif template == Template.WITHDRAW:
            if not form:  # we're done
                return None
            elif isinstance(form, SelectAssetForm):
                return {
                    "title": _("Asset Selection"),
                    "guidance": _(
                        "Please select the asset you would like to "
                        "receive after withdrawing SRT from Stellar. "
                        "(This is just for demonstration, no off-chain "
                        "asset will be delivered after withdrawing SRT."
                    ),
                    "icon_label": _("Stellar Development Foundation"),
                }
            elif isinstance(form, WithdrawForm):
                return {
                    "title": _("Withdraw Amount"),
                    "guidance": _(
                        "Please enter the amount you would like to withdraw from Stellar."
                    ),
                    "icon_label": _("Stellar Development Foundation"),
                    "show_fee_table": False,
                }
            elif isinstance(form, ConfirmationForm):
                content = {
                    "title": _("Transaction Confirmation"),
                    "guidance": _("Review and confirm the transaction details"),
                    "icon_label": _("Stellar Development Foundation"),
                    "template_name": "transaction_confirmation.html",
                    "amount_in": transaction.amount_in,
                    "amount_fee": transaction.amount_fee,
                    "amount_out": transaction.amount_out,
                    "amount_in_symbol": transaction.asset.symbol,
                    "amount_fee_symbol": transaction.asset.symbol,
                    "amount_out_symbol": transaction.asset.symbol,
                    "amount_in_significant_decimals": transaction.asset.significant_decimals,
                    "amount_fee_significant_decimals": transaction.asset.significant_decimals,
                    "amount_out_significant_decimals": transaction.asset.significant_decimals,
                }
                if transaction.quote:
                    content.update(
                        price_significant_decimals=4,
                        price=1 / transaction.quote.price,
                        amount_out_significant_decimals=2,
                        amount_out_symbol="USD",
                        conversion_amount=round(
                            transaction.amount_in - transaction.amount_fee,
                            transaction.asset.significant_decimals,
                        ),
                    )
                return content
        elif template == Template.MORE_INFO:
            content = {
                "title": _("Polaris Transaction Information"),
                "icon_label": _("Stellar Development Foundation"),
            }
            if transaction.quote:
                content.update(
                    **{
                        "price_significant_decimals": 4,
                        "conversion_amount_symbol": transaction.asset.symbol,
                        "conversion_amount": round(
                            transaction.amount_in - transaction.amount_fee,
                            transaction.asset.significant_decimals,
                        ),
                        "conversion_amount_significant_decimals": transaction.asset.significant_decimals,
                    }
                )
            return content

    def after_form_validation(
        self,
        request: Request,
        form: forms.Form,
        transaction: Transaction,
        *args,
        **kwargs,
    ):
        try:
            SEP24KYC.track_user_activity(form, transaction)
        except RuntimeError:
            # Since no polaris account exists for this transaction, KYCForm
            # will be returned from the next form_for_transaction() call
            logger.exception(
                f"KYCForm was not served first for unknown account, id: "
                f"{transaction.stellar_account}"
            )
        if isinstance(form, SelectAssetForm):
            # users will be charged fees in the units of the asset on Stellar
            transaction.fee_asset = transaction.asset.asset_identification_format
            if form.cleaned_data["asset"] == "iso4217:USD":
                scheme, identifier = form.cleaned_data["asset"].split(":")
                offchain_asset = OffChainAsset.objects.get(
                    scheme=scheme, identifier=identifier
                )
                price = round(
                    get_mock_firm_exchange_price(),
                    transaction.asset.significant_decimals,
                )
                transaction.quote = Quote.objects.create(
                    type=Quote.TYPE.firm,
                    stellar_account=transaction.stellar_account,
                    account_memo=transaction.account_memo,
                    muxed_account=transaction.muxed_account,
                    price=price,
                    sell_asset=transaction.asset.asset_identification_format,
                    buy_asset=offchain_asset.asset_identification_format,
                    sell_amount=transaction.amount_in,
                    buy_amount=round(
                        transaction.amount_in / price,
                        offchain_asset.significant_decimals,
                    ),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
                transaction.amount_out = round(
                    (transaction.amount_in - transaction.amount_fee)
                    / transaction.quote.price,
                    offchain_asset.significant_decimals,
                )
            transaction.save()
            PolarisUserTransaction.objects.filter(transaction_id=transaction.id).update(
                requires_confirmation=True
            )
        if isinstance(form, ConfirmationForm):
            PolarisUserTransaction.objects.filter(transaction_id=transaction.id).update(
                confirmed=True
            )

    def process_sep6_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Dict:
        account = (
            PolarisStellarAccount.objects.filter(
                account=token.account or params["account"],
                memo=token.memo or params["memo"],
                memo_type="id" if token.memo else params["memo_type"],
            )
            .select_related("user")
            .first()
        )
        if not account:
            return {
                "type": "non_interactive_customer_info_needed",
                "fields": [
                    "first_name",
                    "last_name",
                    "email_address",
                    "bank_number",
                    "bank_account_number",
                ],
            }
        elif not (account.user.bank_account_number and account.user.bank_number):
            return {
                "type": "non_interactive_customer_info_needed",
                "fields": ["bank_number", "bank_account_number"],
            }
        elif params["type"] != "bank_account":
            raise ValueError(_("'type' must be 'bank_account'"))
        elif not params["dest"]:
            raise ValueError(_("'dest' is required"))
        elif not params["dest_extra"]:
            raise ValueError(_("'dest_extra' is required"))
        elif not account.confirmed:
            # Here is where you would normally return something like this:
            # {
            #     "type": "customer_info_status",
            #     "status": "pending"
            # }
            # However, we're not going to block the client from completing
            # the flow since this is a reference server.
            pass

        if params.get("amount"):
            transaction.amount_in = params["amount"]
            transaction.amount_fee = calculate_fee(
                {
                    "amount": params["amount"],
                    "operation": settings.OPERATION_WITHDRAWAL,
                    "asset_code": params[
                        "asset" if "asset" in params else "source_asset"
                    ].code,
                }
            )
            if params.get("source_asset"):
                transaction.fee_asset = params[
                    "source_asset"
                ].asset_identification_format
                if transaction.quote.type == Quote.TYPE.firm:
                    transaction.amount_out = round(
                        transaction.quote.buy_amount
                        - (transaction.amount_fee / transaction.quote.price),
                        params["destination_asset"].significant_decimals,
                    )
            else:
                transaction.amount_out = round(
                    transaction.amount_in - transaction.amount_fee,
                    params["asset"].significant_decimals,
                )

        stellar_asset = params["asset" if "asset" in params else "source_asset"]
        response = {}
        if stellar_asset.withdrawal_fee_fixed:
            response["fee_fixed"] = round(
                stellar_asset.withdrawal_fee_fixed, stellar_asset.significant_decimals
            )
        if stellar_asset.withdrawal_fee_percent:
            response["fee_percent"] = stellar_asset.withdrawal_fee_percent

        PolarisUserTransaction.objects.create(
            transaction_id=transaction.id, user=account.user, account=account
        )
        return response

    def interactive_url(
        self,
        request: Request,
        transaction: Transaction,
        asset: Asset,
        amount: Optional[Decimal],
        callback: Optional[str],
        *args: List,
        **kwargs: Dict,
    ) -> Optional[str]:
        raise NotImplementedError()

    def save_sep9_fields(
        self,
        token: SEP10Token,
        request: Request,
        stellar_account: str,
        fields: Dict,
        language_code: str,
        muxed_account: Optional[str] = None,
        account_memo: Optional[str] = None,
        account_memo_type: Optional[str] = None,
        *args: List,
        **kwargs: Dict,
    ):
        raise NotImplementedError()

    def patch_transaction(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict,
    ):
        raise NotImplementedError()
