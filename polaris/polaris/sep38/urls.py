from django.urls import path

from polaris.sep38 import info, prices, quote

urlpatterns = [
    path("info", info.info),
    path("prices", prices.get_prices),
    path("price", prices.get_price),
    path("quote", quote.post_quote),
    path("quote/<quote_id>", quote.get_quote),
]
