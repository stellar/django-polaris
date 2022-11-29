import argparse
import requests
import uuid
import time

from stellar_sdk import Asset as StellarSdkAsset
from stellar_sdk import Keypair, TransactionBuilder, Server

from stellar_sdk.exceptions import BaseHorizonError, NotFoundError


CIRCLE_USDC_ASSET_CODE = "USDC"
CIRCLE_USDC_TESTNET_ISSUER = "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"


class GetCircleUsd:
    def __init__(self):
        self.server = Server("https://horizon-testnet.stellar.org")

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

    def get_balance(self, code, issuer_public_key, json):
        for balance_obj in json["balances"]:
            if (
                balance_obj.get("asset_code") == code
                and balance_obj.get("asset_issuer") == issuer_public_key
            ):
                return balance_obj["balance"]
        return None

    def create_trustline(
        self, code: str, asset_issuer_public_key: str, distribution: Keypair
    ):
        accounts = self.get_or_create_accounts([distribution])
        balance = self.get_balance(
            code, asset_issuer_public_key, accounts[distribution.public_key]
        )
        if balance:
            print(f"\nTrustline to {code}:{asset_issuer_public_key} already exists")
            return
        print(f"\nCreating trustline to {code}:{asset_issuer_public_key}")
        tb = TransactionBuilder(
            self.server.load_account(distribution.public_key),
            base_fee=self.server.fetch_base_fee(),
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
            exit()
        else:
            print(f"Success! Trustline to {code}:{asset_issuer_public_key} created!")

    def get_largest_circle_wallet(self, api_key: str):
        """
        Get the Circle testnet wallet with the largest USD balance
        """
        url = "https://api-sandbox.circle.com/v1/wallets"

        headers = {"accept": "application/json", "authorization": f"Bearer {api_key}"}

        response = requests.get(url, headers=headers)
        wallets = response.json().get("data")
        max_wallet_balance = ("", float(0))
        for wallet in wallets:
            for balance in wallet["balances"]:
                if (
                    balance["currency"] == "USD"
                    and float(balance["amount"]) > max_wallet_balance[1]
                ):
                    max_wallet_balance = (wallet["walletId"], float(balance["amount"]))
        print(f"\nLargest circle wallet: {max_wallet_balance}")
        return max_wallet_balance

    def get_circle_usdc(self, api_key: str, distribution_seed: str, amount: float):
        """
        Add Circle USDC to the distribution account
        """
        distribution = Keypair.from_secret(distribution_seed)
        wallet_id, balance = self.get_largest_circle_wallet(api_key)

        if balance < amount:
            print(
                f"Available Circle balance: {balance} is less than the requested amount: {amount}, skipping..."
            )
            return
        print(f"\nUsing circle wallet: {wallet_id} with USD balance: {balance}")

        self.create_trustline(
            CIRCLE_USDC_ASSET_CODE, CIRCLE_USDC_TESTNET_ISSUER, distribution
        )

        url = "https://api-sandbox.circle.com/v1/transfers"

        payload = {
            "source": {"type": "wallet", "id": wallet_id},
            "destination": {
                "type": "blockchain",
                "chain": "XLM",
                "address": distribution.public_key,
            },
            "amount": {"amount": str(amount), "currency": "USD"},
            "idempotencyKey": str(uuid.uuid4()),
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        }
        print("\nSending request for USDC to Circle...")
        response = requests.post(url, json=payload, headers=headers)
        print(f"\nResponse: {response.json()}")
        transfer_id = response.json()["data"]["id"]
        # poll status of Circle transaction
        url = f"https://api-sandbox.circle.com/v1/transfers/{transfer_id}?returnIdentities=false"

        headers = {"accept": "application/json", "authorization": f"Bearer {api_key}"}
        timeout_seconds = 60
        start = time.time()
        while (timeout_seconds + start) > time.time():
            response = requests.get(url, headers=headers)
            data = response.json()["data"]
            status = data["status"]
            print(f"\npolling status of Circle transfer {transfer_id}: {status}")
            if status == "complete":
                print("transfer complete!")
                return
            elif status == "failed":
                error_code = data["errorCode"]
                print(f"transfer failed, error code: {error_code}")
                return
            time.sleep(1)

        print(f"\nPolling Circle transaction timed out after {timeout_seconds} seconds")


if __name__ == "__main__":
    """
    -h, --help            show this help message and exit
    --amount AMOUNT, -a AMOUNT
                          the amount of USDC to add to the distribution account
    --distribution-seed DISTRIBUTION_SEED, -d DISTRIBUTION_SEED
                          the distribution account's secret key
    --api-key API_KEY, -k API_KEY
                          the Circle API key
    """
    get_usdc_parser = argparse.ArgumentParser()
    get_usdc_parser.add_argument(
        "--amount",
        help="amount of USDC to get from Circle and add to the distribution account",
        required=True,
    )
    get_usdc_parser.add_argument(
        "--distribution-seed",
        help="the anchors distribution seed to send the USDC to",
        required=True,
    )
    get_usdc_parser.add_argument("--api-key", help="Circle API key", required=True)

    args = get_usdc_parser.parse_args()

    app = GetCircleUsd()

    app.get_circle_usdc(args.api_key, args.distribution_seed, float(args.amount))
