"""
Polaris-specific settings. This is not django.conf.settings.
"""
# pylint: disable=invalid-name
import os
import environ
from django.conf import settings
from stellar_sdk.server import Server
from stellar_sdk.keypair import Keypair


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

env = environ.Env()
env_file = os.path.join(settings.PROJECT_ROOT, ".env")
if os.path.exists(env_file):
    environ.Env.read_env(str(env_file))

# Stellar Settings
STELLAR_DISTRIBUTION_ACCOUNT_SEED = env("STELLAR_DISTRIBUTION_ACCOUNT_SEED")
STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS = Keypair.from_secret(
    STELLAR_DISTRIBUTION_ACCOUNT_SEED
).public_key
STELLAR_ISSUER_ACCOUNT_ADDRESS = env("STELLAR_ISSUER_ACCOUNT_ADDRESS")
STELLAR_NETWORK_PASSPHRASE = env(
    "STELLAR_NETWORK_PASSPHRASE", default="Test SDF Network ; September 2015"
)
HORIZON_URI = env("HORIZON_URI", default="https://horizon-testnet.stellar.org/")
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)
SERVER_JWT_KEY = env("SERVER_JWT_KEY")
OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
ACCOUNT_STARTING_BALANCE = str(2.01)
