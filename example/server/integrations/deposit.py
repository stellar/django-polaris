from base64 import b64encode
from decimal import Decimal
from typing import Optional, Dict, List

import requests
from django import forms
from django.utils.translation import gettext as _
from rest_framework.request import Request
from stellar_sdk import Keypair

from polaris.integrations import DepositIntegration, TransactionForm, calculate_fee
from polaris.models import Transaction, Asset
from polaris.sep10.token import SEP10Token
from polaris.templates import Template
from polaris.utils import getLogger

from .sep24_kyc import SEP24KYC
from ..models import PolarisStellarAccount, PolarisUserTransaction


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
        if kyc_form:
            return kyc_form
        elif content or transaction.amount_in:
            return None
        elif post_data:
            return TransactionForm(transaction, post_data)
        else:
            return TransactionForm(transaction, initial={"amount": amount})

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
        if kyc_content:
            return kyc_content
        elif template == Template.DEPOSIT:
            if not form:
                return None
            return {
                "title": _("Polaris Transaction Information"),
                "guidance": _("Please enter the amount you would like to transfer."),
                "icon_label": _("Stellar Development Foundation"),
            }
        elif template == Template.MORE_INFO:
            content = {
                "title": _("Polaris Transaction Information"),
                "icon_label": _("Stellar Development Foundation"),
            }
            if transaction.status == Transaction.STATUS.pending_user_transfer_start:
                # We're waiting on the user to send an off-chain payment
                content.update(
                    memo=b64encode(str(hash(transaction)).encode())
                    .decode()[:10]
                    .upper()
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

        asset = params["asset"]
        min_amount = round(asset.deposit_min_amount, asset.significant_decimals)
        max_amount = round(asset.deposit_max_amount, asset.significant_decimals)
        if params["amount"]:
            if not (min_amount <= params["amount"] <= max_amount):
                raise ValueError(_("invalid 'amount'"))
            transaction.amount_in = params["amount"]
            transaction.amount_fee = calculate_fee(
                {
                    "amount": params["amount"],
                    "operation": "deposit",
                    "asset_code": asset.code,
                }
            )
            transaction.amount_out = round(
                transaction.amount_in - transaction.amount_fee,
                asset.significant_decimals,
            )
            transaction.save()

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
