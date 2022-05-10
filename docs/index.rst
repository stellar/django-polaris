==============
Django Polaris
==============

.. image:: https://circleci.com/gh/stellar/django-polaris.svg?style=shield
    :target: https://circleci.com/gh/stellar/django-polaris

.. image:: https://codecov.io/gh/stellar/django-polaris/branch/master/graph/badge.svg?token=3DaW3jM6Q8
    :target: https://codecov.io/gh/stellar/django-polaris

.. image:: https://img.shields.io/badge/python-3.7%20%7C%20%7C%203.8%20%7C%203.9%20%7C%203.10-blue?style=shield
    :alt: Python - Version
    :target: https://pypi.python.org/pypi/django-polaris

.. _`email list`: https://groups.google.com/g/stellar-polaris
.. _Stellar Development Foundation: https://www.stellar.org/
.. _github: https://github.com/stellar/django-polaris
.. _django app: https://docs.djangoproject.com/en/3.0/intro/reusable-apps/
.. _`demo wallet`: http://demo-wallet.stellar.org

Polaris is an extendable `django app`_ for Stellar Ecosystem Proposal (SEP) implementations
maintained by the `Stellar Development Foundation`_ (SDF). Using Polaris, you can run a web
server supporting any combination of SEP-1, 6, 10, 12, 24, 31, & 38.

While Polaris implements the majority of the functionality described in each SEP, there are
pieces of functionality that can only be implemented by the developer using Polaris.
For example, only an anchor can implement the integration with their partner bank.

This is why each SEP implemented by Polaris comes with a programmable interface for developers
to inject their own business logic.

Polaris is completely open source and available on github_. The SDF also runs a reference
server using Polaris that can be tested using our `demo wallet`_.

For important updates on Polaris's development and releases please join the `email list`_.

User Guide
==========

.. toctree::
    :maxdepth: 3

    installation
    sep-1
    sep-10
    sep-24
    rails
    sep-6
    sep-12
    sep-31
    sep-38
    custody

API Reference
=============

.. toctree::
    :maxdepth: 3

    api

Glossary
========

.. toctree::
    :maxdepth: 3

    glossary

:ref:`genindex`
