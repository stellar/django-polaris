from http import HTTPStatus

from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.models import Asset
from polaris.sep38 import list_offchain_assets
from polaris.utils import render_error_response


@api_view(["GET"])
@renderer_classes([JSONRenderer])
def info(request: Request) -> Response:
    """
    Definition of the /info endpoint, in accordance with SEP-0038.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#response
    """

    info_data = {
        "assets": []
    }

    # Populate stellar assets
    for asset in Asset.objects.all():
        info_data["assets"].append({
            "asset": f"stellar:{asset.code}:{asset.issuer}"
        })

    # Populate offchain assets
    offchain_assets = list_offchain_assets()

    if offchain_assets is None:
        return render_error_response(
            "The anchor returned None as a list of offchain-asset. An empty list is expected.",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="text/html",
        )

    for offchain_asset in offchain_assets:
        info_data["assets"].append(offchain_asset)

    return Response(info_data)
