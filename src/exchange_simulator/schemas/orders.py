# schemas/orders.py
"""
Order-related message schemas: place, cancel, status.
Exchange-like field names for compatibility with real exchange clients.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PlaceOrderRequest(BaseModel):
    """Client request to place an order."""

    symbol: str = Field(..., description="Trading pair, e.g. BTC/USDT")
    side: OrderSide
    order_type: OrderType = OrderType.LIMIT
    quantity: float = Field(..., gt=0)
    price: Optional[float] = Field(None, description="Required for limit orders")
    client_order_id: Optional[str] = Field(None, description="Client-assigned ID for idempotency")


class PlaceOrderResponse(BaseModel):
    """Response after accepting an order."""

    order_id: str
    client_order_id: Optional[str] = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    message: Optional[str] = None


class CancelOrderRequest(BaseModel):
    """Client request to cancel an order."""

    symbol: str
    order_id: str


class OrderStatusResponse(BaseModel):
    """Full order status (e.g. for GET /orders/{order_id})."""

    order_id: str
    client_order_id: Optional[str] = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    price: Optional[float] = None
    status: OrderStatus
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
