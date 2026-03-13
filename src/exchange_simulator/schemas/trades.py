# schemas/trades.py
"""
Trade and fill event schemas.
Produced by the matching engine and broadcast to clients.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PublicTrade(BaseModel):
    """
    Public trade event (market data feed).
    Resembles exchange trade tick.
    """

    symbol: str
    trade_id: str
    price: float
    quantity: float
    side: TradeSide
    timestamp: Optional[str] = None  # simulation time or ISO format


class FillEvent(BaseModel):
    """
    Fill event for a specific order (order channel / private feed).
    Links fill to order_id for client reconciliation.
    """

    order_id: str
    client_order_id: Optional[str] = None
    symbol: str
    side: TradeSide
    price: float
    quantity: float
    fill_id: str
    is_maker: bool = False
    timestamp: Optional[str] = None
