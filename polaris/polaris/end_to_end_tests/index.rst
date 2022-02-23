=====================================
Using End-to-End Tests
=====================================

Currently, end-to-end tests are only supported for deposit flows:
 - deposit_with_account_creation
 - deposit_with_existing_account

------------------

**Notes:**
 - It is expected that a test asset has already been created on the Stellar testnet and the asset has been added to Polaris 
 - load_size is how many times you want the tests to be executed (via multithreading)


**Examples:**

Pre-create 2 Stellar Accounts with trustlines added for the given asset, (accounts are written to ./cached_accounts.txt):
::

    python deposit_end_to_end_test.py --asset-name FUNG1 --asset-issuer GAQQTSLTFJZXDP7ZHWVJ3DRB6X46T35QMUJMZVWFSIZPRQ6KWSNPKV3U --generate-accounts 2


Use the 2 pre-created Stellar Accounts to test deposit_with_existing_account (accounts in ./cached_account.txt are used for the test):
::

    python deposit_end_to_end_test.py --asset-name FUNG1 --asset-issuer  GAQQTSLTFJZXDP7ZHWVJ3DRB6X46T35QMUJMZVWFSIZPRQ6KWSNPKV3U --tests deposit_with_existing_account —load_size 2


Create 5 Stellar Accounts (with trustliens) to test deposit_with_existing_account:
::

    python deposit_end_to_end_test.py --asset-name FUNG1 --asset-issuer  GAQQTSLTFJZXDP7ZHWVJ3DRB6X46T35QMUJMZVWFSIZPRQ6KWSNPKV3U --tests deposit_with_existing_account —load_size 5

Test deposit_with_account_creation with load_size of 3 (3 random accounts are generated and Polaris will take care of funding them on the Stellar Network):
::

    python deposit_end_to_end_test.py --asset-name FUNG1 --asset-issuer  GAQQTSLTFJZXDP7ZHWVJ3DRB6X46T35QMUJMZVWFSIZPRQ6KWSNPKV3U --tests deposit_with_account_creation —load_size 3