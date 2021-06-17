import urllib3
from decimal import Decimal
from typing import Optional, Dict
from logging import getLogger

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from stellar_sdk import Keypair, TransactionBuilder, Server
from stellar_sdk.account import Account, Thresholds
from stellar_sdk.exceptions import (
    NotFoundError,
    BaseHorizonError,
    Ed25519SecretSeedInvalidError,
)

from polaris import settings
from polaris.models import Transaction, Asset

logger = getLogger(__name__)


class Command(BaseCommand):
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

    def handle(self, *_args, **options):  # pragma: no cover
        if options.get("subcommands") == "reset":
            self.reset(**options)
        elif options.get("subcommands") == "issue":
            self.issue(**options)

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

        accounts = {}
        for kp in [issuer, distributor, client]:
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
                asset_code=code, asset_issuer=issuer.public_key, source=dest.public_key
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
            asset_code=code,
            asset_issuer=issuer.public_key,
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
        thresholds = Thresholds(
            json["thresholds"]["low_threshold"],
            json["thresholds"]["med_threshold"],
            json["thresholds"]["high_threshold"],
        )
        account = Account(account_id=json["id"], sequence=sequence)
        account.signers = json["signers"]
        account.thresholds = thresholds
        return account

    def get_balance(self, code, issuer_public_key, json) -> Optional[str]:
        for balance_obj in json["balances"]:
            if (
                balance_obj.get("asset_code") == code
                and balance_obj.get("asset_issuer") == issuer_public_key
            ):
                return balance_obj["balance"]
