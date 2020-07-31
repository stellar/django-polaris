from unittest.mock import Mock, patch

import pytest
from polaris.models import Transaction
from polaris.sep31.info import validate_info_response


endpoint = "/sep31/info"
success_info_response = Mock(
    info=Mock(
        return_value={
            "fields": {
                "transaction": {
                    "bank_account": {
                        "description": "bank account",
                        "choices": ["test1"],
                        "optional": False,
                    }
                },
            },
            "sender_sep12_type": "sep31-sender",
            "receiver_sep12_type": "sep31-receiver",
        }
    ),
)


@pytest.mark.django_db
@patch(
    "polaris.sep31.info.registered_sep31_receiver_integration", success_info_response
)
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
        "sender_sep12_type": "sep31-sender",
        "receiver_sep12_type": "sep31-receiver",
        "fields": success_info_response.info()["fields"],
    }


###
# test validate_info_response
###


def test_bad_type_response():
    with pytest.raises(ValueError, match="info integration must return a dictionary"):
        validate_info_response(None)


def test_empty_response():
    with pytest.raises(ValueError, match="missing fields object in info response"):
        validate_info_response({})


def test_empty_fields():
    # this should pass
    validate_info_response({"fields": {}})


def test_extra_category():
    with pytest.raises(
        ValueError, match="unrecognized key in info integration response"
    ):
        validate_info_response({"bad category": 1})


def test_bad_category_value():
    with pytest.raises(ValueError, match="bad type in info response"):
        validate_info_response({"fields": {"transaction": "not a dict"}})


def test_bad_fields_value_type():
    with pytest.raises(
        ValueError, match="field value must be a dict, got <class 'str'>"
    ):
        validate_info_response(
            {"fields": {"transaction": {"field": "should be a dict"}}}
        )


def test_missing_description_key():
    with pytest.raises(ValueError, match="'fields' dict must contain 'description'"):
        validate_info_response(
            {"fields": {"transaction": {"field": {"not description": "value"}}}}
        )


def test_extra_fields_key():
    with pytest.raises(ValueError, match="unexpected keys in 'fields' dict"):
        validate_info_response(
            {
                "fields": {
                    "transaction": {
                        "field": {"description": "description", "extra": "value"}
                    }
                }
            }
        )


def test_bad_optional_type():
    with pytest.raises(ValueError, match="'optional' must be a boolean"):
        validate_info_response(
            {
                "fields": {
                    "transaction": {
                        "field": {"description": "description", "optional": "not bool"}
                    }
                }
            }
        )


def test_bad_choices_type():
    with pytest.raises(ValueError, match="'choices' must be a list"):
        validate_info_response(
            {
                "fields": {
                    "transaction": {
                        "field": {"description": "description", "choices": "not a list"}
                    }
                },
            }
        )
