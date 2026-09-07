import asyncio

import httpx


API_URL = "http://localhost:8000"


async def make_request(client: httpx.AsyncClient):
    return await client.post(
        "/predict",
        json={"text": "Concurrency test request"},
    )


async def main():
    async with httpx.AsyncClient(
        base_url=API_URL,
        timeout=120,
    ) as client:

        responses = await asyncio.gather(
            *(make_request(client) for _ in range(10))
        )

    status_codes = [response.status_code for response in responses]

    allowed = status_codes.count(200)
    blocked = status_codes.count(429)

    print(f"Status codes: {status_codes}")
    print(f"Allowed: {allowed}")
    print(f"Blocked: {blocked}")

    assert allowed == 5
    assert blocked == 5


if __name__ == "__main__":
    asyncio.run(main())