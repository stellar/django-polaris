from django.apps import AppConfig


class PolarisConfig(AppConfig):
    name = "polaris"
    verbose_name = "Django Polaris"

    def ready(self):
        """
        Initialize the app. Currently a no-op.
        """
        from polaris.helpers import check_middleware

        check_middleware()
