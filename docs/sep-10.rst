======================
Require Authentication
======================

.. _`SEP-10 Stellar Web Authentication`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0010.md

As defined by the `SEP-10 Stellar Web Authentication`_ specification,

.. epigraph::

    `This SEP defines the standard way for clients such as wallets or exchanges to create authenticated web sessions on behalf of a user who holds a Stellar account. A wallet may want to authenticate with any web service which requires a Stellar account ownership verification, for example, to upload KYC information to an anchor in an authenticated way as described in SEP-12.`

Most Polaris endpoints require a SEP-10 authentication token, refered to as the JWT, and Polaris includes an easily enabled implemenation of SEP-10 that clients can use to obtain these tokens.

It is also possile to host a SEP-10 server independent of your Polaris deployment as long as secret used to generate the signature of each token matches the value assigned to Polaris' :term:`SERVER_JWT_KEY` environment variable. In this case, the following steps can be skipped.

Configure Settings
==================

Add SEP-10 to :term:`ACTIVE_SEPS`, and add the :term:`SIGNING_SEED` and :term:`SERVER_JWT_KEY` environment variables.

.. code-block:: shell

    ACTIVE_SEPS=sep-1,sep-10
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1
    SIGNING_SEED=S...
    SERVER_JWT_KEY=...

``SIGNING_SEED`` is used to sign challenge transactions requested by client applications, and ``SERVER_JWT_KEY`` is used to verify that the authenticatoin token payload has not been tampered with.

Update the TOML File
====================

If you provided a static SEP-1 file for Polaris to use, make sure you add the ``WEB_AUTH_ENDPOINT`` attribute so clients can find your authentication service.

Confirm its Working
===================

Run the web server.

.. code-block::

    python anchor/manage.py runserver

You should see the ``WEB_AUTH_ENDPOINT`` URL at http://localhost:8000/.well-known/stellar.toml, and making a GET request to it should return a error responses complaining about a missing `account` parameter.

Adding Client Attribution
=========================

Optionally, you can configure your authentication service to deny requests from clients that do not offer to cryptographically verify their identity. :term:`SEP10_CLIENT_ATTRIBUTION_REQUIRED` and related environment variables allow you to define an allow or denylist of domains that can authenticate with your service.

By default, Polaris does not require clients to perform this verification, but it will allow clients to do so voluntarily. In these cases, Polaris will assign the ``client_domain`` property of the :class:`polaris.sep10.token.SEP10Token` object passed to the request with the verified domain.

Issuing Tokens for Other Domains
================================

SEP-10 servers can issue authentication tokens for multiple services, including services hosted on different domains. To enable this, add the domains you would like Polaris to issue authenticaton tokens for to the :term:`SEP10_HOME_DOMAINS` environment variable.