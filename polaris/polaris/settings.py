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
    code = asset_code.upper()

    try:
        dist_seed = env(f"{code}_DISTRIBUTION_ACCOUNT_SEED")
        iss_address = env(f"{code}_ISSUER_ACCOUNT_ADDRESS")
        assert dist_seed and iss_address
    except (environ.ImproperlyConfigured, AssertionError):
        raise ValueError(f"Missing values for {code}")

    try:
        dist_address = Keypair.from_secret(dist_seed).public_key
    except Ed25519SecretSeedInvalidError:
        raise ValueError(f"Invalid distribution private key for {code}")

    ASSETS[code] = {
        "DISTRIBUTION_ACCOUNT_SEED": dist_seed,
        "DISTRIBUTION_ACCOUNT_ADDRESS": dist_address,
        "ISSUER_ACCOUNT_ADDRESS": iss_address,
    }

STELLAR_NETWORK_PASSPHRASE = env(
    "STELLAR_NETWORK_PASSPHRASE", default="Test SDF Network ; September 2015"
)
HORIZON_URI = env("HORIZON_URI", default="https://horizon-testnet.stellar.org/")
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)
SERVER_JWT_KEY = env("SERVER_JWT_KEY")
OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
ACCOUNT_STARTING_BALANCE = str(2.01)
