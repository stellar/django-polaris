from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from polaris.sep38.serializers import OffChainAssetSerializer
from polaris.models import Asset, OffChainAsset


@api_view(["GET"])
@renderer_classes([JSONRenderer])
def info(_: Request) -> Response:
    """
    Definition of the /info endpoint, in accordance with SEP-0038.
    See: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0038.md#response
    """
    info_data = {"assets": []}
    for asset in Asset.objects.filter(sep38_enabled=True):
        info_data["assets"].append({"asset": f"stellar:{asset.code}:{asset.issuer}"})
    info_data["assets"].extend(
        OffChainAssetSerializer(OffChainAsset.objects.all(), many=True).data
    )
    return Response(info_data)
