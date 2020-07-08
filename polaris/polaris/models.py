"""This module defines the models used by Polaris."""
import uuid
import decimal
import datetime
import secrets
from base64 import urlsafe_b64encode as b64e, urlsafe_b64decode as b64d

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from django.core.validators import (
    MinLengthValidator,
    MinValueValidator,
    MaxValueValidator,
)
from django.utils.encoding import force_bytes
from django.utils.translation import gettext_lazy as _
from django.db import models
from model_utils.models import TimeStampedModel
from model_utils import Choices
from stellar_sdk.keypair import Keypair


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class PolarisChoices(Choices):
    """A subclass to change the verbose default string representation"""

    def __repr__(self):
        return str(Choices)


class EncryptedTextField(models.TextField):
    """
    A custom field for ensuring its data is always encrypted at the DB
    layer and only decrypted by this object when in memory.

    Uses Fernet (https://cryptography.io/en/latest/fernet/) encryption,
    which relies on Django's SECRET_KEY setting for generating
    cryptographically secure keys.
    """

    @staticmethod
    def get_key(secret, salt):
        return b64e(
            PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend(),
            ).derive(secret)
        )

    @classmethod
    def decrypt(cls, value):
        from django.conf import settings

        decoded = b64d(value.encode())
        salt, encrypted_value = decoded[:16], b64e(decoded[16:])
        key = cls.get_key(force_bytes(settings.SECRET_KEY), salt)
        return Fernet(key).decrypt(encrypted_value).decode()

    @classmethod
    def encrypt(cls, value):
        from django.conf import settings

        salt = secrets.token_bytes(16)
        key = cls.get_key(force_bytes(settings.SECRET_KEY), salt)
        encrypted_value = b64d(Fernet(key).encrypt(value.encode()))
        return b64e(b"%b%b" % (salt, encrypted_value)).decode()

    def from_db_value(self, value, *args):
        if value is None:
            return value
        return self.decrypt(value)

    def get_db_prep_value(self, value, *args, **kwargs):
        if value is None:
            return value
        return self.encrypt(value)


class Asset(TimeStampedModel):
    """
    .. _Info: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#info

    This defines an Asset, as described in the SEP-24 Info_ endpoint.
    """

    code = models.TextField(default="USD")
    """The asset code as defined on the Stellar network."""

    issuer = models.TextField(validators=[MinLengthValidator(56)])
    """The issuing Stellar account address."""

    significant_decimals = models.IntegerField(
        default=2, validators=[MinValueValidator(0), MaxValueValidator(7)]
    )
    """The number of decimal places Polaris should save when collecting input amounts"""

    # Deposit-related info
    deposit_enabled = models.BooleanField(default=True)
    """``True`` if deposit for this asset is supported."""

    deposit_fee_fixed = models.DecimalField(
        default=0, blank=True, max_digits=30, decimal_places=7
    )
    """
    Optional fixed (base) fee for deposit. In units of the deposited asset. 
    This is in addition to any ``fee_percent``. Omit if there is no fee or the fee 
    schedule is complex.
    """

    deposit_fee_percent = models.DecimalField(
        default=0,
        blank=True,
        max_digits=30,
        decimal_places=7,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    """
    Optional percentage fee for deposit. In percentage points. This is in 
    addition to any ``fee_fixed``. Omit if there is no fee or the fee schedule
    is complex.
    """

    deposit_min_amount = models.DecimalField(
        default=0, blank=True, max_digits=30, decimal_places=7
    )
    """Optional minimum amount. No limit if not specified."""

    deposit_max_amount = models.DecimalField(
        default=decimal.MAX_EMAX, blank=True, max_digits=30, decimal_places=7
    )
    """Optional maximum amount. No limit if not specified."""

    # Withdrawal-related info
    withdrawal_enabled = models.BooleanField(default=True)
    """``True`` if withdrawal for this asset is supported."""

    withdrawal_fee_fixed = models.DecimalField(
        default=0, blank=True, max_digits=30, decimal_places=7
    )
    """
    Optional fixed (base) fee for withdraw. In units of the withdrawn asset. 
    This is in addition to any ``fee_percent``.
    """

    withdrawal_fee_percent = models.DecimalField(
        default=0,
        blank=True,
        max_digits=30,
        decimal_places=7,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    """
    Optional percentage fee for withdraw in percentage points. This is in 
    addition to any ``fee_fixed``.
    """

    withdrawal_min_amount = models.DecimalField(
        default=0, blank=True, max_digits=30, decimal_places=7
    )
    """Optional minimum amount. No limit if not specified."""

    withdrawal_max_amount = models.DecimalField(
        default=decimal.MAX_EMAX, blank=True, max_digits=30, decimal_places=7
    )
    """Optional maximum amount. No limit if not specified."""

    send_fee_fixed = models.DecimalField(
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """
    Optional fixed (base) fee for sending this asset in units of this asset. 
    This is in addition to any ``send_fee_percent``. If null, ``fee_fixed`` will not
    be displayed in SEP31 /info response.
    """

    send_fee_percent = models.DecimalField(
        null=True,
        blank=True,
        max_digits=30,
        decimal_places=7,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    """
    Optional percentage fee for sending this asset in percentage points. This is in 
    addition to any ``send_fee_fixed``. If null, ``fee_percent`` will not be displayed
    in SEP31 /info response.
    """

    send_min_amount = models.DecimalField(
        default=0, blank=True, max_digits=30, decimal_places=7
    )
    """Optional minimum amount. No limit if not specified."""

    send_max_amount = models.DecimalField(
        default=decimal.MAX_EMAX, blank=True, max_digits=30, decimal_places=7
    )
    """Optional maximum amount. No limit if not specified."""

    distribution_seed = EncryptedTextField(null=True)
    """
    The distribution stellar account secret key.
    The value is stored in the database using Fernet symmetric encryption,
    and only decrypted when in the Asset object is in memory.
    """

    sep24_enabled = models.BooleanField(default=False)
    """`True` if this asset is transferable via SEP-24"""

    sep6_enabled = models.BooleanField(default=False)
    """`True` if this asset is transferable via SEP-6"""

    sep31_enabled = models.BooleanField(default=False)
    """`True` if this asset is transferable via SEP-31"""

    symbol = models.TextField(default="$")
    """The symbol used in HTML pages when displaying amounts of this asset"""

    objects = models.Manager()

    @property
    def distribution_account(self):
        if not self.distribution_seed:
            return None
        return Keypair.from_secret(str(self.distribution_seed)).public_key

    class Meta:
        app_label = "polaris"

    def __str__(self):
        return f"{self.code} - issuer({self.issuer})"


class Transaction(models.Model):
    """
    .. _Transactions: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#transaction-history

    This defines a Transaction, as described in the SEP-24 Transactions_ endpoint.
    """

    KIND = PolarisChoices("deposit", "withdrawal", "send")
    """Choices object for ``deposit``, ``withdrawal``, or ``send``."""

    status_to_message = {
        # SEP-6 & SEP-24
        "pending_anchor": _("Processing"),
        "pending_trust": _("waiting for a trustline to be established"),
        "pending_user": _("waiting on user action"),
        "pending_user_transfer_start": _("waiting on the user to transfer funds"),
        "incomplete": _("incomplete"),
        "no_market": _("no market for the asset"),
        "too_small": _("the transaction amount is too small"),
        "too_large": _("the transaction amount is too big"),
        # SEP-31
        # messages are None because they are never displayed to user
        "pending_sender": None,
        "pending_receiver": None,
        "pending_info_update": None,
        # Shared
        "completed": _("complete"),
        "error": _("error"),
        "pending_external": _("waiting on an external entity"),
        "pending_stellar": _("stellar is executing the transaction"),
    }

    STATUS = PolarisChoices(*list(status_to_message.keys()))

    MEMO_TYPES = PolarisChoices("text", "id", "hash")
    """Type for the ``deposit_memo``. Can be either `hash`, `id`, or `text`"""

    PROTOCOL = PolarisChoices("sep6", "sep24", "sep31")
    """Values for `protocol` column"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    """Unique, anchor-generated id for the deposit/withdrawal."""

    paging_token = models.TextField(null=True)
    """The token to be used as a cursor for querying before or after this transaction"""

    # Stellar account to watch, and asset that is being transacted
    # NOTE: these fields should not be publicly exposed
    stellar_account = models.TextField(validators=[MinLengthValidator(1)])
    """The stellar source account for the transaction."""

    asset = models.ForeignKey("Asset", on_delete=models.CASCADE)
    """The Django foreign key to the associated :class:`Asset`"""

    # These fields can be shown through an API:
    kind = models.CharField(choices=KIND, default=KIND.deposit, max_length=20)
    """The character field for the available ``KIND`` choices."""

    status = models.CharField(
        choices=STATUS, default=STATUS.pending_external, max_length=30
    )
    """
    Choices field for processing status of deposit, withdrawal, & send.
    
    SEP-6 & SEP-24 Statuses:

    * **completed**
        
        deposit/withdrawal fully completed
    * **pending_external**
    
        deposit/withdrawal has been submitted to external 
        network, but is not yet confirmed. This is the status when waiting on 
        Bitcoin or other external crypto network to complete a transaction, or 
        when waiting on a bank transfer.
    * **pending_anchor**
    
        deposit/withdrawal is being processed internally by anchor.
    * **pending_stellar**
    
        deposit/withdrawal operation has been submitted to Stellar network, but 
        is not yet confirmed.
    * **pending_trust**
    
        the user must add a trust-line for the asset for the deposit to complete.
    * **pending_user**
    
        the user must take additional action before the deposit / withdrawal can 
        complete.
    * **pending_user_transfer_start**
    
        the user has not yet initiated their transfer to the anchor. This is the 
        necessary first step in any deposit or withdrawal flow.
    * **incomplete**
    
        there is not yet enough information for this transaction to be initiated. 
        Perhaps the user has not yet entered necessary info in an interactive flow.
    * **no_market**
    
        could not complete deposit because no satisfactory asset/XLM market 
        was available to create the account.
    * **too_small**
    
        deposit/withdrawal size less than min_amount.
    * **too_large**
    
        deposit/withdrawal size exceeded max_amount.
    * **error**
    
        catch-all for any error not enumerated above.
        
    SEP-31 Statuses:
    
    * **pending_sender**
    
        awaiting payment to be initiated by sending anchor.
    * **pending_stellar**
    
        transaction has been submitted to Stellar network, but is not yet confirmed.
    * **pending_info_update**
    
        certain pieces of information need to be updated by the sending anchor.
    * **pending_receiver**
    
        payment is being processed by the receiving anchor.
    * **pending_external**
    
        payment has been submitted to external network, but is not yet confirmed.
    * **completed**
    
        deposit/withdrawal fully completed.
    * **error**
    
        catch-all for any error not enumerated above.
    """

    status_eta = models.IntegerField(null=True, blank=True)
    """(optional) Estimated number of seconds until a status change is expected."""

    status_message = models.TextField(null=True, blank=True)
    """A message stored in association to the current status for debugging"""

    stellar_transaction_id = models.TextField(null=True, blank=True)
    """
    transaction_id on Stellar network of the transfer that either completed
    the deposit or started the withdrawal.
    """

    external_transaction_id = models.TextField(null=True, blank=True)
    """
    (optional) ID of transaction on external network that either started 
    the deposit or completed the withdrawal.
    """

    amount_in = models.DecimalField(
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """
    Amount received by anchor at start of transaction as a string with up 
    to 7 decimals. Excludes any fees charged before the anchor received the 
    funds.
    """

    amount_out = models.DecimalField(
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """
    Amount sent by anchor to user at end of transaction as a string with up to
    7 decimals. Excludes amount converted to XLM to fund account and any 
    external fees.
    """

    amount_fee = models.DecimalField(
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """Amount of fee charged by anchor."""

    started_at = models.DateTimeField(default=utc_now)
    """Start date and time of transaction."""

    completed_at = models.DateTimeField(null=True)
    """
    Completion date and time of transaction. Assigned null for in-progress 
    transactions.
    """

    from_address = models.TextField(
        null=True, blank=True
    )  # Using from_address since `from` is a reserved keyword
    """Sent from address, perhaps BTC, IBAN, or bank account."""

    to_address = models.TextField(
        null=True, blank=True
    )  # Using to_address for naming consistency
    """
    Sent to address (perhaps BTC, IBAN, or bank account in the case of a 
    withdrawal or send, Stellar address in the case of a deposit).
    """

    required_info_update = models.TextField(null=True, blank=True)
    """
    (SEP31) (optional) A set of fields that require an update from the sender, 
    in the same format as described in /info. Fields should be broken out by 
    sender, receiver, and transaction as specified in /info.
    """

    required_info_message = models.TextField(null=True, blank=True)
    """
    (SEP31) (optional) A human readable message indicating any errors that 
    require updated information from the sender
    """

    deposit_memo = models.TextField(null=True, blank=True)
    """
    (optional) Value of memo to attach to transaction, for hash this should
    be base64-encoded.
    """

    deposit_memo_type = models.CharField(
        choices=MEMO_TYPES, default=MEMO_TYPES.text, max_length=10
    )
    """
    (optional) Type of memo that anchor should attach to the Stellar payment 
    transaction, one of text, id or hash.
    """

    withdraw_anchor_account = models.TextField(null=True, blank=True)
    """
    (optional) The stellar account ID of the user that wants to do the 
    withdrawal. This is only needed if the anchor requires KYC information for
    withdrawal. The anchor can use account to look up the user's KYC 
    information.
    """

    withdraw_memo = models.TextField(null=True, blank=True)
    """(if specified) use this memo in the payment transaction to the anchor."""

    withdraw_memo_type = models.CharField(
        choices=MEMO_TYPES, default=MEMO_TYPES.text, max_length=10
    )
    """Field for the ``MEMO_TYPES`` Choices"""

    send_memo = models.TextField(null=True, blank=True)
    """The memo to attach to the stellar payment"""

    send_memo_type = models.CharField(
        choices=MEMO_TYPES, default=MEMO_TYPES.text, max_length=10
    )
    """Field for the ``MEMO_TYPES`` Choices"""

    send_anchor_account = models.TextField(null=True, blank=True)
    """
    Stellar account to send payment to
    """

    refunded = models.BooleanField(default=False)
    """True if the transaction was refunded, false otherwise."""

    protocol = models.CharField(choices=PROTOCOL, null=True, max_length=5)
    """Either 'sep6' or 'sep24'"""

    objects = models.Manager()

    @property
    def asset_name(self):
        return self.asset.code + ":" + self.asset.issuer

    @property
    def message(self):
        """
        Human readable explanation of transaction status
        """
        return self.status_to_message[str(self.status)]

    class Meta:
        ordering = ("-started_at",)
        app_label = "polaris"
