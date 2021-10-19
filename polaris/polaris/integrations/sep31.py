from typing import Dict, Optional, List

from rest_framework.request import Request

from polaris.models import Asset, Transaction
from polaris.sep10.token import SEP10Token


class SEP31ReceiverIntegration:
    """
    The container class for SEP31 integrations
    """

    def info(
        self,
        request: Request,
        asset: Asset,
        lang: str = None,
        *args: List,
        **kwargs: Dict
    ) -> Dict:
        """
        .. _info response: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#response

        Return a dictionary containing the ``"fields"`` and `"sep12"` objects as described
        in the `info response`_ for the given `asset`. Polaris will provide the rest of the
        fields documented in the info response.

        Descriptions should be in the `lang` passed if supported.
        ::

            return {
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
                },
                "sep12": {
                    "sender": {
                        "types": {
                            "sep31-sender": {
                                "description": "the only SEP-12 type for SEP-31 sending customers"
                            }
                        }
                    },
                    "receiver": {
                        "types": {
                            "sep31-receiver-cash-pickup": {
                                "description": "recipients who will pick up cash at physical locations"
                            },
                            "sep31-receiver-bank-transfer": {
                                "description" : "recipients who would like to receive funds via direct bank transfer"
                            }
                        }
                    }
                }
            }

        :param request: the ``rest_framework.request.Request`` instance
        :param asset: the ``Asset`` object for the field values returned
        :param lang: the ISO 639-1 language code of the user
        """
        raise NotImplementedError()

    def process_post_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ) -> Optional[Dict]:
        """
        .. _customer-info-needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#customer-info-needed-400-bad-request
        .. _transaction-info-needed: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0031.md#transaction-info-needed-400-bad-request
        .. _SEP-12 GET /customer: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md#customer-get

        Use the `params` passed in the request to do any processing of the user
        and requested transaction necessary to facilitate the payment to the
        receiving user. If the arguments are valid, save ``transaction`` and link it
        to your other models. If the transaction is saved but an error response is
        returned Polaris will return a 500 response to the user.

        If you'd like the user to send ``Transaction.amount_in`` `plus the fee amount`,
        add the amount charged as a fee to ``Transaction.amount_in`` and
        ``Transaction.amount_expected`` here.

        While not required per SEP-31, it is encouraged to also populate
        ``Transaction.amount_fee``, ``Transaction.fee_asset`` (if ``Transaction.quote``
        is not ``None``), and ``Transaction.amount_out`` here as well. Note that the
        amount sent over the Stellar Network could differ from the amount specified
        in this API call, so fees and the amount delievered may have to be recalculated
        in ``RailsIntegration.execute_outgoing_transaction()``.

        Also note that if your anchor service supports SEP-38, ``Transaction.quote``
        may be a firm or indicative ``Quote`` model instance representing the requested
        exchange of on and off-chain assets. If ``Quote.type == Quote.TYPE.indicative``,
        it is not yet saved to the database and Polaris will save it if a success response
        is returned.

        Polaris validates that the request includes all the required fields returned
        by ``SEP31ReceiverIntegration.info()`` but cannot validate the values. Return
        ``None`` if the params passed are valid, otherwise return one of the error
        dictionaries outlined below.

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

        :param token: The ``SEP10Token`` instance representing the authenticated session
        :param request: The ``rest_framework.request.Request`` instance
        :param params: The parameters included in the `/transaction` request
        :param transaction: the ``Transaction`` object representing the transaction being processed
        """
        raise NotImplementedError()

    def process_patch_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args: List,
        **kwargs: Dict
    ):
        """
        Use the `params` passed in the request to update `transaction` or any
        related data.

        Polaris validates that every field listed in
        ``Transaction.required_info_updates`` is present in `params` but
        cannot validate the values. If a ``ValueError`` is raised, Polaris will
        return a 400 response containing the exception message in the body.

        If no exception is raised, Polaris assumes the update was successful and
        will update the transaction's status back to ``pending_receiver`` as well
        as clear the ``required_info_updates`` and ``required_info_message`` fields.

        Once the transaction enters the ``pending_receiver`` status, the
        `execute_outgoing_transactions` process will attempt to send the payment
        to the receiving user. See the
        ``RailsIntegration.execute_outgoing_transaction`` function for more
        information on the lifecycle of a transaction.

        :param token: The ``SEP10Token`` instance representing the authenticated session
        :param request: the ``rest_framework.request.Request`` instance
        :param params: the request body of the `PATCH /transaction` request
        :param transaction: the ``Transaction`` object that should be updated
        """
        raise NotImplementedError()

    def valid_sending_anchor(
        self,
        token: SEP10Token,
        request: Request,
        public_key: str,
        *args: List,
        **kwargs: Dict
    ) -> bool:
        """
        Return ``True`` if `public_key` is a known anchor's stellar account address,
        and ``False`` otherwise. This function ensures that only registered sending
        anchors can make requests to protected endpoints.

        :param token: The ``SEP10Token`` instance representing the authenticated session
        :param request: the ``rest_framework.request.Request`` instance
        :param public_key: the public key of the sending anchor's stellar account
        """
        raise NotImplementedError()


registered_sep31_receiver_integration = SEP31ReceiverIntegration()
