# metrics/collector.py
"""
Metrics collector: tracks number of trades, order throughput, current spread,
simulation speed, and system events. Can be logged periodically or exposed via API.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class SimulationMetrics:
    """Mutable snapshot of current metrics."""

    trades_executed: int = 0
    orders_submitted: int = 0
    orders_cancelled: int = 0
    current_spread: Optional[float] = None
    simulation_speed: float = 1.0
    last_trade_time: Optional[float] = None
    start_time: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        elapsed = time.monotonic() - self.start_time
        return {
            "trades_executed": self.trades_executed,
            "orders_submitted": self.orders_submitted,
            "orders_cancelled": self.orders_cancelled,
            "current_spread": self.current_spread,
            "simulation_speed": self.simulation_speed,
            "uptime_sec": round(elapsed, 2),
            "orders_per_sec": round(self.orders_submitted / elapsed, 2) if elapsed > 0 else 0,
        }


class MetricsCollector:
    """
    Central metrics: increment counters on events, update spread/speed from
    simulation controller and order book. Optional callback for logging.
    """

    def __init__(self, on_snapshot: Optional[Callable[[dict], None]] = None):
        self._metrics = SimulationMetrics()
        self._on_snapshot = on_snapshot
        self._lock = asyncio.Lock()

    def record_trade(self) -> None:
        self._metrics.trades_executed += 1
        self._metrics.last_trade_time = time.monotonic()

    def record_order_submitted(self) -> None:
        self._metrics.orders_submitted += 1

    def record_order_cancelled(self) -> None:
        self._metrics.orders_cancelled += 1

    def update_spread(self, spread: Optional[float]) -> None:
        self._metrics.current_spread = spread

    def update_speed(self, speed: float) -> None:
        self._metrics.simulation_speed = speed

    def snapshot(self) -> dict:
        return self._metrics.to_dict()

    async def log_snapshot_if_needed(self, interval_sec: float = 10.0) -> None:
        """Call periodically from a task to log metrics every interval."""
        if not self._on_snapshot:
            return
        await asyncio.sleep(interval_sec)
        self._on_snapshot(self.snapshot())
