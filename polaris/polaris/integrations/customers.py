from typing import Dict


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

    def put(self, params: Dict):
        """
        .. _SEP-12: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0012.md

        Update or create a record of the customer information passed. This information can
        then later be queried for when a client requests a deposit or withdraw on behalf of
        the customer.

        If the information passed in `params` is invalid in some way, raise a ``ValueError``
        for Polaris to return a 400 Bad Request response to the client. The message contained
        in the exception will be passed as the error message in the response.

        :param params: request parameters as described in SEP-12_
        """
        pass

    def delete(self, account: str):
        """

        Delete the record of the customer specified by `account`. If such a record does not
        exist, raise a ``ValueError`` for Polaris to return a 404 Not Found response.

        :param account: the stellar account associated with the customer
        """
        pass


registered_customer_integration = CustomerIntegration()
