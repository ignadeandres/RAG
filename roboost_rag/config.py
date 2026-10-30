"""Configuration from environment variables (and an optional .env file)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://roboost:roboost@localhost:5432/roboost"

    # Embeddings: local bge-m3 in Ollama by default; OpenAI optional. The schema is vector(1024).
    embedding_provider: Literal["ollama", "openai"] = "ollama"
    embedding_model: str = "bge-m3"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 32
    openai_api_key: SecretStr | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    cohere_api_key: SecretStr | None = None
    rerank_model: str = "rerank-v3.5"
    rerank_timeout_seconds: float = 5.0
    rerank_threshold: float = 0.04  # calibrated with `eval -v`

    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:9b"
    llm_temperature: float = 0.1

    docs_dir: str = "docs"
    reindex_interval_seconds: int = 300
    chunk_size: int = Field(3200, description="Max characters per chunk; overlap is 10%.")

    candidates_per_retriever: int = 20
    fusion_top: int = 10
    final_top_k: int = 4
    rrf_k: int = 60
    weight_vector: float = 1.0
    weight_bm25: float = 1.0

    app_users: str = Field("", description="user:bcrypt_hash:role, comma separated")

    @model_validator(mode="after")
    def _openai_needs_key(self):
        if self.embedding_provider == "openai" and not (
            self.openai_api_key and self.openai_api_key.get_secret_value()
        ):
            raise ValueError("EMBEDDING_PROVIDER=openai requiere la variable OPENAI_API_KEY")
        return self


def load_settings(**overrides) -> Settings:
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        missing = [
            str(err["loc"][0]).upper() for err in exc.errors() if err["type"] == "missing"
        ]
        if missing:
            raise ConfigError(
                f"Faltan variables de entorno obligatorias: {', '.join(missing)}"
            ) from None
        messages = "; ".join(str(err["msg"]).removeprefix("Value error, ") for err in exc.errors())
        raise ConfigError(f"Configuración inválida: {messages}") from None
