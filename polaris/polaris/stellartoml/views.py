"""
This module implements the logic for the `/.well-known` endpoint.
In particular, this generates the `.toml` file for the anchor server.

The importance of the Stellar TOML file is explained in SEP-0001:
https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
"""

import toml
from django.http.response import HttpResponse
from polaris import settings
from rest_framework.decorators import api_view
from polaris.models import Asset


def generate_toml(request):
    """Generate the TOML file."""
    toml_dict = {}

    # Globals.
    toml_dict["TRANSFER_SERVER"] = request.build_absolute_uri("/")
    toml_dict["WEB_AUTH_ENDPOINT"] = request.build_absolute_uri("/auth")
    toml_dict["ACCOUNTS"] = [settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS]
    toml_dict["VERSION"] = "0.1.0"

    toml_dict["DOCUMENTATION"] = {
        "ORG_NAME": "Stellar Development Foundation",
        "ORG_URL": "https://stellar.org",
        "ORG_DESCRIPTION": "SEP 24 reference server.",
        "ORG_KEYBASE": "stellar.public",
        "ORG_TWITTER": "StellarOrg",
        "ORG_GITHUB": "stellar",
    }

    toml_dict["CURRENCIES"] = [
        {"code": asset.code, "issuer": settings.STELLAR_ISSUER_ACCOUNT_ADDRESS}
        for asset in Asset.objects.all().iterator()
    ]

    return HttpResponse(toml.dumps(toml_dict), content_type="text/plain")
