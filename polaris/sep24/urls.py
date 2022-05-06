from django.urls import re_path
from django.views.decorators.csrf import csrf_exempt

from polaris.sep24.info import info
from polaris.sep24.fee import fee
from polaris.sep24.transaction import more_info, transaction, transactions
from polaris.sep24.withdraw import (
    withdraw,
    get_interactive_withdraw,
    post_interactive_withdraw,
    complete_interactive_withdraw,
)
from polaris.sep24.deposit import (
    deposit,
    complete_interactive_deposit,
    post_interactive_deposit,
    get_interactive_deposit,
)
from polaris.sep24.tzinfo import post_tzinfo

SEP24_MORE_INFO_PATH = "transaction/more_info"

urlpatterns = [
    re_path(r"^transactions/deposit/interactive/?$", csrf_exempt(deposit)),
    re_path(
        r"^transactions/deposit/interactive/complete/?$",
        complete_interactive_deposit,
        name="complete_interactive_withdraw",
    ),
    re_path(
        r"^transactions/deposit/webapp/submit/?$",
        post_interactive_deposit,
        name="post_interactive_deposit",
    ),
    re_path(
        r"^transactions/deposit/webapp/?$",
        get_interactive_deposit,
        name="get_interactive_deposit",
    ),
    re_path(r"^transactions/withdraw/interactive/?$", csrf_exempt(withdraw)),
    re_path(
        r"^transactions/withdraw/interactive/complete/?$",
        complete_interactive_withdraw,
        name="complete_interactive_withdraw",
    ),
    re_path(
        r"^transactions/withdraw/webapp/submit/?$",
        post_interactive_withdraw,
        name="post_interactive_withdraw",
    ),
    re_path(
        r"^transactions/withdraw/webapp/?$",
        get_interactive_withdraw,
        name="get_interactive_withdraw",
    ),
    re_path(r"^transactions/webapp/tzinfo/?$", post_tzinfo, name="tzinfo"),
    re_path(r"^info/?$", info),
    re_path(r"^fee/?$", fee),
    re_path(r"^transaction/?$", transaction),
    re_path(r"^transactions/?$", transactions),
    re_path(r"^" + SEP24_MORE_INFO_PATH + r"/?$", more_info, name="more_info"),
]
