# market_generator/generator.py
"""
SyntheticMarketGenerator: realistic synthetic market data.
- Price: Gaussian returns with optional mean reversion (no uniform jumps).
- Order sizes: log-normal style (many small, fewer large), rounded to lot.
- Book: multiple levels each side with size decaying by level (realistic L2).
- Timing: jitter on update interval so ticks aren't perfectly periodic.
"""

import asyncio
import logging
import math
import random
from typing import Optional

from exchange_simulator.matching_engine.engine import MatchingEngine
from exchange_simulator.schemas.orders import OrderSide, OrderType

logger = logging.getLogger("exchange_simulator")


def _log_normal_size(median: float, sigma: float, lot_size: float, max_size: float = 0.5) -> float:
    """Size from log-normal style: median ~ typical order, sigma spreads it. Clamp and round to lot."""
    # log-normal: median = exp(mu), so mu = ln(median). sigma is shape.
    if median <= 0 or sigma <= 0:
        return max(lot_size, 0.001)
    mu = math.log(median)
    raw = math.exp(mu + sigma * random.gauss(0, 1))
    raw = max(lot_size, min(max_size, raw))
    if lot_size > 0:
        raw = round(raw / lot_size) * lot_size
    return max(lot_size, round(raw, 5))


class SyntheticMarketGenerator:
    """
    Async task: each tick updates mid (Gaussian returns, optional mean reversion),
    computes spread, posts synthetic limit orders at several levels and optionally
    injects market orders. Sizes and timing are more realistic.
    """

    def __init__(
        self,
        engine: MatchingEngine,
        symbol: str,
        *,
        initial_mid: float,
        tick_size: float,
        volatility: float,
        spread_fraction_min: float,
        spread_fraction_max: float,
        update_interval_sec: float,
        speed: float = 1.0,
        drift: bool = True,
        inject_market_orders: bool = False,
        market_order_prob: float = 0.0,
        depth_levels: int = 10,
        lot_size: float = 0.00001,
        mean_reversion: float = 0.0,
        size_median: float = 0.005,
        size_sigma: float = 1.2,
        book_levels_per_side: int = 3,
        interval_jitter: float = 0.25,
    ):
        self._engine = engine
        self._symbol = symbol
        self._initial_mid = initial_mid
        self._tick_size = tick_size
        self._volatility = volatility
        self._spread_min = spread_fraction_min
        self._spread_max = spread_fraction_max
        self._interval = update_interval_sec
        self._speed = max(0.01, speed)
        self._drift = drift
        self._inject_market_orders = inject_market_orders
        self._market_order_prob = market_order_prob
        self._depth_levels = depth_levels
        self._lot_size = max(1e-8, lot_size)
        self._mean_reversion = max(0.0, mean_reversion)
        self._size_median = size_median
        self._size_sigma = size_sigma
        self._book_levels = max(1, book_levels_per_side)
        self._interval_jitter = max(0.0, min(0.99, interval_jitter))
        self._mid = initial_mid
        self._spread_frac = (spread_fraction_min + spread_fraction_max) / 2.0
        self._task: Optional[asyncio.Task] = None

    def _round_price(self, price: float) -> float:
        if self._tick_size <= 0:
            return price
        return round(price / self._tick_size) * self._tick_size

    def _next_mid(self) -> float:
        # Gaussian return (realistic: small moves common, large rare)
        ret = self._volatility * random.gauss(0, 1)
        mid = self._mid * (1.0 + ret)
        if self._mean_reversion > 0 and self._initial_mid > 0:
            # Gentle pull toward initial mid
            mid = mid + self._mean_reversion * (self._initial_mid - mid)
        return mid

    def _next_spread_frac(self) -> float:
        # Smooth spread: small random change
        delta = random.uniform(-self._spread_max * 0.3, self._spread_max * 0.3)
        return max(self._spread_min, min(self._spread_max, self._spread_frac + delta))

    def _realistic_size(self) -> float:
        return _log_normal_size(self._size_median, self._size_sigma, self._lot_size)

    async def _tick(self) -> None:
        if self._drift:
            self._mid = self._next_mid()
            self._spread_frac = self._next_spread_frac()
        else:
            book_mid = self._engine.book.mid_price()
            if book_mid is not None:
                self._mid = book_mid
            else:
                self._mid = self._next_mid()
            self._spread_frac = self._next_spread_frac()
        if self._mid <= 0:
            self._mid = self._initial_mid

        spread = self._mid * self._spread_frac
        best_bid = self._round_price(self._mid - spread / 2.0)
        best_ask = self._round_price(self._mid + spread / 2.0)
        if best_bid <= 0 or best_ask <= 0:
            return

        # Post multiple levels each side (realistic L2): size often larger away from mid
        for level in range(self._book_levels):
            off = level * self._tick_size * (1 + level)
            bid = self._round_price(best_bid - off)
            ask = self._round_price(best_ask + off)
            if bid <= 0 or ask <= 0:
                continue
            qty = self._realistic_size()
            if qty <= 0:
                qty = self._lot_size
            try:
                await self._engine.submit_order(
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=qty,
                    price=bid,
                    order_id=None,
                )
            except Exception as e:
                logger.debug("generator limit buy failed: %s", e)
            try:
                await self._engine.submit_order(
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    quantity=qty,
                    price=ask,
                    order_id=None,
                )
            except Exception as e:
                logger.debug("generator limit sell failed: %s", e)

        if self._inject_market_orders and random.random() < self._market_order_prob:
            side = OrderSide.BUY if random.random() < 0.5 else OrderSide.SELL
            mqty = self._realistic_size()
            if mqty <= 0:
                mqty = self._lot_size
            try:
                await self._engine.submit_order(
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=mqty,
                    price=None,
                    order_id=None,
                )
            except Exception as e:
                logger.debug("generator market order failed: %s", e)

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.exception("generator tick error: %s", e)
            jitter = 1.0
            if self._interval_jitter > 0:
                jitter = 1.0 + random.uniform(-self._interval_jitter, self._interval_jitter)
            await asyncio.sleep(max(0.05, self._interval / self._speed * jitter))

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())
        self._task.add_done_callback(self._on_done)

    def _on_done(self, t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error("generator task exited with error: %s", exc)

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
