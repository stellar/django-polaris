"""Helper functions to use across tests."""
from django.http import JsonResponse


def mock_check_auth_success(request, needs_auth, func):
    """Mocks `helpers.check_auth`, for success."""
    return func(request)


def mock_render_error_response(error_str):
    """Mocks `helpers.render_error_response`, for failure."""
    return JsonResponse({"error": error_str}, status=400)
