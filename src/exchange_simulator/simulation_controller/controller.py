# simulation_controller/controller.py
"""
Simulation controller: provides simulation time and speed multiplier.
Allows real-time (1x) or accelerated (Nx) simulation for faster backtesting.
"""

import time
from typing import Optional


class SimulationController:
    """
    Single source of simulation speed. Components (e.g. market generator,
    metrics) call get_speed_multiplier() and get_simulation_time().
    """

    def __init__(self, initial_speed: float = 1.0):
        self._speed = max(0.01, initial_speed)
        self._start_wall = time.monotonic()
        self._start_sim: Optional[float] = None  # optional sim time offset
        self._paused = False
        self._paused_at: Optional[float] = None
        self._accumulated_pause = 0.0

    def get_speed_multiplier(self) -> float:
        """Speed multiplier: 1.0 = real-time, 10.0 = 10x faster."""
        return self._speed

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.01, speed)

    def get_simulation_time(self) -> float:
        """
        Elapsed simulation time in seconds (wall time * speed, minus pauses).
        If not using wall-based time, can be overridden for replay.
        """
        if self._paused and self._paused_at is not None:
            return (self._paused_at - self._start_wall - self._accumulated_pause) * self._speed
        now = time.monotonic()
        return (now - self._start_wall - self._accumulated_pause) * self._speed

    def pause(self) -> None:
        if self._paused:
            return
        self._paused = True
        self._paused_at = time.monotonic()

    def resume(self) -> None:
        if not self._paused:
            return
        self._accumulated_pause += time.monotonic() - (self._paused_at or 0)
        self._paused = False
        self._paused_at = None

    def is_paused(self) -> bool:
        return self._paused
