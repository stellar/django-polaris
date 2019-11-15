"""Helper functions to use across tests."""
import json

from django.conf import settings
from django.http import JsonResponse
from stellar_sdk import Account
from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import NotFoundError


def mock_check_auth_success(request, func):
    """Mocks `helpers.check_auth`, for success."""
    return func(request)


def mock_load_not_exist_account(account_id):
    if account_id != settings.STELLAR_ISSUER_ACCOUNT_ADDRESS and account_id != settings.STELLAR_DISTRIBUTION_ACCOUNT_ADDRESS:
        raise NotFoundError(response=Response(status_code=404, headers={}, url="", text=json.dumps(dict(status=404))))
    return Account(account_id, 1)
