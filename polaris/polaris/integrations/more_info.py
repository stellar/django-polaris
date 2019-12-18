from typing import Tuple, Dict
from polaris.models import Transaction


def get_more_info_template(transaction: Transaction) -> Tuple[str, Dict]:
    """
    .. _more_info.html: https://github.com/stellar/django-polaris/blob/master/polaris/polaris/templates/transaction/more_info.html

    Returns the default more_info template path and an empty dictionary. This
    function should be replaced by anchors who want to use a different
    template for the more_info page.

    The data dictionary returned by this function or its replacement will
    be combined with another dictionary Polaris passes to the more_info
    template. The dictionary Polaris uses will have the following key-value
    pairs:

        * transaction: the Transaction django model object
        * tx_json: a JSON-serialized representation of `transaction`
        * instructions: an optional string of text or HTML to display to
          the user for guidance on starting the deposit transaction

    Take a look at the more_info.html_ default template to see how these
    arguments are used.

    Lastly, any template used in place of more_info.html_ must send a
    JavaScript ``postMessage`` callback to the window that opened the
    interactive flow. This lets the wallet know that the anchor has finished
    and that the wallet may resume control. The call must contain the `tx_json`
    passed to the template:
    ::

            if (window.opener != void 0) {
                targetWindow = window.opener;
            } else if (window.parent != void 0) {
                targetWindow = window.parent;
            } else {
                return;
            }

            targetWindow.postMessage(tx_json, "*");

    Again, look at the more_info.html_ template for a reference.

    This function can be replaced by passing the replacement into
    register_integrations like so:
    ::

        from myapp.integrations import my_more_info_template_func

        register_integrations(
            more_info_template_func=my_more_info_template_func
        )

    :param transaction: a django Transaction model object that will be passed
        to the template
    :return: a tuple of the template path and a dictionary containing the data
        that should be passed to the template.
    """
    return "transaction/more_info.html", {}


registered_more_info_template_func = get_more_info_template
