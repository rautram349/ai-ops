# ── Python backend + MCP servers ─────────────────────────────────────────────
FROM python:3.11-slim AS base

# System deps for psycopg2-binary and general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

WORKDIR /app

# ── Dependency layer (cached unless pyproject.toml / uv.lock changes) ────────
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# Activate the virtual environment created by uv
ENV PATH="/app/.venv/bin:$PATH"

# Default: start backend (overridden in docker-compose for other services)
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8001"]
