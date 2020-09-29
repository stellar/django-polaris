===============================
Anchoring Multisignature Assets
===============================

Background and Definitions
--------------------------
.. _`master key's`: https://developers.stellar.org/docs/glossary/multisig/#additional-signing-keys
.. _`multiple signatures`: https://developers.stellar.org/docs/glossary/multisig
.. _`Set Options`: https://developers.stellar.org/docs/start/list-of-operations/#set-options
.. _`multisignature`: https://developers.stellar.org/docs/glossary/multisig

In the broader Stellar context, a `multisignature`_ account has more than one Stellar public key listed in it's signers list. In an effort not to rephrase good documentation, a good quote from our Stellar dev documentation is:

  In two cases, a transaction may need more than one signature. If the transaction has operations that affect more than one account, it will need authorization from every account in question. A transaction will also need additional signatures if the account associated with the transaction has multiple public keys.

This `optional` feature adds security but also complexity to an anchor's application logic.

Multisignature Assets
^^^^^^^^^^^^^^^^^^^^^

In the context of Polaris, `multisignature assets` refer to SEP-24 or SEP-6 anchored assets that use distribution accounts that require `multiple signatures`_ in order to be successfully submitted to the Stellar network. Specifically, Polaris defines multisignatures assets as those whose distribution account's medium threshold is not met by the `master key's`_ weight.

Anchors can optionally configure each of their assets' distribution accounts to require more than one (or many) signatures from valid signers in order to improve security around the flow of outgoing payments. The signers for each asset's distribution account may or may not include the account's public key as a master signer on the account by reducing it's weight to zero.

Thresholds, signers, and more are configured on a Stellar account using the `Set Options`_ operation.

Note that anchors that issue their own assets may configure the issuing account to require multiple signatures as well. However, this is outside the scope of Polaris' multisignature asset support.

Channel Accounts
^^^^^^^^^^^^^^^^
.. _`channel account`: https://www.stellar.org/developers/guides/channels.html

A `channel account`_ as defined by the documentation,

    [is] simply another Stellar account that is used not to send the funds but as the “source” account of the transaction. Remember transactions in Stellar each have a source account that can be different than the accounts being effected by the operations in the transaction. The source account of the transaction pays the fee and consumes a sequence number [and is not affected in any other way.]

Using channel accounts for transactions that need multiple signatures allows for a good deal of flexibility in terms of how signatures are collected for a transaction, but the reason why they are necessary is best explained by walking through what the process would look like **without channel accounts**.

1. A client application makes a `POST /deposit` request and creates a transaction record
2. The client application sends the funds to be deposited to the anchor's off-chain account
3. The anchor detects the received funds
4. The anchor uses the current sequence number of the asset's distribution account to create a transaction envelope in their database
5. The anchor collects the necessary signatures on the transaction envelope
6. Meanwhile, the distribution account submits another transaction to the Stellar Network
7. When all signatures have been collected, the envelope XDR is submitted to the network
8. The transaction **fails** with a 400 HTTP status code

This is due to the fact that the sequence number used for the transaction in step 3 is less than the current sequence number on the account as a direct result of step 4. Remember, when a Stellar account submits a transaction, the source account's sequence number must be greater than the last sequence number used for that account.

Therefore, when a sequence number is used in an envelope to be submitted later, the sequence number in the envelope is likely `less` than the sequence number on the account when the anchor eventually gets around to submitting the transaction. This will cause the transaction to fail.

All this context is necessary to state the following:

Polaris uses channel accounts created by the anchor per-multisig-transaction as the source accounts on those same transactions so that transaction envelopes can be serialized, signed, and submitted on any schedule.

Integrations
------------

Payment Flow
^^^^^^^^^^^^

Using channel accounts, Polaris supports the following process for multisignature transactions:

1. A client application makes a `POST /deposit` request and creates a transaction record
2. The client application sends the funds to be deposited to the anchor's off-chain account
3. The anchor detects the received funds
4. Polaris detects that the transaction requires more than one signature
5. Polaris calls ``DepositIntegration.create_channel_account()`` for the transaction record
6. The anchor funds a Stellar account using another Stellar account that doesn't require multiple signatures
6. Polaris uses the channel account as the transaction's source account when building and saving the envelope XDR
7. The anchor collects signatures on the transaction and updates it as 'ready for submission'
8. Polaris retrieves multisig transactions ready to be submitted in poll_pending_deposits and submits them
9. Multisig transactions **succeed** assuming proper signatures on the account

Currently, multisignature asset support is only relevant in the context of SEP-6 and 24 deposit transactions. Withdraw transaction flows don't involve the anchor making any Stellar transaction using an asset's distribution account, and SEP-31 outbound payments are not yet supported in Polaris.

However, due to the optional nature and added complexity of configuring and handling multisignaure assets and transactions relative to the normal SEP-6 and SEP-24 flow, the integrations and related application logic is described separately in this section.

.. autofunction:: polaris.integrations.DepositIntegration.create_channel_account

.. autofunction:: polaris.integrations.DepositIntegration.after_deposit
   :noindex:
