# exchange_api/routes.py
"""
REST endpoints for placing orders, cancelling orders, and checking order status.
Orders are forwarded to the matching engine; results and fills are returned.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from exchange_simulator.schemas.orders import (
    CancelOrderRequest,
    OrderStatus,
    OrderStatusResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
)

# Router is attached to app in main; we need the matching engine, order store,
# and optional metrics injected.
_engine_ref: Optional[Any] = None
_order_store_ref: Optional[Any] = None
_metrics_ref: Optional[Any] = None


def set_engine(engine: Any) -> None:
    global _engine_ref
    _engine_ref = engine


def set_order_store(store: Any) -> None:
    global _order_store_ref
    _order_store_ref = store


def set_metrics(metrics: Any) -> None:
    global _metrics_ref
    _metrics_ref = metrics


router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/orders", response_model=PlaceOrderResponse)
async def place_order(req: PlaceOrderRequest) -> PlaceOrderResponse:
    """Place a limit or market order."""
    if _engine_ref is None:
        raise HTTPException(status_code=503, detail="Exchange not ready")
    if req.symbol != _engine_ref.symbol:
        raise HTTPException(status_code=400, detail=f"Symbol {req.symbol} not supported")
    if req.order_type.value == "limit" and (req.price is None or req.price <= 0):
        raise HTTPException(status_code=400, detail="Limit order requires price > 0")

    resting, fills, _ = await _engine_ref.submit_order(
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        client_order_id=req.client_order_id,
    )

    # Determine order_id from resting order or from first fill
    order_id = resting.order_id if resting else (fills[0].order_id if fills else "")
    status = OrderStatus.FILLED if not resting and fills else (OrderStatus.OPEN if resting else OrderStatus.PENDING)
    filled_qty = sum(f.quantity for f in fills if f.order_id == order_id and not f.is_maker)

    if _metrics_ref is not None:
        _metrics_ref.record_order_submitted()
    if _order_store_ref is not None:
        _order_store_ref[order_id] = {
            "order_id": order_id,
            "client_order_id": req.client_order_id,
            "symbol": req.symbol,
            "side": req.side,
            "order_type": req.order_type,
            "quantity": req.quantity,
            "filled_quantity": filled_qty,
            "price": req.price,
            "status": status,
        }

    return PlaceOrderResponse(
        order_id=order_id,
        client_order_id=req.client_order_id,
        symbol=req.symbol,
        side=req.side,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        status=status,
    )


@router.post("/orders/cancel")
async def cancel_order(req: CancelOrderRequest) -> dict:
    """Cancel an order by symbol and order_id."""
    if _engine_ref is None:
        raise HTTPException(status_code=503, detail="Exchange not ready")
    cancelled = await _engine_ref.cancel_order(req.order_id)
    if cancelled is None:
        raise HTTPException(status_code=404, detail="Order not found or already filled/cancelled")
    if _metrics_ref is not None:
        _metrics_ref.record_order_cancelled()
    if _order_store_ref is not None and req.order_id in _order_store_ref:
        _order_store_ref[req.order_id]["status"] = OrderStatus.CANCELLED
    return {"order_id": req.order_id, "status": "cancelled"}


@router.get("/orders/{order_id}", response_model=OrderStatusResponse)
async def get_order_status(order_id: str, symbol: Optional[str] = None) -> OrderStatusResponse:
    """Get current status of an order."""
    if _order_store_ref is None:
        raise HTTPException(status_code=503, detail="Order store not available")
    if order_id not in _order_store_ref:
        raise HTTPException(status_code=404, detail="Order not found")
    rec = _order_store_ref[order_id]
    return OrderStatusResponse(
        order_id=rec["order_id"],
        client_order_id=rec.get("client_order_id"),
        symbol=rec["symbol"],
        side=rec["side"],
        order_type=rec["order_type"],
        quantity=rec["quantity"],
        filled_quantity=rec.get("filled_quantity", 0),
        price=rec.get("price"),
        status=rec["status"],
    )
