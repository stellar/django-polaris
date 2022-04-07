from django.urls import re_path

from polaris.sep38 import info, prices, quote

urlpatterns = [
    re_path(r"^info/?$", info.info),
    re_path(r"^prices/?$", prices.get_prices),
    re_path(r"^price/?$", prices.get_price),
    re_path(r"^quote/?$", quote.post_quote),
    re_path(r"^quote/(?P<quote_id>[^/]+)/?$", quote.get_quote),
]
