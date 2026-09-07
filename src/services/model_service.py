import asyncio

from transformers import pipeline

from src.config import settings


class SentimentModelService:
    def __init__(self):
        self.classifier = None

    async def load_model(self):
        if self.classifier is not None:
            return

        loop = asyncio.get_running_loop()

        self.classifier = await loop.run_in_executor(
            None,
            lambda: pipeline(
                "sentiment-analysis",
                model=settings.model_name,
            ),
        )

    async def predict(self, text: str) -> dict:
        if self.classifier is None:
            await self.load_model()

        loop = asyncio.get_running_loop()

        result = await loop.run_in_executor(
            None,
            lambda: self.classifier(text),
        )

        prediction = result[0]

        return {
            "sentiment": prediction["label"],
            "score": float(prediction["score"]),
        }