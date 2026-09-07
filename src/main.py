import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.endpoints import router
from src.services.cache_service import CacheService
from src.services.model_service import SentimentModelService
from src.services.rate_limiter_service import RateLimiterService

logger = logging.getLogger("uvicorn.error")

model_service = SentimentModelService()
cache_service = CacheService()
rate_limiter_service = RateLimiterService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading sentiment model...")

    await model_service.load_model()

    app.state.model_service = model_service
    app.state.cache_service = cache_service
    app.state.rate_limiter_service = rate_limiter_service

    logger.info("Sentiment model loaded successfully.")

    yield

    logger.info("Application shutting down. Closing Redis connections...")

    await cache_service.close()
    await rate_limiter_service.close()


app = FastAPI(
    title="AI Inference API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )

    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


app.include_router(router)


@app.get("/health")
async def health():
    if model_service.classifier is not None:
        return {
            "status": "ok",
            "model_loaded": True,
        }

    return JSONResponse(
        status_code=503,
        content={
            "status": "unavailable",
            "model_loaded": False,
        },
    )