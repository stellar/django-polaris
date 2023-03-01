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


def env_or_settings(variable, required=True, bool=False, list=False, int=False):
    try:
        if bool:
            return env.bool(variable)
        elif list:
            return env.list(variable)
        elif int:
            return env.int(variable)
        else:
            return env(variable)
    except ImproperlyConfigured as e:
        if hasattr(settings, "POLARIS_" + variable):
            return getattr(settings, "POLARIS_" + variable)
        elif required:
            raise e
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

accepted_seps = [
    "sep-1",
    "sep-6",
    "sep-6",
    "sep-10",
    "sep-12",
    "sep-24",
    "sep-31",
    "sep-38",
]
ACTIVE_SEPS = env_or_settings("ACTIVE_SEPS", list=True)
for i, sep in enumerate(ACTIVE_SEPS):
    if sep.lower() not in accepted_seps:
        raise ImproperlyConfigured(
            f"Unrecognized value in ACTIVE_SEPS list: {sep}; Accepted values: {accepted_seps}"
        )
    ACTIVE_SEPS[i] = sep.lower()

SIGNING_SEED, SIGNING_KEY = None, None
if "sep-10" in ACTIVE_SEPS:
    SIGNING_SEED = env_or_settings("SIGNING_SEED")
    try:
        SIGNING_KEY = Keypair.from_secret(SIGNING_SEED).public_key
    except ValueError:
        raise ImproperlyConfigured("Invalid SIGNING_SEED")

SERVER_JWT_KEY = None
if any(sep in ACTIVE_SEPS for sep in ["sep-10", "sep-24"]):
    SERVER_JWT_KEY = env_or_settings("SERVER_JWT_KEY")

STELLAR_NETWORK_PASSPHRASE = (
    env_or_settings("STELLAR_NETWORK_PASSPHRASE", required=False)
    or "Test SDF Network ; September 2015"
)

HORIZON_URI = (
    env_or_settings("HORIZON_URI", required=False)
    or "https://horizon-testnet.stellar.org"
)
if not HORIZON_URI.startswith("http"):
    raise ImproperlyConfigured("HORIZON_URI must include a protocol (http or https)")
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)

LOCAL_MODE = env_or_settings("LOCAL_MODE", bool=True, required=False) or False

HOST_URL = env_or_settings("HOST_URL")
if not HOST_URL.startswith("http"):
    raise ImproperlyConfigured("HOST_URL must include a protocol (http or https)")
elif LOCAL_MODE and HOST_URL.startswith("https"):
    raise ImproperlyConfigured("HOST_URL uses HTTPS but LOCAL_MODE only supports HTTP")
elif not LOCAL_MODE and not HOST_URL.startswith("https"):
    raise ImproperlyConfigured("HOST_URL uses HTTP but LOCAL_MODE is off")

SEP10_HOME_DOMAINS = env_or_settings(
    "SEP10_HOME_DOMAINS", list=True, required=False
) or [urlparse(HOST_URL).netloc]
if any(d.startswith("http") for d in SEP10_HOME_DOMAINS):
    raise ImproperlyConfigured("SEP10_HOME_DOMAINS must only be hostnames")

MAX_TRANSACTION_FEE_STROOPS = env_or_settings(
    "MAX_TRANSACTION_FEE_STROOPS", int=True, required=False
)

CALLBACK_REQUEST_TIMEOUT = (
    env_or_settings("CALLBACK_REQUEST_TIMEOUT", int=True, required=False) or 3
)
CALLBACK_REQUEST_DOMAIN_DENYLIST = (
    env_or_settings("CALLBACK_REQUEST_DOMAIN_DENYLIST", list=True, required=False) or []
)

SEP6_USE_MORE_INFO_URL = (
    env_or_settings("SEP6_USE_MORE_INFO_URL", bool=True, required=False) or False
)

SEP10_CLIENT_ATTRIBUTION_REQUIRED = env_or_settings(
    "SEP10_CLIENT_ATTRIBUTION_REQUIRED", bool=True, required=False
)
SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT = (
    env_or_settings(
        "SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT", int=True, required=False
    )
    or 3
)
SEP10_CLIENT_ATTRIBUTION_ALLOWLIST = env_or_settings(
    "SEP10_CLIENT_ATTRIBUTION_ALLOWLIST", list=True, required=False
)
SEP10_CLIENT_ATTRIBUTION_DENYLIST = env_or_settings(
    "SEP10_CLIENT_ATTRIBUTION_DENYLIST", list=True, required=False
)

ADDITIVE_FEES_ENABLED = (
    env_or_settings("ADDITIVE_FEES_ENABLED", bool=True, required=False) or False
)

# Constants
OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
OPERATION_SEND = "send"
ACCOUNT_STARTING_BALANCE = str(2.01)
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

INTERACTIVE_JWT_EXPIRATION = (
    env_or_settings("INTERACTIVE_JWT_EXPIRATION", int=True, required=False) or 30
)
if INTERACTIVE_JWT_EXPIRATION <= 0:
    raise ImproperlyConfigured("INTERACTIVE_JWT_EXPIRATION must be positive")
