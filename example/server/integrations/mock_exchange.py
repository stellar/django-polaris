import math
import random
import time

# Rotates the random number at the specified interval
from decimal import Decimal

rotation_interval = 30


def _get_rotating_random_number() -> float:
    """
    Generate a random number every `rotation_interval` seconds.
    """
    random.seed(math.floor(time.time() / rotation_interval))
    return 0.5 + 0.01 * random.randint(0, 100)


def get_mock_indicative_exchange_price() -> Decimal:
    return Decimal(_get_rotating_random_number())


def get_mock_firm_exchange_price() -> Decimal:
    return Decimal(_get_rotating_random_number() + 0.1)
