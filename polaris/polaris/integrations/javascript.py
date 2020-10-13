from typing import List, Dict, Optional


class TemplateScript:
    """
    **DEPRECATED**: `TemplateScript` objects will be removed in Polaris 2.0 in favor
    of allowing the anchor to override and extend Polaris' Django templates.
    See the :doc:`Template Extensions</templates/index>` documentation for more information.
    """

    def __init__(self, path: str = None, url: str = None, is_async: bool = False):
        if path and url:
            raise AttributeError(
                "a script can only have one source from either a path or url."
            )
        elif not (path or url):
            raise AttributeError(
                "must give either a local path or a url for TemplateScript."
            )
        self.path = path
        self.is_async = is_async
        self.url = url


def scripts(page_content: Optional[Dict]) -> List[TemplateScript]:
    """
    .. _`example reference server`: https://github.com/stellar/django-polaris/tree/master/example

    **DEPRECATED**: `TemplateScript` objects will be removed in Polaris 2.0 in favor of
    allowing the anchor to override and extend Polaris' Django templates. See the
    :doc:`Template Extensions</templates/index>` documentation for more information.

    Replace this function with another by passing it to ``register_integrations()`` as
    described in :doc:`Registering Integrations</register_integrations/index>`.

    Return a list of TemplateScript objects containing script source file locations to be added 
    to the bottom of the HTML body served for the current request. The scripts
    will be rendered like so:
    ::

        {% for script in scripts %}
          {% if script.path %}

            <script src="/static/{{ script.path }}" {% if script.is_async %}async{% endif %} ></script>

          {% elif script.url %}

            <script src="{{ script.url }}" {% if script.is_async %}async{% endif %}></script>

          {% endif %}
        {% endfor %}

    `page_content` will be the return value from ``content_for_template()``.
    `page_content` will also contain a ``"form"`` key-value pair if a form
    will be rendered in the UI.

    This gives anchors a great deal of freedom on the client side. The
    `example reference server`_ uses this functionality to inject Google
    Analytics into our deployment of Polaris, and to refresh the Confirm Email
    page every time the window is brought back into focus.

    Note that the scripts will be executed in the order in which they are
    returned.
    """
    return []


registered_scripts_func = scripts
