from django.apps import AppConfig


class AnchorConfig(AppConfig):
    name = "server"

    def ready(self):
        from polaris.integrations import register_integrations
        from .integrations import (
            MyDepositIntegration,
            MyWithdrawalIntegration,
            MyCustomerIntegration,
            toml_integration,
            scripts_integration,
            fee_integration,
            info_integration,
        )

        register_integrations(
            deposit=MyDepositIntegration(),
            withdrawal=MyWithdrawalIntegration(),
            toml_func=toml_integration,
            scripts_func=scripts_integration,
            fee_func=fee_integration,
            info_func=info_integration,
            customer=MyCustomerIntegration(),
        )
