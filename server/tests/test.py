"""
Tests for stellar-anchor-server. Currently just a simple test to keep circleci happy.

Once we introduce django-polaris 1.0 (with integration support) we'll start
writing more tests.
"""

import pytest


@pytest.mark.django_db
def test_get_no_args_endpoints(client):
    for endpoint in ["/.well-known/stellar.toml", "/info"]:
        assert client.get(endpoint).status_code == 200
