from django.apps import AppConfig


class PolarisConfig(AppConfig):
    name = "polaris"
    verbose_name = "Django Polaris"

    def ready(self):
        """
        Initialize the app
        """
        from polaris.sep24.utils import check_middleware
        from django.conf import settings

        if not hasattr(settings, "ACTIVE_SEPS"):
            raise AttributeError(
                "ACTIVE_SEPS must be defined in your django settings file."
            )

        if "sep-24" in settings.ACTIVE_SEPS:
            check_middleware()
