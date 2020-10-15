"""
This module implements the logic for the `/.well-known` endpoint.
In particular, this generates the `.toml` file for the anchor server.

The importance of the Stellar TOML file is explained in SEP-0001:
https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
"""

import os
import sys

import toml
from django.conf import settings as django_settings
from django.contrib.staticfiles import finders
from django.utils.encoding import smart_text
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import BaseRenderer
from rest_framework.decorators import api_view, renderer_classes

from polaris import settings
from polaris.utils import getLogger
from polaris.integrations import registered_toml_func, get_stellar_toml
from polaris.models import Asset


logger = getLogger(__name__)


class PolarisPlainTextRenderer(BaseRenderer):
    """
    .. _documentation: https://www.django-rest-framework.org/api-guide/renderers/#custom-renderers

    Source copied from django-rest-framework's documentation_
    """

    media_type = "text/plain"
    format = "txt"

    def render(self, data, media_type=None, renderer_context=None):
        return smart_text(data, encoding=self.charset)


@api_view(["GET"])
@renderer_classes([PolarisPlainTextRenderer])
def generate_toml(request: Request) -> Response:
    """Generate a TOML-formatted string"""
    # Define the module variable to reference in-memory constants
    # Check if we've already read the TOML contents
    this = sys.modules[__name__]
    if hasattr(this, "STELLAR_TOML_CONTENTS"):
        return Response(this.STELLAR_TOML_CONTENTS, content_type="text/plain")

    # Check for a static TOML file if the cache is empty and the TOML
    # integration function is not replaced.
    if registered_toml_func is get_stellar_toml:
        static_toml = finders.find("polaris/stellar.toml")
        if static_toml:
            with open(static_toml) as f:
                this.STELLAR_TOML_CONTENTS = f.read()
            return Response(this.STELLAR_TOML_CONTENTS, content_type="text/plain")

    # The anchor uses the registered TOML function, replaced or not
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
    # We could assign content to this.STELLAR_TOML_CONTENTS, but if the anchor hasn't
    # transitioned to the static file approach, it's possible the anchor does not want
    # the TOML contents to be cached.
    content = toml.dumps(toml_dict)

    return Response(content, content_type="text/plain")
