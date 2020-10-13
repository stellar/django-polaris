"""
This module implements the logic for the `/.well-known` endpoint.
In particular, this generates the `.toml` file for the anchor server.

The importance of the Stellar TOML file is explained in SEP-0001:
https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
"""

import os

from django.template.loader import get_template
from django.conf import settings as django_settings
from django.utils.encoding import smart_text
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import BaseRenderer
from rest_framework.decorators import api_view, renderer_classes

from polaris import settings
from polaris.integrations import registered_toml_func
from polaris.models import Asset


class PolarisTOMLRenderer(BaseRenderer):
    media_type = "text/plain"
    format = "txt"

    def render(self, data, media_type=None, renderer_context=None):
        template = get_template("polaris/stellar.toml")
        return smart_text(template.render(data))


@api_view(["GET"])
@renderer_classes([PolarisTOMLRenderer])
def generate_toml(request: Request) -> Response:
    """Generate a TOML-formatted string or use the polaris/stellar.toml Template"""
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
    return Response(toml_dict, template_name="polaris/stellar.toml")
