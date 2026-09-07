from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379

    rate_limit_amount: int = 5
    rate_limit_window_seconds: int = 60

    model_name: str = (
        "distilbert-base-uncased-finetuned-sst-2-english"
    )

    cache_ttl_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()