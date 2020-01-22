from typing import List


def javascript_for_templates() -> List[str]:
    """
    .. _`example reference server`: https://github.com/stellar/django-polaris/tree/master/example

    Return a list of strings containing script tags that will be rendered at
    the bottom of every HTML body rendered by the server like so:
    ::

        {% for script in scripts %}
            {{ script|safe }}
        {% endfor %}

    This gives anchors a great deal of freedom on the client side. The
    `example reference server`_ uses this functionality to inject Google
    Analytics into our deployment of Polaris.

    Note that the scripts will be executed in the order in which they are
    returned. This may be relevant if your javascript code has the possibility
    of interacting with other scripts.
    """
    print("IN DEFAULT JAVASCRIPT FUNC")
    return []


registered_javascript_func = javascript_for_templates
