from corsheaders.signals import check_request_enabled


def cors_allow_origins_for_polaris_requests(sender, request, **_kwargs):
    return (
        request.path.startswith("/sep24")
        or request.path.startswith("/sep6")
        or request.path.startswith("/sep31")
        or request.path.startswith("/sep38")
        or request.path.startswith("/.well-known")
        or request.path.startswith("/auth")
        or request.path.startswith("/kyc")
    )


check_request_enabled.connect(cors_allow_origins_for_polaris_requests)
