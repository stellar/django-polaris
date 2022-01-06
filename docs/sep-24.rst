====================================
Enable Hosted Deposits & Withdrawals
====================================

.. _`SEP-24`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0024.md
.. _`SEP-6`: https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0006.md

`SEP-24`_ defines a standardized set of APIs that allow client applications and anchors to communicate for the purpose of depositing or withdrawing value on and off the Stellar blockchain. Practically speaking, users can use applications that implement the client side of SEP-24 to connect to businesses that will accept off-chain value, such as US dollar fiat, in exchange for on-chain value, such as USDC, and vice-versa.

SEP-24 is the `hosted` version of this solution, meaning the user's application must open a webview hosted by the third-party anchor in order for the user provide the information necessary to complete the transaction. `SEP-6`_ is an alternative to SEP-24 that supports a pure API-style solution for the same use case. See the :doc:`sep-6` documentation for guidance on implementing it.

Configure Settings
==================

.. _`SessionMiddleware`: https://docs.djangoproject.com/en/3.2/ref/middleware/#module-django.contrib.sessions.middleware

Activate SEP-24
---------------

Add SEP-24 as an active SEP in your ``.env`` file. ``SERVER_JWT_KEY`` is also required.

.. code-block:: shell

    ACTIVE_SEPS=sep-1,sep-10,sep-24
    HOST_URL=http://localhost:8000
    LOCAL_MODE=1
    ENABLE_SEP_0023=1
    SIGNING_SEED=S...
    SERVER_JWT_KEY=...

Add Browser Session Support
---------------------------

`SessionMiddleware`_ is required for all SEP-24 deployments. :class:`~polaris.middleware.TimeZoneMiddleware` is included in Polaris and ensures Django uses the correct timezone when rendering content to the user. If included, it must be added *after* ``SessionMiddleware``.

.. code-block:: python

    MIDDLEWARE = [
        ...,
        'django.contrib.sessions.middleware.SessionMiddleware',
        'polaris.middleware.TimezoneMiddleware',
        ...
    ]

Allow Custom Templates
----------------------

Add the following variable to your ``settings.py`` file.

.. code-block:: python

    FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

This allows Polaris to override django's default HTML form widgets to provide a great UI out of the box. They can also be replaced with your own custom HTML widgets. See the :doc:`templates` documentation for more information.

Secure Session Cookies
----------------------

The webview, or interactive flow, supported by Polaris uses browser session cookies for maintaining state. These cookies should only be used when the client is using HTTPS to ensure the user's session cannot be highjacked by a malicious actor.

In your ``anchor/anchor/settings.py`` file, add the following variable.

.. code-block:: python

    SESSION_COOKIE_SECURE = True

Polaris requires this setting to be ``True`` for SEP-24 deployments if not in ``LOCAL_MODE``, which should only be used for local development.

Configure Static Assets
-----------------------

.. _serving static files: https://docs.djangoproject.com/en/3.0/howto/static-files/

Polaris comes with a UI for displaying forms and transaction information. This UI will be rendered in a webview by the user's application when they initiate a deposit or withdrawal.

Make sure ``django.contrib.staticfiles`` is listed in ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...,
        "django.contrib.staticfiles",
        ...,
    ]

Additionally, to serve static files in production, use the middleware provided by
``whitenoise``, which comes with your installation of Polaris. It should be near the
top of the list for the best performance, but still under CorsMiddleware.

.. code-block:: python

    MIDDLEWARE = [
        ...,
        "corsheaders.middleware.CorsMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        ...,
    ]

Add the following to your settings.py as well:

.. code-block:: python

    STATIC_URL = "<your static url path, /static/ by default>"
    STATIC_ROOT = os.path.join(BASE_DIR, "<where all static files will be collected>")
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

Since ``whitenoise`` will now be serving your static files, use the ``--nostatic`` flag
when using the ``runserver`` command locally.

Collect the static files Polaris provides into your app:
::

    python manage.py collectstatic --no-input

Create a Stellar Asset
======================

Businesses can choose to create or issue their own Stellar asset or they use a Stellar asset issued by another organization. This is a business decision and is out of the scope of this documentation. Polaris supports both cases, and here we'll create our own asset for the sake of demonstration.

Add an Asset to the Database
----------------------------

.. _`Fernet symmetric encryption`: https://cryptography.io/en/latest/fernet/

Stellar assets are identified using a code, such as USDC, and the Stellar account that created the asset, such as ``GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN``.

Lets drop into the python console.


.. code-block:: shell

    python anchor/manage.py shell

Generate two public and private key pairs. These key pairs will be used for the issuing account, which creates and burns the asset, as well as a distribution account, which will hold a balance of the asset for disbursing and receiving payments.

.. code-block:: python

    from stellar_sdk import Keypair

    issuer = Keypair.random()
    distributor = Keypair.random()

    with open("secretKeys.txt", "w") as f:
        f.write(f"{issuer.secret}\n{distributor.secret}")

This generated two key pairs and wrote the secret keys to the file system. **Make sure to keep these secret keys secret.** The issuing account's secret key is all thats needed to create more of the asset, and the distribution account's secret key will always hold enough of the asset to satisfy the transaction volume of the service.

Finally, create the :class:`~polaris.models.Asset` object and save it to the database. There are many columns not shown here, so check out the :doc:`api` for a complete list.

.. code-block:: python

    from polaris.models import Asset

    Asset.objects.create(
        code="TEST",
        issuer=issuer.public_key,
        distribution_seed=distributor.secret,
        sep24_enabled=True,
        deposit_enabled=True,
        withdrawal_enabled=True,
        symbol="$"
    )

The ``distribution_seed`` column is encrypted at the database layer using `Fernet symmetric encryption`_,  and only decrypted when held in memory within an ``Asset`` object. It uses your Django project's ``SECRET_KEY`` setting to generate the encryption key, **so make sure its value is unguessable and kept a secret**.

Issue the Asset on Stellar
--------------------------

.. _`block explorer`: https://stellar.expert

You can finally create the asset on the Stellar blockchain. This documentation assumes you're issuing on testnet. If you're working on mainnet, you may want to hold off from issuing your asset until you're  ready to go live.

Polaris has a built-in command for issuing assets on testnet.

.. code-block:: shell

    python anchor/manage.py testnet issue --asset TEST --issuer-seed <...> --distribution-seed <...>

Polaris will ask you to specify a home domain for the asset. This must be the domain that hosts your stellar.toml file.

Your asset should not exist on Stellar's testnet. You can use a `block explorer`_ to take a look at your issuing and distribution accounts.

You can optionally specify the amount to be issued. See the :ref:`deployment:CLI Commands` documentation for more information.

Integrations
============

There are several pieces of functionality required to run a anchor that are custom to each business. Polaris implements everything but these pieces, and calls functions that have been passed to :func:`~polaris.integrations.regisiter_integrations` in order to invoke custom functionality implemented by the business.

Defining Django Forms
---------------------

.. _`Django form objects`: https://docs.djangoproject.com/en/3.2/topics/forms/#building-a-form-in-django

SEP-24 anchors must implement a user web-based interface that collects KYC and transaction information from the user of the client application. Because the information necessary to complete transactions differs for each business, Polaris expects the anchor to provide `Django form objects`_ that can be rendered as HTML to the user.

Define a set of forms that collect all of the information needed to facilitate a transaction in a ``anchor/anchor/sep24/forms.py`` file.

.. code-block:: python

    from django import forms
    from us import states  # https://pypi.org/project/us/

    state_list = sorted(
        status.mapping("abbr", "name").items(),
        key=lambda x: x[1]
    )

    class ContactForm(forms.Form):
        first_name = forms.CharField()
        last_name = forms.CharField()
        email = forms.EmailField()

    class AddressForm(forms.Form):
        address_1 = forms.CharField()
        address_2 = forms.CharField()
        city = forms.CharField()
        state = forms.ChoiceField(choices=state_list)
        zip_code = forms.CharField()

    class BankAccount(forms.Form):
        account_number = forms.CharField()
        routing_number = forms.CharField()

Django's form capabilities are comprehensive, so check out the documentation if you want to customize error messages, add validations to specific fields, and more.

Notice how some transaction information is not collected, such as the amount. Because every anchor needs to collect the transaction amount, Polaris defines a :class:`~polaris.integrations.forms.TransactionForm` class that includes proper validations. It is highly recommended to use this form or a subclass of it.

Processing Form Data
--------------------

.. _`Form.is_valid()`: https://docs.djangoproject.com/en/3,2/ref/forms/api/#django.forms.Form.is_valid

When a user initiates a transaction, Polaris will return a URL that the wallet will open in a webview. Once opened, Polaris does the following:

#. Polaris calls :meth:`~polaris.integrations.DepositIntegration.form_for_transaction`
#. Polaris calls :meth:`~polaris.integrations.DepositIntegration.content_for_template`
#. Polaris renders the template with the form and content returned from the methods called
#. The user enters the information requested by the form and submits
#. Polaris calls :meth:`~polaris.integrations.DepositIntegration.form_for_transaction` again. The form returned must be the same form returned previously, because Polaris calls `Form.is_valid()`_ to ensure the data provided is valid. If it isn't, the form is re-rendered with the appropriate error message.
#. When `Form.is_valid()`_ is ``True``, Polaris calls :meth:`~polaris.integrations.DepositIntegration.after_form_validation()`. This method should change the state of the user's flow so the next call to :meth:`~polaris.integrations.DepositIntegration.form_for_transaction` returns the next form.
#. Repeat

When :meth:`~polaris.integrations.DepositIntegration.form_for_transaction` and :meth:`~polaris.integrations.DepositIntegration.content_for_template` both return ``None``, Polaris assumes the anchor is done collecting and processing information and redirects the webview to a transaction information page, called the "more info page" by SEP-24.

All of the methods used to process form data are defined on the :class:`~polaris.integrations.DepositIntegration` and :class:`~polaris.integrations.WithdrawIntegration` classes. Create subclasses of both and implement the methods used to process the forms.

.. code-block:: python

    from decimal import Decimal
    from django import forms
    from rest_framework.request import Request
    from polaris.models import Transaction
    from polaris.templates import Template
    from polaris.integrations import (
        DepositIntegration,
        WithdrawIntegration,
        TransactionForm
    )
    from .users import user_for_account, create_user

    class AnchorDeposit(DepositIntegration):
        def form_for_transaction(
            self,
            request: Request,
            transaction: Transaction,
            post_data: dict = None,
            amount: Decimal = None,
            *args,
            **kwargs
        ):
            # if we haven't collected amount, collect it
            if not transaction.amount_in:
                if post_data:
                    return TransactionForm(transaction, post_data)
                else:
                    return TransactionForm(transaction, initial={"amount": amount})

            # if a user doesn't exist for this Stellar account,
            # collect their contact info
            user = user_for_account(transaction.stellar_account)
            if not user:
                if post_data:
                    return ContactForm(post_data)
                else:
                    return ContactForm()
            # if we haven't gotten the user's full address, colelct it
            elif not user.full_address:
                if post_data:
                    return AddressForm(post_data)
                else:
                    return AddressForm()
            # we don't have anything more to collect
            else:
                return None

        def after_form_validation(
            self,
            request: Request,
            form: forms.Form,
            transaction: Transaction,
            *args,
            **kwargs,
        ):
            if isinstance(form, TransactionForm):
                # Polaris automatically assigns amount to Transaction.amount_in
                return
            if isinstance(form, ContactForm):
                # creates the user to be returned from user_for_account()
                create_user(form)
            elif isinstance(form, AddressForm):
                # assigns user.full_address
                update_user_address(form)

        def content_for_template(
            self,
            request: Request,
            template: Template,
            form: Optional[forms.Form] = None,
            transaction: Optional[Transaction] = None,
            *args,
            **kwargs,
        ):
            if form is not None or template == Template.MORE_INFO:
                # provides a label for the image displayed at the top of each page
                return {"icon_label": "Anchor Inc."}
            else:
                # we're done
                return None

Similar logic should be implemented for :class:`~polaris.integrations.WithdrawIntegration`. For more detailed information on any of the classes or functions used about, see the :doc:`api`.
