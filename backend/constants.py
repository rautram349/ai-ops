"""Single source of truth for application-wide constants, limits, and defaults.

Import from here rather than using raw string literals or magic numbers.
Adding a new domain, status, role, or tunable default requires editing only
this file.
"""

from __future__ import annotations


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ConversationStatus:
    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole:
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RiskLevel:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GuardrailStatus:
    ALLOWED = "allowed"
    BLOCKED = "blocked"


class GuardrailCategory:
    IN_SCOPE = "in_scope"
    IRRELEVANT = "irrelevant"
    CASUAL = "casual"
    PROMPT_INJECTION = "prompt_injection"
    UNKNOWN = "unknown"


DEFAULT_PAGE_LIMIT: int = 50
EVAL_PASS_RATE_THRESHOLD: float = 0.70

# ── Database default URLs ─────────────────────────────────────────────────────
DATABASE_URL_ASYNC_DEFAULT: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ecommerce_ops_brain"
DATABASE_URL_SYNC_DEFAULT: str = "postgresql://postgres:postgres@localhost:5432/ecommerce_ops_brain"

# ── EPAM DIAL (AzureOpenAI proxy) defaults ────────────────────────────────────
EPAM_DIAL_DEFAULT_ENDPOINT: str = "https://ai-proxy.lab.epam.com"
EPAM_DIAL_DEFAULT_DEPLOYMENT: str = "gpt-4o-2024-11-20"
EPAM_DIAL_DEFAULT_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-small"
EPAM_DIAL_DEFAULT_API_VERSION: str = "2023-12-01-preview"

# ── MCP server defaults ───────────────────────────────────────────────────────
MCP_DEFAULT_HOST: str = "localhost"
MCP_METRICS_DEFAULT_PORT: int = 5010
MCP_INVENTORY_DEFAULT_PORT: int = 5011
MCP_MARKETING_DEFAULT_PORT: int = 5012
MCP_SUPPORT_DEFAULT_PORT: int = 5013

# ── LLM defaults ─────────────────────────────────────────────────────────────
LLM_DEFAULT_TEMPERATURE: float = 0.1
LLM_DEFAULT_TIMEOUT: int = 120
LLM_DEFAULT_MAX_RETRIES: int = 1

# ── Backend server defaults ───────────────────────────────────────────────────
BACKEND_DEFAULT_HOST: str = "0.0.0.0"
BACKEND_DEFAULT_PORT: int = 8000

# ── Background monitoring ─────────────────────────────────────────────────────
MONITOR_DEFAULT_INTERVAL_MINUTES: int = 30

# ── HTTP / CORS ───────────────────────────────────────────────────────────────
CORS_DEFAULT_ORIGINS: str = "http://localhost:5173"

# ── Observability ─────────────────────────────────────────────────────────────
LANGFUSE_DEFAULT_HOST: str = "http://localhost:3000"
DEFAULT_LOG_LEVEL: str = "INFO"

# ── Data generation ───────────────────────────────────────────────────────────
DATA_GEN_DEFAULT_SEED: int = 42
DATA_GEN_DEFAULT_START_DATE: str = "2026-02-01"
DATA_GEN_DEFAULT_END_DATE: str = "2026-04-06"
