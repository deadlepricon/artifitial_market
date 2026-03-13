# main.py
"""
Entry point for the synthetic crypto exchange simulator.
Wires: market generator -> order book -> matching engine -> WebSocket broadcaster.
Starts FastAPI (REST + WebSocket) and the simulation loop.
Run from project root: python run.py
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
_src = _root / "src"
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from config.settings import (
    API_HOST,
    API_PORT,
    BOOK_DEPTH_LEVELS,
    DEFAULT_INITIAL_MID_PRICE,
    DEFAULT_SPEED_MULTIPLIER,
    DEFAULT_SYMBOL,
    PRICE_VOLATILITY,
    SPREAD_FRACTION_MAX,
    SPREAD_FRACTION_MIN,
    WS_FEED_PATH,
)
from exchange_simulator.exchange_api.routes import router, set_engine, set_metrics, set_order_store
from exchange_simulator.logging.events import configure_logging, log_error, log_order_filled, log_system
from exchange_simulator.matching_engine.engine import MatchingEngine
from exchange_simulator.metrics.collector import MetricsCollector
from exchange_simulator.schemas.book import OrderBookDelta
from exchange_simulator.schemas.market_data import TickerUpdate
from exchange_simulator.schemas.orders import OrderStatus
from exchange_simulator.schemas.trades import FillEvent, PublicTrade
from exchange_simulator.simulation_controller.controller import SimulationController
from exchange_simulator.websocket_server.feed import FeedBroadcaster, handle_feed_websocket
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware


def run_app() -> None:
    configure_logging()

    order_store: dict = {}
    broadcaster = FeedBroadcaster()
    sim_controller = SimulationController(initial_speed=DEFAULT_SPEED_MULTIPLIER)
    metrics = MetricsCollector(on_snapshot=lambda s: log_system("metrics", **s))

    engine = MatchingEngine(symbol=DEFAULT_SYMBOL, book=None)

    def on_fill(f: FillEvent) -> None:
        metrics.record_trade()
        log_order_filled(f.order_id, f.symbol, f.price, f.quantity, f.fill_id, f.is_maker)
        if f.order_id in order_store:
            rec = order_store[f.order_id]
            rec["filled_quantity"] = rec.get("filled_quantity", 0) + f.quantity
            if rec["filled_quantity"] >= rec["quantity"]:
                rec["status"] = OrderStatus.FILLED

    def on_trade(t: PublicTrade) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcaster.broadcast_trade(t))
        except RuntimeError:
            pass

    def on_book_update() -> None:
        try:
            loop = asyncio.get_running_loop()
            bids, asks, seq = engine.get_book_snapshot(depth=BOOK_DEPTH_LEVELS)
            delta = OrderBookDelta(symbol=DEFAULT_SYMBOL, bids=bids, asks=asks, sequence=seq)
            loop.create_task(broadcaster.broadcast_book_delta(delta))
            spread = engine.book.spread()
            metrics.update_spread(spread)
            if spread is not None and bids and asks:
                ticker = TickerUpdate(
                    symbol=DEFAULT_SYMBOL,
                    last_price=(bids[0].price + asks[0].price) / 2,
                    best_bid=bids[0].price,
                    best_ask=asks[0].price,
                    volume_24h=0.0,
                )
                loop.create_task(broadcaster.broadcast_ticker(ticker))
        except RuntimeError:
            pass

    engine = MatchingEngine(
        symbol=DEFAULT_SYMBOL,
        book=engine.book,
        on_fill=on_fill,
        on_trade=on_trade,
        on_book_update=on_book_update,
    )
    metrics.update_speed(sim_controller.get_speed_multiplier())

    set_engine(engine)
    set_order_store(order_store)
    set_metrics(metrics)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from exchange_simulator.market_generator.generator import SyntheticMarketGenerator
        from exchange_simulator.symbols.registry import ensure_default_symbols

        ensure_default_symbols()
        gen = SyntheticMarketGenerator(
            symbol=DEFAULT_SYMBOL,
            matching_engine=engine,
            initial_mid=DEFAULT_INITIAL_MID_PRICE,
            volatility=PRICE_VOLATILITY,
            spread_fraction_min=SPREAD_FRACTION_MIN,
            spread_fraction_max=SPREAD_FRACTION_MAX,
            get_speed_multiplier=sim_controller.get_speed_multiplier,
        )
        gen.start()
        app.state.generator = gen
        app.state.metrics = metrics
        app.state.sim_controller = sim_controller
        log_system("Simulator started", symbol=DEFAULT_SYMBOL, port=API_PORT)
        yield
        if hasattr(app.state, "generator"):
            app.state.generator.stop()
        log_system("Simulator stopped")

    app = FastAPI(
        title="Synthetic Crypto Exchange Simulator",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)

    @app.websocket(WS_FEED_PATH)
    async def ws_feed(websocket: WebSocket) -> None:
        await handle_feed_websocket(websocket, broadcaster)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "symbol": DEFAULT_SYMBOL}

    @app.get("/api/metrics")
    def get_metrics() -> dict:
        return metrics.snapshot()

    import uvicorn
    try:
        uvicorn.run(app, host=API_HOST, port=API_PORT)
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            log_error(
                f"Port {API_PORT} is already in use. Stop the other process or change API_PORT in config/settings.py"
            )
        raise


if __name__ == "__main__":
    run_app()
