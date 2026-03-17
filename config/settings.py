# config/settings.py
"""
Central config for the exchange simulator.
Live mode vs simulation mode: use SIMULATION_* when run with --simulation.
"""

# Symbol and API
# Tradable symbols; each gets its own order book, matching engine, generator, and Binance feed.
TRADABLE_SYMBOLS = ["BTC/USDT", "ETH/USDT"]
DEFAULT_SYMBOL = "BTC/USDT"  # backward compat: health, default in docs
API_HOST = "0.0.0.0"
API_PORT = 8765
WS_FEED_PATH = "/ws/feed"

# Binance (live mode): one stream per symbol (e.g. BTC/USDT -> btcusdt@trade)
# Set BINANCE_US = True if you're in a region where binance.com returns 451 (e.g. US)
BINANCE_US = True

def _binance_stream_symbol(symbol: str) -> str:
    return symbol.replace("/", "").lower()


def _binance_rest_base() -> str:
    return "https://api.binance.us" if BINANCE_US else "https://api.binance.com"


def _binance_ws_base() -> str:
    return "wss://stream.binance.us:9443" if BINANCE_US else "wss://stream.binance.com:9443"


def binance_trade_ws_url(symbol: str) -> str:
    """Binance WebSocket trade stream URL for a symbol (e.g. BTC/USDT -> .../ws/btcusdt@trade)."""
    return f"{_binance_ws_base()}/ws/{_binance_stream_symbol(symbol)}@trade"


BINANCE_REST_BASE = _binance_rest_base()
BINANCE_TRADE_WS_URL = binance_trade_ws_url(DEFAULT_SYMBOL)

# Speed and book (defaults; per-symbol initial_mid can override in symbol registry)
DEFAULT_SPEED_MULTIPLIER = 1.0
DEFAULT_INITIAL_MID_PRICE = 50000.0   # BTC/USDT
ETH_INITIAL_MID_PRICE = 3500.0        # ETH/USDT
DEFAULT_TICK_SIZE = 0.01
DEFAULT_LOT_SIZE = 0.00001

# Live mode: generator params (no drift, no synthetic market orders)
PRICE_VOLATILITY = 0.002
SPREAD_FRACTION_MIN = 0.0001
SPREAD_FRACTION_MAX = 0.0005
BOOK_DEPTH_LEVELS = 10
GENERATOR_UPDATE_INTERVAL_SEC = 0.5
BROADCAST_SEND_TIMEOUT_SEC = 10.0

# Simulation mode (--simulation): higher volatility, drift, synthetic market orders
SIMULATION_VOLATILITY = 0.012
SIMULATION_SPREAD_FRACTION_MIN = 0.0002
SIMULATION_SPREAD_FRACTION_MAX = 0.001
SIMULATION_MARKET_ORDER_PROB = 0.35
SIMULATION_DRIFT = True

# More realistic synthetic data (generator)
MEAN_REVERSION_STRENGTH = 0.02
SIZE_LOG_MEDIAN = 0.005
SIZE_LOG_SIGMA = 1.2
GENERATOR_BOOK_LEVELS = 3
GENERATOR_INTERVAL_JITTER = 0.25
