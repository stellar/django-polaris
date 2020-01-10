"""Helper functions to use across tests."""
import json
import time

from polaris import settings
from stellar_sdk import Account
from stellar_sdk.client.response import Response
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.keypair import Keypair
from stellar_sdk.transaction_envelope import TransactionEnvelope


def mock_check_auth_success(request, func, content_type: str = "application/json"):
    """Mocks `helpers.check_auth`, for success."""
    return func("test source address", request)


def sep10(client, address, seed):
    response = client.get(f"/auth?account={address}", follow=True)
    content = json.loads(response.content)
    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    client_signing_key = Keypair.from_secret(seed)
    envelope_object.sign(client_signing_key)
    client_signed_envelope_xdr = envelope_object.to_xdr()

    response = client.post(
        "/auth",
        data={"transaction": client_signed_envelope_xdr},
        content_type="application/json",
    )
    content = json.loads(response.content)
    encoded_jwt = content["token"]
    assert encoded_jwt
    return encoded_jwt


def mock_load_not_exist_account(account_id):
    accounts = []
    for vals in settings.ASSETS.values():
        accounts.extend(vals.values())

    if account_id not in accounts:
        raise NotFoundError(
            response=Response(
                status_code=404, headers={}, url="", text=json.dumps(dict(status=404))
            )
        )
    return Account(account_id, 1)


def interactive_jwt_payload(transaction, transaction_type):
    current_time = time.time()
    return {
        "iss": f"http://testserver/transactions/{transaction_type}/interactive",
        "exp": current_time + 30,
        "iat": current_time,
        "jti": str(transaction.id),
        "sub": transaction.stellar_account,
    }
