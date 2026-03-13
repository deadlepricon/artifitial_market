# matching_engine/engine.py
"""
Simplified matching engine: accepts new orders (from API or market generator),
matches them against the order book, generates trades (fills), and updates the book.
Produces fill events and book update events for the WebSocket broadcaster.
"""

import asyncio
from typing import Any, Callable, Optional

from exchange_simulator.order_book.book import BookOrder, OrderBook
from exchange_simulator.schemas.orders import OrderSide, OrderType
from exchange_simulator.schemas.trades import FillEvent, PublicTrade, TradeSide


class MatchingEngine:
    """
    Single-symbol matching engine. Holds the order book and applies
    price-time priority matching. Emits fill and trade events via async queue
    or callback for the broadcaster.
    """

    def __init__(
        self,
        symbol: str,
        book: Optional[OrderBook] = None,
        on_fill: Optional[Callable[[FillEvent], Any]] = None,
        on_trade: Optional[Callable[[PublicTrade], Any]] = None,
        on_book_update: Optional[Callable[[], Any]] = None,
    ):
        self.symbol = symbol
        self._book = book or OrderBook(symbol=symbol)
        self._on_fill = on_fill
        self._on_trade = on_trade
        self._on_book_update = on_book_update
        self._order_id_counter = 0
        self._trade_id_counter = 0
        self._lock = asyncio.Lock()

    def _next_order_id(self) -> str:
        self._order_id_counter += 1
        return f"ord_{self.symbol.replace('/', '')}_{self._order_id_counter}"

    def _next_trade_id(self) -> str:
        self._trade_id_counter += 1
        return f"trd_{self._trade_id_counter}"

    @property
    def book(self) -> OrderBook:
        return self._book

    async def submit_order(
        self,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> tuple[BookOrder | None, list[FillEvent], list[PublicTrade]]:
        """
        Submit an order. Returns (resting_order, fills, public_trades).
        For limit orders: matches first, then rests remainder in book.
        For market orders: matches only; no rest.
        """
        async with self._lock:
            return self._match_and_book(
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                client_order_id=client_order_id,
                order_id=order_id,
            )

    def _match_and_book(
        self,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> tuple[BookOrder | None, list[FillEvent], list[PublicTrade]]:
        if quantity <= 0:
            return None, [], []
        oid = order_id or self._next_order_id()
        side_str = side.value
        fills: list[FillEvent] = []
        public_trades: list[PublicTrade] = []
        remaining = quantity

        # Match against opposite side: buy hits asks, sell hits bids
        opposite_side = self._book._asks if side_str == "buy" else self._book._bids
        while remaining > 0 and opposite_side:
            level_price, level_orders = opposite_side[0]
            if order_type == OrderType.LIMIT and price is not None:
                if side_str == "buy" and level_price > price:
                    break
                if side_str == "sell" and level_price < price:
                    break
            # Match with first order in level (time priority); copy list since we may mutate it
            taker_remaining = remaining
            for book_order in list(level_orders):
                if taker_remaining <= 0:
                    break
                fill_qty = min(taker_remaining, book_order.remaining)
                if fill_qty <= 0:
                    continue
                trade_id = self._next_trade_id()
                fill_side = TradeSide.BUY if side_str == "buy" else TradeSide.SELL
                fills.append(
                    FillEvent(
                        order_id=oid,
                        client_order_id=client_order_id,
                        symbol=self.symbol,
                        side=fill_side,
                        price=level_price,
                        quantity=fill_qty,
                        fill_id=trade_id,
                        is_maker=False,
                    )
                )
                public_trades.append(
                    PublicTrade(
                        symbol=self.symbol,
                        trade_id=trade_id,
                        price=level_price,
                        quantity=fill_qty,
                        side=fill_side,
                    )
                )
                # Maker fill (for the resting order owner)
                fills.append(
                    FillEvent(
                        order_id=book_order.order_id,
                        client_order_id=book_order.client_order_id,
                        symbol=self.symbol,
                        side=TradeSide.SELL if side_str == "buy" else TradeSide.BUY,
                        price=level_price,
                        quantity=fill_qty,
                        fill_id=trade_id,
                        is_maker=True,
                    )
                )
                taker_remaining -= fill_qty
                remaining -= fill_qty
                self._book.reduce_order(book_order.order_id, fill_qty)
                if self._on_fill:
                    self._on_fill(fills[-2])
                    self._on_fill(fills[-1])
                if self._on_trade:
                    self._on_trade(public_trades[-1])
            if not level_orders:
                opposite_side.pop(0)
            if self._on_book_update:
                self._on_book_update()

        resting: BookOrder | None = None
        if remaining > 0 and order_type == OrderType.LIMIT and price is not None:
            resting = BookOrder(
                order_id=oid,
                symbol=self.symbol,
                side=side_str,
                price=price,
                quantity=quantity,
                remaining=remaining,
                timestamp=0.0,  # Caller can set simulation time
            )
            resting.client_order_id = client_order_id
            self._book.add_order(resting)
            if self._on_book_update:
                self._on_book_update()

        return resting, fills, public_trades

    async def cancel_order(self, order_id: str) -> Optional[BookOrder]:
        """Cancel an order by id. Returns the cancelled order or None."""
        async with self._lock:
            cancelled = self._book.cancel_order(order_id)
            if cancelled and self._on_book_update:
                self._on_book_update()
            return cancelled

    def get_book_snapshot(self, depth: int = 10) -> tuple[list, list, int]:
        """Return (bids, asks, sequence) for broadcasting."""
        return self._book.snapshot(depth)
