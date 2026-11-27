from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/ai_customer_expert"
    ollama_base_url: str = "http://host.docker.internal:11434"
    secret_key: str = "dev-secret-key-change-in-production-32chars"
    storage_dir: str = "/app/storage"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()