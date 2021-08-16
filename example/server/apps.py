from django.apps import AppConfig


class AnchorConfig(AppConfig):
    name = "server"

    def ready(self):
        from polaris.integrations import register_integrations
        from .integrations import (
            MyDepositIntegration,
            MyWithdrawalIntegration,
            MyCustomerIntegration,
            MySEP31ReceiverIntegration,
            MyRailsIntegration,
            calculate_fee,
            fee_integration,
            info_integration,
        )

        register_integrations(
            deposit=MyDepositIntegration(),
            withdrawal=MyWithdrawalIntegration(),
            fee=calculate_fee,
            sep6_info=info_integration,
            customer=MyCustomerIntegration(),
            sep31_receiver=MySEP31ReceiverIntegration(),
            rails=MyRailsIntegration(),
        )
