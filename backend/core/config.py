"""Application configuration via pydantic-settings.

Reads from environment variables or an optional ``.env`` file at the project
root. All settings are accessed via the module-level ``settings`` singleton.
Prefer importing ``settings`` directly; call ``get_settings()`` only when you
need an uncached copy (e.g., in tests).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables.

    All fields map to env-var names (case-insensitive). Defaults match the
    values in ``.env.example`` so the app starts without a local ``.env`` for
    read-only operations that do not need live credentials.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ecommerce_ops_brain",
        description="Async database URL used by the FastAPI app.",
    )
    database_url_sync: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/ecommerce_ops_brain",
        description="Sync database URL used by Alembic migrations.",
    )

    # ── LLM — EPAM DIAL (AzureOpenAI proxy) ─────────────────────────────────
    epam_dial_api_key: str = Field(default="", description="EPAM DIAL API key.")
    epam_dial_endpoint: str = Field(
        default="https://ai-proxy.lab.epam.com",
        description="EPAM DIAL Azure endpoint.",
    )
    epam_dial_deployment: str = Field(
        default="gpt-4o-2024-11-20",
        description="Azure deployment name on EPAM DIAL.",
    )
    epam_dial_embedding_deployment: str = Field(
        default="text-embedding-3-small",
        description="Azure deployment name for embedding model on EPAM DIAL.",
    )
    epam_dial_api_version: str = Field(
        default="2023-12-01-preview",
        description="Azure OpenAI API version.",
    )
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    # ── MCP servers ───────────────────────────────────────────────────────────
    mcp_metrics_host: str = Field(default="localhost")
    mcp_metrics_port: int = Field(default=5010)
    mcp_inventory_host: str = Field(default="localhost")
    mcp_inventory_port: int = Field(default=5011)
    mcp_marketing_host: str = Field(default="localhost")
    mcp_marketing_port: int = Field(default=5012)
    mcp_support_host: str = Field(default="localhost")
    mcp_support_port: int = Field(default=5013)

    # ── HTTP server ───────────────────────────────────────────────────────────
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8000)
    cors_origins: str = Field(
        default="http://localhost:5173",
        description="Comma-separated list of allowed CORS origins.",
    )

    # ── Data generation ───────────────────────────────────────────────────────
    data_gen_seed: int = Field(default=42)
    data_gen_start_date: str = Field(default="2026-02-01")
    data_gen_end_date: str = Field(default="2026-04-06")

    # ── Langfuse ──────────────────────────────────────────────────────────────
    langfuse_secret_key: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_host: str = Field(default="http://localhost:3000")

    # ── Scheduled monitoring ──────────────────────────────────────────────────
    monitor_interval_minutes: int = Field(
        default=30,
        description="How often (in minutes) the background health monitor runs.",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Root log level.")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the ``CORS_ORIGINS`` env-var into a list of origin strings."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
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
