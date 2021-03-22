import pytest
import json
from unittest.mock import patch

from polaris.models import Transaction


INFO_PATH = "/sep6/info"


def good_info_integration(asset, lang):
    """
    From the SEP
    """
    return {
        "types": {
            "bank_account": {
                "fields": {
                    "dest": {"description": "your bank account number"},
                    "dest_extra": {"description": "your routing number"},
                    "bank_branch": {"description": "address of your bank branch"},
                    "phone_number": {
                        "description": "your phone number in case there's an issue"
                    },
                }
            },
            "cash": {
                "fields": {
                    "dest": {
                        "description": (
                            "your email address. Your cashout PIN will be sent here. "
                            "If not provided, your account's default email will be used"
                        ),
                        "optional": True,
                    }
                }
            },
        },
        "fields": {
            "email_address": {
                "description": "your email address for transaction status updates",
                "optional": True,
            },
            "amount": {"description": "amount in USD that you plan to deposit"},
            "type": {
                "description": "type of deposit to make",
                "choices": ["SEPA", "SWIFT", "cash"],
            },
        },
    }


@pytest.mark.django_db
@patch("polaris.sep6.info.registered_info_func", good_info_integration)
def test_good_info_response(client, usd_asset_factory):
    usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(INFO_PATH)
    content = json.loads(response.content)
    assert response.status_code == 200
    assert content == {
        "deposit": {
            "USD": {
                "enabled": True,
                "authentication_required": True,
                "min_amount": 0.1,
                "max_amount": 1000.0,
                "fee_fixed": 5.0,
                "fee_percent": 1.0,
                "fields": {
                    "email_address": {
                        "description": "your email address for transaction status updates",
                        "optional": True,
                    },
                    "amount": {"description": "amount in USD that you plan to deposit"},
                    "type": {
                        "description": "type of deposit to make",
                        "choices": ["SEPA", "SWIFT", "cash"],
                    },
                },
            }
        },
        "withdraw": {
            "USD": {
                "enabled": True,
                "authentication_required": True,
                "min_amount": 0.1,
                "max_amount": 1000.0,
                "fee_fixed": 5.0,
                "fee_percent": 0.0,
                "types": {
                    "bank_account": {
                        "fields": {
                            "dest": {"description": "your bank account number"},
                            "dest_extra": {"description": "your routing number"},
                            "bank_branch": {
                                "description": "address of your bank branch"
                            },
                            "phone_number": {
                                "description": "your phone number in case there's an issue"
                            },
                        }
                    },
                    "cash": {
                        "fields": {
                            "dest": {
                                "description": (
                                    "your email address. Your cashout PIN will be sent here. "
                                    "If not provided, your account's default email will be used"
                                ),
                                "optional": True,
                            }
                        }
                    },
                },
            }
        },
        "fee": {"enabled": True, "authentication_required": True},
        "transactions": {"enabled": True, "authentication_required": True},
        "transaction": {"enabled": True, "authentication_required": True},
    }


def bad_fields_type_integration(asset, lang):
    return {"fields": "not a dict"}


@pytest.mark.django_db
@patch("polaris.sep6.info.registered_info_func", bad_fields_type_integration)
def test_bad_fields_type(client, usd_asset_factory):
    server_error(client, usd_asset_factory)


def bad_types_type(asset, lang):
    return {"types": "not a dict"}


@pytest.mark.django_db
@patch("polaris.sep6.info.registered_info_func", bad_types_type)
def test_bad_types_type(client, usd_asset_factory):
    server_error(client, usd_asset_factory)


def bad_nested_fields_no_description(asset, lang):
    return {"types": {"cash": {"fields": {"key": {"optional": True}}}}}


@pytest.mark.django_db
@patch("polaris.sep6.info.registered_info_func", bad_nested_fields_no_description)
def test_bad_nested_fields_no_description(client, usd_asset_factory):
    server_error(client, usd_asset_factory)


def bad_nested_fields_extra_key(asset, lang):
    return {
        "types": {
            "cash": {
                "fields": {
                    "key": {"description": "test", "extra_info": "bad key-val pair"}
                }
            }
        }
    }


@pytest.mark.django_db
@patch("polaris.sep6.info.registered_info_func", bad_nested_fields_extra_key)
def test_bad_nested_fields_extra_key(client, usd_asset_factory):
    server_error(client, usd_asset_factory)


def server_error(client, usd_asset_factory):
    usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(INFO_PATH)
    content = json.loads(response.content)
    assert response.status_code == 500
    assert content == {"error": "unable to process the request"}


def unsupported_lang(asset, lang):
    raise ValueError()


@pytest.mark.django_db
@patch("polaris.sep6.info.registered_info_func", unsupported_lang)
def test_unsupported_lang(client, usd_asset_factory):
    usd_asset_factory(protocols=[Transaction.PROTOCOL.sep6])
    response = client.get(INFO_PATH + "?lang=es")
    content = json.loads(response.content)
    assert response.status_code == 400
    assert content == {"error": "unsupported 'lang'"}
