# order_book/book.py
"""
In-memory Level 2 order book for a single symbol.
Maintains bid and ask sides with price-time priority: best price first,
then earliest order at that price. Supports limit orders, market orders
(consumed by matching engine), cancel, and update.
"""

from dataclasses import dataclass, field
from typing import Optional

from exchange_simulator.schemas.book import PriceLevel


@dataclass
class BookOrder:
    """Single order resting in the book (internal)."""

    order_id: str
    symbol: str
    side: str  # "buy" | "sell"
    price: float
    quantity: float
    remaining: float
    timestamp: float  # for time priority
    client_order_id: Optional[str] = None


@dataclass
class OrderBook:
    """
    Level 2 order book: bids and asks as sorted lists of (price, total_qty)
    and optional per-order tracking for cancellation.
    Uses price-time priority: at each price level, orders are FIFO.
    """

    symbol: str
    # Sorted: bids descending (best bid first), asks ascending (best ask first)
    _bids: list[tuple[float, list[BookOrder]]] = field(default_factory=list)
    _asks: list[tuple[float, list[BookOrder]]] = field(default_factory=list)
    _order_by_id: dict[str, BookOrder] = field(default_factory=dict)
    _sequence: int = 0

    def _best_bid(self) -> Optional[float]:
        if not self._bids:
            return None
        return self._bids[0][0]

    def _best_ask(self) -> Optional[float]:
        if not self._asks:
            return None
        return self._asks[0][0]

    def spread(self) -> Optional[float]:
        """Current spread (ask - bid). None if either side empty."""
        bid, ask = self._best_bid(), self._best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def mid_price(self) -> Optional[float]:
        """Mid from best bid and ask."""
        bid, ask = self._best_bid(), self._best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    def add_order(self, order: BookOrder) -> None:
        """
        Add a limit order to the book. Inserts by price-time.
        Caller (matching engine) should have already matched any crossing quantity.
        """
        self._order_by_id[order.order_id] = order
        if order.side == "buy":
            self._insert_side(self._bids, order, ascending=False)
        else:
            self._insert_side(self._asks, order, ascending=True)
        self._sequence += 1

    def _insert_side(
        self,
        side: list[tuple[float, list[BookOrder]]],
        order: BookOrder,
        *,
        ascending: bool,
    ) -> None:
        price = order.price
        for i, (p, orders) in enumerate(side):
            if (ascending and p >= price) or (not ascending and p <= price):
                if p == price:
                    orders.append(order)
                    return
                # Insert new level
                side.insert(i, (price, [order]))
                return
        side.append((price, [order]))

    def cancel_order(self, order_id: str) -> Optional[BookOrder]:
        """Remove order by id. Returns the cancelled order or None."""
        order = self._order_by_id.pop(order_id, None)
        if order is None:
            return None
        if order.side == "buy":
            self._remove_from_side(self._bids, order_id)
        else:
            self._remove_from_side(self._asks, order_id)
        self._sequence += 1
        return order

    def _remove_from_side(self, side: list[tuple[float, list[BookOrder]]], order_id: str) -> None:
        for i, (price, orders) in enumerate(side):
            for j, o in enumerate(orders):
                if o.order_id == order_id:
                    orders.pop(j)
                    if not orders:
                        side.pop(i)
                    return

    def get_order(self, order_id: str) -> Optional[BookOrder]:
        return self._order_by_id.get(order_id)

    def reduce_order(self, order_id: str, reduce_by: float) -> Optional[BookOrder]:
        """Reduce remaining quantity (e.g. after a fill)."""
        order = self._order_by_id.get(order_id)
        if order is None or reduce_by <= 0:
            return order
        order.remaining -= reduce_by
        if order.remaining <= 0:
            self.cancel_order(order_id)
        else:
            self._sequence += 1
        return order

    def get_levels(self, depth: int = 10) -> tuple[list[PriceLevel], list[PriceLevel]]:
        """Return (bids, asks) as PriceLevel lists, top 'depth' levels each."""
        def levels(side: list[tuple[float, list[BookOrder]]], n: int) -> list[PriceLevel]:
            out: list[PriceLevel] = []
            for price, orders in side[:n]:
                qty = sum(o.remaining for o in orders)
                if qty > 0:
                    out.append(PriceLevel(price=price, quantity=qty))
            return out

        return levels(self._bids, depth), levels(self._asks, depth)

    def sequence(self) -> int:
        return self._sequence

    def snapshot(self, depth: int = 10) -> tuple[list[PriceLevel], list[PriceLevel], int]:
        """Return (bids, asks, sequence) for broadcasting."""
        bids, asks = self.get_levels(depth)
        return bids, asks, self._sequence
