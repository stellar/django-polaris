"""
Polaris-specific settings. This is not django.conf.settings.
"""
import os
import environ
from urllib.parse import urlparse
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from stellar_sdk.server import Server
from stellar_sdk.keypair import Keypair


def env_or_settings(variable, bool=False, list=False):
    try:
        if bool:
            return env.bool(variable)
        elif list:
            return env.list(variable)
        else:
            return env(variable)
    except ImproperlyConfigured:
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
    try:
        SIGNING_KEY = Keypair.from_secret(SIGNING_SEED).public_key
    except ValueError:
        raise ImproperlyConfigured("Invalid SIGNING_SEED")

SERVER_JWT_KEY = None
if any(sep in settings.POLARIS_ACTIVE_SEPS for sep in ["sep-10", "sep-24"]):
    SERVER_JWT_KEY = env_or_settings("SERVER_JWT_KEY")

STELLAR_NETWORK_PASSPHRASE = (
    env_or_settings("STELLAR_NETWORK_PASSPHRASE") or "Test SDF Network ; September 2015"
)

HORIZON_URI = env_or_settings("HORIZON_URI") or "https://horizon-testnet.stellar.org"
if not HORIZON_URI.startswith("http"):
    raise ImproperlyConfigured("HORIZON_URI must include a protocol (http or https)")
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)

HOST_URL = env_or_settings("HOST_URL")
if not HOST_URL.startswith("http"):
    raise ImproperlyConfigured("HOST_URL must include a protocol (http or https)")

SEP10_HOME_DOMAINS = env_or_settings("SEP10_HOME_DOMAINS", list=True) or [
    urlparse(HOST_URL).netloc
]
if any(d.startswith("http") for d in SEP10_HOME_DOMAINS):
    raise ImproperlyConfigured("SEP10_HOME_DOMAINS must only be hostnames")

LOCAL_MODE = env_or_settings("LOCAL_MODE", bool=True) or False

# Constants
OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
ACCOUNT_STARTING_BALANCE = str(2.01)
