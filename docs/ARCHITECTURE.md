# Synthetic Cryptocurrency Exchange Simulator — Architecture

## Overview

Event-driven, async simulator that mimics a crypto exchange for testing algorithmic trading systems. External clients connect via WebSockets for market data and via REST/WebSocket for orders.

## High-Level Data Flow

```
┌─────────────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌────────────────────┐
│  Market Generator   │────▶│  Order Book  │────▶│ Matching Engine │────▶│ WebSocket Broadcaster│
│  (synthetic L2/trades)│     │  (per symbol) │     │ (match & fill)   │     │ (market data feed)   │
└─────────────────────┘     └──────┬───────┘     └────────┬────────┘     └────────────────────┘
                                   │                      │
                                   │  client orders        │  fill / book events
                                   ▼                      ▼
                            ┌──────────────┐     ┌────────────────────┐
                            │  Order API   │────▶│ Simulation Controller│
                            │ (place/cancel)│     │ (time speed, start/stop)│
                            └──────────────┘     └────────────────────┘
```

- **Market Generator**: Produces synthetic bid/ask updates and trade events (random walk, spread, liquidity). Feeds into the order book as simulated market activity.
- **Order Book**: Per-symbol Level 2 book (bids/asks, quantities). Supports limit/market orders, cancel, update; price-time priority.
- **Matching Engine**: Consumes orders (from API and from generator), matches against the book, produces fills and book updates.
- **WebSocket Broadcaster**: Subscribes to book/trade/ticker events and streams them to connected clients.
- **Order API**: REST/WebSocket endpoints for place, cancel, order status. Orders go to the matching engine.
- **Simulation Controller**: Controls simulation speed (real-time vs accelerated) and start/stop; used by generator and metrics.

## Folder Structure

```
artifitial_market/
├── README.md
├── requirements.txt
├── pyproject.toml / setup.py          # optional
├── config/
│   └── settings.py                    # configurable symbol list, ports, speeds
├── src/
│   └── exchange_simulator/
│       ├── __init__.py
│       ├── main.py                    # entry point: start API, WS, generator, controller
│       ├── symbols/
│       │   ├── __init__.py
│       │   └── registry.py            # symbol definitions (BTC/USDT, etc.)
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── orders.py              # Order, OrderSide, OrderType, etc.
│       │   ├── book.py                # Level2Update, PriceLevel
│       │   ├── trades.py              # Trade, Fill
│       │   └── market_data.py         # Ticker, subscription messages
│       ├── order_book/
│       │   ├── __init__.py
│       │   └── book.py                # In-memory L2 book, price-time priority
│       ├── matching_engine/
│       │   ├── __init__.py
│       │   └── engine.py              # match orders, emit fills, update book
│       ├── market_generator/
│       │   ├── __init__.py
│       │   └── generator.py           # synthetic prices, spread, liquidity, trades
│       ├── exchange_api/
│       │   ├── __init__.py
│       │   ├── routes.py              # REST: place order, cancel, order status
│       │   └── websocket_orders.py    # optional: order WS
│       ├── websocket_server/
│       │   ├── __init__.py
│       │   └── feed.py                # WS market data: book, trades, ticker
│       ├── simulation_controller/
│       │   ├── __init__.py
│       │   └── controller.py         # speed (1x, Nx), start/stop, time source
│       ├── metrics/
│       │   ├── __init__.py
│       │   └── collector.py          # trades count, throughput, spread, speed
│       └── logging/
│           ├── __init__.py
│           └── events.py              # structured logging, system events
├── tests/                             # optional placeholder
│   └── __init__.py
└── docs/
    └── ARCHITECTURE.md                # this file
```

## Module Responsibilities

| Module | Purpose |
|--------|--------|
| **symbols** | Symbol registry (BTC/USDT first); base quote, tick size, lot size for future multi-symbol support. |
| **schemas** | Pydantic models for orders, book levels, trades, fills, market data messages (exchange-like formats). |
| **order_book** | Single-symbol L2 book: add/cancel/update limit orders, consume market orders; price-time priority; emit level updates. |
| **matching_engine** | Accept orders (client + synthetic), match against book, generate fills, update book, emit fill and book events. |
| **market_generator** | Async task: random walk mid, spread/liquidity variation, produce bid/ask level and trade events; respects simulation speed. |
| **exchange_api** | REST (and optional WS) for place/cancel/status; forwards orders to matching engine; returns acks/errors. |
| **websocket_server** | WS endpoint; subscription to book/trades/ticker per symbol; broadcast events from matching engine + generator. |
| **simulation_controller** | Single source of simulation time and speed multiplier; start/stop/pause; used by generator and metrics. |
| **metrics** | Counters and gauges: trade count, order throughput, spread, simulation speed; optional periodic log/export. |
| **logging** | Structured system events (order accepted, filled, cancelled, errors). |

## Concurrency Model

- **asyncio** throughout. One event loop.
- **Queues / callbacks**: Matching engine can expose an async queue or callback for fills/book updates; market generator pushes into the same pipeline that updates the book and is then broadcast.
- **Simulation time**: Controller provides `get_simulation_time()` and speed multiplier; generator and metrics use it so that “accelerated” mode runs N× faster for backtesting.

## Extension Points

- **Multiple symbols**: Symbol registry lists symbols; one order book + one generator (or one generator per symbol) per symbol; API and WS include `symbol` in all messages.
- **More order types**: Extend schemas and matching engine (e.g. stop-limit, iceberg) without changing the core flow.
- **Persistence**: Optional persistence layer can subscribe to fill/book events and write to DB or files for replay.

## Technology Choices

- **Python 3.10+**
- **asyncio** for concurrency
- **FastAPI** for HTTP + WebSocket (single server for API and WS feed)
- **pydantic** for request/response and internal message schemas
- **numpy** (optional) for random walk and noise in market generator
