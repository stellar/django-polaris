from typing import Union

import json
from smtplib import SMTPException
from decimal import Decimal
from typing import List, Dict, Optional
from urllib.parse import urlencode
from base64 import b64encode
from collections import defaultdict

from django.db.models import QuerySet
from django.utils.translation import gettext as _
from django import forms
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings as server_settings
from django.template.loader import render_to_string

from polaris.models import Transaction, Asset
from polaris.utils import Logger
from polaris.integrations import (
    DepositIntegration,
    WithdrawalIntegration,
    SendIntegration,
    CustomerIntegration,
    calculate_fee,
    RailsIntegration,
)
from polaris import settings

from . import mock_banking_rails as rails
from .models import PolarisUser, PolarisStellarAccount, PolarisUserTransaction
from .forms import KYCForm, WithdrawForm


logger = Logger(__name__)
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
                account=transaction.stellar_account, user=user
            )
            if server_settings.EMAIL_HOST_USER:
                send_confirmation_email(user, account)
        else:
            try:
                # Look for an account that uses this address but doesn't have a
                # memo, which means its a SEP-24 or SEP-6 Polaris account.
                account = PolarisStellarAccount.objects.get(
                    account=transaction.stellar_account, memo=None
                )
            except PolarisStellarAccount.DoesNotExist:
                raise RuntimeError(
                    f"Unknown address: {transaction.stellar_account}, KYC required."
                )

        PolarisUserTransaction.objects.get_or_create(
            account=account, transaction_id=transaction.id
        )

    @staticmethod
    def check_kyc(transaction: Transaction, post_data=None) -> Optional[Dict]:
        """
        Returns a KYCForm if there is no record of this stellar account,
        otherwise returns None.
        """
        account = PolarisStellarAccount.objects.filter(
            account=transaction.stellar_account, memo=None
        ).first()
        if not account:  # Unknown stellar account, get KYC info
            if post_data:
                form = KYCForm(post_data)
            else:
                form = KYCForm()
            return {
                "form": form,
                "icon_label": _("Stellar Development Foundation"),
                "title": _("Polaris KYC Information"),
                "guidance": (
                    _(
                        "We're legally required to know our customers. "
                        "Please enter the information requested."
                    )
                ),
            }
        elif settings.LOCAL_MODE:
            # When in local mode, request session's are not authenticated,
            # which means account confirmation cannot be skipped. So we'll
            # return None instead of returning the confirm email page.
            return
        elif server_settings.EMAIL_HOST_USER and not account.confirmed:
            return {
                "title": CONFIRM_EMAIL_PAGE_TITLE,
                "guidance": _(
                    "We sent you a confirmation email. Once confirmed, "
                    "continue on this page."
                ),
                "icon_label": _("Stellar Development Foundation"),
            }
        else:
            return None


class MyDepositIntegration(DepositIntegration):
    def poll_pending_deposits(self, pending_deposits: QuerySet) -> List[Transaction]:
        """
        Anchors should implement their banking rails here, as described
        in the :class:`.DepositIntegration` docstrings.

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
                    deposit.amount_fee = calculate_fee(
                        {
                            "amount": 103,
                            "operation": settings.OPERATION_DEPOSIT,
                            "asset_code": deposit.asset.code,
                        }
                    )
                    deposit.save()
                ready_deposits.append(deposit)

        return ready_deposits

    def instructions_for_pending_deposit(self, transaction: Transaction):
        """
        This function provides a message to the user containing instructions for
        how to initiate a bank deposit to the anchor's account.

        This particular implementation generates and provides a unique memo to
        match an incoming deposit to the user, but there are many ways of
        accomplishing this. If you collect KYC information like the user's
        bank account number, that could be used to match the deposit and user
        as well.
        """
        # Generate a unique alphanumeric memo string to identify bank deposit
        memo = b64encode(str(hash(transaction)).encode()).decode()[:10].upper()
        return (
            _(
                "Include this code as the memo when making the deposit: "
                "<strong>%s</strong>. We will use "
                "this memo to identify you as the sender.\n(This deposit is "
                "automatically confirmed for demonstration purposes. Please "
                "wait.)"
            )
            % memo
        )

    def content_for_transaction(
        self, transaction: Transaction, post_data=None, amount=None
    ) -> Optional[Dict]:
        kyc_content = SEP24KYC.check_kyc(transaction, post_data=post_data)
        if kyc_content:
            return kyc_content

        form_content = super().content_for_transaction(
            transaction, post_data=post_data, amount=amount
        )
        if not form_content:
            return None

        return {
            "form": form_content.get("form"),
            "title": _("Polaris Transaction Information"),
            "guidance": _("Please enter the amount you would like to transfer."),
            "icon_label": _("Stellar Development Foundation"),
        }

    def after_form_validation(self, form: forms.Form, transaction: Transaction):
        try:
            SEP24KYC.track_user_activity(form, transaction)
        except RuntimeError:
            # Since no polaris account exists for this transaction, KYCForm
            # will be returned from the next form_for_transaction() call
            logger.exception(
                f"KYCForm was not served first for unknown account, id: "
                f"{transaction.stellar_account}"
            )

    def process_sep6_request(self, params: Dict) -> Dict:
        qparams = {"account": params["account"], "memo": None}
        account = (
            PolarisStellarAccount.objects.filter(**qparams)
            .select_related("user")
            .first()
        )
        info_needed_resp = {
            "type": "non_interactive_customer_info_needed",
            "fields": [
                "first_name",
                "last_name",
                "email_address",
                "bank_number",
                "bank_account_number",
            ],
        }
        if not account:
            return info_needed_resp
        elif not (account.user.bank_account_number and account.user.bank_number):
            return info_needed_resp
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

        # request is valid, return success data
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


class MyWithdrawalIntegration(WithdrawalIntegration):
    def process_withdrawal(self, response: Dict, transaction: Transaction):
        logger.info(f"Processing transaction {transaction.id}")

        mock_bank_account_id = "XXXXXXXXXXXXX"
        client = rails.BankAPIClient(mock_bank_account_id)
        client.send_funds(
            to_account=transaction.to_address,
            amount=transaction.amount_in - transaction.amount_fee,
        )

    def content_for_transaction(
        self, transaction: Transaction, post_data=None, amount=None
    ) -> Optional[Dict]:
        kyc_content = SEP24KYC.check_kyc(transaction, post_data)
        if kyc_content:
            return kyc_content

        if transaction.amount_in:
            return None

        if post_data:
            form = WithdrawForm(transaction, post_data)
        else:
            form = WithdrawForm(transaction, initial=amount)

        return {
            "form": form,
            "title": _("Polaris Transaction Information"),
            "icon_label": _("Stellar Development Foundation"),
            "guidance": (
                _(
                    "Please enter the banking details for the account "
                    "you would like to receive your funds."
                )
            ),
        }

    def after_form_validation(self, form: forms.Form, transaction: Transaction):
        try:
            SEP24KYC.track_user_activity(form, transaction)
        except RuntimeError:
            # Since no polaris account exists for this transaction, KYCForm
            # will be returned from the next form_for_transaction() call
            logger.exception(
                f"KYCForm was not served first for unknown account, id: "
                f"{transaction.stellar_account}"
            )

    def process_sep6_request(self, params: Dict) -> Dict:
        qparams = {"account": params["account"], "memo": None}
        account = (
            PolarisStellarAccount.objects.filter(**qparams)
            .select_related("user")
            .first()
        )
        info_needed_resp = {
            "type": "non_interactive_customer_info_needed",
            "fields": [
                "first_name",
                "last_name",
                "email_address",
                "bank_number",
                "bank_account_number",
            ],
        }
        if not account:
            return info_needed_resp
        elif not (account.user.bank_account_number and account.user.bank_number):
            return info_needed_resp
        elif params["type"] != "bank_account":
            raise ValueError(_("'type' must be 'bank_account'"))
        elif not params["dest"]:
            raise ValueError(_("'dest' is required"))
        elif not params["dest_extra"]:
            raise ValueError(_("'dest_extra' is required"))
        elif params["dest"] != account.user.bank_account_number:
            raise ValueError(_("'dest' must match bank account number for account"))
        elif params["dest_extra"] != account.user.bank_number:
            raise ValueError(
                _("'dest_extra' must match bank routing number for account")
            )
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
        response = {
            "account_id": asset.distribution_account,
            "min_amount": round(
                asset.withdrawal_min_amount, asset.significant_decimals
            ),
            "max_amount": round(
                asset.withdrawal_max_amount, asset.significant_decimals
            ),
            "fee_fixed": round(asset.withdrawal_fee_fixed, asset.significant_decimals),
            "fee_percent": asset.withdrawal_fee_percent,
        }
        if params["memo_type"] and params["memo"]:
            response["memo_type"] = params["memo_type"]
            response["memo"] = params["memo"]

        return response


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

    def get(self, params: Dict) -> Dict:
        query_params = {}
        for attr in ["id", "memo", "memo_type", "account"]:
            if params.get(attr):
                query_params[attr] = params.get(attr)
        account = PolarisStellarAccount.objects.filter(**query_params).first()
        if "id" in query_params and not account:
            # client believes the customer already exists but it doesn't,
            # at least not with the same ID, memo, account values.
            raise ValueError(
                _("customer not found using: %s") % list(query_params.keys())
            )
        elif not account:
            if params.get("type") in ["sep6-deposit", "sep31-sender", "sep31-receiver"]:
                return self.needs_basic_info
            elif params.get("type") in [None, "sep6-withdraw"]:
                return self.needs_all_info
            else:
                raise ValueError(
                    _("invalid 'type'. see /info response for valid values.")
                )
        else:
            user = account.user
            response_data = {"id": user.id}
            if (user.bank_number and user.bank_account_number) or (
                params.get("type") in ["sep6-deposit", "sep31-sender", "sep31-receiver"]
            ):
                response_data.update(self.accepted)
                return response_data
            elif params.get("type") in [None, "sep6-withdraw"]:
                response_data.update(self.needs_bank_info)
                return response_data
            else:
                raise ValueError(
                    _("invalid 'type'. see /info response for valid values.")
                )

    def put(self, params: Dict) -> str:
        # query params for fetching/creating the PolarisStellarAccount
        qparams = {"account": params["account"]}
        if params.get("memo"):
            qparams["memo"] = params["memo"]
            qparams["memo_type"] = params["memo_type"]
        user = None
        account = PolarisStellarAccount.objects.filter(**qparams).first()
        if not account:
            if "email_address" in params:
                # find existing user by previously-specified email
                user = PolarisUser.objects.filter(email=params["email_address"]).first()
                if user:
                    account = PolarisStellarAccount.objects.create(
                        user=user,
                        account=params["account"],
                        memo=params["memo"],
                        memo_type=params["memo_type"],
                    )
                    send_confirmation_email(user, account)
                else:
                    user, account = self.create_new_user(params, qparams)
                    send_confirmation_email(user, account)
            else:
                raise ValueError(
                    "SEP-9 fields were not passed for new customer. "
                    "'first_name', 'last_name', and 'email_address' are required."
                )
        if not user:
            user = account.user
            if (
                user.email != params.get("email_address")
                and PolarisUser.objects.filter(email=params["email_address"]).exists()
            ):
                raise ValueError("email_address is taken")

        user.email = params.get("email_address") or user.email
        user.first_name = params.get("first_name") or user.first_name
        user.last_name = params.get("last_name") or user.last_name
        user.bank_number = params.get("bank_number") or user.bank_number
        user.bank_account_number = (
            params.get("bank_account_number") or user.bank_account_number
        )

        return str(user.id)

    def delete(self, account: str):
        # There could be multiple PolarisStellarAccount for the same address
        account = PolarisStellarAccount.objects.filter(account=account)
        if not account:
            raise ValueError()
        account.user.delete()

    @staticmethod
    def create_new_user(params, qparams):
        if not all(f in params for f in ["first_name", "last_name", "email_address"]):
            raise ValueError(
                "SEP-9 fields were not passed for new customer. "
                "'first_name', 'last_name', and 'email_address' are required."
            )
        user = PolarisUser.objects.create(
            first_name=params["first_name"],
            last_name=params["last_name"],
            email=params["email_address"],
            bank_number=params.get("bank_number"),
            bank_account_number=params.get("bank_account_number"),
        )
        account = PolarisStellarAccount.objects.create(user=user, **qparams)
        return user, account


class MySendIntegration(SendIntegration):
    def info(self, asset: Asset, lang: Optional[str] = None):
        return {
            "sender_sep12_type": "sep31-sender",
            "receiver_sep12_type": "sep31-receiver",
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

    def process_send_request(self, params: Dict, transaction_id: str) -> Optional[Dict]:
        sender_id = params.get("sender_id")  # not actually used
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
        # Transaction doesn't yet exist so transaction_id is a text field
        PolarisUserTransaction.objects.create(
            user=receiving_user, transaction_id=transaction_id
        )

    def process_update_request(self, params: Dict, transaction: Transaction):
        info_fields = params.get("fields", {})
        transaction_fields = info_fields.get("transaction", {})
        if not isinstance(transaction_fields, dict):
            raise ValueError(_("'transaction' value must be an object"))
        possible_fields = set()
        for obj in self.info(transaction.asset)["fields"].values():
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

    def valid_sending_anchor(self, public_key: str) -> bool:
        # A real anchor would check if public_key belongs to a partner anchor
        return True


class MyRailsIntegration(RailsIntegration):
    def poll_outgoing_transactions(self, transactions: QuerySet) -> List[Transaction]:
        """
        Auto-complete pending_external transactions

        An anchor would typically collect information on the transactions passed
        and return only the transactions that have completed the external transfer.
        """
        return list(transactions)

    def execute_outgoing_transaction(self, transaction: Transaction):
        user = (
            PolarisUserTransaction.objects.filter(transaction_id=transaction.id)
            .first()
            .user
        )

        client = rails.BankAPIClient("fake anchor bank account number")
        transaction.amount_fee = 0  # Or calculate your fee
        response = client.send_funds(
            to_account=user.bank_account_number,
            amount=transaction.amount_in - transaction.amount_fee,
        )

        if response["success"]:
            transaction.status = Transaction.STATUS.pending_external
        else:
            # Parse a mock bank API response to demonstrate how an anchor would
            # report back to the sending anchor which fields needed updating.
            error_fields = response.error.fields
            info_fields = MySendIntegration().info(transaction.asset)
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
            transaction.status = Transaction.STATUS.pending_info_update

        transaction.save()


def toml_integration():
    return {
        "DOCUMENTATION": {
            "ORG_NAME": "Stellar Development Foundation",
            "ORG_URL": "https://stellar.org",
            "ORG_DESCRIPTION": "SEP 24 reference server.",
            "ORG_KEYBASE": "stellar.public",
            "ORG_TWITTER": "StellarOrg",
            "ORG_GITHUB": "stellar",
        },
        "CURRENCIES": [
            {
                "code": asset.code.upper(),
                "issuer": asset.issuer,
                "status": "test",
                "is_asset_anchored": False,
                "anchor_asset_type": "other",
                "desc": "A fake anchored asset to use with this example anchor server.",
            }
            for asset in Asset.objects.all()
        ],
        "PRINCIPALS": [
            {
                "name": "Jacob Urban",
                "email": "jake@stellar.org",
                "keybase": "jakeurban",
                "github": "https://www.github.com/JakeUrban",
            }
        ],
    }


def scripts_integration(page_content: Optional[Dict]):
    tags = [
        # Google Analytics
        """
        <!-- Global site tag (gtag.js) - Google Analytics -->
        <script async src="https://www.googletagmanager.com/gtag/js?id=UA-53373928-6"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());
          gtag('config', 'UA-53373928-6');
        </script>
        """
    ]
    if (
        page_content
        and "form" not in page_content
        and page_content.get("title") == CONFIRM_EMAIL_PAGE_TITLE
    ):
        # Refresh the confirm email page whenever the user brings the popup
        # back into focus. This is not strictly necessary since deposit.html
        # and withdraw.html have 'Refresh' buttons, but this is a better UX.
        tags.append(
            """
            <script>
                window.addEventListener("load", () => {
                    window.addEventListener("focus", () => {
                        // Hit the /webapp endpoint again to check if the user's 
                        // email has been confirmed.
                        window.location.reload(true);
                    });
                });
            </script>
            """
        )
        # Add a "Skip Confirmation" button that will make a GET request to the
        # skip confirmation endpoint and reload the page. The email confirmation
        # functionality is just for sake of demonstration anyway.
        tags.append(
            """
            <script>
                (function () {
                    let section = document.querySelector(".main-content").firstElementChild;
                    let button = document.createElement("button");
                    button.className = "button";
                    button.innerHTML = "Skip Confirmation";
                    button.setAttribute("test-action", "submit");
                    button.addEventListener("click", function () {
                        this.disabled = true;
                        let url = window.location.protocol + "//" + window.location.host + "/skip_confirm_email";
                        fetch(url).then(res => res.json()).then((json) => {
                            if (json["status"] === "not found") {
                                // This would only happen if the PolarisStellarAccount doesn't exist.
                                // It should always exist because the user needs to have an existing
                                // account to access the confirm email page.
                                let errElement = document.createElement("p");
                                errElement.style = "color:red";
                                errElement.innerHTML = "Error: Unable to skip confirmation step";
                                errElement.align = "center";
                                section.appendChild(document.createElement("br"));
                                section.appendChild(errElement);
                            } else {
                                window.location.reload(true);
                            }
                        });
                    });
                    section.appendChild(document.createElement("br"));
                    section.appendChild(button);
                })();
            </script>
            """
        )
    return tags


def fee_integration(fee_params: Dict) -> Decimal:
    """
    This function replaces the default registered_fee_func for demonstration
    purposes.

    However, since we don't have any custom logic to implement, it simply
    calls the default that has been replaced.
    """
    logger.info("Using custom fee function")
    return calculate_fee(fee_params)


def info_integration(asset: Asset, lang: str):
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
