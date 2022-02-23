from threading import Thread
from queue import Queue
import argparse
import requests
import json
import time
from datetime import datetime, timezone


from stellar_sdk import (
    Account,
    Asset,
    Keypair,
    TransactionEnvelope,
    TransactionBuilder,
    Server
)

from stellar_sdk.exceptions import (
    NotFoundError,
)

POLARIS_URI = "http://localhost:8000"
POLARIS_AUTH_ENDPOINT = POLARIS_URI + "/auth"
POLARIS_TOML_ENDPOINT = POLARIS_URI + "/.well-known/stellar.toml"
POLARIS_DEPOSIT_ENDPOINT = POLARIS_URI + "/sep6/deposit"
POLARIS_INFO_ENDPOINT = POLARIS_URI + "/sep6/info"
POLARIS_TRANSACTION_ENDPOINT = POLARIS_URI + "/sep6/transaction"
POLARIS_TRANSACTIONS_ENDPOINT = POLARIS_URI + "/transactions"
POLARIS_CUSTOMER_ENDPOINT = POLARIS_URI + "/kyc/customer"

STELLAR_TESTNET_NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"
HORIZON_URI = "https://horizon-testnet.stellar.org"
FRIENDBOT_URI = "https://friendbot.stellar.org"



def get_polaris_token(public_key, secret_key):
    response = requests.get(POLARIS_AUTH_ENDPOINT, {"account": public_key})
    content = response.json()

    envelope_xdr = content["transaction"]
    envelope = TransactionEnvelope.from_xdr(
        envelope_xdr, network_passphrase=STELLAR_TESTNET_NETWORK_PASSPHRASE
    )
    envelope.sign(secret_key)
    response = requests.post(
        POLARIS_AUTH_ENDPOINT,
        data={"transaction": envelope.to_xdr()},
    )
    content = json.loads(response.content)
    return content["token"]


def create_account():
    pass


def create_trustline(server: Server, asset: Asset, account: Account, secret: str):
    #print(f"creating trustline for asset: {asset.code} on account: {account.account.account_id}")
    transaction = (
        TransactionBuilder(
            source_account=account,
            network_passphrase=STELLAR_TESTNET_NETWORK_PASSPHRASE,
            base_fee=100,
        )
    )\
        .append_change_trust_op(asset)\
        .build()

    transaction.sign(secret)

    response = server.submit_transaction(transaction)
    # TODO read response and verify that trustline was created
    # print(response)


def is_pending_trust(asset: Asset, json_resp):
    pending_trust = True
    for balance in json_resp["balances"]:
        if balance.get("asset_type") in ["native", "liquidity_pool_shares"]:
            continue
        asset_code = balance["asset_code"]
        asset_issuer = balance["asset_issuer"]
        if (
            asset.code == asset_code
            and asset.issuer == asset_issuer
        ):
            pending_trust = False
            break
    return pending_trust

def create_polaris_user(user_public_key, headers):
    user_data = {
        "account": user_public_key,
        "first_name": "stephen",
        "last_name": "fung",
        "email_address": "stephen@stellar.org",
        "bank_number": "123",
        "bank_account_number": "123456789"
    }
    create_user = requests.put(POLARIS_CUSTOMER_ENDPOINT, data=user_data, headers=headers)
    #pprint(json.loads(create_user.content))
    return json.loads(create_user.content)


def create_polaris_deposit_transaction(user_public_key, asset_code, headers):
    params = {
        "asset_code": asset_code,
        "account": user_public_key,
        "type": "bank_account",
        "amount": 5,
    }
    #print(f"creating polaris deposit transaction with params: {str(params)}")
    deposit_transaction = requests.get(POLARIS_DEPOSIT_ENDPOINT, params=params, headers=headers)
    json_transaction = json.loads(deposit_transaction.content)
    #pprint(json_transaction)
    return json_transaction

def get_polaris_transaction(transaction_id, headers):
    #print(f"fetching transaction: {transaction_id} from Polaris")
    params = {
        "id": transaction_id
    }
    transaction = requests.get(POLARIS_TRANSACTION_ENDPOINT, params=params, headers=headers)
    json_transaction = json.loads(transaction.content)
    #pprint(json_transaction)
    return json_transaction["transaction"]


def is_account_created(server, user_public_key):
    try:
        json_resp = server.accounts().account_id(account_id=user_public_key).call()
    except NotFoundError:
        raise RuntimeError(f"account {user_public_key} does not exist")

    return load_account(json_resp), json_resp

def load_account(resp):
    sequence = int(resp["sequence"])
    account = Account(account=resp["account_id"], sequence=sequence, raw_data=resp)
    return account

def test_polaris_deposit_with_existing_account_and_trustline(asset, time_results, account):
    verbose = False
    start = time.time()

    user_public_key = account[0]
    user_secret_key = account[1]

    if verbose:
        print(f"public key: {user_public_key}")
        print(f"secret key: {user_secret_key}")

    # get token from polaris
    token = get_polaris_token(user_public_key, user_secret_key)

    headers = {"Authorization": f"Bearer {token}"}

    # create user
    create_polaris_user(user_public_key, headers)

    # create deposit transaction in polaris
    transaction_id = create_polaris_deposit_transaction(user_public_key, asset.code, headers)["id"]

    # wait for polaris to create the account on testnet
    if verbose:
        print(f"waiting for polaris to create account: {user_public_key}")
    while True:
        try:
            json_resp = server.accounts().account_id(account_id=user_public_key).call()
            #print(f"account: {user_public_key} created")
            break
        except NotFoundError:
            time.sleep(1)

    # check if transaction in polaris is complete
    transaction = {}
    while True:
        transaction = get_polaris_transaction(transaction_id, headers)
        transaction_status = transaction["status"]
        #print(f"transaction {transaction_id} status is: {transaction_status}")
        if transaction_status == "completed":
            if verbose:
                print(f"transaction {transaction_id} status is: {transaction_status}")
            time_elapsed = (datetime.now(timezone.utc) -
                            datetime.strptime(transaction["started_at"],
                                              "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)).total_seconds()
            time_results.put(round(time_elapsed, 3))
            break
        time.sleep(1)

    if verify:
        pass
        # TODO verify transaction on testnet
        # TODO check balance in account is equal to expected

    if verbose:
        print(f"test_polaris_deposit_with_account_creation: {time_elapsed} seconds")


def test_polaris_deposit_with_account_creation(asset, time_results):
    verbose = False
    start = time.time()

    # generate keypair to use for new account
    kp = Keypair.random()
    user_public_key = kp.public_key
    user_secret_key = kp.secret

    if verbose:
        print(f"public key: {user_public_key}")
        print(f"secret key: {user_secret_key}")

    # get token from polaris
    token = get_polaris_token(user_public_key, user_secret_key)

    headers = {"Authorization": f"Bearer {token}"}

    # create user
    create_polaris_user(user_public_key, headers)

    # create deposit transaction in polaris
    transaction_id = create_polaris_deposit_transaction(user_public_key, asset.code, headers)["id"]

    # wait for polaris to create the account on testnet
    if verbose:
        print(f"waiting for polaris to create account: {user_public_key}")
    while True:
        try:
            json_resp = server.accounts().account_id(account_id=user_public_key).call()
            print(f"account: {user_public_key} created")
            break
        except NotFoundError:
            time.sleep(5)

    # check that status of transaction in polaris is 'pending_trust'
    if verify:
        while True:
            transaction_status = get_polaris_transaction(transaction_id, headers)["status"]
            #print(f"transaction status is: {transaction_status}")
            if transaction_status == "pending_trust":
                if verbose:
                    print(f"transaction {transaction_id} status is: {transaction_status}")
                break
            time.sleep(1)

    # send request to horizon to create a trustline for this asset
    user_account = server.load_account(account_id=user_public_key)
    create_trustline(server, asset, user_account, user_secret_key)

    # check if transaction in polaris is complete
    while True:
        transaction = get_polaris_transaction(transaction_id, headers)
        transaction_status = transaction["status"]
        #print(f"transaction {transaction_id} status is: {transaction_status}")
        if transaction_status == "completed":
            if verbose:
                print(f"transaction {transaction_id} status is: {transaction_status}")
            time_elapsed = (datetime.now(timezone.utc) -
                            datetime.strptime(transaction["started_at"],
                                              "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)).total_seconds()
            time_results.put(round(time_elapsed, 3))
            break
        time.sleep(1)

    if verify:
        pass
        # TODO verify transaction on testnet
        # TODO check balance in account is equal to expected

    if verbose:
        print(f"test_polaris_deposit_with_account_creation: {time_elapsed} seconds")


def create_stellar_account_with_trustline(server, asset, account_results=None):
    kp = Keypair.random()
    user_public_key = kp.public_key
    user_secret_key = kp.secret
    params = {
        "addr": user_public_key
    }
    res = requests.get(FRIENDBOT_URI, params=params)

    # send request to horizon to create a trustline for this asset
    user_account = server.load_account(account_id=user_public_key)
    create_trustline(server, asset, user_account, user_secret_key)

    if account_results is not None:
        account_results.put((user_public_key, user_secret_key))

    return (user_public_key, user_secret_key)

def create_stellar_accounts_with_trustline(server, count, asset, multithread=False):
    account_results = Queue()
    threads = []
    if multithread:
        for _ in range(count):
            t = Thread(target=create_stellar_account_with_trustline,
                       args=(server, asset, account_results))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()
        for x in list(account_results.queue): print(x)
        return list(account_results.queue)
    else:
        accounts = []
        for _ in range(count):
            account = create_stellar_account_with_trustline(asset)
            accounts.append(account)
    return accounts



def get_existing_stellar_accounts(count):
    accounts = []
    with open("./cached_accounts.txt") as f:
        lines = f.readlines()
    for line in lines:
        l = line.strip().split(",")
        accounts.append((l[0], l[1]))
    return accounts
    # 30 accounts
    accounts = [
        ('GATD7CMWUTKWX3NKCN4BXE4L6TNXG2NYRCCAHXYAQ4U2QVTWYMRGYWBP',
         'SDIETGJBBLUSUPK7UVMNTIPGDFKL6OVN24X3F4E7IUACWSS35T2HVGEM'),
        ('GDY2JT4HQKNYX4N7QTVWIXFAA3BZVBM2XQOVFGCRLZGTBVUS22BCNDV3',
         'SCSHZLCQDVHSPTGVULTNFJCZVP5Q4KKXJVAELRSYZNAQWGYG7FQT4QHV'),
        ('GAMOHNMEI2MVVPN467MCKMU7I25Z6CS7TONQHYG5YORDJPHSK6DH5TE3',
         'SCCPZ7E56METMZJILCRXVIV4ZYOR3PA5EQXGSWKZADMK3A4ZPRPZ3FZZ'),
        ('GD6KQ7UUATLA7L4BSFQPZS4CYWPIPQSB25VDJPLKXMV5RLZ2JT7CV3G7',
         'SDRKRMDG7VVDY2IA72S5FFSIJ5K6TT5J6HDD22G6WM3UUQPMPOWUQWID'),
        ('GDM667EQX4T4EBYRQTCTEQ3L2GPGATSL6AZAJG2PJPZ7G4DP5DRABLX7',
         'SAPVMC4J6WF7U5MUPHKRX6QJFZ2GGJBKZCRUFPKW2ZWRPXO32PHD7GZC'),
        ('GBZR4DJ2GFIEVXX4BCNYW2O4UA724J5T6ZC4W7QRY4AK5WR22W26ZZ6C',
         'SDAHY4OKTYWL54PAROT2NFH4AA6BFJAWGCTTJG2SKAVSL2NPUE4PWZFL'),
        ('GAZQKUBD5H7VSUEMI4J4NCID6DJICYYGNBKDCKHGVMMBFGQWH5DCUBLH',
         'SBAVVBRP2TWPO7ZF4SNCYRQC3FBU5HXEZNSO64NWHWTO2OHLRCNHXI55'),
        ('GACMD6WXNYH3JZ7NM7MP3ERCSOV4FNR25KNNMEJY7S3HTEZH7EXVKC7Z',
         'SAWHDXXBE46HFZDOD4YJPJ6G5TUWROC6CMVTWB4J6H7XD7R7CURO5REJ'),
        ('GBWIC4MV5Z2JSIPDYCETAV6GFPL2SFMKGTRINFTR2S7OFOFSEQ7DMA55',
         'SCT2F7FYMKUK4DVMCE67FHRAKUFMB7RDXPDKDSSVWY2QMQ7XRWH3AF4Q'),
        ('GCAO3TPN3QGKJO6RHPF4YGGIG2DJAGEXR73TMEVMIYJINGYNPENVCCY5',
         'SBRYVS6UD5A4W3YAOMQHC7WGLWQHXQ3EWR2LTK7HVOVUCTUNCZJVJWPF'),
        ('GAAVDMACMFIPMOJ7CG7AI3Q4VG37BLX7V2ND3HTKGDS3XVBNJLPJYJQ7',
         'SCVLFYH5I2S4SMKJ56YWWWQK2WQXCZMIC7QDFW4GZDRUP2JNZ7IFJK2E'),
        ('GDG7JROSB72II3NNWG6UAC3MF2CRQOOAUFITZW3FXANFKF2MAVSO7XNR',
         'SC4NOKCFS6TKPIXXBQ76ZJSPEMNDVFEBA7J3E3SEVOYPLPG2DU3AGF3N'),
        ('GALCZN62PAYWIUMCFCEVYXKMJC665OJDKKKIQYHZSMJSFNAMORO7QLFV',
         'SCNPG34SYDKR5UWMMROP3VGJY4R2AEZ5AASE36FQE37A2SUZ5VRYVEI3'),
        ('GCN62L4HIDPDWCB7D6YW2UJNIR2RZSW6WSYF4LIYW4MIBH3RHRLSH3EH',
         'SBCVCBKFZXNHPZ7VHBF6LAVMXEJ3B4XEWOIJDC3PWXFPN77PFHHBTRLJ'),
        ('GAED7EF4VQ46DTX5AMT6XQ6OI4OTMWTRLYH6PXXPV4BW6JIYAXOHOABM',
         'SBZDYMCK7F5LPP2UXWXUP3QMERESFIJUCPINAIVYIJSIOXQ65YQ6I7LY'),
        ('GDFKYJSYAZUJ7Y5IS7W5C5GZBO3WKVKHPHORK3YRG4LBRC6NL4WISEA6',
         'SAOVSV3H5BQ2CLHUBZRYG4UFQC4ZFN4R2L752F55PG77HOZ5ONW6YTYM'),
        ('GBUDJXCG2V4V23XMWS37MHP3RXBFNKYCH3OCO63PJQ5JR7YO67Q6MVJT',
         'SCWDEZM5UMZGXRKWKOGQ7WQTNVVFQSWG2NETDWYKGWERT4UK7WV4JDQN'),
        ('GBXLFFC3SM34R7WXAF27QYMZXCIVUR4O5W2KHJP352H43VDU2SOYUYMP',
         'SBXUFC462RJVCU2DWSDTEFGON2OXXH2DW7X3BCC6XHPCLHQ4UHXEDHAF'),
        ('GAGLCXJ2KYULS2IVVVBNXZUPOB2FQQ5V3TVZTLI3V6V3GHCZGBPNP3BP',
         'SAVE6MXI4JO2C7EMAEQCZ5KAJDNRO4NS4QO6BRK3JHGXSUWIPV4Y2YWA'),
        ('GAUKGTZOBBVB2OVBOWJMJPLZVENZ2Q4IX6GYKETMKHDPLATLFJACNBVI',
         'SBVU4FZRHLM6KTY626U62WJKS2SWAYITJHLXZW2FGCNTMF77SOG4ZRIY'),
        ('GBDJ5VTCYTYKDYMLYS4RDB46GE6FXARL35KBX2TSLV7G5E7G5OQ2KCID',
         'SD2FSIE2BXUMX3VXAZGG6EUYIIC6RMMLDP6NSZ4IZ56P7JINXT3LENCT'),
        ('GDYHJWLH2K34L5MFC73QHYGYHAY3SDJD2EIISHRAGZIDHIOEYEVKMLHQ',
         'SD7ITSYZTTJHXJEDAJA3FP6KKTKJQSCBQPKGQOAOYFTF53CSQ3YOIR2M'),
        ('GAAFBYUHY2ZNEDW5PZLOAV5QJSUMUEAWY4L6KCRHQFAEDJTLPRUGFDLH',
         'SC2ZLO4YRH3Y6D2KUXM6HMOID36IJKH2L7TR5S6URGYA5GYJ2XTDMOF3'),
        ('GCLUZBV2QKU757F2XDIDLM4T6M2D2TU3LPHBAKMXB5LZ5DICHIEUIXHA',
         'SBBRHHGWYDEEYJPDICCKESNPYPW4ZSAVSFYLKOELCH64COBAG5LNAYBB'),
        ('GAWOLDXQ4NN5ZIU4KTMUIKFPKIAFIVQ5NI6MILLJRCTDJMVZ6GEBZBEU',
         'SAMINFBYEVVSNHWCOFZBA5EDJHRFBWGBDT2GEVAVEXLUIFWOOSYSECWG'),
        ('GDPXDLMA6XZHBDP2OLTMSKJVHO2OOO73P3LHRHDHCYQKBR64UUAEF7XK',
         'SDOV25LDW3JZ7FHSEDX6B3SISLVWY3XEUKGBO2RJENGUOXKTM6X55LTR'),
        ('GAHAAQZ3VLZC4PZ3LQ2IXYTS535NPTG4ITA6HJIHTZ6RCKODIDPCMCHY',
         'SC643JLZJ4HUE6YHAHACQSUUNGELYGTC43BIR22VGFE37DKZ6VVWS6G3'),
        ('GCD5K267JHDDASXNXD7RQ46BME53VUHCT5266HECVTFIE47U5YC2R4HP',
         'SDBMFVB4UJYOGVXG6XYFPJ3IXO43GIAPQT7STZQ7B27YLQC4HWQGNBZ6'),
        ('GDBPDTROTJORREVJNPTKT6NHLRNU5TRFKLHG7IDP5QHIJVYYMNZCHFTS',
         'SBKILG5O2YX52JZ7EANR6ZIX7OZBPZMTWCUFZJNNFNAXNO7PDGB4ZYDS'),
        ('GADZYLZRABA3ZVKEPYFDXD3TUZXFWEKDGZVID553YHV6VTN2TVKSQZZL',
         'SDCDPLCW4Z3WDI6EMSI4DV65DGZ2FZFXQQKMBWY2557EZ6W5GER2OZCQ'),
        ('GAU5SG37PHBTXWLXCFIE6B4IH2ND7V4DC4OI5BI3SAKBR5PD3A6PI7CG',
         'SDMVOEH6G6OQUT4BA43OVJC3IWUIFR6EVC26S4WRBMZLXB7H4FOC2GLQ'),
        ('GBUDJXCG2V4V23XMWS37MHP3RXBFNKYCH3OCO63PJQ5JR7YO67Q6MVJT',
         'SCWDEZM5UMZGXRKWKOGQ7WQTNVVFQSWG2NETDWYKGWERT4UK7WV4JDQN'),
        ('GBXLFFC3SM34R7WXAF27QYMZXCIVUR4O5W2KHJP352H43VDU2SOYUYMP',
         'SBXUFC462RJVCU2DWSDTEFGON2OXXH2DW7X3BCC6XHPCLHQ4UHXEDHAF'),
        ('GAGLCXJ2KYULS2IVVVBNXZUPOB2FQQ5V3TVZTLI3V6V3GHCZGBPNP3BP',
         'SAVE6MXI4JO2C7EMAEQCZ5KAJDNRO4NS4QO6BRK3JHGXSUWIPV4Y2YWA'),
        ('GAUKGTZOBBVB2OVBOWJMJPLZVENZ2Q4IX6GYKETMKHDPLATLFJACNBVI',
         'SBVU4FZRHLM6KTY626U62WJKS2SWAYITJHLXZW2FGCNTMF77SOG4ZRIY'),
        ('GBDJ5VTCYTYKDYMLYS4RDB46GE6FXARL35KBX2TSLV7G5E7G5OQ2KCID',
         'SD2FSIE2BXUMX3VXAZGG6EUYIIC6RMMLDP6NSZ4IZ56P7JINXT3LENCT'),
        ('GDYHJWLH2K34L5MFC73QHYGYHAY3SDJD2EIISHRAGZIDHIOEYEVKMLHQ',
         'SD7ITSYZTTJHXJEDAJA3FP6KKTKJQSCBQPKGQOAOYFTF53CSQ3YOIR2M'),
        ('GAAFBYUHY2ZNEDW5PZLOAV5QJSUMUEAWY4L6KCRHQFAEDJTLPRUGFDLH',
         'SC2ZLO4YRH3Y6D2KUXM6HMOID36IJKH2L7TR5S6URGYA5GYJ2XTDMOF3'),
        ('GCLUZBV2QKU757F2XDIDLM4T6M2D2TU3LPHBAKMXB5LZ5DICHIEUIXHA',
         'SBBRHHGWYDEEYJPDICCKESNPYPW4ZSAVSFYLKOELCH64COBAG5LNAYBB'),
        ('GAWOLDXQ4NN5ZIU4KTMUIKFPKIAFIVQ5NI6MILLJRCTDJMVZ6GEBZBEU',
         'SAMINFBYEVVSNHWCOFZBA5EDJHRFBWGBDT2GEVAVEXLUIFWOOSYSECWG'),
        ('GDPXDLMA6XZHBDP2OLTMSKJVHO2OOO73P3LHRHDHCYQKBR64UUAEF7XK',
         'SDOV25LDW3JZ7FHSEDX6B3SISLVWY3XEUKGBO2RJENGUOXKTM6X55LTR'),
        ('GAHAAQZ3VLZC4PZ3LQ2IXYTS535NPTG4ITA6HJIHTZ6RCKODIDPCMCHY',
         'SC643JLZJ4HUE6YHAHACQSUUNGELYGTC43BIR22VGFE37DKZ6VVWS6G3'),
        ('GCD5K267JHDDASXNXD7RQ46BME53VUHCT5266HECVTFIE47U5YC2R4HP',
         'SDBMFVB4UJYOGVXG6XYFPJ3IXO43GIAPQT7STZQ7B27YLQC4HWQGNBZ6'),
        ('GDBPDTROTJORREVJNPTKT6NHLRNU5TRFKLHG7IDP5QHIJVYYMNZCHFTS',
         'SBKILG5O2YX52JZ7EANR6ZIX7OZBPZMTWCUFZJNNFNAXNO7PDGB4ZYDS'),
        ('GADZYLZRABA3ZVKEPYFDXD3TUZXFWEKDGZVID553YHV6VTN2TVKSQZZL',
         'SDCDPLCW4Z3WDI6EMSI4DV65DGZ2FZFXQQKMBWY2557EZ6W5GER2OZCQ'),
        ('GAU5SG37PHBTXWLXCFIE6B4IH2ND7V4DC4OI5BI3SAKBR5PD3A6PI7CG',
         'SDMVOEH6G6OQUT4BA43OVJC3IWUIFR6EVC26S4WRBMZLXB7H4FOC2GLQ'),
    ]

    return accounts[:count]


if __name__ == "__main__":
    # - implement verbose mode
    # - clean up structure of script
    # NOTES:
    #   - Asset needs to be created on the testnet and added to Polaris

    TESTS = [
        "deposit_with_account_creation",
        "deposit_with_existing_account"
    ]

    parser = argparse.ArgumentParser()
    parser.add_argument('--asset-name', "-an",help="name of the asset to add a trustline for", type=str, required=True)
    parser.add_argument('--asset-issuer', "-ai", help="issuer of the asset to add a trustline for", type=str, required=True)
    parser.add_argument('--verbose', '-v', help="verbose mode", type=bool, default=False)
    parser.add_argument('--generate-accounts', help="verbose mode", type=int, default=0)
    parser.add_argument('--verify', help="verification step that checks deposited assets on testnet", type=bool, default=False)
    parser.add_argument('--load-size', "-ls", help="number of tests to execute (multithreaded)", type=int, default=1)
    parser.add_argument('--tests', "-t", nargs="*", help=f"names of tests to execute: {TESTS}", default=TESTS)
    parser.add_argument('--use-cached-accounts', "-ca", help=f"use pre-created accounts in cached-accounts.txt", default=False)

    
    args=parser.parse_args()

    global verbose, verify
    verbose = args.verbose
    verify = args.verify
    load_size = args.load_size
    tests_to_run = args.tests
    use_cached_accounts = args.use_cached_accounts
    accounts_to_generate = args.generate_accounts
    asset = Asset(args.asset_name, args.asset_issuer)
    
    server = Server(horizon_url=HORIZON_URI)

    if accounts_to_generate:
        print(f"generating accounts {accounts_to_generate} accounts with trustline to asset {asset.code}")
        accounts = create_stellar_accounts_with_trustline(server, accounts_to_generate, asset, multithread=True)
        print(accounts)
        with open("./cached_accounts.txt", "w") as f:
            for acc in accounts:
                f.write(f"{acc[0]},{acc[1]}\n")
        print(f"accounts written to file: cached_accounts.txt")
        exit(0)

    for test in tests_to_run:
        if test not in TESTS:
            print(f"error: '{test}' is not in the list of available tests: {TESTS} ")
            exit(1)

    

    start = time.time()
    for test in tests_to_run:
        results = Queue()
        threads = []
        if test == "deposit_with_account_creation":
            for _ in range(load_size):
                t = Thread(target=test_polaris_deposit_with_account_creation,
                            args=(asset, results))
                threads.append(t)
                t.start()

        elif test == "deposit_with_existing_account":
            if use_cached_accounts:
                accounts = get_existing_stellar_accounts(load_size)
                if len(accounts) < load_size:
                    print(f"not enough pre-created stellar accounts in cached_accounts.txt"
                    f" - need: {load_size}, have: {len(accounts)}")
                    exit(1)
            else:
                accounts = create_stellar_accounts_with_trustline(server, load_size, asset, multithread=True)
            start = time.time()  # start the timer after stellar accounts have been created
            for i in range(args.load_size):
                t = Thread(target=test_polaris_deposit_with_existing_account_and_trustline,
                            args=(asset, results, accounts[i]))
                threads.append(t)
                t.start()

        for t in threads:
            t.join()

        time_elapsed = round(time.time() - start, 3)

        results = list(results.queue)
        print("#################################################")
        print(f"number of deposits: {len(results)}")
        print("deposit transaction times: ")
        print(results)
        print("=================================================")
        average = round(sum(results)/len(results), 3)
        print(f"average deposit time: {average}")
        print("=================================================")
        print(f"total time: {time_elapsed} seconds")
        print("=================================================")


