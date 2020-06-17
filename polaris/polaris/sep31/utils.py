import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from polaris.models import Transaction
from polaris.utils import Logger
from polaris.sep31.serializers import SEP31TransactionSerializer


DEFAULT_TIMEOUT = 5
logger = Logger(__name__)


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.timeout = DEFAULT_TIMEOUT
        if "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
            del kwargs["timeout"]
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


retry = Retry(backoff_factor=0.1)
adapter = TimeoutHTTPAdapter(max_retries=retry)
session = requests.Session()
session.mount("https", adapter)


def sep31_callback(transaction: Transaction) -> requests.Response:
    """
    Could raise a subclass of requests.RequestException
    """
    return session.post(
        transaction.send_callback_url,
        json={"transaction": SEP31TransactionSerializer(transaction).data},
    )


def make_callback(transaction: Transaction):
    try:
        sep31_callback(transaction)
    except requests.RequestException as e:
        # We could mark the transaction's status as error, but the sending
        # anchor can still provide the updates required, so we keep the status
        # as pending_info_update even when callback requests fail.
        logger.error(
            f"callback to {transaction.send_callback_url} failed for transaction {transaction.id}"
        )
