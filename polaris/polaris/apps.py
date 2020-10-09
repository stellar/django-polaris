import json
from datetime import timedelta
from django.apps import AppConfig


class PolarisConfig(AppConfig):
    name = "polaris"
    verbose_name = "Django Polaris"

    def ready(self):
        """
        Initialize the app
        """
        from django.conf import settings as django_settings
        from polaris import cors  # loads CORS signals
        from polaris.sep24.utils import check_sep24_config
        from polaris.models import Asset, utc_now
        from polaris import settings

        if not hasattr(django_settings, "POLARIS_ACTIVE_SEPS"):
            raise AttributeError(
                "POLARIS_ACTIVE_SEPS must be defined in your django settings file."
            )

        self.check_middleware()
        self.check_protocol()

        # If configured, refreshes each Asset's distribution account signers and
        # weights. Limits the refresh interval to once per minute to block Polaris'
        # multiprocess architecture from making an API call and DB query for every
        # process running.
        if settings.REFRESH_ASSETS_ON_STARTUP:
            for asset in Asset.objects.filter(distribution_seed__isnull=False):
                if utc_now() - asset.updated_at > timedelta(minutes=1):
                    self.refresh_distribution_account(asset)

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

    @staticmethod
    def refresh_distribution_account(asset):
        from polaris import settings

        account_json = (
            settings.HORIZON_SERVER.accounts()
            .account_id(account_id=asset.distribution_account)
            .call()
        )
        asset.distribution_account_signers = json.dumps(account_json["signers"])
        asset.distribution_account_thresholds = json.dumps(account_json["thresholds"])
        asset.distribution_account_master_signer = None
        for s in account_json["signers"]:
            if s["key"] == asset.distribution_account:
                asset.distribution_account_master_signer = json.dumps(s)
                break
        asset.save()
