from django.apps import AppConfig


class PolarisConfig(AppConfig):
    name = "polaris"
    verbose_name = "Django Polaris"

    def ready(self):
        """
        Initialize the app
        """
        from polaris import settings  # ensures internal settings are set
        from polaris import cors  # loads CORS signals
        from polaris.utils import check_config

        check_config()
