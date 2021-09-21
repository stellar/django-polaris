=======================
Shared Stellar Accounts
=======================

.. _`Stellar Memo`: https://developers.stellar.org/docs/glossary/transactions/?#memo

Shared accounts, sometimes called pooled or omnibus accounts, are Stellar accounts that hold the funds of multiple users and are managed by a service provider. These service providers can be cryptocurrency exchanges, wallet applications, remittance companies, or other businesses.

In the Stellar ecosystem today, users of these services are often assigned a `Stellar Memo`_ that the service provider uses internally to identify and track users' balances held within the shared account. These user memos can also be attached to Stellar transactions containing payment operations as a way of specifying the user identified by the attached memo as the source or beneficiary of the payment.

Muxed Accounts
--------------

.. _`Muxed Account`: https://developers.stellar.org/docs/glossary/muxed-accounts/

Using memos to identify users of shared accounts has several drawbacks. Users may forget to include their memo ID when making a payment to or from another account, and applications may not know to interpret transaction memos as user IDs, since memos are often used for other purposes as well.

For this reason, Stellar Core introduced `Muxed Account`_ support in Protocol 13. Literally speaking, muxed accounts are Stellar accounts encoded with an ID memo (a 64-bit integer). For example, the Stellar account `GDUI2XWUZLWZQJV3Q4T6DMDMQD75WSVBJWCQ7GFD4TMB6G22TQK4ZPSU` combined with the integer `12345` creates the muxed account `MDUI2XWUZLWZQJV3Q4T6DMDMQD75WSVBJWCQ7GFD4TMB6G22TQK4YAAAAAAAAABQHHOWI`.

Muxed accounts can be used as source and destination addresses within Stellar transactions. This removes the need to use transaction memo values as user IDs, provides applications a clear indication that the sender or recipient is a user of a shared account, and improves the user's experience when transacting on Stellar in general.

SEP Support for Shared Accounts
-------------------------------

Support for shared accounts has been added to the Stellar Ecosystem Protocols. In each protocol, shared accounts can be identified using either one of the approached outlined above (using memos or muxed accounts). Polaris and it's integration functions have been adapted to provide the necessary support for each of these approaches.

SEP 10 Support
^^^^^^^^^^^^^^

SEP-10 allows wallet or client applications to either specify a memo in addition to the Stellar account being authenticated or a muxed account. As a result, the challenge transaction and authentication token will also include this information, which allows services consuming the token to restrict access provided to information relevant to the particular user of the shared account.

See the :ref:`SEP-10 API Reference` section for more information on how to use this information in Polaris.

SEP 12 Support
^^^^^^^^^^^^^^

SEP-12 allows customers to be registered using either a memo in addition to the Stellar account or a muxed account. If the SEP-10 token used to authenticate contains a memo or muxed account when making a SEP-12 request, it must match the memo or muxed account used to originally create the customer.

.. note::
    Anchors must design the data models used to store user information in a way that allows users to be specified using a memo or muxed account.

SEP 6 & 24 Support
^^^^^^^^^^^^^^^^^^

Polaris' ``Transaction`` model has three columns that are used to identify the user that initiated the transaction: ``Transaction.stellar_account``, ``Transaction.muxed_account``, and ``Transaction.account_memo``. These values are assigned directly from information extracted from the SEP-10 JWT used when requesting the transaction.

Additionally, ``Transaction.to_address`` and ``Transaction.from_address`` may now be muxed account addresses. Polaris will properly submit deposit transactions and detect incoming withdrawal payment transaction using the muxed account if present.

SEP 31 Support
^^^^^^^^^^^^^^

SEP-31 is unique in the sense that the owners of the Stellar accounts used to send and receive Stellar payments are service providers, not end-users. This means that the use of muxed accounts or user memos in payment transactions are unnecessary.

However, SEP-31 relies on SEP-12 for registering customers involved in a transaction. The SEP-10 JWT created for SEP-31 sender applications will not include memo or muxed account information, but these applications will use memos in SEP-12 requests for registering customers.
