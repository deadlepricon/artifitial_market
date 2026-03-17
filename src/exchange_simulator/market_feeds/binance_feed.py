# market_feeds/binance_feed.py
"""
Binance live trade feed: connects to Binance WebSocket trade stream,
converts messages to our PublicTrade and TickerUpdate schemas, and
pushes them to the broadcaster. Use this instead of synthetic trades.
"""

import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

from exchange_simulator.schemas.market_data import TickerUpdate
from exchange_simulator.schemas.trades import PublicTrade, TradeSide

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    websockets = None
    ConnectionClosed = Exception


# Binance trade message: e="trade", s="BTCUSDT", t=id, p=price, q=qty, m=buyer_is_maker
def _parse_binance_trade(raw: dict, symbol: str) -> Optional[PublicTrade]:
    if raw.get("e") != "trade":
        return None
    price = float(raw["p"])
    qty = float(raw["q"])
    # m=true => buyer was maker => aggressor was seller => side = sell
    side = TradeSide.SELL if raw.get("m", False) else TradeSide.BUY
    trade_id = str(raw.get("t", ""))
    ts = raw.get("T")
    timestamp = str(ts) if ts is not None else None
    return PublicTrade(
        symbol=symbol,
        trade_id=trade_id,
        price=price,
        quantity=qty,
        side=side,
        timestamp=timestamp,
    )


async def run_binance_trade_feed(
    ws_url: str,
    symbol: str,
    on_trade: Callable[[PublicTrade], Awaitable[Any]],
    on_ticker: Callable[[TickerUpdate], Awaitable[Any]],
    *,
    reconnect_delay: float = 5.0,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Connect to Binance trade stream. For each message: parse, then await on_trade and on_ticker.
    So we literally pipe Binance → your callbacks (e.g. broadcast) one message at a time.
    Reconnects on disconnect.
    """
    if websockets is None:
        raise RuntimeError("Install websockets to use Binance feed: pip install websockets")

    volume_24h = 0.0

    while stop_event is None or not stop_event.is_set():
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=60) as ws:
                async for raw_msg in ws:
                    if stop_event and stop_event.is_set():
                        return
                    try:
                        msg = json.loads(raw_msg)
                        trade = _parse_binance_trade(msg, symbol)
                        if trade is None:
                            continue
                        volume_24h += trade.quantity
                        await on_trade(trade)
                        ticker = TickerUpdate(
                            symbol=symbol,
                            last_price=trade.price,
                            best_bid=trade.price,
                            best_ask=trade.price,
                            volume_24h=volume_24h,
                            timestamp=trade.timestamp,
                        )
                        await on_ticker(ticker)
                    except (KeyError, TypeError, ValueError):
                        continue
        except asyncio.CancelledError:
            return
        except Exception:
            if stop_event and stop_event.is_set():
                return
            await asyncio.sleep(reconnect_delay)
    return


class BinanceTradeFeed:
    """
    Wraps the Binance trade feed. For each Binance message we await your
    async callbacks (e.g. broadcast) so data flows straight through.
    """

    def __init__(
        self,
        ws_url: str,
        symbol: str,
        on_trade: Callable[[PublicTrade], Awaitable[Any]],
        on_ticker: Callable[[TickerUpdate], Awaitable[Any]],
    ):
        self._ws_url = ws_url
        self._symbol = symbol
        self._on_trade = on_trade
        self._on_ticker = on_ticker
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            run_binance_trade_feed(
                self._ws_url,
                self._symbol,
                self._on_trade,
                self._on_ticker,
                stop_event=self._stop,
            )
        )

    def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
