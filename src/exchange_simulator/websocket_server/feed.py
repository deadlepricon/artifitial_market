# websocket_server/feed.py
"""
WebSocket market data feed: FeedBroadcaster and handle_feed_websocket.
Broadcasts book deltas, trades, ticker, and optional fills with send timeout.
"""

import asyncio
import json
from typing import Optional

from exchange_simulator.schemas.book import OrderBookDelta
from exchange_simulator.schemas.market_data import TickerUpdate
from exchange_simulator.schemas.trades import FillEvent, PublicTrade

try:
    from config.settings import BROADCAST_SEND_TIMEOUT_SEC
except ImportError:
    BROADCAST_SEND_TIMEOUT_SEC = 10.0


class FeedBroadcaster:
    """
    Broadcasts book deltas, trades, ticker, and optional fills to all connected
    WebSocket clients. Drops clients that don't accept within BROADCAST_SEND_TIMEOUT_SEC.
    """

    def __init__(self, send_timeout_sec: float = BROADCAST_SEND_TIMEOUT_SEC):
        self._clients: set[asyncio.Queue] = set()
        self._send_timeout = send_timeout_sec
        self._lock = asyncio.Lock()

    def _payload(self, channel: str, type_: str, data: dict) -> str:
        return json.dumps({"channel": channel, "type": type_, "data": data})

    async def _send_to_all(self, channel: str, type_: str, data: dict) -> None:
        msg = self._payload(channel, type_, data)
        async with self._lock:
            dead = set()
            for q in self._clients:
                try:
                    await asyncio.wait_for(q.put(msg), timeout=self._send_timeout)
                except asyncio.TimeoutError:
                    dead.add(q)
                except Exception:
                    dead.add(q)
            for q in dead:
                self._clients.discard(q)

    async def broadcast_book_delta(self, delta: OrderBookDelta) -> None:
        data = {
            "symbol": delta.symbol,
            "bids": [{"price": p.price, "quantity": p.quantity} for p in delta.bids],
            "asks": [{"price": p.price, "quantity": p.quantity} for p in delta.asks],
            "sequence": delta.sequence,
        }
        await self._send_to_all("book", "delta", data)

    async def broadcast_trade(self, trade: PublicTrade) -> None:
        data = {
            "symbol": trade.symbol,
            "trade_id": trade.trade_id,
            "price": trade.price,
            "quantity": trade.quantity,
            "side": trade.side.value,
            "timestamp": trade.timestamp,
        }
        await self._send_to_all("trades", "trade", data)

    async def broadcast_ticker(self, ticker: TickerUpdate) -> None:
        data = {
            "symbol": ticker.symbol,
            "last_price": ticker.last_price,
            "best_bid": ticker.best_bid,
            "best_ask": ticker.best_ask,
            "volume_24h": ticker.volume_24h,
            "timestamp": ticker.timestamp,
        }
        await self._send_to_all("ticker", "ticker", data)

    async def broadcast_fill(self, fill: FillEvent) -> None:
        data = {
            "order_id": fill.order_id,
            "client_order_id": fill.client_order_id,
            "symbol": fill.symbol,
            "side": fill.side.value,
            "price": fill.price,
            "quantity": fill.quantity,
            "fill_id": fill.fill_id,
            "is_maker": fill.is_maker,
            "timestamp": fill.timestamp,
        }
        await self._send_to_all("orders", "fill", data)

    def register(self) -> asyncio.Queue:
        """Register a new client; returns a queue the client should consume from."""
        q: asyncio.Queue = asyncio.Queue()
        self._clients.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)


async def handle_feed_websocket(
    websocket,
    broadcaster: FeedBroadcaster,
) -> None:
    """
    Handle a single WebSocket connection to the feed.
    Sends all broadcast messages to this client; drops if send blocks too long.
    """
    queue = broadcaster.register()
    try:
        while True:
            msg = await queue.get()
            await asyncio.wait_for(websocket.send_text(msg), timeout=BROADCAST_SEND_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        pass
    except Exception:
        pass
    finally:
        broadcaster.unregister(queue)
