from typing import Dict, Optional

from polaris.models import Asset, Transaction


class SendIntegration:
    """
    The container class for SEP31 integrations
    """

    def info(self, asset: Asset, lang: str = None) -> Dict:
        """
        .. _info response: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#response

        Return a dictionary you want assigned to the ``"fields"`` key for the given
        `asset` in the `info response`_. Descriptions should be in the `lang` passed
        if supported.
        ::

            return {
                "sender": {
                    "first_name": {
                        "description": "The first name of the sending user"
                    },
                    "last_name": {
                        "description": "The last name of the sending user"
                    }
                },
                "receiver": {
                    "first_name": {
                        "description": "The first name of the receiving user"
                    },
                    "last_name": {
                        "description": "The last name of the receiving user"
                    },
                    "email_address": {
                        "description": "The email address of the receiving user"
                    }
                },
                "transaction":{
                   "routing_number":{
                      "description": "routing number of the destination bank account"
                   },
                   "account_number":{
                      "description": "bank account number of the destination"
                   },
                   "type":{
                      "description": "type of deposit to make",
                      "choices":[
                         "SEPA",
                         "SWIFT"
                      ]
                   }
                }
            }

        :param asset: the ``Asset`` object for the field values returned
        :param lang: the ISO 639-1 language code of the user
        """
        pass

    def process_send_request(self, params: Dict, transaction_id: str) -> Optional[Dict]:
        """
        .. _customer-info-needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#customer-info-needed-400-bad-request

        Use the `params` passed in the request to do any processing of the user
        and requested transaction necessary to facilitate the payment to the
        receiving user.

        Polaris validates that the request includes all the required fields returned
        by ``SendIntegration.info()`` but cannot validate the field values.

        If some optional fields from ``info()`` are missing but needed for this
        transaction, return a dictionary matching the schema described in the
        customer-info-needed_ response.
        ::

            return {
                "error": "customer_info_needed",
                "fields": {
                    "transaction": {
                        "sender_bank_account": {
                            "description": (
                                "The bank account number used by the sender. "
                                "Only required for large transactions."
                            ),
                            "optional": True
                        }
                    }
                }
            }

        If some parameters passed are simply not acceptable, return a dictionary
        containing a single ``"error"`` key-value pair.
        ::

            return {
                "error": "invalid 'email_address' format"
            }

        Finally, if the request parameters are valid, return ``None`` or a
        dictionary containing the key-value pairs of the fields listed in the
        ``"require_receiver_info"`` list if present in the sent request.
        ::

            # For a "require_receiver_info" list of ["email_address"]
            return {
                "email_address": "receiver@email.com"
            }

        Note that the ``Transaction`` object specified by `transaction_id` does not
        exist when this function is called. A transaction with the passed ID will only
        be created if a non-error response is returned.

        :param params: The parameters included in the `/send` request
        :param transaction_id: The UUID string that will be used as the primary key for
            the Transaction object.
        """
        pass

    def process_update_request(self, params: Dict, transaction: Transaction):
        """
        Use the `params` passed in the request to update `transaction` or any
        related data.

        Polaris validates that every field listed in
        ``Transaction.required_info_update`` is present in `params` but cannot
        validate the field values. If a ``ValueError`` is raised, Polaris will
        return a 400 response containing the exception message in the body.

        If no exception is raised, Polaris assumes the update was successful and
        will update the transaction's status back to ``pending_receiver`` as well
        as clear the ``required_info_update`` and ``required_info_message`` fields.

        Once the transaction enters the ``pending_receiver`` status, the
        `execute_outgoing_transactions` process will attempt to send the payment
        to the receiving user. See the
        ``RailsIntegration.execute_outgoing_transaction`` function for more
        information on the lifecycle of a transaction.

        :param params: the parameters sent in the `/update` request
        :param transaction: the ``Transaction`` object that should be updated
        """
        pass

    def valid_sending_anchor(self, public_key: str) -> bool:
        """
        Return ``True`` if `public_key` is a known anchor's stellar account address,
        and ``False`` otherwise. This function ensures that only registered sending
        anchors can make `/send` requests.

        :param public_key: the public key of the sending anchor's stellar account
        """
        pass


registered_send_integration = SendIntegration()
