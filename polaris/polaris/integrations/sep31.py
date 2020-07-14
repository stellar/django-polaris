from typing import Dict, Optional

from polaris.models import Asset, Transaction


class SendIntegration:
    """
    The container class for SEP31 integrations
    """

    def info(self, asset: Asset, lang: str = None) -> Dict:
        """
        .. _info response: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#response

        Return a dictionary containing the `"fields"` object as described in the
        `info response`_ for the given `asset`. If your anchor requires KYC
        information about the sender or receiver, return the `"receiver_sep12_type"`
        or `"sender_sep12_type"` key-value pairs as well. Polaris will provide the
        rest of the fields documented in the info response.

        Descriptions should be in the `lang` passed if supported.
        ::

            return {
                "receiver_sep12_type": "sep31-receiver",
                "sender_sep12_type": "sep31-sender",
                "fields": {
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
            }

        :param asset: the ``Asset`` object for the field values returned
        :param lang: the ISO 639-1 language code of the user
        """
        pass

    def process_send_request(self, params: Dict, transaction_id: str) -> Optional[Dict]:
        """
        .. _customer-info-needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#customer-info-needed-400-bad-request
        .. _transaction-info-needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#transaction-info-needed-400-bad-request
        .. _SEP-12 GET /customer: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md#customer-get

        Use the `params` passed in the request to do any processing of the user
        and requested transaction necessary to facilitate the payment to the
        receiving user.

        Polaris validates that the request includes all the required fields returned
        by ``SendIntegration.info()`` but cannot validate the values. Return ``None``
        if the params passed are valid, otherwise return one of the error dictionaries
        outlined below.

        If the `sender_id` or `receiver_id` values are invalid or the information
        collected for these users is not sufficient to process this request, return
        a dictionary matching the customer-info-needed_ response schema.
        ::

            return {
                "error": "customer_info_needed",
                "type": "sep31-large-amount-sender"
            }

        For example, the above response could be used if the anchor requires additional
        information on the sender when the `amount` is large. The `type` key specifies
        the appropriate type value the client should use for the sender's
        `SEP-12 GET /customer`_ request, and is optional.

        If some optional fields from ``info()`` are missing but needed for this
        transaction, return a dictionary matching the schema described in the
        transaction-info-needed_ response.
        ::

            return {
                "error": "transaction_info_needed",
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
                "error": "invalid 'sender_bank_account' format"
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
        anchors can make requests to protected endpoints.

        :param public_key: the public key of the sending anchor's stellar account
        """
        pass


registered_send_integration = SendIntegration()
