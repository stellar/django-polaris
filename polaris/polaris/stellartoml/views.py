"""
This module implements the logic for the `/.well-known` endpoint.
In particular, this generates the `.toml` file for the anchor server.

The importance of the Stellar TOML file is explained in SEP-0001:
https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
"""

import os
import toml
from django.http.response import HttpResponse
from polaris import settings
from polaris.integrations import registered_toml_func


def generate_toml(request):
    """Generate the TOML file."""
    toml_dict = {
        "TRANSFER_SERVER": settings.HOST_URL,
        "WEB_AUTH_ENDPOINT": os.path.join(settings.HOST_URL, "auth"),
        "ACCOUNTS": [
            asset["DISTRIBUTION_ACCOUNT_ADDRESS"] for asset in settings.ASSETS.values()
        ],
        "VERSION": "0.1.0",
        "SIGNING_KEY": settings.SIGNING_KEY,
        "NETWORK_PASSPHRASE": settings.STELLAR_NETWORK_PASSPHRASE,
    }
    toml_dict.update(registered_toml_func())

    return HttpResponse(toml.dumps(toml_dict), content_type="text/plain")
