"""Broker adapters.

The engine never talks to a broker. After a PASS (or an acknowledged
REVIEW) and the user's confirmation, the app hands the order to whichever
adapter is configured. The simulated broker fills at the checked price and
is the default. The Alpaca paper adapter uses the same interface and is
selected only when API keys are present in the environment.

The Alpaca adapter follows the alpaca-py TradingClient interface and has
not been exercised in this build; the first live run is on the roadmap.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from .rules import Order


@dataclass
class Fill:
    fill_id: str
    symbol: str
    side: str
    qty: float
    price: float
    asset_type: str
    filled_at: datetime
    broker: str
    contract: str = ""


class BrokerAdapter(Protocol):
    name: str

    def submit(self, order: Order, now: Optional[datetime] = None) -> Fill: ...

    def last_price(self, symbol: str) -> Optional[float]: ...


class SimulatedBroker:
    """Fills immediately at the order's checked price. Used for the demo and the tests."""

    name = "Simulated broker (paper)"

    def __init__(self, quotes: Optional[dict[str, float]] = None):
        self.quotes = dict(quotes or {})
        self.submitted: list[Fill] = []

    def submit(self, order: Order, now: Optional[datetime] = None) -> Fill:
        fill = Fill(
            fill_id=f"SIM-{uuid.uuid4().hex[:8].upper()}",
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=order.price,
            asset_type=order.asset_type,
            filled_at=now or datetime.now(),
            broker=self.name,
            contract=order.contract,
        )
        self.submitted.append(fill)
        return fill

    def last_price(self, symbol: str) -> Optional[float]:
        return self.quotes.get(symbol)


class AlpacaPaperBroker:
    """Routes to Alpaca's paper-trading endpoint through alpaca-py.

    Requires ALPACA_API_KEY and ALPACA_SECRET_KEY. Equities only in this
    version; options routing is on the roadmap.
    """

    name = "Alpaca paper trading"

    def __init__(self, api_key: str, secret_key: str):
        from alpaca.trading.client import TradingClient  # imported lazily; optional dependency

        self._client = TradingClient(api_key, secret_key, paper=True)

    def submit(self, order: Order, now: Optional[datetime] = None) -> Fill:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest

        if order.asset_type != "stock":
            raise NotImplementedError("Options routing is not implemented for the Alpaca adapter yet.")
        req = LimitOrderRequest(
            symbol=order.symbol,
            qty=order.qty,
            side=OrderSide.BUY if order.side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=order.price,
        )
        resp = self._client.submit_order(req)
        price = float(resp.filled_avg_price) if getattr(resp, "filled_avg_price", None) else order.price
        return Fill(
            fill_id=str(resp.id),
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=price,
            asset_type=order.asset_type,
            filled_at=now or datetime.now(),
            broker=self.name,
        )

    def last_price(self, symbol: str) -> Optional[float]:
        return None  # quotes come from the market-data client, not wired in this build


def broker_from_env(quotes: Optional[dict[str, float]] = None) -> BrokerAdapter:
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if key and secret:
        try:
            return AlpacaPaperBroker(key, secret)
        except ImportError:
            pass  # alpaca-py not installed; fall back to the simulator
    return SimulatedBroker(quotes)
