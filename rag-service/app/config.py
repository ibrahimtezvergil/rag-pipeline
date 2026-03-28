import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        extra="ignore",
    )

    database_url: str
    database_direct_url: str = ""
    database_use_pgbouncer: bool = False
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rag_chunks"
    redis_url: str = "redis://localhost:6379/0"
    gemini_api_key: str
    embed_model: str = "gemini-embedding-2-preview"
    embed_dimension: int = 768
    formatter_model: str = "gemini-2.5-flash"
    formatter_input_char_limit: int = 12000
    formatter_output_char_limit: int = 2000
    api_keys: str
    cohere_api_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"
    query_cache_ttl_seconds: int = 3600
    rate_limit_query_per_minute: int = 60
    rate_limit_chat_per_minute: int = 60
    rate_limit_ingest_per_minute: int = 20
    rate_limit_ingest_batch_per_minute: int = 10
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_timeout_seconds: int = 30
    query_expansion_use_llm: bool = False
    query_expansion_max_terms: int = 5
    semantic_dedup_similarity_threshold: float = 0.97
    audio_metadata_enabled: bool = True
    audio_diarization_enabled: bool = False
    ingest_callback_secret: str = "development-callback-secret"
    pgbouncer_default_pool_size: int = 20
    pgbouncer_max_client_conn: int = 50
    pgbouncer_reserve_pool_size: int = 5

    @property
    def api_keys_set(self) -> set[str]:
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
