import requests
from pprint import pprint

if __name__ == "__main__":

    # create asset on testnet
    # TODO

    # add asset to polaris
    # TODO

    # create polaris client
    POLARIS_URI = "http://localhost:8000"
    POLARIS_TOML_ENDPOINT = "/.well-known/stellar.toml"
    POLARIS_DEPOSIT_ENDPOINT = "/deposit"
    POLARIS_INFO_ENDPOINT = "/info"
    POLARIS_TRANSACTION_ENDPOINT = "/transaction"
    POLARIS_TRANSACTIONS_ENDPOINT = "/transactions"

    toml = requests.get(POLARIS_URI + POLARIS_TOML_ENDPOINT)
    pprint(toml)

    # create transaction with new account details

    # wait for polaris to create the account on testnet

    # check the status of transaction to be pending_trust

    # send request to horizon to a the trustline for this asset

    # wait for polaris to detect the trustline and submit the deposit
    # transaction to Horizon

    # check transaction in polaris is complete
    # verify transaction on testnet
    # check balance in account is equal to expected

    pass
