Integrations
==========================================

.. _SEP-24: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _Django Commands: https://docs.djangoproject.com/en/2.2/howto/custom-management-commands
.. _stellar-anchor-server: https://github.com/stellar/stellar-anchor-server

Polaris does most of the work implementing SEP-24_. However, Polaris simply
doesn't have the information it needs to interface with an anchor's partner
financial entities. This is where :class:`.DepositIntegration` and
:class:`.WithdrawalIntegration` come in.

Polaris expects developers to override these base class methods and register
them using :func:`polaris.integrations.register_integrations`. The code will
be executed from inside Polaris `Django Commands`_, which should be run in a
separate process from the web server running Polaris. See the
stellar-anchor-server_ project, specifically the ``docker-compose.yml``,
for an example on how to run the Polaris web server and management commands.

.. automodule:: polaris.integrations.transactions
    :members:
    :exclude-members: RegisteredDepositIntegration, RegisteredWithdrawalIntegration

.. autofunction:: polaris.integrations.register_integrations
