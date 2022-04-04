from typing import Optional, List, Dict

from rest_framework.request import Request

from polaris.sep10.token import SEP10Token


class CustomerIntegration:
    def more_info_url(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        *args: List,
        memo: Optional[int] = None,
        **kwargs: Dict
    ) -> str:
        """
        .. _SEP-6 Customer Information Status: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md#4-customer-information-status

        Return a URL the client can open in a browser to view the status of their account
        with the anchor. This URL will be returned in a `SEP-6 Customer Information Status`_
        response. This is optional.

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framework.request.Request`` instance
        :param account: the stellar or muxed account for the url to be returned
        :param memo: the ID memo used to identify the user of the shared Stellar account
        """
        raise NotImplementedError()

    def get(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        *args: List,
        **kwargs: Dict
    ) -> Dict:
        """
        .. _`SEP-12 GET /customer`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md#customer-get
        .. _ObjectDoesNotExist: https://docs.djangoproject.com/en/3.1/ref/exceptions/#objectdoesnotexist

        Return a dictionary matching the response schema outlined in `SEP-12 GET /customer`_
        based on the `params` passed.

        Raise a ``ValueError`` if the parameters are invalid, or raise an
        ObjectDoesNotExist_ exception if the customer specified via the ``id`` parameter
        does not exist. An error response with the appropriate status will be sent using
        the message passed to the exception.

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framework.request.Request`` instance
        :param params: request parameters as described in SEP-12
        """
        raise NotImplementedError()

    def put(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        *args: List,
        **kwargs: Dict
    ) -> str:
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

        If the anchor requires verification of values passed in `params`, such as
        ``mobile_number`` or ``email_address``, the anchor should initate the verification
        process in this function and ensure the next call to ``GET /customer`` contains the
        field requiring verification with a ``VERIFICATION_REQUIRED`` status. Unless the anchor
        expects users to verify the field value in some other manner, such as opening a
        confirmation link sent via email, client applications will eventually make a call to
        ``PUT /customer/verification`` to return the verification codes sent as a result of the
        initial call to ``PUT /customer``.

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framework.request.Request`` instance
        :param params: request parameters as described in SEP-12
        :raises: ValueError or ObjectDoesNotExist
        """
        raise NotImplementedError()

    def delete(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        memo: Optional[str],
        memo_type: Optional[str],
        *args: List,
        **kwargs: Dict
    ):
        """
        Delete the record of the customer specified by `account`, `memo`, and `memo_type`.
        If such a record does not exist, raise a ``ObjectDoesNotExist`` exception for Polaris
        to return a 404 Not Found response.

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framework.request.Request`` instance
        :param account: the stellar or muxed account associated with the customer
        :param memo: the optional memo used to create the customer
        :param memo_type: the optional type of the memo used to create to the customer
        """
        raise NotImplementedError()

    def callback(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        *args: List,
        **kwargs: Dict
    ):
        """
        Save the URL provided in association with the user identified by the parameters sent
        in the request. The anchor is responsible for making POST requests containing the
        response body of a GET request to the saved URL whenever the SEP-12 status of the
        customer changes. Polaris does not manage an anchor's customer data and therefore
        cannot make these requests.

        Client applications may register callback URLs if the application does not have the
        ability to poll the ``GET /customer`` endopoint at any time, which requires SEP-10
        authentication (and consequently the relevant account's signature).

        If the customer specified does not exist, raise an ``ObjectDoesNotExist``. If the
        URL is provided is invalid in some way, raise a ``ValueError``.

        If this function is not implemented, Polaris will respond with a 501 Not Implemented.

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framework.request.Request`` instance
        :param params: request parameters as described in SEP-12
        :raises: ValueError or django.core.exceptions.ObjectDoesNotExist
        """
        raise NotImplementedError()

    def put_verification(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        params: Dict,
        *args: List,
        **kwargs: Dict
    ) -> Dict:
        """
        .. _`endpoint specification`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md#customer-put-verification

        Validate the values, typically verification codes, passed in `params` for the
        customer identified by ``params["id"]``. See the `endpoint specification`_ for
        more information on the request format.

        Anchors may return fields from ``GET /customer`` requests with the
        ``VERIFICATION_REQUIRED`` status if the anchor requires the user to verify a
        SEP-9 field value provided in a previous call to ``PUT /customer``. The most
        common field needing verification is `mobile_number`. This function will be
        called when the client passes the verification value back to the anchor.

        If the validation values are correct, return a dictionary that is identical to
        what would be returned for a call to ``GET /customer``.

        If any of the validation values are incorrect, raise a ``ValueError`` and
        Polaris will raise a 400 Bad Request.

        If the customer specified by ``params["id"]`` does not exist, or the authenticated
        ``account`` does not match Stellar account associated with the ID, raise an
        ``ObjectDoesNotExist`` exception. Polaris will return a 404 Not Found response.

        If this function is not implemented, Polaris will respond with a 501 Not Implemented.

        :param token: the ``SEP10Token`` object representing the authenticated session
        :param request: a ``rest_framework.request.Request`` instance
        :param account: the Stellar or muxed account authenticated via SEP-10
        :param params: the request body of the ``PUT /customer/verification`` call
        :raises: ValueError, ObjectDoesNotExist, NotImplementedError
        """
        raise NotImplementedError()


registered_customer_integration = CustomerIntegration()
