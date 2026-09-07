# AI Inference API

A production-ready RESTful API for AI model inference (sentiment analysis) built with **FastAPI**, **Redis** (distributed caching + rate limiting), and **HuggingFace Transformers**. It demonstrates the core infrastructure patterns required to deploy ML models as scalable services: asynchronous serving, thread-pooled CPU-bound inference, TTL-based caching, and atomic window-based rate limiting.

## Features

- **Async inference endpoint** — FastAPI (ASGI) with CPU-bound model calls offloaded to a thread pool via `run_in_executor`, keeping the event loop free.
- **Distributed caching with Redis** — identical requests are hashed (`sha256`) into cache keys. Cache hits bypass the model entirely and respond in <5 ms.
- **TTL-backed cache** — every cached result expires after `CACHE_TTL_SECONDS` to prevent memory exhaustion.
- **Atomic rate limiting** — per-client-IP fixed-window limiting via a Redis Lua script (`ZREMRANGEBYSCORE` / `ZADD` / `ZCARD` / `EXPIRE`), so it is safe under concurrency and across multiple API replicas.
- **`Retry-After` header** — blocked clients receive a standard 429 response with the seconds remaining in the window.
- **Containerized** — multi-stage Dockerfile + `docker-compose` orchestrating the API, Redis, and a readiness healthcheck.
- **Fully env-driven** — hosts, thresholds, and model name configured through environment variables.
- **Test suite** — unit tests (mocking Redis) and integration tests (real model + Redis) run via pytest.

## System Architecture

```
                ┌───────────────────────────────┐
                │        Client / HTTP          │
                └──────────────┬────────────────┘
                               │ POST /predict (JSON text)
                               ▼
                    FastAPI Router & Validation
                               │
                               ▼
        ┌─────────────────────────────────────────────────┐
        │            Rate Limiter Service (Redis)          │
        │      per-IP fixed-window via atomic Lua script   │
        └───────────────────────┬─────────────────────────┘
                    limit exceeded? ──────► 429 + Retry-After
                               │ allowed
                               ▼
        ┌─────────────────────────────────────────────────┐
        │              Cache Service (Redis)               │
        │      key = sentiment:sha256(text)                │
        └───────────────────────┬─────────────────────────┘
                    cache hit? ──────────► return cached prediction
                               │ miss
                               ▼
        ┌─────────────────────────────────────────────────┐
        │      Model Service (HuggingFace, thread pool)    │
        └───────────────────────┬─────────────────────────┘
                               │
                               ▼
                   SET with TTL, then return 200
```

## API Endpoints

### `GET /health`

Readiness probe for orchestrators / load balancers.

```json
// 200 OK
{ "status": "ok", "model_loaded": true }

// 503 Service Unavailable (model not loaded yet)
{ "status": "unavailable", "model_loaded": false }
```

### `POST /predict`

Accepts a text string (`1–1000` characters) and returns the sentiment prediction.

```json
// Request
{ "text": "Great product!" }

// Response (200 OK)
{ "sentiment": "POSITIVE", "score": 0.9998, "cached": false }
```

- `cached: true` indicates the response was served from Redis without re-running the model.
- Invalid payloads (empty string, missing field, non-string, >1000 chars) return `422`.
- Requests exceeding the per-IP limit return `429` with a `Retry-After` header.
- Unexpected server errors return a generic `500` — stack traces are logged server-side, never leaked to clients.

## Configuration

All settings are read from environment variables (see `.env.example`). Pydantic parses and validates them on startup.

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_HOST` | `localhost` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `RATE_LIMIT_AMOUNT` | `5` | Max requests per client IP per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window length |
| `MODEL_NAME` | `distilbert-base-uncased-finetuned-sst-2-english` | HuggingFace sentiment model |
| `CACHE_TTL_SECONDS` | `300` | Cache TTL for predictions |

## Getting Started

### Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  |  source .venv/bin/activate (macOS/Linux)
pip install -r requirements.txt
cp .env.example .env           # optional; defaults already match localhost:6379
uvicorn src.main:app --reload --port 8000
```

Your Redis instance must be reachable at `REDIS_HOST:REDIS_PORT`. Tests expect it on `localhost:6379`.

### Docker (recommended)

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

- The API waits for Redis (`depends_on: service_healthy`) before accepting traffic.
- The model is downloaded on first start into the named `hf-cache` volume and reused on subsequent restarts.
- Build uses CPU-only PyTorch (via `--extra-index-url https://download.pytorch.org/whl/cpu`), keeping the image ~1.7 GB instead of multi-GB CUDA builds.

## Testing

```bash
python -m pytest tests/          # requires Redis running and the model cache/download
# or, inside the running stack:
docker compose exec api pytest tests/
```

- **Unit tests** (`tests/unit/`) — mock Redis to verify cache key derivation, TTL usage, rate-limiter allow/block, and the generic-500 error handler.
- **Integration tests** (`tests/integration/`) — boot the app with the real model + Redis via ASGI, verifying the `/predict` schema, cache hits, cache-hit latency (≥80% faster), key TTLs, validation (422), and the `429` + `Retry-After` contract.
- `tests/integration/test_rate_limit_concurrency.py` is a manual script demonstrating 10 concurrent requests → 5 allowed + 5 blocked against a running server.

## Project Structure

```
├── src/
│   ├── main.py                    # FastAPI app, lifespan, global 500 handler, /health
│   ├── config.py                  # pydantic-settings (env parsing)
│   ├── api/
│   │   └── endpoints.py           # /predict endpoint, request/response schemas
│   └── services/
│       ├── model_service.py       # HuggingFace pipeline, thread-pooled inference
│       ├── cache_service.py       # sha256 keys, JSON (de)serialization, TTL
│       └── rate_limiter_service.py# atomic Redis Lua fixed-window limiter
├── tests/
│   ├── unit/                      # mocked Redis unit tests
│   └── integration/               # ASGI integration tests (real model + Redis)
├── .env.example
├── requirements.txt
├── Dockerfile                     # multi-stage build
└── docker-compose.yml             # api + redis orchestration
```