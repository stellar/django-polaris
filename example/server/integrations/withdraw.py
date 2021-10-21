from decimal import Decimal
from typing import Optional, Dict, List

from django import forms
from django.utils.translation import gettext as _
from rest_framework.request import Request

from polaris.integrations import WithdrawalIntegration, calculate_fee
from polaris.models import Transaction, Asset, Quote
from polaris.sep10.token import SEP10Token
from polaris.sep38.utils import asset_id_format
from polaris.templates import Template
from polaris.utils import getLogger
from polaris import settings

from ..forms import WithdrawForm
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
        kyc_form, content = SEP24KYC.check_kyc(transaction, post_data)
        if kyc_form:
            return kyc_form
        elif content or transaction.amount_in:
            return None
        elif post_data:
            return WithdrawForm(transaction, post_data)
        else:
            return WithdrawForm(transaction, initial={"amount": amount})

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
            if not form:
                return None
            return {
                "title": _("Polaris Transaction Information"),
                "icon_label": _("Stellar Development Foundation"),
                "guidance": (
                    _(
                        "Please enter the banking details for the account "
                        "you would like to receive your funds."
                    )
                ),
            }
        else:  # template == Template.MORE_INFO
            return {
                "title": _("Polaris Transaction Information"),
                "icon_label": _("Stellar Development Foundation"),
            }

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
                transaction.fee_asset = asset_id_format(params["source_asset"])
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
