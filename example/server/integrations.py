from smtplib import SMTPException
from decimal import Decimal
from typing import List, Dict, Optional
from urllib.parse import urlencode
from base64 import b64encode

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
    CustomerIntegration,
    calculate_fee,
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
                account = PolarisStellarAccount.objects.get(
                    account=transaction.stellar_account
                )
            except PolarisStellarAccount.DoesNotExist:
                raise RuntimeError(
                    f"Unknown address: {transaction.stellar_account}, KYC required."
                )

        PolarisUserTransaction.objects.get_or_create(
            account=account, transaction=transaction
        )

    @staticmethod
    def check_kyc(transaction: Transaction, post_data=None) -> Optional[Dict]:
        """
        Returns a KYCForm if there is no record of this stellar account,
        otherwise returns None.
        """
        account = PolarisStellarAccount.objects.filter(
            account=transaction.stellar_account
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
            bank_deposit = client.get_deposit(memo=deposit.external_extra)
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

    def after_deposit(self, transaction: Transaction):
        """
        Deposit was successful, do any post-processing necessary.

        In this implementation, we remove the memo from the transaction to
        avoid potential collisions with still-pending deposits.
        """
        logger.info(f"Successfully processed transaction {transaction.id}")
        transaction.external_extra = None
        transaction.save()

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
        transaction.external_extra = memo
        transaction.save()
        return (
            _(
                "Include this code as the memo when making the deposit: "
                "<strong>%s</strong>. We will use "
                "this memo to identify you as the sender.\n(This deposit is "
                "automatically confirmed for demonstration purposes. Please "
                "wait.)"
            )
            % transaction.external_extra
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
        account = (
            PolarisStellarAccount.objects.filter(account=params["account"])
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
        account = (
            PolarisStellarAccount.objects.filter(account=params["account"])
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
        elif params["type"] != "bank_account":
            raise ValueError(_("'type' must be 'bank_account'"))
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
        code = asset.code
        response = {
            "account_id": settings.ASSETS[code]["DISTRIBUTION_ACCOUNT_ADDRESS"],
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
    def put(self, params: Dict):
        required_fields = [
            "account",
            "first_name",
            "last_name",
            "email_address",
            "bank_account_number",
            "bank_number",
        ]
        if not all(val in params for val in required_fields):
            raise ValueError(f"required fields: {', '.join(required_fields)}")

        user = PolarisUser.objects.filter(email=params["email"]).first()
        if not user:
            # the client could be trying to update to a new email, so try to
            # find the user based on the account
            account = PolarisStellarAccount.objects.filter(
                account=params["account"]
            ).first()
            if not account:
                user = PolarisUser.objects.create(
                    first_name=params["first_name"],
                    last_name=params["last_name"],
                    email=params["email"],
                    bank_number=params["bank_number"],
                    bank_account_number=params["bank_account_number"],
                )
                account = PolarisStellarAccount.objects.create(
                    account=params["account"], user=user
                )

            else:
                user = account.user
                user.email = params["email"]
                user.first_name = params["first_name"]
                user.last_name = params["last_name"]
                user.bank_number = params["bank_number"]
                user.bank_account_number = params["bank_account_number"]
                user.save()

            send_confirmation_email(user, account)

        else:
            account, created = PolarisStellarAccount.objects.get_or_create(
                user=user, account=params["account"]
            )
            if created:
                send_confirmation_email(user, account)

    def delete(self, account: str):
        account = PolarisStellarAccount.objects.filter(account=account).first()
        if not account:
            raise ValueError()
        account.user.delete()


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
