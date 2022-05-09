from base64 import b64encode
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, List

import requests
from django import forms
from django.utils.translation import gettext as _
from rest_framework.request import Request
from stellar_sdk import Keypair

from polaris.integrations import DepositIntegration, TransactionForm, calculate_fee
from polaris.models import Transaction, Asset, Quote, OffChainAsset
from polaris.sep10.token import SEP10Token
from polaris.templates import Template
from polaris.utils import getLogger
from .mock_exchange import get_mock_firm_exchange_price

from .sep24_kyc import SEP24KYC
from ..forms import SelectAssetForm, OffChainAssetTransactionForm, ConfirmationForm
from ..models import PolarisStellarAccount, PolarisUserTransaction, OffChainAssetExtra

logger = getLogger(__name__)


class MyDepositIntegration(DepositIntegration):
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
        if not transaction.fee_asset:  # the user hasn't selected the asset to provide
            if post_data:
                return SelectAssetForm(post_data)
            else:
                return SelectAssetForm()
        elif not transaction.amount_in:  # the user hasn't entered the amount to provide
            if transaction.fee_asset == transaction.asset.asset_identification_format:
                if post_data:
                    return TransactionForm(transaction, post_data)
                else:
                    return TransactionForm(transaction, initial={"amount": amount})
            else:
                if post_data:
                    return OffChainAssetTransactionForm(post_data)
                else:
                    return OffChainAssetTransactionForm()
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
        na, kyc_content = SEP24KYC.check_kyc(transaction)
        if kyc_content:  # the user needs to confirm their email (or skip confirmation)
            return kyc_content
        elif template == Template.DEPOSIT:
            if not form:  # we're done
                return None
            elif isinstance(form, SelectAssetForm):
                return {
                    "title": _("Asset Selection Form"),
                    "guidance": _(
                        "Please select the asset you would like to "
                        "provide in order to fund your deposit. (This is "
                        "just for demonstration, you don't need to provide "
                        "any off-chain asset to receive SRT."
                    ),
                    "icon_label": _("Stellar Development Foundation"),
                }
            elif isinstance(form, TransactionForm) or isinstance(
                form, OffChainAssetTransactionForm
            ):
                return {
                    "title": _("Transaction Amount Form"),
                    "guidance": _("Please enter the amount you would like to provide."),
                    "icon_label": _("Stellar Development Foundation"),
                }
            elif isinstance(form, ConfirmationForm):
                return {
                    "title": _("Transaction Confirmation Page"),
                    "guidance": _("Review and confirm the transaction details"),
                    "icon_label": _("Stellar Development Foundation"),
                    "template_name": "transaction_confirmation.html",
                    "amount_in": transaction.amount_in,
                    "amount_fee": transaction.amount_fee,
                    "conversion_amount": round(
                        transaction.amount_in - transaction.amount_fee,
                        transaction.asset.significant_decimals,
                    ),
                    "amount_out": transaction.amount_out,
                    "amount_in_symbol": "USD",
                    "amount_fee_symbol": "USD",
                    "amount_out_symbol": transaction.asset.symbol,
                    "amount_in_significant_decimals": 2,
                    "amount_fee_significant_decimals": 2,
                    "amount_out_significant_decimals": transaction.asset.significant_decimals,
                    "price_significant_decimals": 4,
                    "price": 1 / transaction.quote.price,
                }
        elif template == Template.MORE_INFO:
            content = {
                "title": _("Polaris Transaction Information"),
                "icon_label": _("Stellar Development Foundation"),
                "memo": b64encode(str(hash(transaction)).encode())
                .decode()[:10]
                .upper(),
            }
            if transaction.quote:
                scheme, identifier = transaction.quote.sell_asset.split(":")
                offchain_asset = OffChainAsset.objects.get(
                    scheme=scheme, identifier=identifier
                )
                content.update(
                    **{
                        "price_significant_decimals": 4,
                        "conversion_amount_symbol": offchain_asset.symbol,
                        "conversion_amount": round(
                            transaction.amount_in - transaction.amount_fee,
                            offchain_asset.significant_decimals,
                        ),
                        "conversion_amount_significant_decimals": offchain_asset.significant_decimals,
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
            # users will be charged fees in the units of the asset provided
            # to the anchor, not in units of the asset received on Stellar
            transaction.fee_asset = form.cleaned_data["asset"]
            transaction.save()
        if isinstance(form, OffChainAssetTransactionForm):
            offchain_asset_extra = OffChainAssetExtra.objects.select_related(
                "offchain_asset"
            ).get(offchain_asset__identifier="USD")
            transaction.amount_in = round(
                form.cleaned_data["amount"],
                offchain_asset_extra.offchain_asset.significant_decimals,
            )
            transaction.amount_expected = transaction.amount_in
            transaction.amount_fee = round(
                offchain_asset_extra.fee_fixed
                + (
                    offchain_asset_extra.fee_percent
                    / Decimal(100)
                    * transaction.amount_in
                ),
                offchain_asset_extra.offchain_asset.significant_decimals,
            )
            price = round(
                get_mock_firm_exchange_price(),
                offchain_asset_extra.offchain_asset.significant_decimals,
            )
            transaction.quote = Quote.objects.create(
                type=Quote.TYPE.firm,
                stellar_account=transaction.stellar_account,
                account_memo=transaction.account_memo,
                muxed_account=transaction.muxed_account,
                price=price,
                sell_asset=offchain_asset_extra.offchain_asset.asset_identification_format,
                buy_asset=transaction.asset.asset_identification_format,
                sell_amount=transaction.amount_in,
                buy_amount=round(
                    transaction.amount_in / price,
                    transaction.asset.significant_decimals,
                ),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            transaction.amount_out = round(
                (transaction.amount_in - transaction.amount_fee)
                / transaction.quote.price,
                transaction.asset.significant_decimals,
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
            PolarisStellarAccount.objects.filter(account=params["account"], memo=None)
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
        elif not account.confirmed:
            # Here is where you would normally return something like this:
            # {
            #     "type": "customer_info_status",
            #     "status": "pending"
            # }
            # However, we're not going to block the client from completing
            # the flow since this is a reference server.
            pass

        if params.get("asset") and params.get("amount"):
            transaction.amount_in = params["amount"]
            transaction.amount_fee = calculate_fee(
                {
                    "amount": params["amount"],
                    "operation": "deposit",
                    "asset_code": params["asset"].code,
                }
            )
            transaction.amount_out = round(
                transaction.amount_in - transaction.amount_fee,
                params["asset"].significant_decimals,
            )
        elif params.get("destination_asset"):  # GET /deposit-exchange
            offchain_asset_extra = OffChainAssetExtra.objects.get(
                offchain_asset=params["source_asset"]
            )
            transaction.amount_in = params["amount"]
            transaction.fee_asset = params["source_asset"].asset_identification_format
            if transaction.quote.type == Quote.TYPE.firm:
                transaction.amount_fee = round(
                    offchain_asset_extra.fee_fixed
                    + (
                        (offchain_asset_extra.fee_percent / Decimal(100))
                        * transaction.quote.sell_amount
                    ),
                    params["source_asset"].significant_decimals,
                )
                transaction.amount_out = transaction.quote.buy_amount - round(
                    transaction.amount_fee / transaction.quote.price,
                    params["destination_asset"].significant_decimals,
                )

        # request is valid, return success data and add transaction to user model
        PolarisUserTransaction.objects.create(
            transaction_id=transaction.id, user=account.user, account=account
        )
        return {
            "how": "fake bank account number",
            "extra_info": {
                "message": (
                    "'how' would normally contain a terse explanation for how "
                    "to deposit the asset with the anchor, and 'extra_info' "
                    "would provide any additional information."
                )
            },
        }

    def create_channel_account(self, transaction: Transaction, *args, **kwargs):
        kp = Keypair.random()
        requests.get(f"https://friendbot.stellar.org/?addr={kp.public_key}")
        transaction.channel_seed = kp.secret
        transaction.save()

    def after_deposit(self, transaction: Transaction, *args, **kwargs):
        transaction.channel_seed = None
        transaction.save()

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
