from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class PredictRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class PredictResponse(BaseModel):
    sentiment: str
    score: float
    cached: bool


@router.post("/predict", response_model=PredictResponse)
async def predict(request: Request, body: PredictRequest):
    rate_limiter = request.app.state.rate_limiter_service
    cache_service = request.app.state.cache_service
    model_service = request.app.state.model_service

    client_ip = request.client.host

    allowed, retry_after = await rate_limiter.check_limit(client_ip)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    cached_result = await cache_service.get(body.text)

    if cached_result is not None:
        return {
            "sentiment": cached_result["sentiment"],
            "score": float(cached_result["score"]),
            "cached": True,
        }

    result = await model_service.predict(body.text)

    await cache_service.set(body.text, result)

    return {
        "sentiment": result["sentiment"],
        "score": result["score"],
        "cached": False,
    }