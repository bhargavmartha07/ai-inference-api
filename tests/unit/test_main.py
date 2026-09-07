import json

import pytest
from starlette.requests import Request

from src.main import global_exception_handler


@pytest.mark.asyncio
async def test_global_exception_handler_returns_generic_500():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/boom",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )

    response = await global_exception_handler(
        request,
        ValueError("secret-internal-traceback-detail"),
    )

    assert response.status_code == 500

    body = json.loads(response.body)

    assert body == {"error": "Internal server error"}
    assert "secret-internal-traceback-detail" not in json.dumps(body)