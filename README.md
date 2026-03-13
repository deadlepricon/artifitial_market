# Synthetic Cryptocurrency Exchange Simulator

A local, in-memory crypto exchange simulator for testing algorithmic trading systems. It exposes WebSocket market data and an order API so external strategies can connect and trade against synthetic, realistic-looking markets.

## Features

- **Synthetic market**: Random-walk prices, spread and liquidity variation, continuous bid/ask and trade events (BTC/USDT by default; multi-symbol ready).
- **Level 2 order book**: Limit and market orders, cancel/update, price-time priority.
- **Matching engine**: Matches client and synthetic orders, produces fills and book updates.
- **WebSocket feed**: Order book updates, trades, ticker in exchange-like message formats.
- **Order API**: Place, cancel, and check order status (REST; WebSocket optional).
- **Simulation controller**: Real-time or accelerated simulation speed for faster backtesting.
- **Metrics and logging**: Trade count, throughput, spread, speed, and system events.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for data flow, folder structure, and module responsibilities.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt
# From project root (recommended):
python run.py
# Or with module + PYTHONPATH:
PYTHONPATH=src:. python -m exchange_simulator.main
```

Then:

- **Market data WebSocket**: `ws://localhost:8765/ws/feed` (or port from config).
- **REST API**: `http://localhost:8765/docs` for Swagger; place/cancel at `/api/orders`, health at `/api/health`, metrics at `/api/metrics`.

## Project Layout

```
config/           # settings (symbols, ports, simulation speed)
src/exchange_simulator/
  symbols/        # symbol registry (BTC/USDT, etc.)
  schemas/        # orders, book, trades, market data (pydantic)
  order_book/     # in-memory L2 book
  matching_engine/# order matching and fills
  market_generator/# synthetic prices and liquidity
  exchange_api/   # REST (and optional WS) order API
  websocket_server/# market data WebSocket
  simulation_controller/  # time and speed control
  metrics/        # counters and gauges
  logging/        # structured events
docs/             # architecture and design
```

## Configuration

Edit `config/settings.py` to change symbols, WebSocket/API ports, and default simulation speed.

## License

MIT (or your choice).
