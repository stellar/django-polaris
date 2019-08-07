from rest_framework import status
from rest_framework.response import Response


def render_error_response(description: str) -> Response:
    data = {"error": description}
    return Response(data, status=status.HTTP_400_BAD_REQUEST)
