from typing import Dict, Union, Optional


class CustomerIntegration:
    def more_info_url(self, account: str) -> str:
        """
        .. _SEP-6 Customer Information Status: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#4-customer-information-status

        Return a URL the client can open in a browser to view the status of their account
        with the anchor. This URL will be returned in a `SEP-6 Customer Information Status`_
        response. This is optional.

        :param account: the stellar account for the url to be returned
        """
        pass

    def get(self, params: Dict) -> Dict:
        """
        .. _`SEP-12 GET /customer`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md#customer-get

        Return a dictionary matching the response schema outlined in `SEP-12 GET /customer`_
        based on the `params` passed. The key-value pairs in `params` match the arguments
        sent in the request.

        Raise a ``ValueError`` if the parameters are invalid or the transaction specified
        is not found. An error response will be sent using the message passed to the
        exception.

        :param params: request parameters as described in SEP-12
        """
        pass

    def put(self, params: Dict) -> str:
        """
        Update or create a record of the customer information passed. This information can
        then later be queried for when a client requests a deposit or withdraw on behalf of
        the customer.

        If the information passed in `params` is invalid in some way, raise a ``ValueError``
        for Polaris to return a 400 Bad Request response to the client. The message contained
        in the exception will be passed as the error message in the response.

        Return a customer ID that clients can use in future requests, such as a `GET /customer`
        request or a SEP-31 `POST /send` request.

        :param params: request parameters as described in SEP-12_
        """
        pass

    def delete(self, account: str, memo: Optional[str], memo_type: Optional[str]):
        """
        Delete the record of the customer specified by `account`, `memo`, and `memo_type`.
        If such a record does not exist, raise a ``ValueError`` for Polaris to return a
        404 Not Found response.

        :param account: the stellar account associated with the customer
        :param memo: the optional memo used to create the customer
        :param memo_type: the optional type of the memo used to create to the customer
        """
        pass


registered_customer_integration = CustomerIntegration()
