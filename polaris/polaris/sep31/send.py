"""
This module implements the logic for the `/send` endpoint.
This lets a sender initiate a transaction process
"""
# from urllib.parse import urlencode

# from django.urls import reverse
# from django.shortcuts import redirect
# from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.translation import gettext as _

# from rest_framework import status
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
# from stellar_sdk.keypair import Keypair
# from stellar_sdk.exceptions import Ed25519PublicKeyInvalidError

# from polaris import settings
from polaris.utils import (
    render_error_response,
    # Logger,
    # extract_sep9_fields,
    # create_transaction_id,
    # memo_str,
)
# from polaris.sep10.utils import validate_sep10_token
from polaris.sep10.utils import validate_sep10_token
from polaris.models import SEP31Payment
# from polaris.integrations.forms import TransactionForm
# from polaris.locale.utils import validate_language, activate_lang_for_request
from polaris.integrations import (
    registered_sep31_approve_transaction_func as approve_fn
)
import pdb

@api_view(["POST"])
@renderer_classes([JSONRenderer, BrowsableAPIRenderer])
@validate_sep10_token("sep31")
def send(account: str, request: Request) -> Response:
    if not approve_fn(account):
        return render_error_response(_("Transaction not approved"))
    
    return Response({}, status=status.HTTP_200_OK)
