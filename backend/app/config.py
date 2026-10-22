"""Application configuration loaded from environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://checkout:checkout@localhost:5432/checkout"
    observer_database_url: str = (
        "postgresql+psycopg://observer:observer@localhost:5432/checkout"
    )
    executor_database_url: str = (
        "postgresql+psycopg://remediator:remediator@localhost:5432/checkout"
    )

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:8080,http://localhost:3000"

    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = "nvidia/nemotron-3-nano-30b-a3b"
    inference_mode: str = "fixture"  # fixture | nemotron
    inference_timeout_seconds: float = 60.0
    inference_max_retries: int = 2
    inference_temperature: float = 0.2

    zetaris_enabled: bool = False
    zetaris_url: str = ""
    zetaris_email: str = ""
    zetaris_password: str = ""
    zetaris_target_role: str = ""

    hmem_persist_dir: str = "./data/hmem"
    hmem_enabled: bool = True

    negotiation_max_rounds: int = 4
    negotiation_timeout_seconds: float = 120.0

    authority_ttl_seconds: int = 120
    authority_max_executions: int = 1
    simulated_human_approval_latency_ms: int = 30_000

    checkout_timeout_ms: int = 3000
    traffic_rps: float = 2.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
