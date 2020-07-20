from django.apps import AppConfig


class AnchorConfig(AppConfig):
    name = "server"

    def ready(self):
        from polaris.integrations import register_integrations
        from .integrations import (
            MyDepositIntegration,
            MyWithdrawalIntegration,
            MyCustomerIntegration,
            MySendIntegration,
            MyRailsIntegration,
            toml_integration,
            scripts_integration,
            fee_integration,
            info_integration,
        )

        register_integrations(
            deposit=MyDepositIntegration(),
            withdrawal=MyWithdrawalIntegration(),
            toml=toml_integration,
            scripts=scripts_integration,
            fee=fee_integration,
            sep6_info=info_integration,
            customer=MyCustomerIntegration(),
            send=MySendIntegration(),
            rails=MyRailsIntegration(),
        )
