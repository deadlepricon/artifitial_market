# config/settings.py
"""
Central configuration for the exchange simulator.
Adjust symbols, ports, and simulation defaults here.
"""

# Default symbol (multi-symbol architecture is supported)
DEFAULT_SYMBOL = "BTC/USDT"

# API and WebSocket server
API_HOST = "0.0.0.0"
API_PORT = 8765
WS_FEED_PATH = "/ws/feed"

# Simulation speed: 1.0 = real-time, 10.0 = 10x faster, etc.
DEFAULT_SPEED_MULTIPLIER = 1.0

# Market generator defaults (e.g. for BTC/USDT)
DEFAULT_INITIAL_MID_PRICE = 50_000.0
DEFAULT_TICK_SIZE = 0.01
DEFAULT_LOT_SIZE = 0.00001
# Random walk step size (as fraction of price)
PRICE_VOLATILITY = 0.0002
# Spread as fraction of mid
SPREAD_FRACTION_MIN = 0.0001
SPREAD_FRACTION_MAX = 0.0005
# Levels to publish in L2
BOOK_DEPTH_LEVELS = 10
