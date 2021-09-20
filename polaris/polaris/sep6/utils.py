from typing import Dict

from rest_framework.request import Request

from polaris.utils import getLogger
from polaris.utils import SEP_9_FIELDS
from polaris.integrations import registered_customer_integration as rci
from polaris.models import Transaction
from polaris.sep10.token import SEP10Token
from polaris import settings


logger = getLogger(__name__)


def validate_403_response(
    token: SEP10Token,
    request: Request,
    integration_response: Dict,
    transaction: Transaction,
) -> Dict:
    """
    Ensures the response returned from `process_sep6_request()` matches the definitions
    described in SEP-6. This function can be used for both /deposit and /withdraw
    endpoints since the response schemas are identical.

    Note that this validation function is only for 403 responses. /deposit and /withdraw
    have distinct 200 Success response schemas so the validation for those are done in
    depost.py and withdraw.py.

    :param integration_response: the response dictionary returned from
        `process_sep6_request()`
    :param transaction: the transaction object that should not be saved to the DB
    :return: a new dictionary containing the valid key-value pairs from
        integration_response
    """
    if Transaction.objects.filter(id=transaction.id).exists():
        logger.error(
            "transaction cannot be saved when returning 403 SEP-6 deposit/withdraw response"
        )
        raise ValueError()

    statuses = ["pending", "denied"]
    types = ["customer_info_status", "non_interactive_customer_info_needed"]
    response = {"type": integration_response["type"]}
    if response["type"] not in types:
        logger.error("Invalid 'type' returned from process_sep6_request()")
        raise ValueError()

    elif response["type"] == types[0]:
        if integration_response.get("status") not in statuses:
            logger.error("Invalid 'status' returned from process_sep6_request()")
            raise ValueError()
        response["status"] = integration_response["status"]
        if settings.SEP6_USE_MORE_INFO_URL:
            more_info_url = rci.more_info_url(
                token=token,
                request=request,
                account=token.muxed_account or token.account,
                memo=token.memo,
            )
            response["more_info_url"] = more_info_url

    else:
        if "fields" not in integration_response:
            logger.error(f"missing 'fields' for {types[1]}")
            raise ValueError()
        elif not isinstance(integration_response["fields"], list):
            logger.error(f"invalid 'fields' for {types[1]}")
            raise ValueError()
        elif not all(f in SEP_9_FIELDS for f in integration_response["fields"]):
            logger.error(f"invalid 'fields' for {types[1]}")
            raise ValueError()
        else:
            response["fields"] = integration_response["fields"]

    return response
