"""
This module implements the logic for the `/.well-known` endpoint.
In particular, this generates the `.toml` file for the anchor server.

The importance of the Stellar TOML file is explained in SEP-0001:
https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
"""

import os

import toml
from django.http.response import HttpResponse
from django.conf import settings as django_settings

from polaris import settings
from polaris.integrations import registered_toml_func
from polaris.models import Asset


def generate_toml(request):
    """Generate the TOML file."""
    toml_dict = {
        "ACCOUNTS": [
            asset.distribution_account
            for asset in Asset.objects.exclude(distribution_seed__isnull=True)
        ],
        "VERSION": "0.1.0",
        "SIGNING_KEY": settings.SIGNING_KEY,
        "NETWORK_PASSPHRASE": settings.STELLAR_NETWORK_PASSPHRASE,
    }

    if "sep-24" in django_settings.POLARIS_ACTIVE_SEPS:
        toml_dict["TRANSFER_SERVER"] = os.path.join(settings.HOST_URL, "sep24")
        toml_dict["TRANSFER_SERVER_SEP0024"] = toml_dict["TRANSFER_SERVER"]
    if "sep-6" in django_settings.POLARIS_ACTIVE_SEPS:
        toml_dict["TRANSFER_SERVER"] = os.path.join(settings.HOST_URL, "sep6")
    if "sep-10" in django_settings.POLARIS_ACTIVE_SEPS:
        toml_dict["WEB_AUTH_ENDPOINT"] = os.path.join(settings.HOST_URL, "auth")
    if "sep-12" in django_settings.POLARIS_ACTIVE_SEPS:
        toml_dict["KYC_SERVER"] = os.path.join(settings.HOST_URL, "kyc")
    if "sep-31" in django_settings.POLARIS_ACTIVE_SEPS:
        toml_dict["DIRECT_PAYMENT_SERVER"] = os.path.join(settings.HOST_URL, "sep31")

    toml_dict.update(registered_toml_func())

    return HttpResponse(toml.dumps(toml_dict), content_type="text/plain")
