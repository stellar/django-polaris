from decimal import Decimal
from typing import Dict

from polaris.integrations import calculate_fee


def fee_integration(fee_params: Dict, *args, **kwargs) -> Decimal:
    """
    This function replaces the default registered_fee_func for demonstration
    purposes.

    However, since we don't have any custom logic to implement, it simply
    calls the default that has been replaced.
    """
    return calculate_fee(fee_params)
