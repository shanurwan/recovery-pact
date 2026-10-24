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

    # --- AI provider ---
    # meterless (primary): every model call goes through Meterless Runtime (Nightshift),
    # which serves the Nemotron models configured in its lanes; the NVIDIA key lives
    # in Nightshift's Providers tab. nvidia: call the NVIDIA NIM API directly.
    ai_provider: str = "meterless"
    meterless_base_url: str = "http://127.0.0.1:8088/v1"
    meterless_runtime_token: str = ""
    meterless_model: str = "meterless/auto"
    # Logical Nemotron model -> Meterless route, e.g.
    # METERLESS_ROUTES="nvidia/nemotron-3.5-lightning-30b-a3b=meterless/fast,nvidia/nemotron-3-super-120b-a12b=meterless/deep"
    # Models not listed go to METERLESS_MODEL.
    meterless_routes: str = ""
    # Optional embedding route on the runtime; empty uses the H-MEM spec's hash embedder.
    meterless_embed_model: str = ""
    # The injection guard (its safety classifiers are not in the runtime's catalog) and these
    # models are called on the NVIDIA API directly when a key is set; every agent turn
    # (guardians, auditor) stays on Meterless.
    meterless_direct_models: str = "nvidia/llama-3.1-nemotron-safety-guard-8b-v3,nvidia/nemotron-3.5-content-safety"

    # --- Inference: NVIDIA Nemotron (OpenAI-compatible NIM API) ---
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    nemotron_thinking: bool = False
    # nemotron: live calls (recorded). replay: recorded Nemotron responses.
    inference_mode: str = "nemotron"
    # SAMPLE_MODE=true: replay recorded Nemotron decisions, no API key or model network needed.
    sample_mode: bool = False
    inference_timeout_seconds: float = 90.0
    inference_max_retries: int = 2
    inference_temperature: float = 0.2
    inference_max_tokens: int = 1500
    # Per-role models; empty means NEMOTRON_MODEL. Lets a team mix Nemotron sizes.
    model_database_guardian: str = ""
    model_continuity_guardian: str = ""
    model_auditor: str = ""
    model_solo_agent: str = ""
    # Reasoning scaffold: grounding retries, evidence checklist, trade-off calculator,
    # code-enforced business invariants and the injection guard. Off only for ablation.
    reasoning_scaffold: bool = True
    # Untrusted text from the database and business systems is screened before agents see it.
    guard_enabled: bool = True
    guard_model: str = "nvidia/nemotron-3.5-content-safety"
    guard_fallback_model: str = "nvidia/llama-3.1-nemotron-safety-guard-8b-v3"
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
    # When Zetaris fails: answer locally from the same sources, labeled (true), or report
    # the business context as unavailable, which the pact treats as unknown (false).
    business_fallback: bool = True
    # Fault injection for the dependency experiments: questions whose Zetaris call fails,
    # e.g. "calendar" or "registry,calendar,impact" or "all". Empty in normal operation.
    business_outage: str = ""

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
    # Rule I8, signed provenance: every model answer a contract rests on must carry a
    # valid Nightshift receipt (app/integrations/meterless/receipts.py). On for every
    # Nightshift run; off when models are called on the NVIDIA API directly.
    receipt_gate: bool = False
    meterless_receipts_url: str = ""  # the read-only relay next to Nightshift
    meterless_receipt_key: str = ""  # Nightshift's public key (base64) or its 16-hex fingerprint
    receipt_models: str = "nvidia/nemotron"  # allowed model prefixes, comma-separated
    receipt_egress: str = "nvidia,local"  # allowed prompt destinations

    # --- Demo ---
    checkout_timeout_ms: int = 3000
    traffic_rps: float = 4.0
    runs_dir: str = "./data/runs"
    logs_dir: str = "./logs"

    @property
    def meterless_route_map(self) -> dict[str, str]:
        out = {}
        for pair in self.meterless_routes.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def meterless_route(self, model: str) -> str:
        return self.meterless_route_map.get(model, self.meterless_model)

    @property
    def receipt_model_prefixes(self) -> list[str]:
        return [p.strip() for p in self.receipt_models.split(",") if p.strip()]

    @property
    def receipt_egress_allowed(self) -> set[str]:
        return {d.strip() for d in self.receipt_egress.split(",") if d.strip()}

    def model_for(self, role: str) -> str:
        return getattr(self, f"model_{role}", "") or self.nemotron_model

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
