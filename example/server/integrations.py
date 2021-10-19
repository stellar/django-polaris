import json
import random
import uuid

import requests
from requests import RequestException
from base64 import b64encode
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from logging import getLogger
from unittest.mock import Mock
from smtplib import SMTPException
from typing import List, Dict, Optional, Tuple, Union
from urllib.parse import urlencode

from django import forms
from django.conf import settings as server_settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.db.models import QuerySet
from django.template.loader import render_to_string
from stellar_sdk import MuxedAccount
from django.urls import reverse
from django.utils.translation import gettext as _
from polaris import settings
from polaris.integrations import (
    DepositIntegration,
    WithdrawalIntegration,
    SEP31ReceiverIntegration,
    CustomerIntegration,
    calculate_fee,
    RailsIntegration,
    TransactionForm,
)
from polaris.integrations.quote import QuoteIntegration
from polaris.models import Transaction, Asset, Quote, OffChainAsset, DeliveryMethod
from polaris.sep10.token import SEP10Token
from polaris.templates import Template
from polaris.sep38.utils import asset_id_format
from rest_framework.request import Request
from stellar_sdk.keypair import Keypair

from . import mock_banking_rails as rails
from .forms import KYCForm, WithdrawForm
from .mock_exchange import (
    get_mock_firm_exchange_price,
    get_mock_indicative_exchange_price,
)
from .models import PolarisUser, PolarisStellarAccount, PolarisUserTransaction

logger = getLogger(__name__)
CONFIRM_EMAIL_PAGE_TITLE = _("Confirm Email")


def send_confirmation_email(user: PolarisUser, account: PolarisStellarAccount):
    """
    Sends a confirmation email to user.email

    In a real production deployment, you would never want to send emails
    as part of the request/response cycle. Instead, use a job queue service
    like Celery. This reference server is not intended to handle heavy
    traffic so we are making an exception here.
    """
    args = urlencode({"token": account.confirmation_token, "email": user.email})
    url = f"{settings.HOST_URL}{reverse('confirm_email')}?{args}"
    try:
        send_mail(
            _("Reference Anchor Server: Confirm Email"),
            # email body if the HTML is not rendered
            _("Confirm your email by pasting this URL in your browser: %s") % url,
            server_settings.EMAIL_HOST_USER,
            [user.email],
            html_message=render_to_string(
                "confirmation_email.html",
                {"first_name": user.first_name, "confirmation_url": url},
            ),
        )
    except SMTPException as e:
        logger.error(f"Unable to send email to {user.email}: {e}")


class SEP24KYC:
    @staticmethod
    def track_user_activity(form: forms.Form, transaction: Transaction):
        """
        Creates a PolarisUserTransaction object, and depending on the form
        passed, also creates a new PolarisStellarAccount and potentially a
        new PolarisUser. This function ensures an accurate record of a
        particular person's activity.
        """
        if isinstance(form, KYCForm):
            data = form.cleaned_data
            user = PolarisUser.objects.filter(email=data.get("email")).first()
            if not user:
                user = PolarisUser.objects.create(
                    first_name=data.get("first_name"),
                    last_name=data.get("last_name"),
                    email=data.get("email"),
                )

            account = PolarisStellarAccount.objects.create(
                user=user,
                account=transaction.stellar_account,
                muxed_account=transaction.muxed_account,
                memo=transaction.account_memo,
                memo_type=Transaction.MEMO_TYPES.id
                if transaction.account_memo
                else None,
            )
            if server_settings.EMAIL_HOST_USER:
                send_confirmation_email(user, account)
        else:
            try:
                account = PolarisStellarAccount.objects.get(
                    account=transaction.stellar_account,
                    muxed_account=transaction.muxed_account,
                    memo=transaction.account_memo,
                )
            except ObjectDoesNotExist:
                raise RuntimeError(
                    f"Unknown address: {transaction.stellar_account}, KYC required."
                )

        PolarisUserTransaction.objects.get_or_create(
            user=account.user, account=account, transaction_id=transaction.id
        )

    @staticmethod
    def check_kyc(
        transaction: Transaction, post_data=None
    ) -> Tuple[Optional[forms.Form], Optional[Dict]]:
        """
        Returns a KYCForm if there is no record of this stellar account,
        otherwise returns None.
        """
        account = PolarisStellarAccount.objects.filter(
            account=transaction.stellar_account,
            muxed_account=transaction.muxed_account,
            memo=transaction.account_memo,
        ).first()
        if not account:  # Unknown stellar account, get KYC info
            if post_data:
                form = KYCForm(post_data)
            else:
                form = KYCForm()
            return (
                form,
                {
                    "icon_label": _("Stellar Development Foundation"),
                    "title": _("Polaris KYC Information"),
                    "guidance": (
                        _(
                            "We're legally required to know our customers. "
                            "Please enter the information requested."
                        )
                    ),
                },
            )
        elif settings.LOCAL_MODE:
            # When in local mode, request session's are not authenticated,
            # which means account confirmation cannot be skipped. So we'll
            # return None instead of returning the confirm email page.
            return None, None
        elif server_settings.EMAIL_HOST_USER and not account.confirmed:
            return (
                None,
                {
                    "title": CONFIRM_EMAIL_PAGE_TITLE,
                    "guidance": _(
                        "We sent you a confirmation email. Once confirmed, "
                        "continue on this page."
                    ),
                    "icon_label": _("Stellar Development Foundation"),
                },
            )
        else:
            return None, None


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
                account=params["account"],
                memo=params["memo"],
                memo_type=params["memo_type"],
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

        asset = params["asset"]
        min_amount = round(asset.withdrawal_min_amount, asset.significant_decimals)
        max_amount = round(asset.withdrawal_max_amount, asset.significant_decimals)
        if params["amount"]:
            if not (min_amount <= params["amount"] <= max_amount):
                raise ValueError(_("invalid 'amount'"))
            transaction.amount_in = params["amount"]
            transaction.amount_fee = calculate_fee(
                {
                    "amount": params["amount"],
                    "operation": "withdraw",
                    "asset_code": asset.code,
                }
            )
            transaction.amount_out = round(
                transaction.amount_in - transaction.amount_fee,
                asset.significant_decimals,
            )
            transaction.save()

        response = {
            "account_id": asset.distribution_account,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "fee_fixed": round(asset.withdrawal_fee_fixed, asset.significant_decimals),
            "fee_percent": asset.withdrawal_fee_percent,
        }
        if params["memo_type"] and params["memo"]:
            response["memo_type"] = params["memo_type"]
            response["memo"] = params["memo"]

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


class MyCustomerIntegration(CustomerIntegration):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.required_fields = [
            "account",
            "first_name",
            "last_name",
            "email_address",
            "bank_account_number",
            "bank_number",
        ]
        self.accepted = {"status": "ACCEPTED"}
        self.needs_basic_info = {
            "status": "NEEDS_INFO",
            "fields": {
                "first_name": {
                    "description": "first name of the customer",
                    "type": "string",
                },
                "last_name": {
                    "description": "last name of the customer",
                    "type": "string",
                },
                "email_address": {
                    "description": "email address of the customer",
                    "type": "string",
                },
            },
        }
        self.needs_bank_info = {
            "status": "NEEDS_INFO",
            "fields": {
                "bank_account_number": {
                    "description": "bank account number of the customer",
                    "type": "string",
                },
                "bank_number": {
                    "description": "routing number of the customer",
                    "type": "string",
                },
            },
        }
        self.needs_all_info = {
            "status": "NEEDS_INFO",
            "fields": {
                "first_name": {
                    "description": "first name of the customer",
                    "type": "string",
                },
                "last_name": {
                    "description": "last name of the customer",
                    "type": "string",
                },
                "email_address": {
                    "description": "email address of the customer",
                    "type": "string",
                },
                "bank_account_number": {
                    "description": "bank account number of the customer",
                    "type": "string",
                },
                "bank_number": {
                    "description": "routing number of the customer",
                    "type": "string",
                },
            },
        }

    def get(
        self, token: SEP10Token, request: Request, params: Dict, *args, **kwargs
    ) -> Dict:
        user = None
        if params.get("id"):
            user = PolarisUser.objects.filter(id=params["id"]).first()
            if not user:
                raise ObjectDoesNotExist(_("customer not found"))
        elif params.get("account"):
            if params["account"].startswith("M"):
                stellar_account = MuxedAccount.from_account(
                    params["account"]
                ).account_id
                muxed_account = params["account"]
            else:
                stellar_account = params["account"]
                muxed_account = None
            account = PolarisStellarAccount.objects.filter(
                account=stellar_account,
                muxed_account=muxed_account,
                memo=params.get("memo"),
                memo_type=params.get("memo_type"),
            ).first()
            user = account.user if account else None

        if not user:
            if params.get("type") in ["sep6-deposit", "sep31-sender", "sep31-receiver"]:
                return self.needs_basic_info
            elif params.get("type") in [None, "sep6-withdraw"]:
                return self.needs_all_info
            else:
                raise ValueError(
                    _("invalid 'type'. see /info response for valid values.")
                )

        response_data = {"id": str(user.id)}
        basic_info_accepted = {
            "provided_fields": {
                "first_name": {
                    "description": "first name of the customer",
                    "type": "string",
                    "status": "ACCEPTED",
                },
                "last_name": {
                    "description": "last name of the customer",
                    "type": "string",
                    "status": "ACCEPTED",
                },
                "email_address": {
                    "description": "email address of the customer",
                    "type": "string",
                    "status": "ACCEPTED",
                },
            }
        }
        if (user.bank_number and user.bank_account_number) or (
            params.get("type") in ["sep6-deposit", "sep31-sender", "sep31-receiver"]
        ):
            response_data.update(self.accepted)
            response_data.update(basic_info_accepted)
            if user.bank_number and user.bank_account_number:
                response_data["provided_fields"].update(
                    {
                        "bank_account_number": {
                            "description": "bank account number of the customer",
                            "type": "string",
                            "status": "ACCEPTED",
                        },
                        "bank_number": {
                            "description": "routing number of the customer",
                            "type": "string",
                            "status": "ACCEPTED",
                        },
                    }
                )
        elif params.get("type") in [None, "sep6-withdraw"]:
            response_data.update(basic_info_accepted)
            response_data.update(self.needs_bank_info)
        else:
            raise ValueError(_("invalid 'type'. see /info response for valid values."))
        return response_data

    def put(
        self, token: SEP10Token, request: Request, params: Dict, *args, **kwargs
    ) -> str:
        if params.get("id"):
            user = PolarisUser.objects.filter(id=params["id"]).first()
            if not user:
                raise ObjectDoesNotExist("could not identify user customer 'id'")
        else:
            if params["account"].startswith("M"):
                stellar_account = MuxedAccount.from_account(
                    params["account"]
                ).account_id
                muxed_account = params["account"]
            else:
                stellar_account = params["account"]
                muxed_account = None
            account = PolarisStellarAccount.objects.filter(
                account=stellar_account,
                muxed_account=muxed_account,
                memo=params.get("memo"),
                memo_type=params.get("memo_type"),
            ).first()
            if not account:
                # email_address is a secondary ID
                if "email_address" not in params:
                    raise ValueError(
                        "SEP-9 fields were not passed for new customer. "
                        "'first_name', 'last_name', and 'email_address' are required."
                    )
                # find existing user by previously-specified email
                user = PolarisUser.objects.filter(email=params["email_address"]).first()
                if user:
                    account = PolarisStellarAccount.objects.create(
                        user=user,
                        account=stellar_account,
                        muxed_account=muxed_account,
                        memo=params["memo"],
                        memo_type=params["memo_type"],
                    )
                    send_confirmation_email(user, account)
                else:
                    user, account = self.create_new_user(params)
                    send_confirmation_email(user, account)
            else:
                user = account.user

        if (
            user.email != params.get("email_address")
            and PolarisUser.objects.filter(email=params.get("email_address")).exists()
        ):
            raise ValueError("email_address is taken")

        user.email = params.get("email_address") or user.email
        user.first_name = params.get("first_name") or user.first_name
        user.last_name = params.get("last_name") or user.last_name
        user.bank_number = params.get("bank_number") or user.bank_number
        user.bank_account_number = (
            params.get("bank_account_number") or user.bank_account_number
        )
        user.save()

        return str(user.id)

    def delete(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        memo: Optional[str],
        memo_type: Optional[str],
        *args,
        **kwargs,
    ):
        if account.startswith("M"):
            stellar_account = MuxedAccount.from_account(account).account_id
            muxed_account = account
        else:
            stellar_account = account
            muxed_account = None
        qparams = {
            "account": stellar_account,
            "muxed_account": muxed_account,
            "memo": memo,
            "memo_type": memo_type,
        }
        account = PolarisStellarAccount.objects.filter(**qparams).first()
        if not account:
            raise ObjectDoesNotExist()
        account.user.delete()

    @staticmethod
    def create_new_user(params):
        if not all(f in params for f in ["first_name", "last_name", "email_address"]):
            raise ValueError(
                "SEP-9 fields were not passed for new customer. "
                "'first_name', 'last_name', and 'email_address' are required."
            )
        if params["account"].startswith("M"):
            stellar_account = MuxedAccount.from_account(params["account"]).account_id
            muxed_account = params["account"]
        else:
            stellar_account = params["account"]
            muxed_account = None
        user = PolarisUser.objects.create(
            first_name=params["first_name"],
            last_name=params["last_name"],
            email=params["email_address"],
            bank_number=params.get("bank_number"),
            bank_account_number=params.get("bank_account_number"),
        )
        account = PolarisStellarAccount.objects.create(
            user=user,
            account=stellar_account,
            muxed_account=muxed_account,
            memo=params.get("memo"),
            memo_type=params.get("memo_type"),
        )
        return user, account

    def more_info_url(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        *args: List,
        memo: Optional[int] = None,
        **kwargs: Dict,
    ) -> str:
        raise NotImplementedError()

    def callback(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        *args: List,
        **kwargs: Dict,
    ):
        raise NotImplementedError()

    def put_verification(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        params: Dict,
        *args: List,
        **kwargs: Dict,
    ) -> Dict:
        raise NotImplementedError()


class MySEP31ReceiverIntegration(SEP31ReceiverIntegration):
    def info(
        self,
        request: Request,
        asset: Asset,
        lang: Optional[str] = None,
        *args,
        **kwargs,
    ):
        return {
            "sep12": {
                "sender": {
                    "types": {
                        "sep31-sender": {
                            "description": "the basic type for sending customers"
                        }
                    }
                },
                "receiver": {
                    "types": {
                        "sep31-receiver": {
                            "description": "the basic type for receiving customers"
                        }
                    }
                },
            },
            "fields": {
                "transaction": {
                    "routing_number": {
                        "description": "routing number of the destination bank account"
                    },
                    "account_number": {
                        "description": "bank account number of the destination"
                    },
                },
            },
        }

    def process_post_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Optional[Dict]:
        _ = params.get("sender_id")  # not actually used
        receiver_id = params.get("receiver_id")
        transaction_fields = params.get("fields", {}).get("transaction")
        for field, val in transaction_fields.items():
            if not isinstance(val, str):
                return {"error": f"'{field}'" + _(" is not of type str")}

        receiving_user = PolarisUser.objects.filter(id=receiver_id).first()
        if not receiving_user:
            return {"error": "customer_info_needed", "type": "sep31-receiver"}

        elif not (receiving_user.bank_account_number and receiving_user.bank_number):
            receiving_user.bank_account_number = transaction_fields["account_number"]
            receiving_user.bank_number = transaction_fields["routing_number"]
            receiving_user.save()
        transaction.save()
        PolarisUserTransaction.objects.create(
            user=receiving_user, transaction_id=transaction.id
        )

    def process_patch_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ):
        info_fields = params.get("fields", {})
        transaction_fields = info_fields.get("transaction", {})
        if not isinstance(transaction_fields, dict):
            raise ValueError(_("'transaction' value must be an object"))
        possible_fields = set()
        for obj in self.info(request, transaction.asset)["fields"].values():
            possible_fields.union(obj.keys())
        update_fields = list(transaction_fields.keys())
        if not update_fields:
            raise ValueError(_("No fields provided"))
        elif any(f not in possible_fields for f in update_fields):
            raise ValueError(_("unexpected fields provided"))
        elif not all(isinstance(update_fields[f], str) for f in update_fields):
            raise ValueError(_("field values must be strings"))
        user = (
            PolarisUserTransaction.objects.filter(transaction_id=transaction.id)
            .first()
            .user
        )
        if "routing_number" in update_fields:
            user.bank_number = transaction_fields["routing_number"]
        elif "account_number" in update_fields:
            user.bank_account_number = transaction_fields["account_number"]
        user.save()

    def valid_sending_anchor(
        self, token: SEP10Token, request: Request, public_key: str, *args, **kwargs
    ) -> bool:
        # A real anchor would check if public_key belongs to a partner anchor
        return True


class MyRailsIntegration(RailsIntegration):
    def poll_pending_deposits(
        self, pending_deposits: QuerySet, *args, **kwargs
    ) -> List[Transaction]:
        """
        Anchors should implement their banking rails here, as described
        in the :class:`.RailsIntegration` docstrings.

        This implementation interfaces with a fake banking rails client
        for demonstration purposes.
        """
        # interface with mock banking rails
        ready_deposits = []
        mock_bank_account_id = "XXXXXXXXXXXXX"
        client = rails.BankAPIClient(mock_bank_account_id)
        for deposit in pending_deposits:
            bank_deposit = client.get_deposit(deposit=deposit)
            if bank_deposit and bank_deposit.status == "complete":
                if not deposit.amount_in:
                    deposit.amount_in = Decimal(103)

                if bank_deposit.amount != deposit.amount_in or not deposit.amount_fee:
                    deposit.amount_fee = calculate_fee(
                        {
                            "amount": deposit.amount_in,
                            "operation": settings.OPERATION_DEPOSIT,
                            "asset_code": deposit.asset.code,
                        }
                    )
                deposit.amount_out = round(
                    deposit.amount_in - deposit.amount_fee,
                    deposit.asset.significant_decimals,
                )
                deposit.save()
                ready_deposits.append(deposit)

        return ready_deposits

    def poll_outgoing_transactions(
        self, transactions: QuerySet, *args, **kwargs
    ) -> List[Transaction]:
        """
        Auto-complete pending_external transactions

        An anchor would typically collect information on the transactions passed
        and return only the transactions that have completed the external transfer.
        """
        return list(transactions)

    def execute_outgoing_transaction(self, transaction: Transaction, *args, **kwargs):
        def error():
            transaction.status = Transaction.STATUS.error
            transaction.status_message = (
                f"Unable to find user info for transaction {transaction.id}"
            )
            transaction.save()

        logger.info("fetching user data for transaction")
        user_transaction = PolarisUserTransaction.objects.filter(
            transaction_id=transaction.id
        ).first()
        if not user_transaction:  # something is wrong with our user tracking code
            error()
            return

        # SEP31 users don't have stellar accounts, so check the user column on the transaction.
        # Since that is a new column, it may be None. If so, use the account's user column
        if user_transaction.user:
            user = user_transaction.user
        else:
            user = getattr(user_transaction.account, "user", None)

        if not user:  # something is wrong with our user tracking code
            error()
            return

        if transaction.kind == Transaction.KIND.withdrawal:
            operation = settings.OPERATION_WITHDRAWAL
        else:
            operation = Transaction.KIND.send
        if not transaction.amount_fee:
            transaction.amount_fee = calculate_fee(
                {
                    "amount": transaction.amount_in,
                    "operation": operation,
                    "asset_code": transaction.asset.code,
                }
            )
        transaction.amount_out = round(
            transaction.amount_in - transaction.amount_fee,
            transaction.asset.significant_decimals,
        )
        client = rails.BankAPIClient("fake anchor bank account number")
        response = client.send_funds(
            to_account=user.bank_account_number,
            amount=transaction.amount_in - transaction.amount_fee,
        )

        if response["success"]:
            logger.info(f"successfully sent mock outgoing transaction {transaction.id}")
            transaction.status = Transaction.STATUS.pending_external
        else:
            # Parse a mock bank API response to demonstrate how an anchor would
            # report back to the sending anchor which fields needed updating.
            error_fields = response.error.fields
            info_fields = MySEP31ReceiverIntegration().info(Mock(), transaction.asset)
            required_info_update = defaultdict(dict)
            for field in error_fields:
                if "name" in field:
                    required_info_update["receiver"][field] = info_fields["receiver"][
                        field
                    ]
                elif "account" in field:
                    required_info_update["transaction"][field] = info_fields[
                        "receiver"
                    ][field]
            transaction.required_info_update = json.dumps(required_info_update)
            transaction.required_info_message = response.error.message
            transaction.status = Transaction.STATUS.pending_transaction_info_update

        transaction.save()


def fee_integration(fee_params: Dict, *args, **kwargs) -> Decimal:
    """
    This function replaces the default registered_fee_func for demonstration
    purposes.

    However, since we don't have any custom logic to implement, it simply
    calls the default that has been replaced.
    """
    return calculate_fee(fee_params)


def info_integration(request: Request, asset: Asset, lang: str):
    # Not using `asset` since this reference server only supports SRT
    languages = [l[0] for l in server_settings.LANGUAGES]
    if lang and lang not in languages:
        raise ValueError()
    return {
        "fields": {
            "type": {
                "description": _("'bank_account' is the only value supported'"),
                "choices": ["bank_account"],
            },
        },
        "types": {
            "bank_account": {
                "fields": {
                    "dest": {"description": _("bank account number")},
                    "dest_extra": {"description": _("bank routing number")},
                }
            }
        },
    }


class MyQuoteIntegration(QuoteIntegration):
    def get_prices(
        self,
        token: SEP10Token,
        request: Request,
        sell_asset: Union[Asset, OffChainAsset],
        sell_amount: Decimal,
        buy_assets: List[Union[Asset, OffChainAsset]],
        sell_delivery_method: Optional[DeliveryMethod] = None,
        buy_delivery_method: Optional[DeliveryMethod] = None,
        country_code: Optional[str] = None,
        *args,
        **kwargs,
    ) -> List[Decimal]:
        prices = []
        for _ in buy_assets:
            try:
                prices.append(get_mock_indicative_exchange_price())
            except RequestException:
                raise RuntimeError("unable to fetch prices")
        return prices

    def get_price(
        self,
        token: SEP10Token,
        request: Request,
        sell_asset: Union[Asset, OffChainAsset],
        sell_amount: Decimal,
        buy_asset: Union[Asset, OffChainAsset],
        buy_amount: Decimal,
        sell_delivery_method: Optional[DeliveryMethod] = None,
        buy_delivery_method: Optional[DeliveryMethod] = None,
        country_code: Optional[str] = None,
        *args,
        **kwargs,
    ) -> Decimal:
        try:
            return get_mock_indicative_exchange_price()
        except RequestException:
            raise RuntimeError("unable to fetch price")

    @staticmethod
    def approve_expiration(_expire_after) -> bool:
        return True

    def post_quote(
        self, token: SEP10Token, request: Request, quote: Quote, *args, **kwargs,
    ) -> Quote:
        if quote.requested_expire_after and not self.approve_expiration(
            quote.requested_expire_after
        ):
            raise ValueError(
                f"expiration ({quote.requested_expire_after.strftime(settings.DATETIME_FORMAT)}) cannot be provided.",
            )
        try:
            quote.price = get_mock_firm_exchange_price()
        except RequestException:
            raise RuntimeError("unable to fetch price for quote")
        quote.expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=random.randrange(5, 60)
        )
        return quote
