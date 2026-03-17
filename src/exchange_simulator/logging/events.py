# logging/events.py
"""
Structured logging for system events: order accepted, filled, cancelled,
errors. Keeps a simple event log and optional stdout/stderr output.
"""

import logging
import time
from typing import Any, Optional

# Module-level logger; can be configured by main
logger = logging.getLogger("exchange_simulator")


def log_order_received(side: str, quantity: float, order_type: str, price: Optional[float] = None) -> None:
    """Log when a buy/sell order is received from a client (REST API)."""
    if order_type == "market":
        logger.info("client order received: %s %s qty=%.6f (market)", side.upper(), order_type, quantity)
    else:
        logger.info("client order received: %s %s qty=%.6f price=%s", side.upper(), order_type, quantity, price)


def log_order_placed(
    order_id: str,
    symbol: str,
    side: str,
    quantity: float,
    price: Optional[float] = None,
    client_order_id: Optional[str] = None,
) -> None:
    logger.info(
        "order_placed order_id=%s symbol=%s side=%s quantity=%s price=%s client_order_id=%s",
        order_id,
        symbol,
        side,
        quantity,
        price,
        client_order_id,
    )


def log_order_filled(
    order_id: str,
    symbol: str,
    price: float,
    quantity: float,
    fill_id: str,
    is_maker: bool,
) -> None:
    logger.info(
        "order_filled order_id=%s symbol=%s price=%s quantity=%s fill_id=%s is_maker=%s",
        order_id,
        symbol,
        price,
        quantity,
        fill_id,
        is_maker,
    )


def log_order_cancelled(order_id: str, symbol: str) -> None:
    logger.info("order_cancelled order_id=%s symbol=%s", order_id, symbol)


def log_client_trade_closed(
    order_id: str,
    symbol: str,
    reason: str,
    *,
    filled_quantity: Optional[float] = None,
    avg_price: Optional[float] = None,
) -> None:
    """Log when a client closes a trade: by cancel or by full fill."""
    if reason == "cancelled":
        logger.info("client closed trade order_id=%s symbol=%s reason=cancelled", order_id, symbol)
    else:
        logger.info(
            "client closed trade order_id=%s symbol=%s reason=filled filled_quantity=%s avg_price=%s",
            order_id,
            symbol,
            filled_quantity,
            avg_price,
        )


def log_trade(symbol: str, trade_id: str, price: float, quantity: float, side: str) -> None:
    logger.info(
        "trade symbol=%s trade_id=%s price=%s quantity=%s side=%s",
        symbol,
        trade_id,
        price,
        quantity,
        side,
    )


def log_error(message: str, **kwargs: Any) -> None:
    logger.error("error %s %s", message, kwargs)


def log_system(message: str, **kwargs: Any) -> None:
    logger.info("system %s %s", message, kwargs)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logger for the simulator."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
