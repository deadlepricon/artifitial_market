# schemas/book.py
"""
Order book (Level 2) message schemas.
Used for broadcasting book updates over the WebSocket feed.
"""

from pydantic import BaseModel, Field


class PriceLevel(BaseModel):
    """A single price level (price and quantity)."""

    price: float
    quantity: float


class OrderBookSnapshot(BaseModel):
    """
    Full L2 snapshot: list of bid and ask levels.
    Sent on subscription or when client requests snapshot.
    """

    symbol: str
    bids: list[PriceLevel] = Field(default_factory=list)
    asks: list[PriceLevel] = Field(default_factory=list)
    sequence: int = 0


class OrderBookDelta(BaseModel):
    """
    Incremental book update: changed levels only.
    Reduces bandwidth compared to full snapshot.
    """

    symbol: str
    bids: list[PriceLevel] = Field(default_factory=list)
    asks: list[PriceLevel] = Field(default_factory=list)
    sequence: int = 0
