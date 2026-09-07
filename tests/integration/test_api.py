import hashlib
import itertools
import time

import pytest
import pytest_asyncio
import redis.asyncio as redis
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import app

_ip_counter = itertools.count(start=1)


async def _reset_redis_state() -> None:
    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )

    async for key in client.scan_iter("rate_limit:*"):
        await client.delete(key)

    async for key in client.scan_iter("sentiment:*"):
        await client.delete(key)

    await client.aclose()


@pytest_asyncio.fixture(scope="session")
async def app_with_lifespan():
    await _reset_redis_state()

    async with LifespanManager(app):
        yield app


@pytest_asyncio.fixture
async def client(app_with_lifespan):
    await _reset_redis_state()

    client_ip = f"10.0.0.{next(_ip_counter)}"

    transport = ASGITransport(
        app=app_with_lifespan,
        client=(client_ip, 12345),
    )

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as http_client:
        yield http_client


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data == {
        "status": "ok",
        "model_loaded": True,
    }


@pytest.mark.asyncio
async def test_predict_endpoint_schema(client):
    response = await client.post(
        "/predict",
        json={"text": "Integration test is fantastic!"},
    )

    assert response.status_code == 200

    data = response.json()

    assert set(data.keys()) == {"sentiment", "score", "cached"}
    assert isinstance(data["sentiment"], str)
    assert isinstance(data["score"], float)
    assert data["cached"] is False


@pytest.mark.asyncio
async def test_predict_cached_flag(client):
    text = "This exact text tests caching!"

    first = await client.post("/predict", json={"text": text})
    second = await client.post("/predict", json={"text": text})

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["sentiment"] == first.json()["sentiment"]
    assert second.json()["score"] == first.json()["score"]


@pytest.mark.asyncio
async def test_cached_prediction_latency(client):
    text = "Benchmark latency caching test"

    start = time.perf_counter()
    first = await client.post("/predict", json={"text": text})
    miss_elapsed = time.perf_counter() - start

    assert first.status_code == 200
    assert first.json()["cached"] is False

    start = time.perf_counter()
    second = await client.post("/predict", json={"text": text})
    hit_elapsed = time.perf_counter() - start

    assert second.status_code == 200
    assert second.json()["cached"] is True

    assert hit_elapsed < 0.005
    assert hit_elapsed * 5 < miss_elapsed


@pytest.mark.asyncio
async def test_cache_key_has_ttl(client):
    text = "TTL inspection test"

    response = await client.post("/predict", json={"text": text})

    assert response.status_code == 200

    expected_key = (
        "sentiment:"
        + hashlib.sha256(text.encode("utf-8")).hexdigest()
    )

    cache_service = app.state.cache_service

    ttl = await cache_service.redis.ttl(expected_key)

    assert ttl > 0
    assert ttl <= settings.cache_ttl_seconds


@pytest.mark.asyncio
async def test_validation_rejects_bad_input(client):
    empty = await client.post("/predict", json={"text": ""})

    missing = await client.post("/predict", json={})

    too_long = await client.post(
        "/predict",
        json={"text": "x" * 1001},
    )

    non_string = await client.post(
        "/predict",
        json={"text": 123},
    )

    assert empty.status_code == 422
    assert missing.status_code == 422
    assert too_long.status_code == 422
    assert non_string.status_code == 422


@pytest.mark.asyncio
async def test_rate_limit_returns_429_with_retry_after(client):
    responses = []

    for i in range(6):
        response = await client.post(
            "/predict",
            json={"text": f"Rate limit request number {i}"},
        )

        responses.append(response)

    status_codes = [response.status_code for response in responses]

    assert status_codes == [200, 200, 200, 200, 200, 429]

    blocked = responses[-1]

    retry_after = blocked.headers.get("retry-after")

    assert retry_after is not None

    assert float(retry_after) >= 1