def noop_decor(*args):
    def decorator(func):
        return func

    return decorator


_stellar_assets = [
    {
        "code": "SRT",
        "issuer": "GCDNJUBQSX7AJWLJACMJ7I4BC3Z47BQUTMHEICZLE6MU4KQBRYG5JY6B",
    }
]

_offchain_assets = [
    {
        "id": 1,
        "schema": "iso4217",
        "identifier": "USD",
        "significant_decimals": 2,
        "country_codes": "USA",
    },
    {
        "id": 2,
        "schema": "iso4217",
        "identifier": "NGN",
        "significant_decimals": 2,
        "country_codes": "NRA",
    },
    {
        "id": 3,
        "schema": "iso4217",
        "identifier": "BRL",
        "significant_decimals": 2,
        "country_codes": "BRA",
    },
]

_sell_delivery_methods = [
    {
        "id": 1,
        "asset": "iso4217:USD",
        "name": "cash",
        "description": "Deposit cash USD at one of our agent locations.",
    },
    {
        "id": 2,
        "asset": "iso4217:USD",
        "name": "ACH",
        "description": "Send USD directly to the Anchor's bank account.",
    },
    {
        "id": 3,
        "asset": "iso4217:USD",
        "name": "PIX",
        "description": "Send USD directly to the Anchor's bank account.",
    },
    {
        "id": 4,
        "asset": "iso4217:BRL",
        "name": "cash",
        "description": "Deposit cash BRL at one of our agent locations.",
    },
    {
        "id": 5,
        "asset": "iso4217:BRL",
        "name": "ACH",
        "description": "Send BRL directly to the Anchor's bank account.",
    },
    {
        "id": 6,
        "asset": "iso4217:BRL",
        "name": "PIX",
        "description": "Send BRL directly to the Anchor's bank account.",
    },
    {
        "id": 7,
        "asset": "iso4217:NGN",
        "name": "cash",
        "description": "Deposit cash NGN at one of our agent locations.",
    },
]

_buy_delivery_methods = [
    {
        "id": 1,
        "asset": "iso4217:USD",
        "name": "cash",
        "description": "Pick up cash USD at one of our payout locations.",
    },
    {
        "id": 2,
        "asset": "iso4217:USD",
        "name": "ACH",
        "description": "Have USD sent directly to your bank account.",
    },
    {
        "id": 3,
        "asset": "iso4217:USD",
        "name": "PIX",
        "description": "Have USD sent directly to the account of your choice.",
    },
    {
        "id": 4,
        "asset": "iso4217:BRL",
        "name": "cash",
        "description": "Pick up cash BRL at one of our payout locations.",
    },
    {
        "id": 5,
        "asset": "iso4217:BRL",
        "name": "ACH",
        "description": "Have BRL sent directly to your bank account.",
    },
    {
        "id": 6,
        "asset": "iso4217:BRL",
        "name": "PIX",
        "description": "Have BRL sent directly to the account of your choice.",
    },
    {
        "id": 7,
        "asset": "iso4217:NGN",
        "name": "cash",
        "description": "Pick up cash NGN at one of our payout locations.",
    },
]


def get_mock_offchain_assets():
    assets = []
    for os in _offchain_assets:
        from polaris.models import OffChainAsset

        asset = OffChainAsset()
        asset.__dict__.update(os)
        assets.append(asset)

    return assets


def get_mock_stellar_assets():
    assets = []
    for ss in _stellar_assets:
        from polaris.models import Asset

        asset = Asset()
        asset.__dict__.update(ss)
        assets.append(asset)

    return assets


def get_mock_buy_delivery_methods():
    methods = []
    for bdms in _buy_delivery_methods:
        from polaris.models import BuyDeliveryMethod

        bdm = BuyDeliveryMethod()
        bdm.__dict__.update(bdms)
        methods.append(bdm)
    return methods


def get_mock_sell_delivery_methods():
    methods = []
    for sdms in _sell_delivery_methods:
        from polaris.models import SellDeliveryMethod

        sdm = SellDeliveryMethod()
        sdm.__dict__.update(sdms)
        methods.append(sdm)
    return methods
