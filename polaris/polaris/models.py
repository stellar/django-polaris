"""This module defines the models used by Polaris."""
import uuid

from polaris import settings
from django.core.validators import MinLengthValidator
from django.db import models
from model_utils.models import TimeStampedModel
from model_utils import Choices


class PolarisChoices(Choices):
    """A subclass to change the verbose default string representation"""

    def __repr__(self):
        return str(Choices)


class Asset(TimeStampedModel):
    """
    .. _Info: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#info

    This defines an Asset, as described in the SEP-24 Info_ endpoint.
    """

    code = models.TextField(validators=[MinLengthValidator(1)], default="USD")
    """The asset code as defined on the Stellar network."""

    issuer = models.TextField(validators=[MinLengthValidator(56)])
    """The issuing Stellar account address."""

    # Deposit-related info
    deposit_enabled = models.BooleanField(null=False, default=True)
    """``True`` if SEP-6 deposit for this asset is supported."""
    deposit_fee_fixed = models.DecimalField(
        default=1.0, blank=True, max_digits=50, decimal_places=25
    )
    """
    Optional fixed (base) fee for deposit. In units of the deposited asset. 
    This is in addition to any ``fee_percent``. Omit if there is no fee or the fee 
    schedule is complex.
    """
    deposit_fee_percent = models.DecimalField(
        default=0.01, blank=True, max_digits=50, decimal_places=25
    )
    """
    Optional percentage fee for deposit. In percentage points. This is in 
    addition to any ``fee_fixed``. Omit if there is no fee or the fee schedule
    is complex.
    """
    deposit_min_amount = models.DecimalField(
        default=10.0, blank=True, max_digits=50, decimal_places=25
    )
    """Optional minimum amount. No limit if not specified."""
    deposit_max_amount = models.DecimalField(
        default=10000.0, blank=True, max_digits=50, decimal_places=25
    )
    """Optional maximum amount. No limit if not specified."""

    # Withdrawal-related info
    withdrawal_enabled = models.BooleanField(null=False, default=True)
    """``True`` if SEP-6 withdrawal for this asset is supported."""
    withdrawal_fee_fixed = models.DecimalField(
        default=1.0, blank=True, max_digits=50, decimal_places=25
    )
    """
    Optional fixed (base) fee for withdraw. In units of the withdrawn asset. 
    This is in addition to any ``fee_percent``.
    """
    withdrawal_fee_percent = models.DecimalField(
        default=0.01, blank=True, max_digits=50, decimal_places=25
    )
    """
    Optional percentage fee for withdraw in percentage points. This is in 
    addition to any ``fee_fixed``.
    """
    withdrawal_min_amount = models.DecimalField(
        default=10.0, blank=True, max_digits=50, decimal_places=25
    )
    """Optional minimum amount. No limit if not specified."""
    withdrawal_max_amount = models.DecimalField(
        default=10000.0, blank=True, max_digits=50, decimal_places=25
    )
    """Optional maximum amount. No limit if not specified."""

    objects = models.Manager()

    class Meta:
        app_label = "polaris"


class Transaction(models.Model):
    """
    .. _Transactions: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md#transaction-history

    This defines a Transaction, as described in the SEP-24 Transactions_ endpoint.
    """

    KIND = PolarisChoices("deposit", "withdrawal")
    """Choices object for ``deposit`` or ``withdrawal``."""
    STATUS = PolarisChoices(
        "completed",
        "pending_external",
        "pending_anchor",
        "pending_stellar",
        "pending_trust",
        "pending_user",
        "pending_user_transfer_start",
        "incomplete",
        "no_market",
        "too_small",
        "too_large",
        "error",
    )
    MEMO_TYPES = PolarisChoices("text", "id", "hash")
    """Type for the ``deposit_memo``. Can be either `hash`, `id`, or `text`"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    """Unique, anchor-generated id for the deposit/withdrawal."""

    # Stellar account to watch, and asset that is being transactioned
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
    Choices object for processing status of deposit/withdrawal.

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
    """
    status_eta = models.IntegerField(null=True, blank=True, default=3600)
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
        null=True, blank=True, max_digits=50, decimal_places=25
    )
    """
    Amount received by anchor at start of transaction as a string with up 
    to 7 decimals. Excludes any fees charged before the anchor received the 
    funds.
    """
    amount_out = models.DecimalField(
        null=True, blank=True, max_digits=50, decimal_places=25
    )
    """
    Amount sent by anchor to user at end of transaction as a string with up to
    7 decimals. Excludes amount converted to XLM to fund account and any 
    external fees.
    """
    amount_fee = models.DecimalField(
        null=True, blank=True, max_digits=50, decimal_places=25
    )
    """Amount of fee charged by anchor."""
    started_at = models.DateTimeField(auto_now_add=True)
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
    withdrawal, Stellar address in the case of a deposit).
    """
    external_extra = models.TextField(null=True, blank=True)
    """"""
    external_extra_text = models.TextField(null=True, blank=True)
    """
    The bank name or store name that the user will be withdrawing 
    their funds to.
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

    objects = models.Manager()

    @property
    def asset_name(self):
        return self.asset.code + ":" + self.asset.issuer

    class Meta:
        ordering = ("-started_at",)
        app_label = "polaris"
