from jwt import InvalidIssuerError
import urllib3
from decimal import Decimal
from typing import Optional, Dict
from logging import getLogger

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from stellar_sdk import Keypair, TransactionBuilder, Server
from stellar_sdk import Asset as StellarSdkAsset
from stellar_sdk.account import Account
from stellar_sdk.exceptions import (
    NotFoundError,
    BaseHorizonError,
    Ed25519SecretSeedInvalidError,
)

from polaris import settings
from polaris.models import Transaction, Asset

logger = getLogger(__name__)


class Command(BaseCommand):
    """
    The testnet command comes with the following commands:

    ``issue`` allows users to create assets on the Stellar testnet network. When
    the test network resets, you’ll have to reissue your assets.

    ``reset`` calls the functionality invoked by ``issue`` for each asset in the
    anchor’s database. Since the database does not store the issuing account’s
    secret key, the user must input each key as requested by the Polaris command.
    It also performs a couple other functions necessary to ensure your Polaris
    instance runs successfully after a testnet reset:

    Moves all pending_trust transactions to error
        This is done because all accounts have been cleared from the network. While
        its possible an account that required a trustline could be recreated and a
        trustline could be established, its unlikely. Polaris assumes a testnet
        reset makes in-progress transactions unrecoverable.

    Updates the paging_token of latest transaction streamed for each anchored asset
        :mod:`~polaris.management.commands.watch_transactions` streams transactions to
        and from each anchored asset’s distribution account. Specifically, it streams
        transactions starting with the most recently completed transaction’s
        :attr:`~polaris.models.Transaction.paging_token` on startup. When the testnet
        resets, the :attr:`~polaris.models.Transaction.paging_token` used for transactions
        prior to the reset are no longer valid. To fix this, Polaris updates the
        :attr:`~polaris.models.Transaction.paging_token` of the most recently completed
        transaction for each anchored asset to "now".

    **Positional arguments:**

    reset
        -h, --help  show this help message and exit

    issue
        -h, --help          show this help message and exit
        --asset ASSET, -a ASSET
                            the code of the asset issued
        --issuer-seed ISSUER_SEED, -i ISSUER_SEED
                            the issuer's secret key
        --distribution-seed DISTRIBUTION_SEED, -d DISTRIBUTION_SEED
                            the distribution account's secret key
        --client-seed CLIENT_SEED, -c CLIENT_SEED
                            the client account's secret key
        --issue-amount ISSUE_AMOUNT
                            the amount sent to distribution account. Also the
                            limit for the trustline.
        --client-amount CLIENT_AMOUNT
                            the amount sent to client account. Also the limit for
                            the trustline.

    ``add-asset`` allows users to add assets to the database:

    add-asset
        -h, --help           show this help message and exit
        --asset ASSET, -a ASSET
                             the code of the asset issued
        --issuer-public ISSUER_PUBLIC, -i ISSUER_PUBLIC
                             the issuer's public key
        --distribution-seed  DISTRIBUTION_SEED, -d DISTRIBUTION_SEED
                             the distribution account's secret key
        --sep6-enabled       (Optional) flag to enable sep6 for this asset, defaults to false
        --sep24-enabled      (Optional) flag to enable sep24 for this asset, defaults to false
        --sep31-enabled      (Optional) flag to enable sep31 for this asset, defaults to false
        --sep38-enabled      (Optional) flag to enable sep38 for this asset, defaults to false
        --deposit-enabled    (Optional) flag to enable deposits for this asset, defaults to false
        --withdrawal-enabled (Optional) flag to enable withdrawals for this asset, defaults to false
        --symbol             (Optional) symbol for the asset, default to "$"

    ``delete-asset`` allows users to delete assets from the database:

    delete-asset
        -h, --help            show this help message and exit
        --asset ASSET, -a ASSET
                              the code of the asset to be deleted
        --issuer-public ISSUER_PUBLIC, -i ISSUER_PUBLIC
                              the issuer's public key
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_parser = None
        self.issue_parser = None
        self.add_asset_parser = None
        self.delete_asset_parser = None
        self.server = settings.HORIZON_SERVER
        self.http = urllib3.PoolManager()

    def add_arguments(self, parser):  # pragma: no cover
        subparsers = parser.add_subparsers(dest="subcommands", required=True)
        self.reset_parser = subparsers.add_parser(
            "reset", help="a sub-command for testnet resets"
        )
        self.issue_parser = subparsers.add_parser(
            "issue", help="a sub-command for issuing assets on testnet"
        )
        self.issue_parser.add_argument(
            "--asset", "-a", help="the code of the asset issued"
        )
        self.issue_parser.add_argument(
            "--issuer-seed", "-i", help="the issuer's secret key"
        )
        self.issue_parser.add_argument(
            "--distribution-seed", "-d", help="the distribution account's secret key"
        )
        self.issue_parser.add_argument(
            "--client-seed", "-c", help="the client account's secret key"
        )
        self.issue_parser.add_argument(
            "--issue-amount",
            type=Decimal,
            help="the amount sent to distribution account. Also the limit for the trustline.",
        )
        self.issue_parser.add_argument(
            "--client-amount",
            type=Decimal,
            help="the amount sent to client account. Also the limit for the trustline.",
        )

        self.add_asset_parser = subparsers.add_parser(
            "add-asset", help="a sub-command for adding assets to the database"
        )
        self.add_asset_parser.add_argument(
            "--asset", help="asset code to add to the database", required=True
        )
        self.add_asset_parser.add_argument(
            "--issuer-public", help="the asset issuer's public key", required=True
        )
        self.add_asset_parser.add_argument(
            "--distribution-seed",
            help="the anchors distribution seed for this asset",
            required=True,
        )
        self.add_asset_parser.add_argument(
            "--sep6-enabled",
            help="enable sep6 for this asset",
            action="store_true",
        )
        self.add_asset_parser.add_argument(
            "--sep24-enabled",
            help="enable sep24 for this asset",
            action="store_true",
        )
        self.add_asset_parser.add_argument(
            "--sep31-enabled",
            help="enable sep31 for this asset",
            action="store_true",
        )
        self.add_asset_parser.add_argument(
            "--sep38-enabled",
            help="enable sep38 for this asset",
            action="store_true",
        )
        self.add_asset_parser.add_argument(
            "--deposit-enabled",
            help="enable deposits for this asset",
            action="store_true",
        )
        self.add_asset_parser.add_argument(
            "--withdrawal-enabled",
            help="enable withdrawals for this asset",
            action="store_true",
        )
        self.add_asset_parser.add_argument(
            "--symbol",
            help="symbol for the asset",
        )

        self.delete_asset_parser = subparsers.add_parser(
            "delete-asset", help="a sub-command for deleting assets to the database"
        )
        self.delete_asset_parser.add_argument(
            "--asset", help="asset code to delete to the database", required=True
        )
        self.delete_asset_parser.add_argument(
            "--issuer-public", help="the asset issuer's public key", required=True
        )

    def handle(self, *_args, **options):  # pragma: no cover
        if options.get("subcommands") == "reset":
            self.reset(**options)
        elif options.get("subcommands") == "issue":
            self.issue(**options)
        elif options.get("subcommands") == "add-asset":
            self.add_asset_to_db(**options)
        elif options.get("subcommands") == "delete-asset":
            self.delete_asset_from_db(**options)

    def reset(self, **options):
        """
        Perform any necessary functions to ensure the anchor is in a valid
        state after a testnet reset. Currently this involves the following:

        - re-issuing every Asset object in the DB
        - moves all `pending_trust` Transactions to `error`
        - setting the most-recently streamed Transaction object's
            `paging_token` attribute to None. This signals to
            watch_transactions to stream using the `"now"` keyword.
        """
        print("\nResetting each asset's most recent paging token")
        for asset in Asset.objects.filter(distribution_seed__isnull=False):
            transaction = (
                Transaction.objects.filter(
                    Q(kind=Transaction.KIND.withdrawal) | Q(kind=Transaction.KIND.send),
                    receiving_anchor_account=asset.distribution_account,
                    status=Transaction.STATUS.completed,
                )
                .order_by("-completed_at")
                .first()
            )
            if transaction:
                transaction.paging_token = None
                transaction.save()
        print("\nPlacing all pending_trust transactions into error status")
        Transaction.objects.filter(status=Transaction.STATUS.pending_trust).update(
            status=Transaction.STATUS.error
        )
        for asset in Asset.objects.filter(issuer__isnull=False):
            print(f"\nIssuing {asset.code}")
            issuer_seed = input(f"Seed for {asset.code} issuer (enter to skip): ")
            if not issuer_seed:
                continue
            try:
                Keypair.from_secret(issuer_seed)
            except Ed25519SecretSeedInvalidError:
                raise CommandError("Bad seed string for issuer account")
            distribution_seed = asset.distribution_seed
            if not distribution_seed:
                distribution_seed = input(
                    f"Seed for {asset.code} distribution account: "
                )
                try:
                    Keypair.from_secret(distribution_seed)
                except Ed25519SecretSeedInvalidError:
                    raise CommandError("Bad seed string for distribution account")
            self.issue(
                **{
                    "asset": asset.code,
                    "issuer_seed": issuer_seed,
                    "distribution_seed": distribution_seed,
                    "issue_amount": Decimal(10000000),
                }
            )

    def get_or_create_accounts(self, account_keypairs: list):
        """
        Get account details from horizon for the specified account_keypairs,
        if the account doesnt exist, create the account
        """
        accounts = {}
        for kp in account_keypairs:
            if not kp:
                continue
            try:
                accounts[kp.public_key] = (
                    self.server.accounts().account_id(kp.public_key).call()
                )
            except NotFoundError:
                print(f"Funding {kp.public_key} ...")
                self.http.request(
                    "GET", f"https://friendbot.stellar.org?addr={kp.public_key}"
                )
                accounts[kp.public_key] = (
                    self.server.accounts().account_id(kp.public_key).call()
                )
        return accounts

    def issue(self, **options):
        """
        Issue the asset specified using the `options` passed to the subcommand
        or function call. The code here is a port of the following project:

        https://github.com/stellar/create-stellar-token

        Users can setup distribution and client accounts for the asset being
        issued as well.
        """
        code = options.get("asset") or "TEST"
        issuer = Keypair.from_secret(
            options.get("issuer_seed") or Keypair.random().secret
        )
        distributor = Keypair.from_secret(
            options.get("distribution_seed") or Keypair.random().secret
        )
        client, client_amount = None, None
        if options.get("client_seed") or options.get("client_amount"):
            client = Keypair.from_secret(
                options.get("client_seed") or Keypair.random().secret
            )
            client_amount = options.get("client_amount") or Decimal(1000)
        issue_amount = options.get("issue_amount") or Decimal(100000)

        print("\nIssuer account public and private keys:")
        print(f"public key: {issuer.public_key}")
        print(f"secret key: {issuer.secret}\n")
        print("Distribution account public and private keys:")
        print(f"public key: {distributor.public_key}")
        print(f"secret key: {distributor.secret}\n")
        print(f"Issuing {issue_amount} {code} to the distribution account")
        if client:
            print("\nClient account public and private keys:")
            print(f"public key: {client.public_key}")
            print(f"secret key: {client.secret}\n")
            print(f"Sending {client_amount} to the client account\n")

        accounts = self.get_or_create_accounts([issuer, distributor, client])

        self.add_balance(code, issue_amount, accounts, distributor, issuer, issuer)
        if client:
            self.add_balance(code, client_amount, accounts, client, distributor, issuer)

        home_domain = input("Home domain for the issuing account (enter to skip): ")
        if home_domain:
            self.set_home_domain(issuer, home_domain)

    def set_home_domain(self, issuer: Keypair, home_domain: str):
        envelope = (
            TransactionBuilder(
                self.server.load_account(issuer.public_key),
                base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
                or self.server.fetch_base_fee(),
                network_passphrase="Test SDF Network ; September 2015",
            )
            .append_set_options_op(home_domain=home_domain)
            .set_timeout(30)
            .build()
        )
        envelope.sign(issuer)
        try:
            self.server.submit_transaction(envelope)
        except BaseHorizonError as e:
            print(
                f"Failed to set {home_domain} as home_domain for {issuer.public_key}."
                f"Result codes: {e.extras.get('result_codes')}"
            )
        else:
            print("Success!")

    def add_balance(self, code, amount, accounts, dest, src, issuer):
        tb = TransactionBuilder(
            self.server.load_account(src.public_key),
            base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
            or self.server.fetch_base_fee(),
            network_passphrase="Test SDF Network ; September 2015",
        )
        balance = self.get_balance(code, issuer.public_key, accounts[dest.public_key])
        if not balance:
            print(f"\nCreating {code} trustline for {dest.public_key}")
            if settings.MAX_TRANSACTION_FEE_STROOPS:
                # halve the base_fee because there are 2 operations
                tb.base_fee = tb.base_fee // 2
            tb.append_change_trust_op(
                asset=StellarSdkAsset(code=code, issuer=issuer.public_key),
                source=dest.public_key,
            )
            payment_amount = amount
        elif Decimal(balance) < amount:
            print(f"\nReplenishing {code} balance to {amount} for {dest.public_key}")
            payment_amount = amount - Decimal(balance)
        else:
            print(
                "Destination account already has more than the amount "
                "specified, skipping\n"
            )
            return

        print(f"Sending {code} payment of {payment_amount} to {dest.public_key}")
        tb.append_payment_op(
            destination=dest.public_key,
            amount=payment_amount,
            asset=StellarSdkAsset(code=code, issuer=issuer.public_key),
            source=src.public_key,
        )
        envelope = tb.set_timeout(30).build()
        if len(tb.operations) == 2:
            # add destination's signature if we're adding a trustline
            envelope.sign(dest)
        envelope.sign(src)
        try:
            self.server.submit_transaction(envelope)
        except BaseHorizonError as e:
            print(
                f"Failed to send {code} payment to {dest.public_key}. "
                f"Result codes: {e.extras.get('result_codes')}"
            )
        else:
            print("Success!")

    def get_balance(self, code, issuer_public_key, json) -> Optional[str]:
        for balance_obj in json["balances"]:
            if (
                balance_obj.get("asset_code") == code
                and balance_obj.get("asset_issuer") == issuer_public_key
            ):
                return balance_obj["balance"]

    def add_asset_to_db(self, **options):
        """
        Add an asset to the database
        """
        asset_code = options.get("asset")
        issuer = options.get("issuer_public")
        distribution_seed = options.get("distribution_seed")
        if not (issuer and asset_code):
            print(f"\ninvalid value in options {options}")
            return
        for asset in Asset.objects.filter(issuer__isnull=False):
            if asset.code == asset_code:
                print(
                    f"\nAsset {asset.code}:{asset.issuer} already exists in the database, skipping..."
                )
                return

        print(f"\nAdding asset {asset_code}:{issuer} to database")
        Asset.objects.create(
            code=asset_code,
            issuer=issuer,
            distribution_seed=distribution_seed,
            sep6_enabled=options.get("sep6_enabled") or False,
            sep24_enabled=options.get("sep24_enabled") or False,
            sep31_enabled=options.get("sep31_enabled") or False,
            sep38_enabled=options.get("sep38_enabled") or False,
            deposit_enabled=options.get("deposit_enabled") or False,
            withdrawal_enabled=options.get("withdrawal_enabled") or False,
            symbol=options.get("symbol") or "$",
        )
        print(f"\nAsset {asset_code}:{issuer} added to database!")

    def delete_asset_from_db(self, **options):
        """
        Delete an asset from the database
        """
        asset_code = options.get("asset")
        issuer = options.get("issuer_public")

        asset_to_delete = Asset.objects.filter(code=asset_code, issuer=issuer).first()
        if not asset_to_delete:
            print(f"\nNo asset matching {asset_code}:{issuer} found to delete")
            return

        asset_to_delete.delete()
        print(f"\nAsset: {asset_code}:{issuer} deleted from the database")
