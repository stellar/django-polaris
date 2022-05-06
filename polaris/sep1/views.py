"""
This module implements the logic for the `/.well-known` endpoint.
In particular, this generates the `.toml` file for the anchor server.

The importance of the Stellar TOML file is explained in SEP-0001:
https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0001.md
"""

import os

import toml
from django.contrib.staticfiles import finders
from django.utils.encoding import smart_str
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import BaseRenderer
from rest_framework.decorators import api_view, renderer_classes

from polaris import settings
from polaris.utils import getLogger
from polaris.integrations import (
    registered_toml_func,
    get_stellar_toml,
    registered_custody_integration as rci,
)
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
        return smart_str(data, encoding=self.charset)


@api_view(["GET"])
@renderer_classes([PolarisPlainTextRenderer])
def generate_toml(request: Request) -> Response:
    """Generate a TOML-formatted string"""
    if registered_toml_func is get_stellar_toml:
        # integration function is not used, check to see if a static file is defined
        static_toml = None
        if settings.LOCAL_MODE:
            static_toml = finders.find("polaris/local-stellar.toml")
        if not static_toml:
            static_toml = finders.find("polaris/stellar.toml")
        if static_toml:
            with open(static_toml) as f:
                return Response(f.read(), content_type="text/plain")

    # The anchor uses the registered TOML function, replaced or not
    toml_dict = {
        "NETWORK_PASSPHRASE": settings.STELLAR_NETWORK_PASSPHRASE,
    }
    distribution_accounts = []
    for asset in Asset.objects.all():
        try:
            distribution_accounts.append(rci.get_distribution_account(asset))
        except NotImplementedError:
            break
    if distribution_accounts:
        toml_dict["ACCOUNTS"] = distribution_accounts
    if "sep-24" in settings.ACTIVE_SEPS:
        toml_dict["TRANSFER_SERVER"] = os.path.join(settings.HOST_URL, "sep24")
        toml_dict["TRANSFER_SERVER_SEP0024"] = toml_dict["TRANSFER_SERVER"]
    if "sep-6" in settings.ACTIVE_SEPS:
        toml_dict["TRANSFER_SERVER"] = os.path.join(settings.HOST_URL, "sep6")
    if "sep-10" in settings.ACTIVE_SEPS:
        toml_dict["WEB_AUTH_ENDPOINT"] = os.path.join(settings.HOST_URL, "auth")
        toml_dict["SIGNING_KEY"] = settings.SIGNING_KEY
    if "sep-12" in settings.ACTIVE_SEPS:
        toml_dict["KYC_SERVER"] = os.path.join(settings.HOST_URL, "kyc")
    if "sep-31" in settings.ACTIVE_SEPS:
        toml_dict["DIRECT_PAYMENT_SERVER"] = os.path.join(settings.HOST_URL, "sep31")
    if "sep-38" in settings.ACTIVE_SEPS:
        toml_dict["ANCHOR_QUOTE_SERVER"] = os.path.join(settings.HOST_URL, "sep38")

    toml_dict.update(registered_toml_func(request))
    content = toml.dumps(toml_dict)

    return Response(content, content_type="text/plain")
