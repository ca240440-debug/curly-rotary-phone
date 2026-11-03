"""Future approved price-feed contract; no scraping or scheduled jobs enabled."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

@dataclass(frozen=True)
class PriceObservation:
    amount: Decimal
    currency: str
    observed_at: datetime
    source: str
    product_url: str

class PriceProvider(Protocol):
    def fetch(self, product_url: str) -> PriceObservation: ...

# Future workers must enforce retailer caching/display terms, record source and
# observation time, reject stale observations, and deliver alerts only to opted-in
# parents. A target match is not a prediction of future prices.
