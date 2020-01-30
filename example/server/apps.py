from django.apps import AppConfig


class AnchorConfig(AppConfig):
    name = "server"

    def ready(self):
        from polaris.integrations import register_integrations
        from .integrations import (
            MyDepositIntegration,
            MyWithdrawalIntegration,
            get_stellar_toml,
            scripts,
            calculate_custom_fee,
        )

        register_integrations(
            deposit=MyDepositIntegration(),
            withdrawal=MyWithdrawalIntegration(),
            toml_func=get_stellar_toml,
            javascript_func=scripts,
            fee_func=calculate_custom_fee,
        )
