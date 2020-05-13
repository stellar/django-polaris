from typing import Dict, Optional
from polaris.models import Asset


def default_info_func(asset: Asset, lang: Optional[str]) -> Dict:
    """
    .. _/info response: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#response-2

    Replace this function with another by passing it to
    ``register_integrations()`` as described in
    :doc:`Registering Integrations</register_integrations/index>`.

    Return a dictionary containing the `fields` and `types` key-value pairs
    described in the SEP-6 /info response for the asset passed. Raise a
    ``ValueError()`` if `lang` is not supported. For example,
    ::

        if asset.code == "USD":
            return {
                "fields": {
                    "email_address" : {
                        "description": "your email address for transaction status updates",
                        "optional": True
                    },
                    "amount" : {
                        "description": "amount in USD that you plan to deposit"
                    },
                    "type" : {
                        "description": "type of deposit to make",
                        "choices": ["SEPA", "SWIFT", "cash"]
                    }
                },
                "types": {
                    "bank_account": {
                        "fields": {
                            "dest": {"description": "your bank account number" },
                            "dest_extra": { "description": "your routing number" },
                            "bank_branch": { "description": "address of your bank branch" },
                            "phone_number": { "description": "your phone number in case there's an issue" }
                        }
                    },
                    "cash": {
                        "fields": {
                            "dest": {
                                "description": "your email address. Your cashout PIN will be sent here.",
                                "optional": True
                            }
                        }
                    }
                }
            }

    :param asset: ``Asset`` object for which to return the `fields` and `types`
        key-value pairs
    :param lang: the language code the client requested for the `description`
        values in the response
    """
    return {}


registered_info_func = default_info_func
