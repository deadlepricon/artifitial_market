# market_generator/generator.py
"""
Synthetic market generator: produces realistic market activity by driving
random walk price movement, spread fluctuations, varying liquidity, and
trade events. Continuously submits synthetic bid/ask levels and optional
market-style flow to the matching engine so the order book stays lively.
"""

import asyncio
import random
from typing import Callable, Optional

from exchange_simulator.matching_engine.engine import MatchingEngine
from exchange_simulator.schemas.orders import OrderSide, OrderType

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class SyntheticMarketGenerator:
    """
    Async generator that updates the market at a configurable rate.
    Uses random walk for mid price, random spread, and posts synthetic
    limit orders (and optionally market orders) to the matching engine.
    """

    def __init__(
        self,
        symbol: str,
        matching_engine: MatchingEngine,
        *,
        initial_mid: float = 50_000.0,
        tick_size: float = 0.01,
        volatility: float = 0.0002,
        spread_fraction_min: float = 0.0001,
        spread_fraction_max: float = 0.0005,
        update_interval_sec: float = 0.5,
        get_speed_multiplier: Optional[Callable[[], float]] = None,
    ):
        self.symbol = symbol
        self._engine = matching_engine
        self._mid = initial_mid
        self._tick_size = tick_size
        self._volatility = volatility
        self._spread_min = spread_fraction_min
        self._spread_max = spread_fraction_max
        self._interval = update_interval_sec
        self._get_speed = get_speed_multiplier or (lambda: 1.0)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _random_step(self) -> float:
        """Random step for price (fraction of mid)."""
        if HAS_NUMPY:
            return float(np.random.normal(0, self._volatility))
        return (random.random() - 0.5) * 2 * self._volatility

    def _round_price(self, p: float) -> float:
        if self._tick_size <= 0:
            return p
        return round(p / self._tick_size) * self._tick_size

    def _next_mid(self) -> float:
        self._mid = self._mid * (1 + self._random_step())
        return self._round_price(self._mid)

    def _spread_fraction(self) -> float:
        return self._spread_min + (self._spread_max - self._spread_min) * random.random()

    def _spread(self) -> float:
        return self._round_price(self._mid * self._spread_fraction())

    async def _tick(self) -> None:
        """One generator tick: update mid, spread, post synthetic levels."""
        # Use book mid if available so we don't drift from actual book
        book_mid = self._engine.book.mid_price()
        if book_mid is not None:
            self._mid = book_mid
        else:
            self._next_mid()

        spread = self._spread()
        best_bid = self._round_price(self._mid - spread / 2)
        best_ask = self._round_price(self._mid + spread / 2)

        # Post a few synthetic limit orders at best bid/ask (small size)
        base_qty = 0.001 + random.random() * 0.01
        await self._engine.submit_order(
            OrderSide.BUY,
            OrderType.LIMIT,
            quantity=round(base_qty, 5),
            price=best_bid,
            order_id=None,
        )
        await self._engine.submit_order(
            OrderSide.SELL,
            OrderType.LIMIT,
            quantity=round(base_qty, 5),
            price=best_ask,
            order_id=None,
        )

        # Occasionally inject a small market sell/buy to create trades
        if random.random() < 0.2:
            side = OrderSide.SELL if random.random() < 0.5 else OrderSide.BUY
            await self._engine.submit_order(
                side,
                OrderType.MARKET,
                quantity=round(0.0005 + random.random() * 0.001, 5),
                price=None,
                order_id=None,
            )

    async def _run_loop(self) -> None:
        """Main loop: tick at interval adjusted by speed multiplier."""
        while self._running:
            await self._tick()
            speed = max(0.01, self._get_speed())
            sleep_time = self._interval / speed
            await asyncio.sleep(sleep_time)

    def start(self) -> None:
        """Start the generator loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    def stop(self) -> None:
        """Stop the generator loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def run_until_stopped(self) -> None:
        """Run the loop (for use when started explicitly)."""
        self._running = True
        try:
            await self._run_loop()
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
