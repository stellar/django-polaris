from unittest.mock import Mock, patch

import pytest
from polaris.models import Transaction
from polaris.sep31.info import validate_info_fields


endpoint = "/sep31/info"
success_info_response = Mock(
    info=Mock(
        return_value={
            "receiver": {
                "first_name": {"description": "first name"},
                "last_name": {"description": "last name"},
            },
            "sender": {
                "first_name": {"description": "first name"},
                "last_name": {"description": "last name"},
            },
            "transaction": {
                "bank_account": {
                    "description": "bank account",
                    "choices": ["test1"],
                    "optional": False,
                }
            },
        }
    ),
)


@pytest.mark.django_db
@patch("polaris.sep31.info.registered_send_integration", success_info_response)
def test_success_response(client, usd_asset_factory):
    asset = usd_asset_factory(protocols=[Transaction.PROTOCOL.sep31])
    response = client.get(endpoint)
    body = response.json()
    assert response.status_code == 200
    assert body["receive"][asset.code] == {
        "enabled": True,
        "fee_fixed": asset.send_fee_fixed,
        "min_amount": asset.send_min_amount,
        "max_amount": asset.send_max_amount,
        "fields": success_info_response.info(),
    }


###
# test validate_info_fields
###


def test_bad_type_response():
    with pytest.raises(ValueError) as e:
        validate_info_fields(None)


def test_empty_response():
    """
    Should not raise an error
    """
    validate_info_fields({})


def test_extra_category():
    with pytest.raises(ValueError) as e:
        validate_info_fields({"bad category": 1})


def test_bad_category_value():
    with pytest.raises(ValueError):
        validate_info_fields({"sender": "not a dict"})


def test_bad_fields_value_type():
    with pytest.raises(ValueError):
        validate_info_fields({"sender": {"field": "should be a dict"}})


def test_missing_fields_value_key():
    with pytest.raises(ValueError):
        validate_info_fields({"sender": {"fields": {"not description": "value"}}})


def test_extra_fields_key():
    with pytest.raises(ValueError):
        validate_info_fields(
            {"sender": {"fields": {"description": "description", "extra": "value"}}}
        )


def test_bad_optional_type():
    with pytest.raises(ValueError):
        validate_info_fields(
            {
                "sender": {
                    "fields": {"description": "description", "optional": "not bool"}
                }
            }
        )


def test_bad_choices_type():
    with pytest.raises(ValueError):
        validate_info_fields(
            {
                "sender": {
                    "fields": {"description": "description", "choices": "not a list"}
                }
            }
        )
