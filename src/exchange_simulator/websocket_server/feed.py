# websocket_server/feed.py
"""
WebSocket market data feed: streams order book updates, trade events,
and ticker updates to connected clients. Messages resemble real exchange formats.
"""

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from exchange_simulator.schemas.book import OrderBookDelta, OrderBookSnapshot
from exchange_simulator.schemas.market_data import TickerUpdate
from exchange_simulator.schemas.trades import PublicTrade


class FeedBroadcaster:
    """
    Manages WebSocket connections and broadcasts market data events
    (book snapshot/delta, trade, ticker) to all connected clients
    or to clients subscribed to specific channels/symbols.
    """

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def subscribe(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def unsubscribe(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        text = json.dumps(message)
        async with self._lock:
            dead = []
            for conn in self._connections:
                try:
                    await conn.send_text(text)
                except Exception:
                    dead.append(conn)
            for conn in dead:
                if conn in self._connections:
                    self._connections.remove(conn)

    async def broadcast_book_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        await self.broadcast({"channel": "book", "type": "snapshot", "data": snapshot.model_dump()})

    async def broadcast_book_delta(self, delta: OrderBookDelta) -> None:
        await self.broadcast({"channel": "book", "type": "delta", "data": delta.model_dump()})

    async def broadcast_trade(self, trade: PublicTrade) -> None:
        await self.broadcast({"channel": "trades", "type": "trade", "data": trade.model_dump()})

    async def broadcast_ticker(self, ticker: TickerUpdate) -> None:
        await self.broadcast({"channel": "ticker", "type": "ticker", "data": ticker.model_dump()})


async def handle_feed_websocket(ws: WebSocket, broadcaster: FeedBroadcaster) -> None:
    """
    Handle a single WebSocket connection to the feed.
    Client can send subscribe messages; server pushes market data.
    """
    await broadcaster.subscribe(ws)
    try:
        while True:
            raw = await ws.receive_text()
            # Optional: parse subscribe message and filter by channel/symbol
            try:
                msg = json.loads(raw)
                if msg.get("action") == "subscribe":
                    # For now we send everything; could filter by msg.get("channels") / symbols
                    await ws.send_text(json.dumps({"event": "subscribed", "message": "OK"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unsubscribe(ws)
