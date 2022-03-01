"""This module defines the models used by Polaris."""
import datetime
import decimal
import secrets
import uuid
from base64 import urlsafe_b64encode as b64e, urlsafe_b64decode as b64d

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.core.exceptions import ValidationError
from django.core.validators import (
    MinLengthValidator,
    MinValueValidator,
    MaxValueValidator,
)
from django.db import models
from django.utils.encoding import force_bytes
from django.utils.translation import gettext_lazy as _
from model_utils import Choices
from model_utils.models import TimeStampedModel
from stellar_sdk.server_async import ServerAsync
from stellar_sdk.client.aiohttp_client import AiohttpClient
from stellar_sdk.exceptions import SdkError
from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope

from polaris import settings

# Used for loading the distribution signers data onto an Asset obj
ASSET_DISTRIBUTION_ACCOUNT_MAP = {}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class PolarisHeartbeat(models.Model):
    """
    Used as a locking mechanism to ensure that certain processes such as
    process_pending_deposits.py don't have more than 1 instance running
    at any given time. The last_heatbeat is a timestamp that is periodically
    updated by the process. If a process unexpectedly dies, another instance
    can check this value at startup and if its been too long since the last
    update, the lock is considered 'expired' and the new process can acquire
    it. This mechanism is an advisory lock and the locking logic is implemented
    at the application level.
    This value can also be used to create a 'health check' endpoint for the
    application
    Note: The application is expected to delete this key during a gracefully
    shutdown - see process_pending_deposits.py for an example
    """

    key = models.CharField(max_length=80, unique=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()


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

    def from_db_value(self, value, *_args):
        if value is None:
            return value
        return self.decrypt(value)

    def get_db_prep_value(self, value, *_args, **_kwargs):
        if value is None:
            return value
        return self.encrypt(value)


class Asset(TimeStampedModel):
    code = models.TextField()
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
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """
    Optional fixed (base) fee for deposit. In units of the deposited asset. 
    This is in addition to any ``fee_percent``. Omit if there is no fee or the fee 
    schedule is complex.
    """

    deposit_fee_percent = models.DecimalField(
        null=True,
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
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """
    Optional fixed (base) fee for withdraw. In units of the withdrawn asset. 
    This is in addition to any ``fee_percent``.
    """

    withdrawal_fee_percent = models.DecimalField(
        null=True,
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

    distribution_seed = EncryptedTextField(null=True, blank=True)
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

    sep38_enabled = models.BooleanField(default=False)
    """`True` if this asset is exchangeable via SEP-38"""

    symbol = models.TextField(default="$")
    """The symbol used in HTML pages when displaying amounts of this asset"""

    objects = models.Manager()

    @property
    def distribution_account(self):
        """
        The Stellar public key derived from `Asset.distribution_seed`
        """
        if not self.distribution_seed:
            return None
        return Keypair.from_secret(str(self.distribution_seed)).public_key

    @property
    def asset_identification_format(self):
        """
        SEP-38 asset identification format
        """
        return f"stellar:{self.code}:{self.issuer}"

    def get_distribution_account_data(self, refresh=False):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            account_json = (
                settings.HORIZON_SERVER.accounts()
                .account_id(self.distribution_account)
                .call()
            )
            ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account] = account_json
            return account_json
        else:
            return ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]

    def get_distribution_account_signers(self, refresh=False):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            account_json = self.get_distribution_account_data(refresh=refresh)
        else:
            account_json = ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]
        return account_json["signers"]

    def get_distribution_account_thresholds(self, refresh=False):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            account_json = self.get_distribution_account_data(refresh=refresh)
        else:
            account_json = ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]
        return account_json["thresholds"]

    def get_distribution_account_master_signer(self, refresh=False):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            account_json = self.get_distribution_account_data(refresh=refresh)
        else:
            account_json = ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]
        master_signer = None
        for signer in account_json["signers"]:
            if signer["key"] == self.distribution_account:
                master_signer = signer
        return master_signer

    async def get_distribution_account_data_async(self, refresh=False):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            async with ServerAsync(
                settings.HORIZON_URI, client=AiohttpClient()
            ) as server:
                account_json = (
                    await server.accounts().account_id(self.distribution_account).call()
                )
            ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account] = account_json
            return account_json
        else:
            return ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]

    async def get_distributiion_account_signers_async(self, refresh=False):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            account_json = await self.get_distribution_account_data_async(
                refresh=refresh
            )
        else:
            account_json = ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]
        return account_json["signers"]

    async def get_distribution_account_thresholds_async(self, refresh=False):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            account_json = await self.get_distribution_account_data_async(
                refresh=refresh
            )
        else:
            account_json = ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]
        return account_json["thresholds"]

    async def get_distribution_account_master_signer_async(
        self, refresh=False, server=None
    ):
        if refresh or self.distribution_account not in ASSET_DISTRIBUTION_ACCOUNT_MAP:
            account_json = await self.get_distribution_account_data_async(
                refresh=refresh
            )
        else:
            account_json = ASSET_DISTRIBUTION_ACCOUNT_MAP[self.distribution_account]
        master_signer = None
        for signer in account_json["signers"]:
            if signer["key"] == self.distribution_account:
                master_signer = signer
        return master_signer

    class Meta:
        app_label = "polaris"

    def __str__(self):
        return f"{self.code} - issuer({self.issuer})"


def deserialize(value):
    """
    Validation function for Transaction.envelope_xdr
    """
    from polaris import settings

    try:
        TransactionEnvelope.from_xdr(value, settings.STELLAR_NETWORK_PASSPHRASE)
    except SdkError as e:
        raise ValidationError(
            _("Cannot decode envelope XDR for transaction: %(error)s"),
            params={"error": str(e)},
        )


class Transaction(models.Model):
    KIND = PolarisChoices(
        "deposit", "withdrawal", "send", "deposit-exchange", "withdrawal-exchange"
    )
    """Choices object for the kind of transaction"""

    status_to_message = {
        # SEP-6 & SEP-24
        "pending_anchor": _("processing"),
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
        "pending_transaction_info_update": None,
        "pending_customer_info_update": None,
        # Shared
        "completed": _("complete"),
        "error": _("error"),
        "pending_external": _("waiting on an external entity"),
        "pending_stellar": _("stellar is executing the transaction"),
    }

    SUBMISSION_STATUS = PolarisChoices(
        "not_ready",
        "ready",
        "processing",
        "pending",
        "pending_funding",
        "pending_trust",
        "blocked",
        "unblocked",
        "completed",
        "failed",
    )
    """ 
        Submission Statuses

    * **not_ready**
        used until a transaction is returned from RailsIntegration.poll_pending_deposits()
        and determined by check_account to be ready for submission to the Stellar Network
    
    * **ready**
        used when the transaction has been processed by the check_account task and verified
        that the transaction is ready to be submitted to the Stellar Network

    * **processing**
        used when Polaris is submitting the transaction to Stellar. Note that up to two 
        transactions could be submitted for this Transaction object, one for creating the 
        account if it doesn't exist, and the other for sending the deposit payment.

    * **pending**
        used when the transaction has been passed to 
        CustodyIntegration.create_destination_account() or 
        CustodyIntegration.submit_deposit_transaction() but a `TransactionSubmissionPending` 
        exception was raised in the most-recent invocation, and a SIGINT or SIGTERM was 
        sent, preventing Polaris from submitting again.
    
    * **pending_trust**
        used when the transaction destination account does not yet have a trustline
    
    * **blocked**
        used when the transaction has been passed to 
        CustodyIntegration.create_destination_account()
        or CustodyIntegration.submit_deposit_transaction() but a `TransactionSubmissionBlocked` 
        exception was raised in the most-recent invocation. Polaris will simply move to the 
        next transaction.
    
    * **unblocked**
        Similar to READY, but indicates that the transaction was previously blocked.
    
    * **completed**
        used when a transaction has been successfully submitted to the Stellar network

    * **failed**
        used when a transaction has been passed to 
        CustodyIntegration.submit_deposit_transaction() but a `TransactionSubmissionFailed`
        exception was raised
    """

    STATUS = PolarisChoices(*list(status_to_message.keys()))

    MEMO_TYPES = PolarisChoices("text", "id", "hash")
    """Type for the ``memo``. Can be either `hash`, `id`, or `text`"""

    PROTOCOL = PolarisChoices("sep6", "sep24", "sep31")
    """Values for `protocol` column"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    """Unique, anchor-generated id for the deposit/withdrawal."""

    paging_token = models.TextField(null=True, blank=True)
    """The token to be used as a cursor for querying before or after this transaction"""

    stellar_account = models.TextField(validators=[MinLengthValidator(1)])
    """
    The Stellar (G...) account authenticated via SEP-10 that initiated this transaction.
    Note that if ``Transaction.muxed_account`` is not null, this column's value is 
    derived from the muxed account.
    """

    muxed_account = models.TextField(null=True, blank=True)
    """
    The muxed (M...) account authenticated via SEP-10 that initiated this transaction.
    If this column value is not null, ``Transaction.stellar_account`` is derived from
    this value and ``Transaction.account_memo`` will be null.
    """

    account_memo = models.PositiveIntegerField(null=True, blank=True)
    """
    The ID (64-bit integer) memo identifying the user of the shared Stellar account 
    authenticated via SEP-10 that initiated this transaction. If this column value
    is not null, ``Transaction.muxed_account`` will be null.
    """

    asset = models.ForeignKey("Asset", on_delete=models.CASCADE)
    """The Django foreign key to the associated :class:`Asset`"""

    quote = models.ForeignKey("Quote", null=True, blank=True, on_delete=models.CASCADE)

    # These fields can be shown through an API:
    kind = models.CharField(choices=KIND, default=KIND.deposit, max_length=20)
    """The character field for the available ``KIND`` choices."""

    submission_status = models.CharField(
        choices=SUBMISSION_STATUS, default=SUBMISSION_STATUS.not_ready, max_length=31
    )

    status = models.CharField(
        choices=STATUS, default=STATUS.pending_external, max_length=31
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
    * **pending_transaction_info_update**
    
        transaction details must be updated to successfully execute transaction off-chain
    * **pending_customer_info_update**
    
        customer (SEP-12) information must be updated to facilitate transactions
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

    amount_expected = models.DecimalField(
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """
    Amount the client specified would be sent to the anchor at the start of
    a transaction. Note that ``Transaction.amount_in`` can differ from this field 
    after funds have been received. Until then, the fields will match. This field
    makes it possible to check if the amount sent to the anchor matches the amount
    the client initially specified in an API request or form.
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

    fee_asset = models.TextField(null=True, blank=True)
    """
    The string representing the asset in which the fee is charged. The string
    must be formatted using SEP-38's Asset Identification Format, and is only
    necessary for transactions using different on and off-chain assets.
    """

    queue = models.TextField(null=True, blank=True)
    """The queue that this transaction is currently in"""

    queued_at = models.DateTimeField(null=True, blank=True)
    """The time when this transaction was queued"""

    started_at = models.DateTimeField(default=utc_now)
    """Start date and time of transaction."""

    completed_at = models.DateTimeField(null=True, blank=True)
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
    withdrawal or send, Stellar or muxed address in the case of a deposit).
    """

    required_info_updates = models.TextField(null=True, blank=True)
    """
    (SEP31) (optional) A set of fields that require an update from the sender, 
    in the same format as described in /info.
    """

    required_info_message = models.TextField(null=True, blank=True)
    """
    (SEP31) (optional) A human readable message indicating any errors that 
    require updated information from the sender
    """

    memo = models.TextField(null=True, blank=True)
    """
    (optional) Value of memo to attach to transaction, for hash this should
    be base64-encoded.
    """

    memo_type = models.CharField(
        choices=MEMO_TYPES, default=MEMO_TYPES.text, max_length=10
    )
    """
    (optional) Type of memo that anchor should attach to the Stellar payment 
    transaction, one of text, id or hash.
    """

    receiving_anchor_account = models.TextField(null=True, blank=True)
    """
    Stellar account to send payment or withdrawal funds to
    """

    refunded = models.BooleanField(default=False)
    """True if the transaction was refunded, false otherwise."""

    protocol = models.CharField(choices=PROTOCOL, null=True, max_length=5, blank=True)
    """Either 'sep6', 'sep24', or 'sep31'"""

    pending_signatures = models.BooleanField(default=False)
    """
    Boolean for whether or not non-Polaris signatures are needed for this 
    transaction's envelope.
    """

    envelope_xdr = models.TextField(validators=[deserialize], null=True, blank=True)
    """
    The base64-encoded XDR blob that can be deserialized to inspect and sign 
    the encoded transaction.
    """

    channel_seed = EncryptedTextField(null=True, blank=True)
    """
    A keypair of the account used when sending SEP-6 or SEP-24 deposit 
    transactions to Transaction.to_address, if present. 
    This is only used for transactions requiring signatures Polaris cannot
    add itself.
    """

    claimable_balance_supported = models.BooleanField(default=False)
    """
    claimable_balance_supported is a boolean to indicate if the wallet supports the SEP24
    requirements for handeling claimable balance deposits.
    """

    claimable_balance_id = models.TextField(null=True, blank=True)
    """
    The ID of the claimable balance used to send funds to the user. This column will be
    ``None`` if ``claimable_balance_supported`` is ``False`` or if the transaction has
    not yet been submitted to the Stellar network.
    """

    more_info_url = models.TextField(null=True, blank=True)
    """
    A URL that is opened by wallets after the interactive flow is complete. It can include
    banking information for users to start deposits, the status of the transaction, or any
    other information the user might need to know about the transaction.
    """

    on_change_callback = models.TextField(null=True, blank=True)
    """
    A URL that the anchor should POST a JSON message to when the status property of the
    transaction created as a result of this request changes.
    """

    pending_execution_attempt = models.BooleanField(default=False)
    """
    An internal column used to ensure transactions are not retrieved from the database 
    and executed by different processes running the same command, specifically 
    process_pending_deposits and execute_outgoing_transactions.
    """

    client_domain = models.TextField(null=True, blank=True)
    """
    The hostname of the client application that requested this transaction on behalf of
    the user. The SIGNING_KEY on `https://client_domain/.well-known/stellar.toml` signed 
    the challenge transaction used to obtain the authentication token necessary to 
    request this transaction, effectively allowing requests including the authentication 
    token to be attributed to it.
    """

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

    @property
    def channel_account(self):
        if not self.channel_seed:
            return None
        return Keypair.from_secret(str(self.channel_seed)).public_key

    class Meta:
        ordering = ("-started_at",)
        app_label = "polaris"


class Quote(models.Model):
    """
    Quote objects represent either firm or indicative quotes requested by the client
    application and provided by the anchor. Quote objects will be assigned to the
    Transaction.quote column by Polaris when requested via a SEP-6 or SEP-31 request.
    Anchors must create their own Quote objects when facilitating a SEP-24 transaction.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    """
    The unique ID for the quote.
    """

    stellar_account = models.TextField()
    """
    The Stellar (G...) account authenticated via SEP-10 when this Quote was created.
    Note that if ``Quote.muxed_account`` is not null, this column's value is 
    derived from the muxed account. 
    """

    account_memo = models.PositiveIntegerField(null=True, blank=True)
    """
    The ID (64-bit integer) memo identifying the user of the shared Stellar account 
    authenticated via SEP-10 when this Quote was created. If this column value
    is not null, ``Quote.muxed_account`` will be null.
    """

    muxed_account = models.TextField(null=True, blank=True)
    """
    The muxed (M...) account authenticated via SEP-10 when this Quote was created.
    If this column value is not null, ``Quote.stellar_account`` is derived from
    this value and ``Quote.account_memo`` will be null.
    """

    TYPE = PolarisChoices("firm", "indicative")
    """
    Choices for type.
    """

    type = models.TextField(choices=TYPE)
    """
    The type of quote. Firm quotes have a non-null price and expiration, indicative quotes 
    may have a null price and expiration.
    """

    sell_asset = models.TextField()
    """
    The asset the client would like to sell. Ex. USDC:G..., iso4217:ARS
    """

    buy_asset = models.TextField()
    """
    The asset the client would like to receive for some amount of sell_asset.
    """

    sell_amount = models.DecimalField(max_digits=30, decimal_places=7)
    """
    The amount of sell_asset the client would exchange for buy_asset.
    """

    buy_amount = models.DecimalField(
        null=True, blank=True, max_digits=30, decimal_places=7
    )
    """
    The amount of buy_asset the client would like to purchase with sell_asset.
    """

    price = models.DecimalField(null=True, blank=True, max_digits=30, decimal_places=7)
    """
    The price offered by the anchor for one unit of buy_asset in terms of sell_asset.
    """

    expires_at = models.DateTimeField(null=True, blank=True)
    """
    The expiration time of the quote. Null if type is Quote.TYPE.indicative.
    """

    sell_delivery_method = models.ForeignKey(
        "DeliveryMethod",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    """
    One of the name values specified by the sell_delivery_methods array.
    """

    buy_delivery_method = models.ForeignKey(
        "DeliveryMethod",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    """
    One of the name values specified by the buy_delivery_methods array.
    """

    country_code = models.TextField(null=True, blank=True)
    """
    The ISO 3166-1 alpha-3 code of the user's current address. 
    """

    requested_expire_after = models.DateTimeField(null=True, blank=True)
    """
    The requested expiration date from the client.
    """

    objects = models.Manager()


class OffChainAsset(models.Model):
    """
    Off-chain assets represent the asset being exchanged with the Stellar asset. Each
    off-chain asset has a set of delivery methods by which the user can provide funds to
    the anchor and by which the anchor can deliver funds to the user.
    """

    scheme = models.TextField()
    """
    The scheme of the off-chain asset as defined by SEP-38's Asset Identification Format.
    """

    identifier = models.TextField()
    """
    The identifier of the off-chain asset as defined by SEP-38's Asset Identification Format.
    """

    significant_decimals = models.PositiveIntegerField(default=2)
    """
    The number of decimal places Polaris should preserve when collecting & calculating amounts.
    """

    country_codes = models.TextField(null=True, blank=True)
    """
    A comma-separated list of ISO 3166-1 alpha-3 codes of the countries where the anchor 
    supports delivery of this asset.
    """

    delivery_methods = models.ManyToManyField("DeliveryMethod")
    """
    The list of delivery methods support for collecting and receiving this asset
    """

    symbol = models.TextField(null=True, blank=True)
    """
    The symbol to use when displaying amounts of this asset
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scheme", "identifier"], name="offchain_unique_index"
            )
        ]

    objects = models.Manager()

    @property
    def asset_identification_format(self):
        return f"{self.scheme}:{self.identifier}"


class DeliveryMethod(models.Model):
    """
    Delivery methods are the supported means of payment from the user to the anchor and from
    the anchor to the user. For example, an anchor may have retail stores that accept cash
    drop-off and pick-up, or only accept debit or credit card payments. The method used by
    the anchor to collect or deliver funds to the user may affect the rate or fees charged
    for facilitating the transaction.
    """

    TYPE = PolarisChoices("buy", "sell")
    """
    The types of delivery methods.
    """

    type = models.TextField(choices=TYPE)
    """
    The type of delivery method. Sell methods describe how a client can deliver funds to the 
    anchor. Buy methods describe how a client can receive or collect funds from the anchor.
    """

    name = models.TextField()
    """
    The name of the delivery method, to be used in SEP-38 request and response bodies.
    """

    description = models.TextField()
    """
    The human-readable description of the deliver method, to be used in SEP-38 
    response bodies.
    """

    objects = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "type"], name="deliverymethod_unique_index"
            )
        ]


class ExchangePair(models.Model):
    """
    Exchange pairs consist of an off-chain and on-chain asset that can be exchanged.
    Specifically, one of these assets can be sold by the client (sell_asset) and the
    other is bought by the client (buy_asset). ExchangePairs cannot consist of two
    off-chain assets or two on-chain assets. Note that two exchange pair objects must
    be created if each asset can be bought or sold for the other.
    """

    buy_asset = models.TextField()
    """
    The asset the client can purchase with sell_asset using SEP-38's Asset 
    Identification Format.
    """

    sell_asset = models.TextField()
    """
    The asset the client can provide in exchange for buy_asset using SEP-38's
    Asset Identification Format.
    """

    objects = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["buy_asset", "sell_asset"], name="exchangepair_unique_index"
            )
        ]
