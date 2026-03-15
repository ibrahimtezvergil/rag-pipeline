import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        extra="ignore",
    )

    database_url: str
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rag_chunks"
    redis_url: str = "redis://localhost:6379/0"
    gemini_api_key: str
    embed_model: str = "gemini-embedding-2"
    embed_dimension: int = 768
    formatter_model: str = "gemini-2.5-flash"
    formatter_input_char_limit: int = 12000
    formatter_output_char_limit: int = 2000
    api_keys: str
    cohere_api_key: str = ""

    @property
    def api_keys_set(self) -> set[str]:
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
