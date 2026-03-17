# main.py
"""
App entry: FastAPI app with lifespan that wires per-symbol engines, broadcaster,
generators, Binance feeds (when not simulation), and REST/WS routes.
"""

import asyncio
import json
import logging
import time
import urllib.request
from contextlib import asynccontextmanager

logger = logging.getLogger("exchange_simulator")

from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse

from config.settings import (
    API_HOST,
    API_PORT,
    BINANCE_REST_BASE,
    BOOK_DEPTH_LEVELS,
    BROADCAST_SEND_TIMEOUT_SEC,
    DEFAULT_INITIAL_MID_PRICE,
    DEFAULT_LOT_SIZE,
    DEFAULT_SYMBOL,
    DEFAULT_SPEED_MULTIPLIER,
    DEFAULT_TICK_SIZE,
    GENERATOR_BOOK_LEVELS,
    GENERATOR_INTERVAL_JITTER,
    GENERATOR_UPDATE_INTERVAL_SEC,
    MEAN_REVERSION_STRENGTH,
    PRICE_VOLATILITY,
    SIMULATION_DRIFT,
    SIMULATION_MARKET_ORDER_PROB,
    SIMULATION_SPREAD_FRACTION_MAX,
    SIMULATION_SPREAD_FRACTION_MIN,
    SIMULATION_VOLATILITY,
    SIZE_LOG_MEDIAN,
    SIZE_LOG_SIGMA,
    SPREAD_FRACTION_MAX,
    SPREAD_FRACTION_MIN,
    TRADABLE_SYMBOLS,
    WS_FEED_PATH,
    binance_trade_ws_url,
)
from exchange_simulator.exchange_api.routes import (
    router as api_router,
    set_broadcaster,
    set_engines,
    set_metrics,
    set_order_store,
)
from exchange_simulator.symbols.registry import get_symbol
from exchange_simulator.market_feeds.binance_feed import BinanceTradeFeed
from exchange_simulator.market_generator.generator import SyntheticMarketGenerator
from exchange_simulator.matching_engine.engine import MatchingEngine
from exchange_simulator.schemas.book import OrderBookDelta, PriceLevel
from exchange_simulator.schemas.market_data import TickerUpdate
from exchange_simulator.schemas.trades import PublicTrade
from exchange_simulator.symbols.registry import ensure_default_symbols
from exchange_simulator.logging.events import log_client_trade_closed
from exchange_simulator.metrics.collector import MetricsCollector
from exchange_simulator.websocket_server.feed import FeedBroadcaster, handle_feed_websocket


def run_app(simulation: bool = False) -> None:
    """Create app and run uvicorn. Called from run.py."""
    app = create_app(simulation=simulation)
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)


def _fetch_binance_price_sync(rest_base: str, symbol_rest: str) -> tuple[float | None, str | None]:
    """
    Fetch current price from Binance REST. rest_base e.g. 'https://api.binance.us', symbol_rest e.g. 'BTCUSDT'.
    Returns (price, None) on success, (None, error_message) on failure.
    """
    try:
        url = f"{rest_base.rstrip('/')}/api/v3/ticker/price?symbol={symbol_rest}"
        req = urllib.request.Request(url, headers={"User-Agent": "ExchangeSimulator/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            price = float(data["price"])
            return (price, None)
    except Exception as e:
        return (None, str(e))


def create_app(simulation: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sim = getattr(app.state, "simulation", False)
        ensure_default_symbols()
        order_store: dict = {}
        broadcaster = FeedBroadcaster(send_timeout_sec=BROADCAST_SEND_TIMEOUT_SEC)
        metrics = MetricsCollector()
        speed = DEFAULT_SPEED_MULTIPLIER
        engines: dict[str, MatchingEngine] = {}
        generators: list[SyntheticMarketGenerator] = []
        binance_feeds: list[BinanceTradeFeed] = []

        async def _do_fill(fill):
            if broadcaster:
                await broadcaster.broadcast_fill(fill)
            if fill.order_id in order_store:
                row = order_store[fill.order_id]
                row["filled_quantity"] = row.get("filled_quantity", 0) + fill.quantity
                if row["filled_quantity"] >= row["quantity"]:
                    from exchange_simulator.schemas.orders import OrderStatus
                    row["status"] = OrderStatus.FILLED
                    log_client_trade_closed(
                        fill.order_id,
                        fill.symbol,
                        "filled",
                        filled_quantity=row["filled_quantity"],
                        avg_price=fill.price,
                    )

        def on_fill(fill):
            asyncio.create_task(_do_fill(fill))

        async def _do_trade(trade: PublicTrade):
            metrics.record_trade()
            if broadcaster:
                await broadcaster.broadcast_trade(trade)

        def on_trade(trade: PublicTrade):
            asyncio.create_task(_do_trade(trade))

        for symbol in TRADABLE_SYMBOLS:
            def _make_book_update(eng: MatchingEngine, sym: str):
                async def _do_book_update():
                    if not broadcaster:
                        return
                    bids, asks, seq = eng.get_book_snapshot(depth=BOOK_DEPTH_LEVELS)
                    delta = OrderBookDelta(
                        symbol=sym,
                        bids=bids,
                        asks=asks,
                        sequence=seq,
                    )
                    await broadcaster.broadcast_book_delta(delta)
                    metrics.update_spread(eng.book.spread())
                    metrics.update_speed(speed)
                    if sim:
                        mid = eng.book.mid_price()
                        best_bid = eng.book._best_bid()
                        best_ask = eng.book._best_ask()
                        if mid is not None and best_bid is not None and best_ask is not None:
                            ticker = TickerUpdate(
                                symbol=sym,
                                last_price=mid,
                                best_bid=best_bid,
                                best_ask=best_ask,
                                volume_24h=0.0,
                                timestamp=str(int(time.time() * 1000)),
                            )
                            await broadcaster.broadcast_ticker(ticker)
                def on_book_update():
                    asyncio.create_task(_do_book_update())
                return on_book_update

            engine = MatchingEngine(
                symbol=symbol,
                on_fill=on_fill,
                on_trade=on_trade,
                on_book_update=None,
            )
            engine._on_book_update = _make_book_update(engine, symbol)
            engines[symbol] = engine

            # Live: seed from Binance; else use registry initial_mid
            info = get_symbol(symbol)
            initial_mid = info.initial_mid_price if info else DEFAULT_INITIAL_MID_PRICE
            if not sim:
                binance_rest_symbol = symbol.replace("/", "").upper()
                fetched, err = await asyncio.to_thread(
                    _fetch_binance_price_sync, BINANCE_REST_BASE, binance_rest_symbol
                )
                if fetched is not None and fetched > 0:
                    initial_mid = fetched
                    logger.info("live seed price from Binance %s: %.2f", binance_rest_symbol, initial_mid)
                else:
                    logger.warning(
                        "Binance price fetch failed for %s: %s; using fallback initial_mid=%.2f",
                        binance_rest_symbol,
                        err or "unknown",
                        initial_mid,
                    )

            _gen_kw = dict(
                initial_mid=initial_mid,
                tick_size=DEFAULT_TICK_SIZE,
                update_interval_sec=GENERATOR_UPDATE_INTERVAL_SEC,
                speed=speed,
                depth_levels=BOOK_DEPTH_LEVELS,
                lot_size=DEFAULT_LOT_SIZE,
                mean_reversion=MEAN_REVERSION_STRENGTH,
                size_median=SIZE_LOG_MEDIAN,
                size_sigma=SIZE_LOG_SIGMA,
                book_levels_per_side=GENERATOR_BOOK_LEVELS,
                interval_jitter=GENERATOR_INTERVAL_JITTER,
            )
            if sim:
                gen = SyntheticMarketGenerator(
                    engine,
                    symbol,
                    volatility=SIMULATION_VOLATILITY,
                    spread_fraction_min=SIMULATION_SPREAD_FRACTION_MIN,
                    spread_fraction_max=SIMULATION_SPREAD_FRACTION_MAX,
                    drift=SIMULATION_DRIFT,
                    inject_market_orders=True,
                    market_order_prob=SIMULATION_MARKET_ORDER_PROB,
                    **_gen_kw,
                )
            else:
                gen = SyntheticMarketGenerator(
                    engine,
                    symbol,
                    volatility=PRICE_VOLATILITY,
                    spread_fraction_min=SPREAD_FRACTION_MIN,
                    spread_fraction_max=SPREAD_FRACTION_MAX,
                    drift=False,
                    inject_market_orders=False,
                    market_order_prob=0.0,
                    **_gen_kw,
                )
            generators.append(gen)
            gen.start()

            if not sim:
                def _make_binance_ticker_cb(eng: MatchingEngine):
                    async def on_binance_ticker(ticker: TickerUpdate):
                        bids, asks, _ = eng.get_book_snapshot(depth=1)
                        best_bid = bids[0].price if bids else ticker.last_price
                        best_ask = asks[0].price if asks else ticker.last_price
                        t2 = TickerUpdate(
                            symbol=ticker.symbol,
                            last_price=ticker.last_price,
                            best_bid=best_bid,
                            best_ask=best_ask,
                            volume_24h=ticker.volume_24h,
                            timestamp=ticker.timestamp,
                        )
                        await broadcaster.broadcast_ticker(t2)
                    return on_binance_ticker

                async def on_binance_trade(t: PublicTrade):
                    await broadcaster.broadcast_trade(t)

                feed = BinanceTradeFeed(
                    binance_trade_ws_url(symbol),
                    symbol,
                    on_trade=on_binance_trade,
                    on_ticker=_make_binance_ticker_cb(engine),
                )
                binance_feeds.append(feed)
                feed.start()

        app.state.engines = engines
        app.state.broadcaster = broadcaster
        app.state.order_store = order_store
        app.state.metrics = metrics
        set_engines(engines)
        set_broadcaster(broadcaster)
        set_order_store(order_store)
        set_metrics(metrics)

        yield
        for gen in generators:
            gen.stop()
        for feed in binance_feeds:
            feed.stop()

    app = FastAPI(title="Exchange Simulator", lifespan=lifespan)
    app.state.simulation = simulation
    app.include_router(api_router)

    @app.get("/api/health")
    async def health():
        return JSONResponse({
            "status": "ok",
            "symbol": DEFAULT_SYMBOL,
            "symbols": list(getattr(app.state, "engines", {}).keys()) or TRADABLE_SYMBOLS,
        })

    @app.get("/api/metrics")
    async def api_metrics():
        m = getattr(app.state, "metrics", None)
        if m is not None:
            return JSONResponse(m.snapshot())
        return JSONResponse({
            "trades_executed": 0,
            "orders_submitted": 0,
            "current_spread": None,
            "simulation_speed": 1.0,
            "uptime_sec": 0,
            "orders_per_sec": 0,
        })

    @app.websocket(WS_FEED_PATH)
    async def ws_feed(websocket: WebSocket):
        await websocket.accept()
        await handle_feed_websocket(websocket, app.state.broadcaster)

    return app
