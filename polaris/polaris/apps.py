from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


class PolarisConfig(AppConfig):
    name = "polaris"
    verbose_name = "Django Polaris"

    def ready(self):
        """
        Initialize the app
        """
        from polaris import settings  # loads internal settings
        from polaris import cors  # loads CORS signals
        from polaris.sep24.utils import check_sep24_config

        self.check_middleware()
        self.check_protocol()
        if "sep-24" in settings.ACTIVE_SEPS:
            check_sep24_config()

    @staticmethod
    def check_middleware():
        from django.conf import settings as django_settings

        cors_middleware_path = "corsheaders.middleware.CorsMiddleware"
        if cors_middleware_path not in django_settings.MIDDLEWARE:
            raise ImproperlyConfigured(
                f"{cors_middleware_path} is not installed in settings.MIDDLEWARE"
            )

    @staticmethod
    def check_protocol():
        from polaris import settings
        from polaris.utils import getLogger
        from django.conf import settings as django_settings

        logger = getLogger(__name__)
        if settings.LOCAL_MODE:
            logger.warning(
                "Polaris is in local mode. This makes the SEP-24 interactive flow "
                "insecure and should only be used for local development."
            )
        if getattr(django_settings, "SECURE_PROXY_SSL_HEADER"):
            logger.debug(
                "SECURE_PROXY_SSL_HEADER should only be set if Polaris is "
                "running behind an HTTPS reverse proxy."
            )
        elif not (
            settings.LOCAL_MODE or getattr(django_settings, "SECURE_SSL_REDIRECT")
        ):
            logger.debug(
                "SECURE_SSL_REDIRECT is required to redirect HTTP traffic to HTTPS"
            )
