Templates
=========

.. _`Django's template system`: https://docs.djangoproject.com/en/3.1/ref/templates/

Polaris uses `Django's template system`_ for defining the UI content rendered to users, and these templates can be written in a way that allows others to override or extend them. Specifically, Polaris' templates have the following inheritance structure:

- ``templates/polaris/base.html``
    - ``templates/polaris/deposit.html``
    - ``templates/polaris/withdraw.html``
    - ``templates/polaris/more_info.html``

``base.html`` defines the top-level HTML tags like `html`, `body`, and `head`, while each of the four other templates extend the file and override the `content` block, among others. ``deposit.html`` and ``withdraw.html`` are very similar and are used for pages that display forms. ``more_info.html`` simply displays transaction details.

Template Extensions
-------------------

.. _`template syntax documentation`: https://docs.djangoproject.com/en/3.1/ref/templates/language/#
.. _`block documentation`: https://docs.djangoproject.com/en/3.1/ref/templates/language/#template-inheritance

In order to override or extend a Polaris Template, anchors must create a file with the same path and name of the file its replacing. Once created, the anchor can override any ``block`` tag defined in the template (or it's parent templates).

Polaris provides two ``block`` tags that are intentionally left empty for anchors to extend: ``extra_head`` and ``extra_body``. You are also allowed to extend any of the blocks actually implemented by Polaris, such as ``header``, ``content``, and ``footer``. Note that ``header`` contains ``extra_header``.

For example, the SDF's reference server extends ``base.html`` by creating an HTML file within the app's ``templates/polaris`` directory. In the file, we declare the template we are extending, load any django-provided templates tools such as ``static``, and define an ``extra_body`` block:
::

    {% extends "polaris/base.html" %} {% load static %} {% load i18n %}

    {% trans "Confirm Email" as ce %}

    {% block extra_body %}

        <script src="https://www.googletagmanager.com/gtag/js?id=UA-53373928-6" async></script>
        <script src="{% static 'sep24_scripts/google_analytics.js' %}"></script>

        {% if not form is not None and title != ce %}
            <script src="{% static 'sep24_scripts/check_email_confirmation.js' %}"></script>
        {% endif %}

    {% endblock %}

The ``extra_body`` block adds ``<script>`` tags for a Google Analytics and a local script within the app's ``static`` directory that requests the email confirmation status of the user on page focus, improving UX. If you're unfamiliar with the syntax of Django's templates, check out the `template syntax documentation`_ and particularly the `block documentation`_. The ``extra_head`` template block is ideal for linking anchor-defined CSS files or other resources that must load before the page is displayed.

Note that the content rendered within ``extra_body`` and ``extra_head`` is in addition to the content defined by Polaris' templates. If you wish to replace a template completely, create a file with the same relative path from the `templates` directory but do not use the ``extend`` keyword. Instead, simply write a Django template that does not extend one defined by Polaris.

Template Contexts
-----------------

.. _`context`: https://docs.djangoproject.com/en/3.1/ref/templates/api/#rendering-a-context

Whenever a template is rendered and displayed to the user, its rendered using a `context`_, which is a Python dictionary containing key-value pairs that can be used to alter the content rendered. Polaris has an integration function that allows anchors to add key-value pairs to the context used whenever a template is about to be rendered.

.. autofunction:: polaris.integrations.DepositIntegration.content_for_template
   :noindex:

.. autofunction:: polaris.integrations.WithdrawalIntegration.content_for_template
   :noindex:

Using this function in conjunction with template extensions, you can define template blocks that use context variables passed from ``content_for_template()``. This gives anchors complete control of the interactive UX.

Outlined below are the default key-value pairs passed as `context`_ objects to each template. In addition to the attributes listed in each ``Template`` section, Polaris also passes the key-value pairs returned from ``content_for_template()``.

``Template.DEPOSIT``

- `form`: The Django ``Form`` object return by ``form_for_transaction()``
- `post_url`: The URL to use when making the POST request containing form data
- `get_url`: The URL to use when making the GET request for the form
- `scripts`: A list of ``TemplateScript`` objects (deprecated)
- `operation`: The ``/fee?operation=`` value for the transaction
- `asset`: The Polaris ``Asset`` object for the transaction requested
- `use_fee_endpoint`: A boolean for whether the anchor requires the custom fee endpoint
- `org_logo_url`: A URL to the organization's logo, to be used as the page center icon

``Template.WITHDRAW``

All attributes listed here have identical definitions to the above set of attributes:

- `form`
- `post_url`
- `get_url`
- `scripts`
- `operation`
- `asset`
- `use_fee_endpoint`

``Template.MORE_INFO``

- `tx_json`: A JSON-serialized object matching the response body from ``/transactions``
- `amount_in`: The amount sent to the anchor's off-chain account
- `amount_out`: The amount send to the user's off-chain account
- `amount_fee`: The amount charged by the anchor for facilitating the transaction
- `transaction`: The ``Transaction`` Polaris database object
- `asset_code`: The code string representing the asset

