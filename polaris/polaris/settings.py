"""
Polaris-specific settings. This is not django.conf.settings.
"""
# pylint: disable=invalid-name
import os
import environ
from django.conf import settings
from stellar_sdk.server import Server
from stellar_sdk.keypair import Keypair


env = environ.Env()
env_file = os.path.join(settings.PROJECT_ROOT, ".env")
if os.path.exists(env_file):
    environ.Env.read_env(str(env_file))

SIGNING_SEED, SIGNING_KEY = None, None
if "sep-10" in settings.ACTIVE_SEPS:
    SIGNING_SEED = env("SIGNING_SEED")
    SIGNING_KEY = Keypair.from_secret(SIGNING_SEED).public_key

SERVER_JWT_KEY = None
if any(sep in settings.ACTIVE_SEPS for sep in ["sep-10", "sep-24"]):
    SERVER_JWT_KEY = env("SERVER_JWT_KEY")

STELLAR_NETWORK_PASSPHRASE = env(
    "STELLAR_NETWORK_PASSPHRASE", default="Test SDF Network ; September 2015"
)
HORIZON_URI = env("HORIZON_URI", default="https://horizon-testnet.stellar.org/")
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)
HOST_URL = env("HOST_URL")

LOCAL_MODE = env.bool("LOCAL_MODE", default=False)

# Constants

OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
ACCOUNT_STARTING_BALANCE = str(2.01)
