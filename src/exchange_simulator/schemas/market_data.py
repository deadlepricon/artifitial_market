# schemas/market_data.py
"""
Market data message schemas: ticker, subscriptions.
Used by the WebSocket feed to send updates to clients.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .book import OrderBookDelta, OrderBookSnapshot
from .trades import PublicTrade


class TickerUpdate(BaseModel):
    """24h-style ticker (simplified): last, bid, ask, volume."""

    symbol: str
    last_price: float
    best_bid: float
    best_ask: float
    volume_24h: float = 0.0
    timestamp: Optional[str] = None


# Subscription types clients can request
SubscriptionChannel = Literal["book", "trades", "ticker"]


class SubscribeMessage(BaseModel):
    """Client subscription request (e.g. over WebSocket)."""

    action: Literal["subscribe"] = "subscribe"
    channels: list[SubscriptionChannel] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)


# Union of all feed message types for broadcasting
FeedMessage = OrderBookSnapshot | OrderBookDelta | PublicTrade | TickerUpdate
