from jwt import InvalidIssuerError
import urllib3
import requests
import uuid
import time
from decimal import Decimal
from typing import Optional, Dict
from logging import getLogger

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from stellar_sdk import Keypair, TransactionBuilder, Server, keypair
from stellar_sdk import Asset as StellarSdkAsset
from stellar_sdk.account import Account, Thresholds
from stellar_sdk.exceptions import (
    NotFoundError,
    BaseHorizonError,
    Ed25519SecretSeedInvalidError,
)

from polaris import settings
from polaris.models import Transaction, Asset

logger = getLogger(__name__)

CIRCLE_USDC_ASSET_CODE = "USDC"
CIRCLE_USDC_TESTNET_ISSUER = "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"



class Command(BaseCommand):
    """
    The testnet command comes with two subcommands, ``issue`` and ``reset``.

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
    
    add-asset
        -h, --help           show this help message and exit
        --asset ASSET, -a ASSET
                             the code of the asset issued
        --issuer-public ISSUER_PUBLIC, -i ISSUER_PUBLIC
                             the issuer's public key
        --distribution-seed  DISTRIBUTION_SEED, -d DISTRIBUTION_SEED
                             the distribution account's secret key
        --sep24-disabled     (Optional) flag to disable sep24 for this asset
        --deposit-disabled   (Optional) flag to disable deposits for this asset
        --withdrawl-disabled (Optional) flag to disable withdrawls for this asset
    
    delete-asset
        -h, --help            show this help message and exit
        --asset ASSET, -a ASSET
                              the code of the asset to be deleted
        --issuer-public ISSUER_PUBLIC, -i ISSUER_PUBLIC
                              the issuer's public key
    
    get-usdc
        -h, --help            show this help message and exit
        --amount AMOUNT, -a AMOUNT
                              the amount of USDC to add to the distribution account
        --distribution-seed DISTRIBUTION_SEED, -d DISTRIBUTION_SEED
                              the distribution account's secret key
        --api-key API_KEY, -k API_KEY
                              the Circle API key
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_parser = None
        self.issue_parser = None
        self.server = Server("https://horizon-testnet.stellar.org")
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
            "--distribution-seed", help="the anchors distribution seed for this asset", required=True
        )
        self.add_asset_parser.add_argument(
            "--sep24-disabled", help="disabled sep24 for this asset", action='store_false'
        )
        self.add_asset_parser.add_argument(
            "--deposit-disabled", help="disabled deposits for this asset", action='store_false'
        )
        self.add_asset_parser.add_argument(
            "--withdrawl-disabled", help="disabled withdrawls for this asset", action='store_false'
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

        self.get_usdc_parser = subparsers.add_parser(
            "get-usdc", help="a sub-command for adding more USDC to the distribution account"
        )
        self.get_usdc_parser.add_argument(
            "--amount", help="amount of USDC to get from Circle and add to the distribution account", required=True
        )
        self.get_usdc_parser.add_argument(
            "--distribution-seed", help="the anchors distribution seed to send the USDC to", required=True
        )       
        self.get_usdc_parser.add_argument(
            "--api-key", help="Circle API key", required=True
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
        elif options.get("subcommands") == "get-usdc":
            self.get_circle_usdc(**options)
        

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

    def account_from_json(self, json):
        sequence = int(json["sequence"])
        account = Account(account=json["id"], sequence=sequence, raw_data=json)
        return account

    def get_balance(self, code, issuer_public_key, json) -> Optional[str]:
        for balance_obj in json["balances"]:
            if (
                balance_obj.get("asset_code") == code
                and balance_obj.get("asset_issuer") == issuer_public_key
            ):
                return balance_obj["balance"]

    def create_trustline(self, code :str, asset_issuer_public_key: str, distribution: Keypair):
        accounts = self.get_or_create_accounts([distribution])
        balance = self.get_balance(code, asset_issuer_public_key, accounts[distribution.public_key])
        if balance:
            print(f"\nTrustline to {code}:{asset_issuer_public_key} already exists")
            return
        print(f"\nCreating trustline to {code}:{asset_issuer_public_key}")
        tb = TransactionBuilder(
            self.server.load_account(distribution.public_key),
            base_fee=settings.MAX_TRANSACTION_FEE_STROOPS
            or self.server.fetch_base_fee(),
            network_passphrase="Test SDF Network ; September 2015",
        )
        tb.append_change_trust_op(
            asset=StellarSdkAsset(code=code, issuer=asset_issuer_public_key),
            source=distribution.public_key,
        )
        envelope = tb.set_timeout(30).build()
        envelope.sign(distribution)
        try:
            self.server.submit_transaction(envelope)
        except BaseHorizonError as e:
            print(
                f"Failed to create trustline "
                f"Result codes: {e.extras.get('result_codes')}"
            )
        else:
            print(f"Success! Trustline to {code}:{asset_issuer_public_key} created!")

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
                print(f"\nAsset {asset_code}:{issuer} already exists in the database, skipping...")
                return
        
        print(f"\nAdding asset {asset_code}:{issuer} to database")
        Asset.objects.create(
            code=asset_code,
            issuer=issuer,
            distribution_seed=distribution_seed,
            sep24_enabled=options.get("sep24_enabled") or True,
            deposit_enabled=options.get("deposit_enabled") or True,
            withdrawal_enabled=options.get("withdrawal_enabled") or True,
            symbol="$"
        )
        print(f"Asset {asset_code}:{issuer} added to database")
    
    def delete_asset_from_db(self, **options):
        """
        Delete an asset from the database
        """
        asset_code = options.get("asset")
        issuer = options.get("issuer_public")
        
        asset_to_delete = Asset.objects.filter(code=asset_code, issuer=issuer).first()
        if not asset_to_delete:
            print("\nNo asset matching {asset_code}:{issuer} found to delete")
            return
        
        asset_to_delete.delete()
        print(f"\nAsset: {asset_code}:{issuer} deleted from the database")
        
    def get_largest_circle_wallet(self, api_key: str):
        """
        Get the Circle testnet wallet with the largest USD balance
        """
        url = "https://api-sandbox.circle.com/v1/wallets"

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {api_key}"
        }

        response = requests.get(url, headers=headers)
        wallets = response.json().get("data")
        max_wallet_balance = ("", float(0))  
        for wallet in wallets:
            for balance in wallet["balances"]:
                if balance["currency"] == "USD" and float(balance["amount"]) > max_wallet_balance[1]:
                    max_wallet_balance = (wallet["walletId"], float(balance["amount"]))
        print(f"\nLargest circle wallet: {max_wallet_balance}")
        return max_wallet_balance

    def get_circle_usdc(self, **options):
        """
        Add Circle USDC to the distribution account
        """
        api_key = options.get("api_key")
        amount = float(options.get("amount"))
        distribution_seed = options.get("distribution_seed")
        distribution = Keypair.from_secret(distribution_seed)
        wallet_id, balance = self.get_largest_circle_wallet(api_key)

        if balance < amount:
            print(f"Available Circle balance: {balance} is less than the requested amount: {amount}, skipping...")
            return
        print(f"\nUsing circle wallet: {wallet_id} with USD balance: {balance}")

        self.create_trustline(CIRCLE_USDC_ASSET_CODE, CIRCLE_USDC_TESTNET_ISSUER, distribution)

        url = "https://api-sandbox.circle.com/v1/transfers"

        payload = {
            "source": {
                "type": "wallet",
                "id": wallet_id
            },
            "destination": {
                "type": "blockchain",
                "chain": "XLM",
                "address": distribution.public_key
            },
            "amount": {
                "amount": str(amount),
                "currency": "USD"
            },
            "idempotencyKey": str(uuid.uuid4())
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}"
        }

        response = requests.post(url, json=payload, headers=headers)
        transfer_id = response.json()["data"]["id"]
        # poll status of Circle transaction
        url = f"https://api-sandbox.circle.com/v1/transfers/{transfer_id}?returnIdentities=false"

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {api_key}"
        }
        timeout_seconds = 60
        start = time.time()
        while (timeout_seconds + start) > time.time():
            response = requests.get(url, headers=headers)
            data = response.json()["data"]
            status = data["status"]
            if status == "completed":
                print("transfer complete!")
                return
            elif status == "failed":
                error_code = data["errorCode"]
                print(f"transfer failed, error code: {error_code}")
                return
            time.sleep(1)

        print(f"\nPolling Circle transaction timed out after {timeout_seconds} seconds")