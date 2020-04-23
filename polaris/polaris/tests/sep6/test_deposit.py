import pytest
import json
from unittest.mock import patch
from typing import Dict

from polaris.tests.helpers import mock_check_auth_success
from polaris.integrations import DepositIntegration

DEPOSIT_PATH = "/sep6/deposit"


class GoodDepositIntegration(DepositIntegration):
    def process_sep6_request(self, params: Dict) -> Dict:
        return {"how": "test"}


@pytest.mark.django_db
@patch(
    "polaris.integrations.registered_deposit_integration",
    new_callable=GoodDepositIntegration,
)
@patch("polaris.sep10.utils.check_auth", side_effect=mock_check_auth_success)
def test_deposit_success(
    mock_check, mock_integration, client, acc1_usd_deposit_transaction_factory
):
    del mock_check, mock_integration
    deposit = acc1_usd_deposit_transaction_factory(sep6=True)
    asset = deposit.asset
    response = client.get(
        DEPOSIT_PATH, {"asset_code": asset.code, "account_id": deposit.stellar_account},
    )
    content = json.loads(response.content)
    assert content == {
        "how": "test",
        "min_amount": round(asset.deposit_min_amount, asset.significant_decimals),
        "max_amount": round(asset.deposit_max_amount, asset.significant_decimals),
        "fee_fixed": round(asset.deposit_fee_fixed, asset.significant_decimals),
        "fee_percent": asset.deposit_fee_percent,
    }
