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
        .. _ObjectDoesNotExist: https://docs.djangoproject.com/en/3.1/ref/exceptions/#objectdoesnotexist

        Return a dictionary matching the response schema outlined in `SEP-12 GET /customer`_
        based on the `params` passed. The key-value pairs in `params` match the arguments
        sent in the request with the exception of ``sep10_client_account``, which will always be
        included in `params` so the anchor can ensure the customer returned was created
        by the same account specified in the corresponding ``PUT /customer`` request.

        Raise a ``ValueError`` if the parameters are invalid, or raise an
        ObjectDoesNotExist_ exception if the customer specified via the ``id`` parameter
        does not exist. An error response with the appropriate status will be sent using
        the message passed to the exception.

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
        in the exception will be passed as the error message in the response. If the request
        specified a customer `id` in the request body but a record with that ID doesn't exist,
        raise a ``django.exceptions.ObjectDoesNotExist`` exception. Polaris will return a 404
        response.

        Return a customer ID that clients can use in future requests, such as a `GET /customer`
        request or a SEP-31 `POST /transactions` request. If the request included an `id`
        parameter, make sure the same id is returned.

        If the required information is provided and the customer has ``Transaction`` objects
        in the ``pending_customer_info_update`` status, all such ``Transaction.status`` values
        should be updated to ``pending_receiver``. Polaris will then call the
        ``execute_outgoing_transaction`` integration function for each updated transaction.

        :param params: request parameters as described in SEP-12_
        """
        pass

    def delete(self, account: str, memo: Optional[str], memo_type: Optional[str]):
        """
        Delete the record of the customer specified by `account`, `memo`, and `memo_type`.
        If such a record does not exist, raise a ``ObjectDoesNotExist`` exception for Polaris
        to return a 404 Not Found response.

        :param account: the stellar account associated with the customer
        :param memo: the optional memo used to create the customer
        :param memo_type: the optional type of the memo used to create to the customer
        """
        pass


registered_customer_integration = CustomerIntegration()
