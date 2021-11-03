from smtplib import SMTPException
from typing import Tuple, Optional, Dict
from urllib.parse import urlencode

from django import forms
from django.utils.translation import gettext as _
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from polaris import settings
from polaris.models import Transaction
from polaris.utils import getLogger

from ..forms import KYCForm
from .. import settings as server_settings
from ..models import PolarisUser, PolarisStellarAccount, PolarisUserTransaction


CONFIRM_EMAIL_PAGE_TITLE = _("Confirm Email")
logger = getLogger(__name__)


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
                # this would be where a confirmation email is sent
                pass
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
        if not PolarisUserTransaction.objects.filter(
            transaction_id=transaction.id
        ).exists():
            PolarisUserTransaction.objects.create(
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
