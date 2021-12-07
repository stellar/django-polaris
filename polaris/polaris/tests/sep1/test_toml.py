from unittest.mock import patch, Mock

import toml
import pytest
from stellar_sdk import Keypair
from rest_framework.request import Request

from polaris import settings
from polaris.models import Asset

TOML_PATH = "/.well-known/stellar.toml"
TEST_MODULE = "polaris.sep1.views"


@pytest.mark.django_db
@patch(f"{TEST_MODULE}.registered_toml_func")
def test_toml_generated(mock_toml_func, client):
    usd = Asset.objects.create(
        code="USD",
        issuer=Keypair.random().public_key,
        distribution_seed=Keypair.random().secret,
    )
    with patch(
        f"{TEST_MODULE}.settings.ACTIVE_SEPS",
        ["sep-1", "sep-6", "sep-10", "sep-12", "sep-24", "sep-31", "sep-38"],
    ):
        response = client.get(TOML_PATH)
    assert response.status_code == 200
    assert response.content_type == "text/plain"
    assert mock_toml_func.was_called_once()
    assert isinstance(mock_toml_func.call_args[0][0], Request)

    toml_data = toml.loads(response.content.decode())
    assert "NETWORK_PASSPHRASE" in toml_data
    assert "ACCOUNTS" in toml_data
    assert "TRANSFER_SERVER" in toml_data
    assert "TRANSFER_SERVER_SEP0024" in toml_data
    assert "WEB_AUTH_ENDPOINT" in toml_data
    assert "SIGNING_KEY" in toml_data
    assert "KYC_SERVER" in toml_data
    assert "DIRECT_PAYMENT_SERVER" in toml_data
    assert toml_data["TRANSFER_SERVER"] != toml_data["TRANSFER_SERVER_SEP0024"]
    assert toml_data["ACCOUNTS"] == [usd.distribution_account]
    assert toml_data["NETWORK_PASSPHRASE"] == settings.STELLAR_NETWORK_PASSPHRASE
    assert toml_data["SIGNING_KEY"] == settings.SIGNING_KEY


@patch(f"{TEST_MODULE}.finders.find")
@patch(f"{TEST_MODULE}.open")
def test_toml_static(mock_open, mock_find, client):
    mock_find.return_value = "test.toml"
    mock_open.return_value = Mock(
        __enter__=Mock(
            return_value=Mock(read=Mock(return_value="TEST_ATTR=1".encode()))
        ),
        __exit__=Mock(),
    )
    response = client.get(TOML_PATH)

    assert response.status_code == 200
    assert response.content_type == "text/plain"
    mock_find.assert_called_once_with("polaris/stellar.toml")
    mock_open.assert_called_once()

    toml_data = toml.loads(response.content.decode())
    assert toml_data == {"TEST_ATTR": 1}


@patch(f"{TEST_MODULE}.finders.find")
@patch(f"{TEST_MODULE}.open")
@patch(f"{TEST_MODULE}.settings.LOCAL_MODE", True)
def test_toml_static_local_mode(mock_open, mock_find, client):
    mock_find.return_value = "test.toml"
    mock_open.return_value = Mock(
        __enter__=Mock(
            return_value=Mock(read=Mock(return_value="TEST_ATTR=1".encode()))
        ),
        __exit__=Mock(),
    )
    response = client.get(TOML_PATH)

    assert response.status_code == 200
    assert response.content_type == "text/plain"
    mock_find.assert_called_once_with("polaris/local-stellar.toml")
    mock_open.assert_called_once()

    toml_data = toml.loads(response.content.decode())
    assert toml_data == {"TEST_ATTR": 1}
