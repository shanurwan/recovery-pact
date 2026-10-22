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
    # Only the naive_single ablation arm uses this: it models an agent holding
    # unrestricted credentials. The product path never touches it.
    unrestricted_database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/checkout"
    )
    continuity_database_url: str = (
        "postgresql+psycopg://observer:observer@localhost:5432/continuity"
    )

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:8080,http://localhost:3000"

    # --- Inference: NVIDIA Nemotron (OpenAI-compatible NIM API) ---
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nemotron_thinking: bool = False
    # nemotron: live calls (recorded). replay: recorded Nemotron responses.
    inference_mode: str = "nemotron"
    inference_timeout_seconds: float = 90.0
    inference_max_retries: int = 2
    inference_temperature: float = 0.2
    inference_max_tokens: int = 1500
    recordings_dir: str = "./recordings"  # shipped recordings, read by replay
    record_dir: str = "./data/recordings"  # where live runs write new recordings
    embedding_model: str = "nvidia/nemotron-3-embed-1b"

    # --- Zetaris: federated business context ---
    zetaris_enabled: bool = False
    zetaris_url: str = ""
    zetaris_email: str = ""
    zetaris_password: str = ""
    zetaris_org_id: str = "1"
    zetaris_timeout_seconds: float = 30.0
    # Names the setup script registers. Overridable for another tenant.
    zetaris_continuity_ds: str = "continuity"
    zetaris_shop_ds: str = "shop"
    zetaris_calendar_db: str = "RP_CHANGE_MGMT"
    change_calendar_csv: str = "./seed/business/change_calendar.csv"

    # --- Meterless H-MEM ---
    hmem_persist_dir: str = "./data/hmem"
    hmem_enabled: bool = True
    hmem_recall_threshold: float = 0.30
    hmem_use_nvidia_embedder: bool = True

    # --- Negotiation ---
    negotiation_max_rounds: int = 3
    negotiation_timeout_seconds: float = 240.0

    # --- Authority ---
    authority_ttl_seconds: int = 120
    authority_max_executions: int = 1

    # --- Demo ---
    checkout_timeout_ms: int = 3000
    traffic_rps: float = 4.0
    runs_dir: str = "./data/runs"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
