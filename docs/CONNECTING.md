# Connecting to the Exchange Simulator (e.g. from Rust HFT)

Base URL: **http://localhost:8765**  
WebSocket URL: **ws://localhost:8765/ws/feed**  
Symbol: **BTC/USDT** (only symbol supported for now)

**Market data:**
- **Trades** — Live from Binance; you also get trades when your orders fill on the simulator.
- **Ticker** — From Binance (`last_price`, volume); `best_bid` / `best_ask` from the simulator’s order book.
- **Order book** — Synthetic (simulator-generated); book deltas keep your in-memory book in sync.

---

## HFT market-making strategy compliance

This simulator satisfies the “Artificial Market” requirements for the HFT market-making strategy:

| Requirement | Status |
|-------------|--------|
| WebSocket at `ws://localhost:8765/ws/feed` | ✅ |
| Book deltas: `channel: "book"`, `type: "delta"`, `data: { symbol, bids, asks, sequence }` | ✅ |
| Trades: `channel: "trades"`, `type: "trade"`, `data: { symbol, trade_id, price, quantity, side, timestamp }` | ✅ |
| `POST /api/orders` with `symbol`, `side`, `order_type`, `quantity`, `price`, `client_order_id`; response has `order_id` | ✅ |
| `POST /api/orders/cancel` with `symbol`, `order_id` | ✅ |
| `GET /api/orders/{order_id}` | ✅ |
| Symbol format `BTC/USDT` | ✅ |
| **Optional:** Real matching + book updates on fill | ✅ (limit orders go in book or match; book delta sent on change) |
| **Optional:** Fill events for client orders | ✅ (`channel: "orders"`, `type: "fill"` — see below) |

---

## 1. REST API (orders)

All order endpoints use **JSON** and **Content-Type: application/json**.

### Place order

- **POST** `http://localhost:8765/api/orders`

**Request body:**

```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "limit",
  "quantity": 0.001,
  "price": 50000.0,
  "client_order_id": "optional-your-id"
}
```

- `side`: `"buy"` or `"sell"`
- `order_type`: `"limit"` or `"market"`
- `quantity`: number > 0
- `price`: required for `"limit"`, omit or null for `"market"`
- `client_order_id`: optional string

**Response (200):**

```json
{
  "order_id": "ord_BTCUSDT_42",
  "client_order_id": "optional-your-id",
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "limit",
  "quantity": 0.001,
  "price": 50000.0,
  "status": "open"
}
```

`status` is one of: `pending`, `open`, `partially_filled`, `filled`, `cancelled`, `rejected`.

### Cancel order

- **POST** `http://localhost:8765/api/orders/cancel`

**Request body:**

```json
{
  "symbol": "BTC/USDT",
  "order_id": "ord_BTCUSDT_42"
}
```

**Response (200):**

```json
{
  "order_id": "ord_BTCUSDT_42",
  "status": "cancelled"
}
```

404 if order not found or already filled/cancelled.

### Get order status

- **GET** `http://localhost:8765/api/orders/{order_id}`

Example: `GET http://localhost:8765/api/orders/ord_BTCUSDT_42`

**Response (200):**

```json
{
  "order_id": "ord_BTCUSDT_42",
  "client_order_id": null,
  "symbol": "BTC/USDT",
  "side": "buy",
  "order_type": "limit",
  "quantity": 0.001,
  "filled_quantity": 0.0,
  "price": 50000.0,
  "status": "open",
  "created_at": null,
  "updated_at": null
}
```

---

## 2. WebSocket (market data)

- **URL:** `ws://localhost:8765/ws/feed`
- **Protocol:** plain WebSocket; all messages are **UTF-8 JSON text frames**.

### Connecting

1. Open WebSocket to `ws://localhost:8765/ws/feed`.
2. Optionally send a subscribe message (server still sends everything):

```json
{"action": "subscribe", "channels": ["book", "trades", "ticker"], "symbols": ["BTC/USDT"]}
```

Server may reply: `{"event": "subscribed", "message": "OK"}`.

### Messages you receive (server → client)

Every message is a JSON object with `channel`, `type`, and `data`.

**Order book update (incremental, synthetic):**

```json
{
  "channel": "book",
  "type": "delta",
  "data": {
    "symbol": "BTC/USDT",
    "bids": [{"price": 49999.5, "quantity": 0.01}, {"price": 49999.0, "quantity": 0.02}],
    "asks": [{"price": 50000.5, "quantity": 0.008}, {"price": 50001.0, "quantity": 0.015}],
    "sequence": 123
  }
}
```

- `bids` / `asks`: arrays of `{"price": number, "quantity": number}` (best first).
- `sequence`: increments on each book change.

**Trade (live from Binance or from your fills):**

```json
{
  "channel": "trades",
  "type": "trade",
  "data": {
    "symbol": "BTC/USDT",
    "trade_id": "123456789",
    "price": 97234.56,
    "quantity": 0.0015,
    "side": "sell",
    "timestamp": "1699900123456"
  }
}
```

- **From Binance:** `trade_id` is numeric string; `timestamp` is **milliseconds since epoch** (string).
- **From simulator (your fill):** `trade_id` is like `"trd_42"`; `timestamp` may be `null`.
- `side`: `"buy"` or `"sell"` (aggressor side).

**Ticker (from Binance last trade):**

```json
{
  "channel": "ticker",
  "type": "ticker",
  "data": {
    "symbol": "BTC/USDT",
    "last_price": 97234.56,
    "best_bid": 97234.56,
    "best_ask": 97234.56,
    "volume_24h": 125.5,
    "timestamp": "1699900123456"
  }
}
```

- `last_price`: last trade price from Binance.
- `best_bid` / `best_ask`: from the simulator’s order book (top of book).
- `volume_24h`: cumulative volume since simulator started.
- `timestamp`: last trade time in **milliseconds** (string).

**Fill (optional — when your order is filled):**

```json
{
  "channel": "orders",
  "type": "fill",
  "data": {
    "order_id": "ord_BTCUSDT_42",
    "client_order_id": null,
    "symbol": "BTC/USDT",
    "side": "buy",
    "price": 97234.5,
    "quantity": 0.001,
    "fill_id": "trd_123",
    "is_maker": false,
    "timestamp": null
  }
}
```

- One message per fill (partial or full). Use for real fill feedback when not in paper mode.

---

## 3. Other endpoints

- **GET** `http://localhost:8765/api/health`  
  Response: `{"status": "ok", "symbol": "BTC/USDT"}`

- **GET** `http://localhost:8765/api/metrics`  
  Response: `{"trades_executed": 42, "orders_submitted": 100, "current_spread": 0.5, "simulation_speed": 1.0, "uptime_sec": 3600, "orders_per_sec": 0.5, ...}`

---

## 4. Rust checklist

- **REST:** any HTTP client (e.g. `reqwest`) to `http://localhost:8765/api/*` with JSON bodies.
- **WebSocket:** use a WS client (e.g. `tokio-tungstenite`) to `ws://localhost:8765/ws/feed`; parse each text frame as JSON and switch on `channel` + `type` to handle `book` (delta), `trades` (trade), `ticker` (ticker), `orders` (fill).
- **Symbol:** always `"BTC/USDT"` for the simulator.
- **Trade IDs:** Binance trades use numeric strings; simulator-generated fills use `"trd_<n>"`. Use `trade_id` to dedupe if needed.
- **Timestamps:** Trade/ticker `timestamp` from Binance is **milliseconds since epoch** (string). Simulator fills may have `null`.
- **Errors:** REST returns 4xx/5xx with a body like `{"detail": "..."}`.
