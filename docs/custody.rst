=========================
Using a Custodial Service
=========================

.. _`django-polaris-circle`: https://github.com/stellar/django-polaris-circle
.. _`django-polaris-bitgo`: https://github.com/CheesecakeLabs/django-polaris-bitgo

Polaris defaults to a self-custody approach, meaning it assumes the business has access to the secret keys of their distribution accounts on Stellar.

However, businesses may want to use a third-party service for custodying their on-chain assets. Polaris supports this use case through its generic :class:`~polaris.integrations.CustodyIntegration` class. Implementations of this standardized interface can connect to various custodial solutions, allowing Polaris to leverage the service's functionality.

The only implementation that is built into Polaris is the default :class:`~polaris.integrations.SelfCustodyIntegration`. As other implementations are developed, they may be added to Polaris or available as another resuable Django app.

Below is a list of in-progress or third party implementations. Because this list can only be updated on each Polaris release, it may not be exhaustive.

* `django-polaris-circle`_: a WIP impelementation for the Circle API
* `django-polaris-bitgo`_: an implementation for the BitGo API

Contributions to new or existing implementations are welcome!
