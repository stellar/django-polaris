from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.sep24.utils import check_authentication
from polaris.sep38.utils import list_stellar_assets, list_offchain_assets
from polaris.utils import render_error_response


@api_view(["GET"])
@renderer_classes([JSONRenderer])
@check_authentication()
def info(_: Request) -> Response:
    """
    Definition of the /info endpoint, in accordance with SEP-0038.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#response
    """
    info_data = {"assets": []}

    # Populate stellar assets
    for asset in list_stellar_assets():
        info_data["assets"].append({"asset": f"stellar:{asset.code}:{asset.issuer}"})

    # Populate offchain assets
    offchain_assets = list_offchain_assets()

    for offchain_asset in offchain_assets:
        info_data["assets"].append(offchain_asset)

    return Response(info_data)
