# exchange_api/routes.py
"""
REST routes: place order, cancel, order status.
Uses engine, order_store, broadcaster, metrics. Immediate fill broadcast after submit_order.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from exchange_simulator.logging.events import (
    log_client_trade_closed,
    log_order_cancelled,
    log_order_placed,
    log_order_received,
)
from exchange_simulator.schemas.orders import (
    CancelOrderRequest,
    OrderSide,
    OrderStatus,
    OrderStatusResponse,
    OrderType,
    PlaceOrderRequest,
    PlaceOrderResponse,
)

# Set by main.py: symbol -> engine for multi-symbol routing
_broadcaster: Any = None
_engines: dict[str, Any] = {}
_order_store: dict[str, dict] = {}
_metrics: Any = None


def set_broadcaster(b) -> None:
    global _broadcaster
    _broadcaster = b


def set_engines(engines: dict[str, Any]) -> None:
    """Set the map of symbol -> MatchingEngine for order routing."""
    global _engines
    _engines = engines


def set_order_store(s: dict) -> None:
    global _order_store
    _order_store = s


def set_metrics(m) -> None:
    global _metrics
    _metrics = m


def _status_from_fills(quantity: float, filled_qty: float, cancelled: bool = False) -> OrderStatus:
    if cancelled:
        return OrderStatus.CANCELLED
    if filled_qty <= 0:
        return OrderStatus.OPEN
    if filled_qty >= quantity:
        return OrderStatus.FILLED
    return OrderStatus.PARTIALLY_FILLED


router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/orders", response_model=PlaceOrderResponse)
async def place_order(req: PlaceOrderRequest) -> PlaceOrderResponse:
    if not _engines or _broadcaster is None:
        raise HTTPException(status_code=503, detail="Engine or broadcaster not ready")
    symbol = req.symbol
    engine = _engines.get(symbol)
    if engine is None:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {symbol}")
    side = req.side
    order_type = req.order_type
    quantity = req.quantity
    price = req.price
    client_order_id = req.client_order_id

    log_order_received(side.value, quantity, order_type.value, price)

    if order_type.value == "limit" and (price is None or price <= 0):
        raise HTTPException(status_code=400, detail="Limit order requires price > 0")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    resting, fills, _ = await engine.submit_order(
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        client_order_id=client_order_id,
    )
    order_id = (resting.order_id if resting else None) or (fills[0].order_id if fills else None)
    if order_id is None:
        raise HTTPException(status_code=500, detail="No order_id returned")

    filled_qty = sum(f.quantity for f in fills if f.order_id == order_id and not f.is_maker)
    status = _status_from_fills(quantity, filled_qty, cancelled=False)

    _order_store[order_id] = {
        "order_id": order_id,
        "client_order_id": client_order_id,
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "filled_quantity": filled_qty,
        "price": price,
        "status": status,
    }
    if _metrics:
        _metrics.record_order_submitted()

    log_order_placed(order_id, symbol, side.value, quantity, price, client_order_id)

    # Immediate fill broadcast for this order (taker fills only; maker fills are for other orders)
    for f in fills:
        if f.order_id == order_id and not f.is_maker:
            await _broadcaster.broadcast_fill(f)

    return PlaceOrderResponse(
        order_id=order_id,
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        status=status,
    )


@router.post("/orders/cancel")
async def cancel_order(req: CancelOrderRequest) -> dict:
    if not _engines:
        raise HTTPException(status_code=503, detail="Engine not ready")
    order_id = req.order_id
    symbol = req.symbol
    engine = _engines.get(symbol)
    if engine is None:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {symbol}")
    cancelled = await engine.cancel_order(order_id)
    if cancelled is None:
        raise HTTPException(status_code=404, detail="Order not found or already filled/cancelled")
    if order_id in _order_store:
        _order_store[order_id]["status"] = OrderStatus.CANCELLED
    if _metrics:
        _metrics.record_order_cancelled()
    log_order_cancelled(order_id, symbol)
    log_client_trade_closed(order_id, symbol, "cancelled")
    return {"order_id": order_id, "status": "cancelled"}


@router.get("/orders/{order_id}", response_model=OrderStatusResponse)
async def get_order(order_id: str) -> OrderStatusResponse:
    if not _engines:
        raise HTTPException(status_code=503, detail="Engine not ready")
    if order_id in _order_store:
        row = _order_store[order_id]
        return OrderStatusResponse(
            order_id=row["order_id"],
            client_order_id=row.get("client_order_id"),
            symbol=row["symbol"],
            side=row["side"],
            order_type=row["order_type"],
            quantity=row["quantity"],
            filled_quantity=row.get("filled_quantity", 0),
            price=row.get("price"),
            status=row["status"],
        )
    # Check each symbol's book for open order (order_id is global)
    for engine in _engines.values():
        book_order = engine.book.get_order(order_id)
        if book_order:
            return OrderStatusResponse(
                order_id=book_order.order_id,
                client_order_id=book_order.client_order_id,
                symbol=book_order.symbol,
                side=OrderSide(book_order.side),
                order_type=OrderType.LIMIT,
                quantity=book_order.quantity,
                filled_quantity=book_order.quantity - book_order.remaining,
                price=book_order.price,
                status=OrderStatus.OPEN,
            )
    raise HTTPException(status_code=404, detail="Order not found")
