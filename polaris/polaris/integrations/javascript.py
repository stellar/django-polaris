from typing import List, Dict, Optional


def scripts(page_content: Optional[Dict]) -> List[str]:
    """
    .. _`example reference server`: https://github.com/stellar/django-polaris/tree/master/example

    Return a list of strings containing script tags that will be added to the
    bottom of the HTML body served for the current request. The scripts
    will be rendered like so:
    ::

        {% for script in scripts %}
            {{ script|safe }}
        {% endfor %}

    `page_content` will be the return value from ``content_for_transaction()``
    for requests during the interactive flow and ``None`` for requests to the
    `/more_info` endpoint. Anchors can
    use `page_content` to determine which scripts need to be rendered.

    This gives anchors a great deal of freedom on the client side. The
    `example reference server`_ uses this functionality to inject Google
    Analytics into our deployment of Polaris, and to refresh the Confirm Email
    page every time the window is brought back into focus.

    Replace this function with another by passing it to
    :func:`polaris.integrations.register_integrations` like so:
    ::

        from myapp.integrations import (
            scripts,
            MyDepositIntegration,
            MyWithdrawalIntegration
        )

        register_integrations(
            deposit=MyDepositIntegration(),
            withdrawal=MyWithdrawalIntegration(),
            javascript_func=scripts
        )

    Note that the scripts will be executed in the order in which they are
    returned.
    """
    return []


registered_scripts_func = scripts
