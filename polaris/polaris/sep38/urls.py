from django.urls import path

from polaris.sep38 import info, prices
from polaris.sep38.quote import QuoteAPIView

urlpatterns = [
    path("info", info.info),
    path("prices", prices.get_prices),
    path("price", prices.get_price),
    path("quote", QuoteAPIView.as_view()),
    path("quote/<quote_id>", QuoteAPIView.as_view())
]
