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
                    }
                },
            },
            "sep12": {
                "sender": {"types": {}},
                "receiver": {
                    "types": {
                        "sep31-receiver-cash-out": {
                            "description": "customer using physical cash out locations"
                        },
                        "sep31-receiver-bank-transfer": {
                            "description": "customers who want direct bank deposits and withdraws"
                        },
                    }
                },
            },
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
        "fields": success_info_response.info()["fields"],
        "sep12": success_info_response.info()["sep12"],
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


def test_empty_fields_and_types():
    validate_info_response({"fields": {}, "sep12": {"sender": {}, "receiver": {}}})


def test_extra_category():
    with pytest.raises(
        ValueError, match="unrecognized key in info integration response"
    ):
        validate_info_response({"bad category": 1})


def test_bad_category_value():
    with pytest.raises(ValueError, match="fields key value must be a dict"):
        validate_info_response(
            {
                "fields": {"transaction": "not a dict"},
                "sep12": {"sender": {}, "receiver": {}},
            }
        )


def test_bad_fields_value_type():
    with pytest.raises(
        ValueError, match="field value must be a dict, got <class 'str'>"
    ):
        validate_info_response(
            {
                "fields": {"transaction": {"field": "should be a dict"}},
                "sep12": {"sender": {}, "receiver": {}},
            }
        )


def test_missing_description_key():
    with pytest.raises(ValueError, match="'fields' dict must contain 'description'"):
        validate_info_response(
            {
                "fields": {"transaction": {"field": {"not description": "value"}}},
                "sep12": {"sender": {}, "receiver": {}},
            }
        )


def test_extra_fields_key():
    with pytest.raises(ValueError, match="unexpected keys in 'fields' dict"):
        validate_info_response(
            {
                "fields": {
                    "transaction": {
                        "field": {"description": "description", "extra": "value"}
                    }
                },
                "sep12": {"sender": {}, "receiver": {}},
            }
        )


def test_bad_optional_type():
    with pytest.raises(ValueError, match="'optional' must be a boolean"):
        validate_info_response(
            {
                "fields": {
                    "transaction": {
                        "field": {"description": "description", "optional": "not bool"},
                    }
                },
                "sep12": {"sender": {}, "receiver": {}},
            }
        )


def test_bad_choices_type():
    with pytest.raises(ValueError, match="'choices' must be a list"):
        validate_info_response(
            {
                "fields": {
                    "transaction": {
                        "field": {
                            "description": "description",
                            "choices": "not a list",
                        },
                    }
                },
                "sep12": {"sender": {}, "receiver": {}},
            }
        )


def test_missing_sep12_object():
    with pytest.raises(ValueError, match="missing sep12 object in info response"):
        validate_info_response({"fields": {}})


def test_missing_sender_key():
    with pytest.raises(
        ValueError, match="sender and/or receiver object missing in sep12 object"
    ):
        validate_info_response({"fields": {}, "sep12": {"receiver": {}}})


def test_bad_sender_type():
    with pytest.raises(ValueError, match="types key value must be an dict"):
        validate_info_response(
            {"fields": {}, "sep12": {"receiver": {}, "sender": {"types": "not a dict"}}}
        )


def test_bad_sender_type_value():
    with pytest.raises(
        ValueError, match="sep31-sender value must be a dict, got <class 'str'>"
    ):
        validate_info_response(
            {
                "fields": {},
                "sep12": {
                    "receiver": {},
                    "sender": {"types": {"sep31-sender": "test"}},
                },
            }
        )


def test_bad_sender_type_missing_description():
    with pytest.raises(
        ValueError, match="sep31-sender dict must contain a description"
    ):
        validate_info_response(
            {
                "fields": {},
                "sep12": {"receiver": {}, "sender": {"types": {"sep31-sender": {}}}},
            }
        )


def test_bad_sender_type_description_type():
    with pytest.raises(
        ValueError, match="sep31-sender description must be a human-readable string"
    ):
        validate_info_response(
            {
                "fields": {},
                "sep12": {
                    "receiver": {},
                    "sender": {"types": {"sep31-sender": {"description": {}}}},
                },
            }
        )


def test_sender_sep12_type_still_supported():
    validate_info_response({"fields": {}, "sender_sep12_type": "test"})
