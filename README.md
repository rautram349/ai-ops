# E-commerce Operations Brain

An AI-powered operations copilot for e-commerce businesses. Investigates business anomalies across sales, inventory, marketing, and customer support; explains root causes with cross-domain evidence; recommends and executes corrective actions with human-in-the-loop approval; and learns from past incidents.

---

## Features

- **Multi-domain investigation** — correlates signals across sales, inventory, marketing, and support in a single query
- **Write action execution** — restock products, apply discounts, pause campaigns, create support tickets — all with human-in-the-loop approval
- **Direct action intent** — imperative queries like "restock PROD-001" skip domain investigation and go straight to write-action planning
- **Incident memory** — stores and recalls past incidents via pgvector similarity search
- **Reflection loop** — self-checks for evidence gaps and triggers targeted follow-up tool calls
- **Streaming chat** — live node-progress events streamed to the frontend while a response is being generated
- **Synthetic data generator** — produces 1 year of realistic e-commerce data (25k customers, 52 campaigns, 187k+ orders) with a 24-check validation suite
- **Structured outputs** — every response follows a defined schema with findings, severity, root cause, and recommendations
- **Multi-modal input** — voice + text input supported in the frontend

---

## Architecture

```
React Frontend  →  FastAPI Backend  →  LangGraph AI-ops Engine  →  MCP Servers  →  PostgreSQL
```

The **LangGraph AI-ops engine** routes each user query through a multi-step pipeline:

1. **Route** — LLM classifies the query into an intent: `sales_analysis`, `inventory_check`, `marketing_performance`, `support_analysis`, `multi_domain`, `memory_recall`, `action`, `irrelevant`, or `unknown`
2. **Plan Domains** — selects which domains to investigate (sales, inventory, marketing, support)
3. **Domain Agents** — call domain-specific MCP tools in parallel
4. **Synthesize** — aggregates findings from all domain agents
5. **Reflect** — checks evidence quality and confidence; triggers reinvestigation if gaps found
6. **Plan** — decides whether write actions are needed, with risk assessment and approval queuing
7. **Execute** — runs approved write actions
8. **Respond** — synthesises all data into a structured response with findings, recommendations, and actions taken

For **`action`** intent queries (e.g. "restock PROD-001", "apply 20% discount to Electronics"), the pipeline shortcuts directly from **Route → Plan → Execute → Respond**, skipping all domain investigation.

---

## Tech Stack

| Component     | Technology                                   |
| ------------- | -------------------------------------------- |
| Database      | PostgreSQL 16+ with pgvector                 |
| Backend       | FastAPI + uvicorn (Python 3.11+)             |
| Orchestration | LangGraph (multi-agent graph)                |
| Tool Servers  | FastMCP (Model Context Protocol, SSE)        |
| LLM           | EPAM DIAL proxy — Gemini 2.5 Flash (default) |
| Observability | Langfuse (traces, evals)                     |
| Frontend      | React 19 + TypeScript + Vite                 |

---

## Project Structure

```
├── backend/                    # FastAPI application
│   ├── api/                    # Route handlers (chat, approvals, incidents, conversations, health)
│   ├── core/                   # Config, dependencies, logging
│   ├── db/                     # Async SQLAlchemy session + repositories
│   ├── models/                 # Pydantic request/response models
│   ├── services/               # Business logic (chat, monitor, run store)
│   ├── scheduler.py            # APScheduler background health-monitor job
│   └── app.py                  # FastAPI app factory
│
├── ai_ops_engine/              # LangGraph orchestration engine
│   ├── graph/
│   │   ├── nodes/              # Individual graph node functions
│   │   │   ├── route.py        # Intent classification + guardrails
│   │   │   ├── plan_domains.py # Domain selection
│   │   │   ├── recall.py       # Incident memory recall
│   │   │   ├── synthesize.py   # Cross-domain finding aggregation
│   │   │   ├── reflect.py      # Evidence quality check + reinvestigation
│   │   │   ├── plan.py         # Write action detection + approval queuing
│   │   │   ├── execute.py      # Approved write tool execution
│   │   │   ├── respond.py      # Final structured response generation
│   │   │   └── shared.py       # Common utilities
│   │   ├── builder.py          # Graph assembly + SSE streaming
│   │   └── state.py            # AgentState TypedDict
│   ├── agents/                 # Domain agent runners
│   │   ├── base.py             # Shared agent runner logic
│   │   ├── sales_agent.py
│   │   ├── inventory_agent.py
│   │   ├── marketing_agent.py
│   │   ├── support_agent.py
│   │   └── memory_agent.py
│   ├── clients/                # MCP client wrapper (parallel tool calls)
│   ├── prompts/                # LLM prompt templates (.md files)
│   │   ├── route.md
│   │   ├── plan_domains.md
│   │   ├── plan.md
│   │   ├── respond.md
│   │   ├── reflect.md
│   │   ├── recall_keyword.md
│   │   ├── synthesize.md
│   │   ├── memory.md
│   │   ├── unknown.md
│   │   ├── sales.md
│   │   ├── inventory.md
│   │   ├── marketing.md
│   │   └── support.md
│   ├── embeddings.py           # pgvector embedding utilities
│   └── llm.py                  # LLM client factory
│
├── mcp_servers/                # MCP tool servers (FastMCP, SSE transport)
│   ├── metrics/                # Sales & revenue tools
│   ├── inventory/              # Stock, restock, stockout tools
│   ├── marketing/              # Campaign, discount, channel tools
│   ├── support/                # Ticket, review sentiment, refund tools
│   ├── db.py                   # Shared psycopg2 connection pool
│   └── start.py                # Launches all 4 servers in subprocesses
│
├── data_gen/                   # Synthetic data generation (1-year simulation)
│   ├── generators/             # Domain generators (orders, inventory, campaigns, …)
│   ├── generate.py             # Full generation + DB load orchestrator
│   └── validate.py             # 24-check validation suite
│
├── db/
│   ├── migrations/             # SQL migration files
│   └── setup.py                # Applies migrations via psycopg2
│
├── frontend/                   # React SPA
│   └── src/
│       ├── views/              # Chat, Approvals, Incidents views
│       ├── components/         # Shared UI components (chat, incidents, layout, charts)
│       ├── api/                # Typed API clients
│       ├── stores/             # Zustand state stores
│       ├── hooks/              # Custom React hooks
│       └── types/              # Shared TypeScript types
│
├── evals/                      # Evaluation framework (pytest + Langfuse)
│   ├── scenarios/              # Benchmark scenario definitions (JSON)
│   ├── runner.py               # Async eval runner
│   ├── scoring.py              # Scoring engine
│   ├── test_guardrails.py      # Guardrail classification tests
│   └── test_safety.py          # Safety / prompt-injection tests
│
├── main.py                     # Entry point — starts uvicorn
├── pyproject.toml              # Python project metadata + dependencies (uv)
├── .env.example                # Environment variable template
├── docker-compose.yml          # Multi-service Docker setup
├── Dockerfile                  # Python service container image
└── .python-version             # Pinned Python version (3.11)
```

---

## Quick Start

### Option A: Docker (recommended)

```bash
# 1. Start PostgreSQL
docker compose up -d postgres

# 2. Run database migrations
docker compose run --rm db-init

# 3. Generate 1 year of synthetic data
docker compose run --rm data-gen

# 4. Start all services (MCP servers, backend, frontend)
docker compose up -d

# Frontend:   http://localhost:3001
# Backend:    http://localhost:8001
```

### Option B: Manual

#### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+ (local or Docker)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- An LLM API key — see [LLM Configuration](#llm-configuration)

#### 1. Clone and install

```bash
git clone <repo-url>
cd E-commerce_Operations_Brain

# Using uv (recommended)
uv sync

# Or pip
pip install -r requirements.txt
```

#### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in DATABASE_URL, LLM keys, etc.
```

#### 3. Set up PostgreSQL

```bash
# Create the database
createdb ecommerce_ops_brain

# Run migrations
python -m db.setup
```

#### 4. Generate synthetic data

Generates 1 year of data: 25k customers, 52 campaigns, 187k+ orders.

```bash
python -m data_gen.generate

# Validate the generated data (24 checks)
python -m data_gen.validate
```

#### 5. Start MCP servers

```bash
python -m mcp_servers.start
# Launches metrics (:5010), inventory (:5011), marketing (:5012),
# support (:5013) MCP servers
```

#### 6. Start the backend

```bash
python main.py
# or: uvicorn backend.app:app --reload --host 127.0.0.1 --port 8001
```

#### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

Voice input uses the browser's built-in speech recognition support when available. Voice output uses `window.speechSynthesis`, so no backend audio service is required for local development.

---

## LLM Configuration

The system uses EPAM DIAL (AzureOpenAI proxy) by default, pointing at **Gemini 2.5 Flash**. Configure in `.env`:

```env
EPAM_DIAL_API_KEY=...
EPAM_DIAL_ENDPOINT=https://ai-proxy.lab.epam.com
EPAM_DIAL_DEPLOYMENT=gemini-2.5-flash
EPAM_DIAL_API_VERSION=2023-12-01-preview
LLM_TEMPERATURE=0.1
```

To switch models, change `EPAM_DIAL_DEPLOYMENT` or update `ai_ops_engine/llm.py` to use a different LangChain provider.

---

## MCP Servers

Each server runs as an independent SSE process:

| Server    | Port | Tools                                                                                                                                     |
| --------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| metrics   | 5010 | `get_sales_summary`, `compare_sales`, `get_revenue_by_product`, `get_revenue_by_region`, `detect_anomaly`                                 |
| inventory | 5011 | `get_stock_levels`, `get_near_stockout`, `get_stockout_events`, `get_product_availability_impact`, `restock_product`                      |
| marketing | 5012 | `get_campaign_status`, `get_campaign_performance`, `get_missed_promotions`, `get_channel_performance`, `pause_campaign`, `apply_discount` |
| support   | 5013 | `get_complaint_summary`, `get_issue_clusters`, `get_refund_return_summary`, `get_review_sentiment`, `create_support_ticket`               |

Write tools (`restock_product`, `pause_campaign`, `apply_discount`, `create_support_ticket`) require explicit human approval before executing.

---

## Evaluation

```bash
# Run the full eval suite
pytest evals/ -v

# Run safety tests only
pytest evals/test_safety.py -v
```

Results are stored in `evals/results/` and pushed to Langfuse.

---

## Observability

- **Langfuse** integration for tracing LLM calls and eval results
- **SSE streaming** — the chat API streams live node-progress events (route → plan_domains → agent → synthesize → reflect → plan → execute → respond) so the frontend can show real-time progress

---

## Key Capabilities

- **Multi-domain investigation** — correlates signals across sales, inventory, marketing, and support in a single query
- **Cross-domain reasoning** — identifies causal chains, not just isolated metric pulls
- **Direct action intent** — imperative queries (e.g. "restock PROD-001", "apply discount") shortcut directly to write-action planning, skipping investigation
- **Human-in-the-loop** — all write actions (restock, discount, pause campaign, create ticket) require explicit approval before execution
- **Incident memory** — stores and recalls past incidents via pgvector similarity search
- **Category-aware tools** — filters by product category (Electronics, Clothing, etc.) across all domains
- **Structured outputs** — every response follows a defined schema with findings, severity, root cause, and recommendations
- **Reflection loop** — self-checks for evidence gaps and triggers targeted follow-up tool calls
- **Streaming chat** — live node-progress events streamed to the frontend during response generation
- **Synthetic data validation** — 24-check validation suite ensures generated data integrity
