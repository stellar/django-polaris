from typing import Dict, Optional

from polaris.utils import Logger
from polaris.integrations import registered_customer_integration as rci


logger = Logger(__name__)


def validate_403_response(account: Optional[str], integration_response: Dict) -> Dict:
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
        if account:
            more_info_url = rci.more_info_url(account)
            if more_info_url:
                response["more_info_url"] = more_info_url

    else:
        if "fields" not in integration_response:
            logger.error(f"Missing 'fields' for {types[1]}")
            raise ValueError()
        response["fields"] = integration_response["fields"]

    return response
