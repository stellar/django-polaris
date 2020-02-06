"""
Polaris-specific settings. This is not django.conf.settings.
"""
# pylint: disable=invalid-name
import os
import environ
from django.conf import settings
from stellar_sdk.server import Server
from stellar_sdk.keypair import Keypair
from stellar_sdk.exceptions import Ed25519SecretSeedInvalidError


env = environ.Env()
env_file = os.path.join(settings.PROJECT_ROOT, ".env")
if os.path.exists(env_file):
    environ.Env.read_env(str(env_file))

try:
    assets = env.list("ASSETS")
    assert len(assets)
except (environ.ImproperlyConfigured, AssertionError):
    raise ValueError("ASSETS must be set in your .env file")

ASSETS = {}
for asset_code in assets:
    try:
        dist_seed = env(f"{asset_code}_DISTRIBUTION_ACCOUNT_SEED")
        iss_address = env(f"{asset_code}_ISSUER_ACCOUNT_ADDRESS")
        assert dist_seed and iss_address
    except AssertionError:
        raise ValueError(f"Environment variable {asset_code} cannot be an empty string")

    try:
        dist_address = Keypair.from_secret(dist_seed).public_key
    except Ed25519SecretSeedInvalidError:
        raise ValueError(f"Invalid distribution private key for {asset_code}")

    ASSETS[asset_code] = {
        "DISTRIBUTION_ACCOUNT_SEED": dist_seed,
        "DISTRIBUTION_ACCOUNT_ADDRESS": dist_address,
        "ISSUER_ACCOUNT_ADDRESS": iss_address,
    }

# The SIGNING_KEY should probably be independent of the assets being anchored,
# but if they are not specified we can use the first distribution account.
SIGNING_SEED = env(
    "SIGNING_SEED", default=list(ASSETS.values())[0]["DISTRIBUTION_ACCOUNT_SEED"]
)
SIGNING_KEY = Keypair.from_secret(SIGNING_SEED).public_key

STELLAR_NETWORK_PASSPHRASE = env(
    "STELLAR_NETWORK_PASSPHRASE", default="Test SDF Network ; September 2015"
)
HORIZON_URI = env("HORIZON_URI", default="https://horizon-testnet.stellar.org/")
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)
SERVER_JWT_KEY = env("SERVER_JWT_KEY")
OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
ACCOUNT_STARTING_BALANCE = str(2.01)
HOST_URL = env("HOST_URL")
