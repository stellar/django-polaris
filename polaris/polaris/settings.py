"""
Polaris-specific settings. This is not django.conf.settings.
"""
# pylint: disable=invalid-name
import os
import environ
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from stellar_sdk.server import Server
from stellar_sdk.keypair import Keypair


def env_or_settings(variable, bool=False):
    try:
        return env.bool(variable) if bool else env(variable)
    except ImproperlyConfigured as e:
        if hasattr(settings, "POLARIS_" + variable):
            return getattr(settings, "POLARIS_" + variable)
        else:
            return None


env = environ.Env()
env_file = os.path.join(getattr(settings, "BASE_DIR", ""), ".env")
if os.path.exists(env_file):
    env.read_env(env_file)
elif hasattr(settings, "POLARIS_ENV_PATH"):
    if os.path.exists(settings.POLARIS_ENV_PATH):
        env.read_env(settings.POLARIS_ENV_PATH)
    else:
        raise ImproperlyConfigured(
            f"Could not find env file at {settings.POLARIS_ENV_PATH}"
        )

SIGNING_SEED, SIGNING_KEY = None, None
if "sep-10" in settings.POLARIS_ACTIVE_SEPS:
    SIGNING_SEED = env_or_settings("SIGNING_SEED")
    SIGNING_KEY = Keypair.from_secret(SIGNING_SEED).public_key

SERVER_JWT_KEY = None
if any(sep in settings.POLARIS_ACTIVE_SEPS for sep in ["sep-10", "sep-24"]):
    SERVER_JWT_KEY = env_or_settings("SERVER_JWT_KEY")

STELLAR_NETWORK_PASSPHRASE = (
    env_or_settings("STELLAR_NETWORK_PASSPHRASE") or "Test SDF Network ; September 2015"
)
HORIZON_URI = env_or_settings("HORIZON_URI") or "https://horizon-testnet.stellar.org/"
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)
HOST_URL = env_or_settings("HOST_URL")

LOCAL_MODE = env_or_settings("LOCAL_MODE", bool=True) or False

# Constants
OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
ACCOUNT_STARTING_BALANCE = str(2.01)
