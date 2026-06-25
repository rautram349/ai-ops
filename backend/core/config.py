"""Application configuration via pydantic-settings.

Reads from environment variables or an optional ``.env`` file at the project
root. All settings are accessed via the module-level ``settings`` singleton.
Prefer importing ``settings`` directly; call ``get_settings()`` only when you
need an uncached copy (e.g., in tests).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from backend.constants import (
    BACKEND_DEFAULT_HOST,
    BACKEND_DEFAULT_PORT,
    CORS_DEFAULT_ORIGINS,
    DATA_GEN_DEFAULT_END_DATE,
    DATA_GEN_DEFAULT_SEED,
    DATA_GEN_DEFAULT_START_DATE,
    DATABASE_URL_ASYNC_DEFAULT,
    DATABASE_URL_SYNC_DEFAULT,
    DEFAULT_LOG_LEVEL,
    EPAM_DIAL_DEFAULT_API_VERSION,
    EPAM_DIAL_DEFAULT_DEPLOYMENT,
    EPAM_DIAL_DEFAULT_EMBEDDING_DEPLOYMENT,
    EPAM_DIAL_DEFAULT_ENDPOINT,
    LANGFUSE_DEFAULT_HOST,
    LLM_DEFAULT_MAX_RETRIES,
    LLM_DEFAULT_TEMPERATURE,
    LLM_DEFAULT_TIMEOUT,
    MCP_DEFAULT_HOST,
    MCP_INVENTORY_DEFAULT_PORT,
    MCP_MARKETING_DEFAULT_PORT,
    MCP_METRICS_DEFAULT_PORT,
    MCP_SUPPORT_DEFAULT_PORT,
    MONITOR_DEFAULT_INTERVAL_MINUTES,
)


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables.

    All fields map to env-var names (case-insensitive). Defaults match the
    values in ``.env.example`` so the app starts without a local ``.env`` for
    read-only operations that do not need live credentials.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default=DATABASE_URL_ASYNC_DEFAULT,
        description="Async database URL used by the FastAPI app.",
    )
    database_url_sync: str = Field(
        default=DATABASE_URL_SYNC_DEFAULT,
        description="Sync database URL used by Alembic migrations.",
    )

    # ── LLM — EPAM DIAL (AzureOpenAI proxy) ─────────────────────────────────
    epam_dial_api_key: str = Field(default="", description="EPAM DIAL API key.")
    epam_dial_endpoint: str = Field(
        default=EPAM_DIAL_DEFAULT_ENDPOINT,
        description="EPAM DIAL Azure endpoint.",
    )
    epam_dial_deployment: str = Field(
        default=EPAM_DIAL_DEFAULT_DEPLOYMENT,
        description="Azure deployment name on EPAM DIAL.",
    )
    epam_dial_embedding_deployment: str = Field(
        default=EPAM_DIAL_DEFAULT_EMBEDDING_DEPLOYMENT,
        description="Azure deployment name for embedding model on EPAM DIAL.",
    )
    epam_dial_api_version: str = Field(
        default=EPAM_DIAL_DEFAULT_API_VERSION,
        description="Azure OpenAI API version.",
    )
    llm_temperature: float = Field(default=LLM_DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    llm_timeout: int = Field(default=LLM_DEFAULT_TIMEOUT, description="HTTP timeout for LLM requests in seconds.")
    llm_max_retries: int = Field(default=LLM_DEFAULT_MAX_RETRIES, description="Max retries for LLM requests.")

    # ── MCP servers ───────────────────────────────────────────────────────────
    mcp_metrics_host: str = Field(default=MCP_DEFAULT_HOST)
    mcp_metrics_port: int = Field(default=MCP_METRICS_DEFAULT_PORT)
    mcp_inventory_host: str = Field(default=MCP_DEFAULT_HOST)
    mcp_inventory_port: int = Field(default=MCP_INVENTORY_DEFAULT_PORT)
    mcp_marketing_host: str = Field(default=MCP_DEFAULT_HOST)
    mcp_marketing_port: int = Field(default=MCP_MARKETING_DEFAULT_PORT)
    mcp_support_host: str = Field(default=MCP_DEFAULT_HOST)
    mcp_support_port: int = Field(default=MCP_SUPPORT_DEFAULT_PORT)

    # ── HTTP server ───────────────────────────────────────────────────────────
    backend_host: str = Field(default=BACKEND_DEFAULT_HOST)
    backend_port: int = Field(default=BACKEND_DEFAULT_PORT)
    cors_origins: str = Field(
        default=CORS_DEFAULT_ORIGINS,
        description="Comma-separated list of allowed CORS origins.",
    )

    # ── Data generation ───────────────────────────────────────────────────────
    data_gen_seed: int = Field(default=DATA_GEN_DEFAULT_SEED)
    data_gen_start_date: str = Field(default=DATA_GEN_DEFAULT_START_DATE)
    data_gen_end_date: str = Field(default=DATA_GEN_DEFAULT_END_DATE)

    # ── Langfuse ──────────────────────────────────────────────────────────────
    langfuse_secret_key: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_host: str = Field(default=LANGFUSE_DEFAULT_HOST)

    # ── Scheduled monitoring ──────────────────────────────────────────────────
    monitor_interval_minutes: int = Field(
        default=MONITOR_DEFAULT_INTERVAL_MINUTES,
        description="How often (in minutes) the background health monitor runs.",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, description="Root log level.")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the ``CORS_ORIGINS`` env-var into a list of origin strings."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Prefer the repository .env over inherited shell variables."""
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application Settings singleton.

    Returns:
        A fully-initialised ``Settings`` instance loaded from env / ``.env``.
    """
    return Settings()


settings: Settings = get_settings()
