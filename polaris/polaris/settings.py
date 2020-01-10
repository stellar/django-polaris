"""
Polaris-specific settings. This is not django.conf.settings.
"""
# pylint: disable=invalid-name
import os
import yaml
from django.conf import settings
from stellar_sdk.server import Server
from stellar_sdk.keypair import Keypair


config_filepath = os.path.join(settings.PROJECT_ROOT, "config.yml")
try:
    config = yaml.safe_load(open(config_filepath).read())
except FileNotFoundError:
    raise ValueError("Missing config.yml file.")
except yaml.YAMLError as e:
    raise ValueError(f"Error parsing yaml file: {str(e)}")

if not config.get("assets"):
    raise ValueError("You must provide at least one asset to anchor")
for asset_type, values in config["assets"].items():
    if not (
        values.get("distribution_account_seed") and values.get("issuer_account_address")
    ):
        raise ValueError(f"Missing values for {asset_type}")

# Stellar Settings
ASSETS = {
    asset_type.upper(): {
        "DISTRIBUTION_ACCOUNT_SEED": values.get("distribution_account_seed"),
        "DISTRIBUTION_ACCOUNT_ADDRESS": Keypair.from_secret(
            values.get("distribution_account_seed")
        ).public_key,
        "ISSUER_ACCOUNT_ADDRESS": values.get("issuer_account_address"),
    }
    for asset_type, values in config.get("assets", {}).items()
}
STELLAR_NETWORK_PASSPHRASE = config.get(
    "stellar_network_passphrase", "Test SDF Network ; September 2015"
)
HORIZON_URI = config.get("horizon_uri", "https://horizon-testnet.stellar.org/")
HORIZON_SERVER = Server(horizon_url=HORIZON_URI)
SERVER_JWT_KEY = config.get("secret_jwt_key")
OPERATION_DEPOSIT = "deposit"
OPERATION_WITHDRAWAL = "withdraw"
ACCOUNT_STARTING_BALANCE = str(2.01)
