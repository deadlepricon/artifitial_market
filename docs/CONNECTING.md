# Connecting to the Exchange Simulator (e.g. from Rust HFT)

Base URL: **http://localhost:8765**  
WebSocket URL: **ws://localhost:8765/ws/feed**  
Symbol: **BTC/USDT** (only symbol supported for now)

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

**Order book update (incremental):**

```json
{
  "channel": "book",
  "type": "delta",
  "data": {
    "symbol": "BTC/USDT",
    "bids": [{"price": 49999.5, "quantity": 0.01}, ...],
    "asks": [{"price": 50000.5, "quantity": 0.008}, ...],
    "sequence": 123
  }
}
```

**Trade:**

```json
{
  "channel": "trades",
  "type": "trade",
  "data": {
    "symbol": "BTC/USDT",
    "trade_id": "trd_1",
    "price": 50000.25,
    "quantity": 0.001,
    "side": "buy",
    "timestamp": null
  }
}
```

**Ticker:**

```json
{
  "channel": "ticker",
  "type": "ticker",
  "data": {
    "symbol": "BTC/USDT",
    "last_price": 50000.25,
    "best_bid": 50000.0,
    "best_ask": 50000.5,
    "volume_24h": 0.0,
    "timestamp": null
  }
}
```

---

## 3. Other endpoints

- **GET** `http://localhost:8765/api/health`  
  Response: `{"status": "ok", "symbol": "BTC/USDT"}`

- **GET** `http://localhost:8765/api/metrics`  
  Response: `{"trades_executed": 42, "orders_submitted": 100, "current_spread": 0.5, "simulation_speed": 1.0, "uptime_sec": 3600, "orders_per_sec": 0.5, ...}`

---

## 4. Rust checklist

- **REST:** any HTTP client (e.g. `reqwest`) to `http://localhost:8765/api/*` with JSON bodies.
- **WebSocket:** use a WS client (e.g. `tokio-tungstenite`) to `ws://localhost:8765/ws/feed`; parse each text frame as JSON and switch on `channel` + `type` to handle `book` (delta), `trades` (trade), `ticker` (ticker).
- **Symbol:** always `"BTC/USDT"` for the simulator.
- **Errors:** REST returns 4xx/5xx with a body like `{"detail": "..."}`.
