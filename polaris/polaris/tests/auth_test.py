"""This module tests the <auth> endpoint."""
import jwt
import base64
import json
from unittest.mock import Mock, patch
from urllib.parse import urlparse

from stellar_sdk.keypair import Keypair
from stellar_sdk.exceptions import NotFoundError
from stellar_sdk.sep.ed25519_public_key_signer import Ed25519PublicKeySigner
from stellar_sdk.transaction_envelope import TransactionEnvelope
from stellar_sdk.operation import ManageData

from polaris import settings
from polaris.tests.conftest import STELLAR_ACCOUNT_1
from polaris.sep10.utils import check_auth

endpoint = "/auth"

CLIENT_ADDRESS = "GDKFNRUATPH4BSZGVFDRBIGZ5QAFILVFRIRYNSQ4UO7V2ZQAPRNL73RI"
CLIENT_SEED = "SDKWSBERDHP3SXW5A3LXSI7FWMMO5H7HG33KNYBKWH2HYOXJG2DXQHQY"

CLIENT_ATTRIBUTION_DOMAIN = "clientdomain.com"
CLIENT_ATTRIBUTION_ADDRESS = "GB5LULKGYA44XDYEDDBK6OZPVUXFKVNARRKU2DKATGWJXA7YKQ22HW67"
CLIENT_ATTRIBUTION_SEED = "SBSCUJ7Q5WDKETV572MRORDO2NLAJ5542RHQGEU4N5P7IFBRDVEOBBLL"


def test_auth_get_no_account_param(client):
    """`GET <auth>` fails with no `account` parameter."""
    response = client.get(endpoint, follow=True)
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "no 'account' provided"}


def test_auth_get_success(client):
    """`GET <auth>` succeeds with a valid TransactionEnvelope XDR."""
    response = client.get(f"{endpoint}?account={STELLAR_ACCOUNT_1}", follow=True)
    content = json.loads(response.content)
    assert content["network_passphrase"] == "Test SDF Network ; September 2015"
    assert content["transaction"]

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    transaction_object = envelope_object.transaction
    assert transaction_object.sequence == 0
    assert len(transaction_object.operations) == 2

    home_domain_op = transaction_object.operations[0]
    assert isinstance(home_domain_op, ManageData)
    assert home_domain_op.data_name == f"{urlparse(settings.HOST_URL).netloc} auth"
    assert len(home_domain_op.data_value) <= 64
    assert len(base64.b64decode(home_domain_op.data_value)) == 48

    web_auth_domain_op = transaction_object.operations[1]
    assert isinstance(web_auth_domain_op, ManageData)
    assert web_auth_domain_op.data_name == "web_auth_domain"
    assert (
        web_auth_domain_op.data_value
        == f"{urlparse(settings.HOST_URL).netloc}".encode()
    )

    signatures = envelope_object.signatures
    assert len(signatures) == 1

    tx_hash = envelope_object.hash()
    server_public_key = Keypair.from_public_key(settings.SIGNING_KEY)
    server_public_key.verify(tx_hash, signatures[0].signature)


@patch(
    "polaris.sep10.views.fetch_stellar_toml",
    Mock(return_value={"SIGNING_KEY": CLIENT_ATTRIBUTION_ADDRESS}),
)
def test_auth_get_client_attribution_success(client):
    """`GET <auth>` succeeds with a valid TransactionEnvelope XDR."""
    response = client.get(
        f"{endpoint}?account={STELLAR_ACCOUNT_1}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    content = json.loads(response.content)
    assert content["network_passphrase"] == "Test SDF Network ; September 2015"
    assert content["transaction"]

    envelope_xdr = content["transaction"]
    envelope_object = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    transaction_object = envelope_object.transaction
    assert transaction_object.sequence == 0
    assert len(transaction_object.operations) == 3

    home_domain_op = transaction_object.operations[0]
    assert isinstance(home_domain_op, ManageData)
    assert home_domain_op.data_name == f"{urlparse(settings.HOST_URL).netloc} auth"
    assert len(home_domain_op.data_value) <= 64
    assert len(base64.b64decode(home_domain_op.data_value)) == 48
    assert home_domain_op.source == STELLAR_ACCOUNT_1

    web_auth_domain_op = transaction_object.operations[1]
    assert isinstance(web_auth_domain_op, ManageData)
    assert web_auth_domain_op.data_name == "web_auth_domain"
    assert (
        web_auth_domain_op.data_value
        == f"{urlparse(settings.HOST_URL).netloc}".encode()
    )
    assert web_auth_domain_op.source == settings.SIGNING_KEY

    client_domain_op = transaction_object.operations[2]
    assert isinstance(client_domain_op, ManageData)
    assert client_domain_op.data_name == "client_domain"
    assert client_domain_op.data_value == CLIENT_ATTRIBUTION_DOMAIN.encode()
    assert client_domain_op.source == CLIENT_ATTRIBUTION_ADDRESS

    signatures = envelope_object.signatures
    assert len(signatures) == 1

    tx_hash = envelope_object.hash()
    server_public_key = Keypair.from_public_key(settings.SIGNING_KEY)
    server_public_key.verify(tx_hash, signatures[0].signature)


auth_str = "Bearer {}"
mock_request = Mock(META={})
account_exists = Mock(
    load_ed25519_public_key_signers=Mock(
        return_value=[Ed25519PublicKeySigner(CLIENT_ADDRESS)]
    ),
    thresholds=Mock(med_threshold=0),
)


@patch(
    "polaris.sep10.views.settings.HORIZON_SERVER.load_account",
    Mock(return_value=account_exists),
)
def test_auth_post_success_account_exists(client):
    """`POST <auth>` succeeds when given a proper JSON-encoded transaction."""
    response = client.get(f"{endpoint}?account={CLIENT_ADDRESS}", follow=True)
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(CLIENT_SEED)
    response = client.post(
        endpoint,
        data={"transaction": envelope.to_xdr()},
        content_type="application/json",
    )

    content = json.loads(response.content)
    assert content["token"]
    mock_request.META["HTTP_AUTHORIZATION"] = auth_str.format(content["token"])
    mock_view_function = Mock()
    check_auth(mock_request, mock_view_function)
    mock_view_function.assert_called_once_with(CLIENT_ADDRESS, None, mock_request)


@patch(
    "polaris.sep10.views.settings.HORIZON_SERVER.load_account",
    Mock(side_effect=NotFoundError(Mock())),
)
def test_auth_post_success_account_does_not_exist(client):
    """`POST <auth>` succeeds when given a proper JSON-encoded transaction."""
    response = client.get(f"{endpoint}?account={CLIENT_ADDRESS}", follow=True)
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(CLIENT_SEED)
    response = client.post(
        endpoint,
        data={"transaction": envelope.to_xdr()},
        content_type="application/json",
    )

    content = json.loads(response.content)
    assert content["token"]
    mock_request.META["HTTP_AUTHORIZATION"] = auth_str.format(content["token"])
    mock_view_function = Mock()
    check_auth(mock_request, mock_view_function)
    mock_view_function.assert_called_once_with(CLIENT_ADDRESS, None, mock_request)


@patch(
    "polaris.sep10.views.settings.HORIZON_SERVER.load_account",
    Mock(return_value=account_exists),
)
@patch(
    "polaris.sep10.views.fetch_stellar_toml",
    Mock(return_value={"SIGNING_KEY": CLIENT_ATTRIBUTION_ADDRESS}),
)
def test_auth_post_success_client_attribution(client):
    response = client.get(
        f"{endpoint}?account={CLIENT_ADDRESS}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(CLIENT_SEED)
    envelope.sign(CLIENT_ATTRIBUTION_SEED)
    response = client.post(
        endpoint,
        data={"transaction": envelope.to_xdr()},
        content_type="application/json",
    )

    content = json.loads(response.content)
    assert content["token"]
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    assert jwt_contents["client_domain"] == CLIENT_ATTRIBUTION_DOMAIN
    mock_request.META["HTTP_AUTHORIZATION"] = auth_str.format(content["token"])
    mock_view_function = Mock()
    check_auth(mock_request, mock_view_function)
    mock_view_function.assert_called_once_with(
        CLIENT_ADDRESS, CLIENT_ATTRIBUTION_DOMAIN, mock_request
    )


@patch("polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
@patch(
    "polaris.sep10.views.settings.HORIZON_SERVER.load_account",
    Mock(return_value=account_exists),
)
@patch(
    "polaris.sep10.views.fetch_stellar_toml",
    Mock(return_value={"SIGNING_KEY": CLIENT_ATTRIBUTION_ADDRESS}),
)
def test_auth_post_success_client_attribution_required(client):
    response = client.get(
        f"{endpoint}?account={CLIENT_ADDRESS}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(CLIENT_SEED)
    envelope.sign(CLIENT_ATTRIBUTION_SEED)
    response = client.post(
        endpoint,
        data={"transaction": envelope.to_xdr()},
        content_type="application/json",
    )

    content = json.loads(response.content)
    assert content["token"]
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    assert jwt_contents["client_domain"] == CLIENT_ATTRIBUTION_DOMAIN
    mock_request.META["HTTP_AUTHORIZATION"] = auth_str.format(content["token"])
    mock_view_function = Mock()
    check_auth(mock_request, mock_view_function)
    mock_view_function.assert_called_once_with(
        CLIENT_ADDRESS, CLIENT_ATTRIBUTION_DOMAIN, mock_request
    )


@patch("polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
def test_auth_attribution_required_no_domain(client):
    response = client.get(f"{endpoint}?account={CLIENT_ADDRESS}", follow=True,)
    assert response.status_code == 400


@patch("polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
@patch(
    "polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_DENYLIST",
    [CLIENT_ATTRIBUTION_DOMAIN],
)
def test_auth_attribution_required_in_denylist(client):
    response = client.get(
        f"{endpoint}?account={CLIENT_ADDRESS}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    assert response.status_code == 403


@patch("polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
@patch(
    "polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST",
    ["notclientdomain.com"],
)
def test_auth_attribution_required_in_denylist(client):
    response = client.get(
        f"{endpoint}?account={CLIENT_ADDRESS}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    assert response.status_code == 403


@patch("polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_REQUIRED", True)
@patch(
    "polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST",
    [CLIENT_ATTRIBUTION_DOMAIN],
)
@patch(
    "polaris.sep10.views.settings.HORIZON_SERVER.load_account",
    Mock(return_value=account_exists),
)
@patch(
    "polaris.sep10.views.fetch_stellar_toml",
    Mock(return_value={"SIGNING_KEY": CLIENT_ATTRIBUTION_ADDRESS}),
)
def test_auth_post_success_client_attribution_required_allowlist_provided(client):
    response = client.get(
        f"{endpoint}?account={CLIENT_ADDRESS}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    envelope.sign(CLIENT_SEED)
    envelope.sign(CLIENT_ATTRIBUTION_SEED)
    response = client.post(
        endpoint,
        data={"transaction": envelope.to_xdr()},
        content_type="application/json",
    )

    content = json.loads(response.content)
    assert content["token"]
    jwt_contents = jwt.decode(
        content["token"], settings.SERVER_JWT_KEY, algorithms=["HS256"]
    )
    assert jwt_contents["client_domain"] == CLIENT_ATTRIBUTION_DOMAIN
    mock_request.META["HTTP_AUTHORIZATION"] = auth_str.format(content["token"])
    mock_view_function = Mock()
    check_auth(mock_request, mock_view_function)
    mock_view_function.assert_called_once_with(
        CLIENT_ADDRESS, CLIENT_ATTRIBUTION_DOMAIN, mock_request
    )


@patch(
    "polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_ALLOWLIST",
    ["notclientdomain.com"],
)
@patch(
    "polaris.sep10.views.settings.HORIZON_SERVER.load_account",
    Mock(return_value=account_exists),
)
@patch(
    "polaris.sep10.views.fetch_stellar_toml",
    Mock(
        side_effect=AssertionError(
            "attempted to fetch TOML when domain not included in allowlist"
        )
    ),
)
def test_auth_get_no_client_attribution_required_domain_passed_allowlist_provided_no_match(
    client,
):
    response = client.get(
        f"{endpoint}?account={CLIENT_ADDRESS}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    # attribution manage data op not included
    assert len(envelope.transaction.operations) == 2


@patch(
    "polaris.sep10.views.settings.SEP10_CLIENT_ATTRIBUTION_DENYLIST",
    [CLIENT_ATTRIBUTION_DOMAIN],
)
@patch(
    "polaris.sep10.views.settings.HORIZON_SERVER.load_account",
    Mock(return_value=account_exists),
)
@patch(
    "polaris.sep10.views.fetch_stellar_toml",
    Mock(
        side_effect=AssertionError(
            "attempted to fetch TOML when domain not included in allowlist"
        )
    ),
)
def test_auth_get_no_client_attribution_required_domain_passed_denylist_provided_match(
    client,
):
    response = client.get(
        f"{endpoint}?account={CLIENT_ADDRESS}&client_domain={CLIENT_ATTRIBUTION_DOMAIN}",
        follow=True,
    )
    content = json.loads(response.content)

    # Sign the XDR with the client.
    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE
    )
    # attribution manage data op not included
    assert len(envelope.transaction.operations) == 2
