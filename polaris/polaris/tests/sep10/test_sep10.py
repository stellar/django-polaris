import os
import jwt
import json
import base64
from urllib.parse import urlparse
from unittest.mock import patch, Mock, MagicMock
from toml.decoder import TomlDecodeError

from stellar_sdk import (
    Keypair,
    ManageData,
    TransactionEnvelope,
    MuxedAccount,
    TransactionBuilder,
    Account,
    Network,
)
from stellar_sdk.sep.ed25519_public_key_signer import Ed25519PublicKeySigner
from stellar_sdk.exceptions import ConnectionError, NotFoundError
from stellar_sdk.sep.exceptions import StellarTomlNotFoundError
from stellar_sdk.client.requests_client import RequestsClient
from stellar_sdk.sep.stellar_web_authentication import (
    read_challenge_transaction,
    build_challenge_transaction,
)

from polaris import settings

AUTH_PATH = "/auth"
test_module = "polaris.sep10.views"


def test_get_success(client):
    kp = Keypair.random()
    response = client.get(AUTH_PATH, {"account": kp.public_key})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE


def test_get_success_muxed_account(client):
    muxed_account = MuxedAccount(Keypair.random().public_key, 123)
    response = client.get(AUTH_PATH, {"account": muxed_account.account_muxed})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    challenge = read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert challenge.client_account_id == muxed_account.account_muxed
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE


def test_get_muxed_account_and_memo(client):
    muxed_account = MuxedAccount(Keypair.random().public_key, 123)
    response = client.get(
        AUTH_PATH, {"account": muxed_account.account_muxed, "memo": 123}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert (
        content["error"]
        == "'memo' cannot be passed with a muxed client account address (M...)"
    )


def test_get_stellar_account_and_memo(client):
    kp = Keypair.random()
    response = client.get(AUTH_PATH, {"account": kp.public_key, "memo": 123})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    challenge = read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert challenge.client_account_id == kp.public_key
    assert challenge.memo == 123
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE


def test_get_stellar_account_and_non_id_memo(client):
    kp = Keypair.random()
    response = client.get(AUTH_PATH, {"account": kp.public_key, "memo": "not an int"})

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert content["error"] == "invalid 'memo' value. Expected a 64-bit integer."


def test_get_no_account_provied(client):
    response = client.get(AUTH_PATH)

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert content["error"] == "no 'account' provided"


def test_get_invalid_account_provied(client):
    response = client.get(AUTH_PATH, {"account": "test"})

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert content["error"] == "This is not a valid account: test"


def test_get_invalid_home_domain(client):
    kp = Keypair.random()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "home_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert (
        content["error"]
        == f"invalid 'home_domain' value. Accepted values: {settings.SEP10_HOME_DOMAINS}"
    )


@patch(f"{test_module}.fetch_stellar_toml")
def test_get_success_client_attribution(mock_fetch_stellar_toml, client):
    client_kp = Keypair.random()
    client_domain_kp = Keypair.random()
    request_client_domain = urlparse(settings.HOST_URL).netloc
    mock_fetch_stellar_toml.return_value = {"SIGNING_KEY": client_domain_kp.public_key}
    response = client.get(
        AUTH_PATH,
        {"account": client_kp.public_key, "client_domain": request_client_domain},
    )

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    challenge = read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE

    mock_fetch_stellar_toml.assert_called_once()
    args, kwargs = mock_fetch_stellar_toml.call_args
    assert args[0] == request_client_domain
    assert isinstance(kwargs.get("client"), RequestsClient)
    assert (
        kwargs["client"].request_timeout
        == settings.SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT
    )

    client_domain = None
    client_domain_signing_key = None
    for op in challenge.transaction.transaction.operations:
        if isinstance(op, ManageData) and op.data_name == "client_domain":
            client_domain = op.data_value.decode()
            client_domain_signing_key = op.source.account_id

    assert client_domain == request_client_domain
    assert client_domain_signing_key == client_domain_kp.public_key


@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
def test_get_client_attribution_required_no_client_domain(client):
    kp = Keypair.random()
    response = client.get(AUTH_PATH, {"account": kp.public_key})

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert content["error"] == "'client_domain' is required"


def test_get_client_attribution_required_invalid_client_domain(client):
    kp = Keypair.random()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "https://test.com"}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert content["error"] == "'client_domain' must be a valid hostname"


@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_DENYLIST", ["test.com"])
def test_get_client_attribution_required_denied_client_domain(client):
    kp = Keypair.random()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 403, json.dumps(content, indent=2)
    assert content["error"] == "unrecognized 'client_domain'"


@patch(f"{test_module}.fetch_stellar_toml")
@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_DENYLIST", ["test.com"])
def test_get_client_attribution_optional_denied_client_domain(
    mock_fetch_stellar_toml, client
):
    kp = Keypair.random()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    challenge = read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE

    mock_fetch_stellar_toml.assert_not_called()

    client_domain = None
    client_domain_signing_key = None
    for op in challenge.transaction.transaction.operations:
        if isinstance(op, ManageData) and op.data_name == "client_domain":
            client_domain = op.data_value.decode()
            client_domain_signing_key = op.source.account_id

    assert client_domain is None
    assert client_domain_signing_key is None


@patch(f"{test_module}.fetch_stellar_toml")
@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_DENYLIST", ["nottest.com"])
def test_get_success_client_attribution_not_denied(mock_fetch_stellar_toml, client):
    client_kp = Keypair.random()
    client_domain_kp = Keypair.random()
    request_client_domain = urlparse(settings.HOST_URL).netloc
    mock_fetch_stellar_toml.return_value = {"SIGNING_KEY": client_domain_kp.public_key}
    response = client.get(
        AUTH_PATH,
        {"account": client_kp.public_key, "client_domain": request_client_domain},
    )

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    challenge = read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE

    mock_fetch_stellar_toml.assert_called_once()
    args, kwargs = mock_fetch_stellar_toml.call_args
    assert args[0] == request_client_domain
    assert isinstance(kwargs.get("client"), RequestsClient)
    assert (
        kwargs["client"].request_timeout
        == settings.SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT
    )

    client_domain = None
    client_domain_signing_key = None
    for op in challenge.transaction.transaction.operations:
        if isinstance(op, ManageData) and op.data_name == "client_domain":
            client_domain = op.data_value.decode()
            client_domain_signing_key = op.source.account_id

    assert client_domain == request_client_domain
    assert client_domain_signing_key == client_domain_kp.public_key


@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST", ["nottest.com"])
def test_get_client_attribution_required_not_allowed_client_domain(client):
    kp = Keypair.random()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 403, json.dumps(content, indent=2)
    assert content["error"] == "unrecognized 'client_domain'"


@patch(f"{test_module}.fetch_stellar_toml")
@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST", ["nottest.com"])
def test_get_client_attribution_optional_not_allowed_client_domain(
    mock_fetch_stellar_toml, client
):
    kp = Keypair.random()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    challenge = read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE

    mock_fetch_stellar_toml.assert_not_called()

    client_domain = None
    client_domain_signing_key = None
    for op in challenge.transaction.transaction.operations:
        if isinstance(op, ManageData) and op.data_name == "client_domain":
            client_domain = op.data_value.decode()
            client_domain_signing_key = op.source.account_id

    assert client_domain is None
    assert client_domain_signing_key is None


@patch(f"{test_module}.fetch_stellar_toml")
@patch(f"{test_module}.settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST", ["test.com"])
def test_get_success_client_attribution_is_allowed(mock_fetch_stellar_toml, client):
    client_kp = Keypair.random()
    client_domain_kp = Keypair.random()
    request_client_domain = "test.com"
    mock_fetch_stellar_toml.return_value = {"SIGNING_KEY": client_domain_kp.public_key}
    response = client.get(
        AUTH_PATH,
        {"account": client_kp.public_key, "client_domain": request_client_domain},
    )

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)

    challenge = read_challenge_transaction(
        challenge_transaction=content["transaction"],
        server_account_id=settings.SIGNING_KEY,
        home_domains=urlparse(settings.HOST_URL).netloc,
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    assert content["network_passphrase"] == settings.STELLAR_NETWORK_PASSPHRASE

    mock_fetch_stellar_toml.assert_called_once()
    args, kwargs = mock_fetch_stellar_toml.call_args
    assert args[0] == request_client_domain
    assert isinstance(kwargs.get("client"), RequestsClient)
    assert (
        kwargs["client"].request_timeout
        == settings.SEP10_CLIENT_ATTRIBUTION_REQUEST_TIMEOUT
    )

    client_domain = None
    client_domain_signing_key = None
    for op in challenge.transaction.transaction.operations:
        if isinstance(op, ManageData) and op.data_name == "client_domain":
            client_domain = op.data_value.decode()
            client_domain_signing_key = op.source.account_id

    assert client_domain == request_client_domain
    assert client_domain_signing_key == client_domain_kp.public_key


@patch(f"{test_module}.fetch_stellar_toml")
def test_get_client_attribution_connection_error(mock_fetch_stellar_toml, client):
    kp = Keypair.random()
    mock_fetch_stellar_toml.side_effect = ConnectionError()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    mock_fetch_stellar_toml.assert_called_once()
    assert content["error"] == "unable to fetch 'client_domain' SIGNING_KEY"


@patch(f"{test_module}.fetch_stellar_toml")
def test_get_client_attribution_no_stellar_toml(mock_fetch_stellar_toml, client):
    kp = Keypair.random()
    mock_fetch_stellar_toml.side_effect = StellarTomlNotFoundError()
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    mock_fetch_stellar_toml.assert_called_once()
    assert content["error"] == "unable to fetch 'client_domain' SIGNING_KEY"


@patch(f"{test_module}.fetch_stellar_toml")
def test_get_client_attribution_invalid_stellar_toml(mock_fetch_stellar_toml, client):
    kp = Keypair.random()
    mock_fetch_stellar_toml.side_effect = TomlDecodeError(
        MagicMock(), MagicMock(), MagicMock()
    )
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    mock_fetch_stellar_toml.assert_called_once()
    assert content["error"] == "unable to fetch 'client_domain' SIGNING_KEY"


@patch(f"{test_module}.fetch_stellar_toml")
def test_get_client_attribution_no_signing_key(mock_fetch_stellar_toml, client):
    kp = Keypair.random()
    mock_fetch_stellar_toml.return_value = {}
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    mock_fetch_stellar_toml.assert_called_once()
    assert content["error"] == "SIGNING_KEY not present on 'client_domain' TOML"


@patch(f"{test_module}.fetch_stellar_toml")
def test_get_client_attribution_invalid_signing_key(mock_fetch_stellar_toml, client):
    kp = Keypair.random()
    mock_fetch_stellar_toml.return_value = {"SIGNING_KEY": "test"}
    response = client.get(
        AUTH_PATH, {"account": kp.public_key, "client_domain": "test.com"}
    )

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    mock_fetch_stellar_toml.assert_called_once()
    assert content["error"] == "invalid SIGNING_KEY value on 'client_domain' TOML"


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_account_exists(mock_load_account, client):
    kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.return_value = Mock(
        load_ed25519_public_key_signers=Mock(
            return_value=[Ed25519PublicKeySigner(kp.public_key, 0)]
        ),
        thresholds=Mock(med_threshold=0),
    )

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": kp.public_key,
        "jti": envelope.hash().hex(),
        "client_domain": None,
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_muxed_account_exists(mock_load_account, client):
    stellar_account_kp = Keypair.random()
    muxed_account = MuxedAccount(stellar_account_kp.public_key, 123).account_muxed
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=muxed_account,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(stellar_account_kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.return_value = Mock(
        load_ed25519_public_key_signers=Mock(
            return_value=[Ed25519PublicKeySigner(stellar_account_kp.public_key, 1)]
        ),
        thresholds=Mock(med_threshold=0),
    )

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": muxed_account,
        "jti": envelope.hash().hex(),
        "client_domain": None,
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_account_exists_with_memo(mock_load_account, client):
    stellar_account_kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=stellar_account_kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        memo=123,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(stellar_account_kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.return_value = Mock(
        load_ed25519_public_key_signers=Mock(
            return_value=[Ed25519PublicKeySigner(stellar_account_kp.public_key, 1)]
        ),
        thresholds=Mock(med_threshold=0),
    )

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": f"{stellar_account_kp.public_key}:123",
        "jti": envelope.hash().hex(),
        "client_domain": None,
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_failure_muxed_account_exists_challenge_has_memo(
    mock_load_account, client
):
    server_kp = Keypair.from_secret(settings.SIGNING_SEED)
    client_kp = Keypair.random()
    muxed_account = MuxedAccount(client_kp.public_key, 123).account_muxed
    nonce_encoded = base64.b64encode(os.urandom(48))

    # build valid challenge transaction except have memo with muxed account
    envelope = (
        TransactionBuilder(
            source_account=Account(server_kp.public_key, -1),
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
        )
        .append_manage_data_op(
            data_name=f"{urlparse(settings.HOST_URL).netloc} auth",
            data_value=nonce_encoded,
            source=muxed_account,
        )
        .append_manage_data_op(
            data_name="web_auth_domain",
            data_value=urlparse(settings.HOST_URL).netloc,
            source=server_kp.public_key,
        )
        .add_id_memo(123)
        .set_timeout(15 * 60)
        .build()
    )
    envelope.sign(server_kp)
    envelope.sign(client_kp)
    signed_challenge_xdr = envelope.to_xdr()

    mock_load_account.return_value = Mock(
        load_ed25519_public_key_signers=Mock(
            return_value=[Ed25519PublicKeySigner(server_kp.public_key, 1)]
        ),
        thresholds=Mock(med_threshold=0),
    )

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert content["error"] == (
        "error while validating challenge: Invalid challenge, memos are "
        "not permitted if the client account is muxed"
    )


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_account_exists_client_attribution(mock_load_account, client):
    kp = Keypair.random()
    client_domain_kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        client_domain="test.com",
        client_signing_key=client_domain_kp.public_key,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(kp)
    envelope.sign(client_domain_kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.return_value = Mock(
        load_ed25519_public_key_signers=Mock(
            return_value=[Ed25519PublicKeySigner(kp.public_key, 0)]
        ),
        thresholds=Mock(med_threshold=0),
    )

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": kp.public_key,
        "jti": envelope.hash().hex(),
        "client_domain": "test.com",
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_fails_account_exists_client_attribution_no_client_signature(
    mock_load_account, client
):
    kp = Keypair.random()
    client_domain_kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        client_domain="test.com",
        client_signing_key=client_domain_kp.public_key,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.return_value = Mock(
        load_ed25519_public_key_signers=Mock(
            return_value=[Ed25519PublicKeySigner(kp.public_key, 0)]
        ),
        thresholds=Mock(med_threshold=0),
    )

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert (
        content["error"] == "error while validating challenge: "
        "Transaction not signed by the source account of the 'client_domain' ManageData operation"
    )


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_account_doesnt_exist(mock_load_account, client):
    kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.side_effect = NotFoundError(MagicMock())

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": kp.public_key,
        "jti": envelope.hash().hex(),
        "client_domain": None,
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_muxed_account_doesnt_exist(mock_load_account, client):
    stellar_account_kp = Keypair.random()
    muxed_account = MuxedAccount(stellar_account_kp.public_key, 123).account_muxed
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=muxed_account,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(stellar_account_kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.side_effect = NotFoundError(MagicMock())

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": muxed_account,
        "jti": envelope.hash().hex(),
        "client_domain": None,
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_account_doesnt_exist_with_memo(mock_load_account, client):
    kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        memo=123,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.side_effect = NotFoundError(MagicMock())

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": f"{kp.public_key}:123",
        "jti": envelope.hash().hex(),
        "client_domain": None,
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_success_account_doesnt_exist_client_attribution(
    mock_load_account, client
):
    kp = Keypair.random()
    client_domain_kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        client_domain="test.com",
        client_signing_key=client_domain_kp.public_key,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(kp)
    envelope.sign(client_domain_kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.side_effect = NotFoundError(MagicMock())

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 200, json.dumps(content, indent=2)
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    iat = jwt_contents.pop("iat")
    exp = jwt_contents.pop("exp")
    assert exp - iat == 24 * 60 * 60
    assert jwt_contents == {
        "iss": os.path.join(settings.HOST_URL, "auth"),
        "sub": kp.public_key,
        "jti": envelope.hash().hex(),
        "client_domain": "test.com",
    }


@patch(f"{test_module}.settings.HORIZON_SERVER.load_account")
def test_post_fails_account_doesnt_exist_no_client_attribution_signature(
    mock_load_account, client
):
    kp = Keypair.random()
    client_domain_kp = Keypair.random()
    challenge_xdr = build_challenge_transaction(
        server_secret=settings.SIGNING_SEED,
        client_account_id=kp.public_key,
        home_domain=settings.SEP10_HOME_DOMAINS[0],
        web_auth_domain=urlparse(settings.HOST_URL).netloc,
        network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
        client_domain="test.com",
        client_signing_key=client_domain_kp.public_key,
    )
    envelope = TransactionEnvelope.from_xdr(
        challenge_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(kp)
    signed_challenge_xdr = envelope.to_xdr()
    mock_load_account.side_effect = NotFoundError(MagicMock())

    response = client.post(AUTH_PATH, {"transaction": signed_challenge_xdr})

    content = response.json()
    assert response.status_code == 400, json.dumps(content, indent=2)
    assert (
        content["error"] == "error while validating challenge: "
        "Transaction not signed by the source account of the 'client_domain' ManageData operation"
    )
