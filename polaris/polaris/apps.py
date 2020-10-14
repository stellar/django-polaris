from django.apps import AppConfig


class PolarisConfig(AppConfig):
    name = "polaris"
    verbose_name = "Django Polaris"

    def ready(self):
        """
        Initialize the app
        """
        from django.conf import settings as django_settings
        from polaris import settings  # loads internal settings
        from polaris import cors  # loads CORS signals
        from polaris.sep24.utils import check_sep24_config

        if not hasattr(django_settings, "POLARIS_ACTIVE_SEPS"):
            raise AttributeError(
                "POLARIS_ACTIVE_SEPS must be defined in your django settings file."
            )

        self.check_middleware()
        self.check_protocol()
        if "sep-24" in django_settings.POLARIS_ACTIVE_SEPS:
            check_sep24_config()

    @staticmethod
    def check_middleware():
        from django.conf import settings as django_settings

        err_msg = "{} is not installed in settings.MIDDLEWARE"
        cors_middleware_path = "corsheaders.middleware.CorsMiddleware"
        if cors_middleware_path not in django_settings.MIDDLEWARE:
            raise ValueError(err_msg.format(cors_middleware_path))

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
        if not (settings.LOCAL_MODE or getattr(django_settings, "SECURE_SSL_REDIRECT")):
            logger.warning(
                "SECURE_SSL_REDIRECT is required to redirect HTTP traffic to HTTPS"
            )
        if getattr(django_settings, "SECURE_PROXY_SSL_HEADER"):
            logger.warning(
                "SECURE_PROXY_SSL_HEADER should only be set if Polaris is "
                "running behind an HTTPS reverse proxy."
            )
