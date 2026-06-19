# E-commerce Operations Brain

An AI-powered operations copilot for e-commerce businesses. The system investigates business anomalies across sales, inventory, marketing, and customer support; explains root causes with cross-domain evidence; recommends corrective actions with human-in-the-loop approval; and learns from past incidents.

---

## Architecture

```
React Frontend  →  FastAPI Backend  →  LangGraph AI-ops Engine  →  MCP Servers  →  PostgreSQL
```

The **LangGraph AI-ops engine** routes each user query through a multi-step pipeline:

1. **Route** — classifies the query and selects relevant domains (metrics, inventory, marketing, support)
2. **Domain Agents** — call domain-specific MCP tools in parallel
3. **Reflect** — checks for evidence gaps and triggers targeted follow-up calls
4. **Plan** — decides whether write actions are needed, with risk assessment
5. **Execute** — runs approved write actions via human-in-the-loop approval
6. **Respond** — synthesises findings into a structured response

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
│   ├── api/                    # Route handlers (chat, approvals, runs, data)
│   ├── core/                   # Config, dependencies
│   ├── db/                     # Async SQLAlchemy session
│   ├── models/                 # Pydantic request/response models
│   ├── services/               # Business logic
│   ├── scheduler.py            # APScheduler background jobs
│   └── app.py                  # FastAPI app factory
│
├── ai_ops_engine/               # LangGraph orchestration engine
│   ├── graph/
│   │   ├── nodes.py            # All graph nodes (route, reflect, plan, execute, respond, …)
│   │   ├── builder.py          # Graph assembly + SSE streaming
│   │   └── state.py            # AgentState TypedDict
│   ├── agents/                 # Domain agents (metrics, inventory, marketing, support)
│   ├── clients/                # MCP client wrapper
│   ├── prompts/                # LLM prompt templates (agents.py, nodes.py)
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
│   ├── validate.py             # 24-check validation suite
│   └── output/                 # CSV backups (git-ignored)
│
├── db/
│   ├── migrations/             # SQL migration files (001_initial_schema, 002_write_tables)
│   └── setup.py                # Applies migrations via psycopg2
│
├── frontend/                   # React SPA
│   └── src/
│       ├── views/              # Chat, Approvals, Incidents, Run Trace
│       ├── components/         # Shared UI components (layout, badges, charts)
│       ├── api/                # Typed API clients (chat, approvals, runs, data)
│       ├── stores/             # Zustand state stores
│       └── types/              # Shared TypeScript types
│
├── evals/                      # Evaluation framework (Langfuse-backed)
│   ├── scenarios/              # Benchmark scenario definitions (YAML/JSON)
│   ├── runner.py               # Async eval runner
│   ├── scoring.py              # LLM-as-judge scoring
│   ├── test_safety.py          # Safety / guardrail tests
│   └── results/                # Eval run outputs (git-ignored)
│
├── docs/specs/                 # Project specifications
├── main.py                     # Entry point — starts uvicorn
├── pyproject.toml              # Python project metadata + dependencies (uv)
├── .env.example                # Environment variable template
└── .python-version             # Pinned Python version (3.11)
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+ (local or Docker)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- An LLM API key — see [LLM Configuration](#llm-configuration)

### 1. Clone and install

```bash
git clone <repo-url>
cd E-commerce_Operations_Brain

# Using uv (recommended)
uv sync

# Or pip
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in DATABASE_URL, LLM keys, etc.
```

### 3. Set up PostgreSQL

```bash
# Create the database
createdb ecommerce_ops_brain

# Run migrations
python -m db.setup
```

### 4. Generate synthetic data

Generates 1 year of data: 25k customers, 52 campaigns, 187k+ orders.

```bash
python -m data_gen.generate

# Validate the generated data (24 checks)
python -m data_gen.validate
```

### 5. Start MCP servers

```bash
python -m mcp_servers.start
# Launches metrics (:5010), inventory (:5011), marketing (:5012),
# support (:5013) MCP servers
```

### 6. Start the backend

```bash
python main.py
# or: uvicorn backend.app:app --reload --host 127.0.0.1 --port 8001
```

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

Voice input uses the browser's built-in speech recognition support when
available. Voice output uses `window.speechSynthesis`, so no backend audio
service is required for local development.

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

## Observability

Local run-trace persistence has been removed. Chat still streams live node-progress events while a response is being generated, but completed run-step/tool-call traces are no longer stored or exposed in the UI.

## Evaluation

```bash
# Run the full eval suite
pytest evals/ -v

# Run safety tests only
pytest evals/test_safety.py -v
```

Results are stored in `evals/results/` and pushed to Langfuse.

---

## Key Capabilities

- **Multi-domain investigation** — correlates signals across sales, inventory, marketing, and support in a single query
- **Cross-domain reasoning** — identifies causal chains, not just isolated metric pulls
- **Human-in-the-loop** — all write actions (restock, discount, pause campaign, ticket) require explicit approval
- **Incident memory** — stores and recalls past incidents via pgvector similarity search
- **Category-aware tools** — filters by product category (Electronics, Clothing, etc.) across all domains
- **Structured outputs** — every response follows a defined schema with findings, severity, root cause, and recommendations
- **Observability** — full run traces showing reasoning steps, tool calls, arguments, and decisions
- **Reflection loop** — self-checks for evidence gaps and triggers targeted follow-up tool calls
- **Incremental data extension** — append-only data generation keeps the simulation fresh

---

## Documentation

- [Product Spec](docs/specs/01_product_spec.md)
- [System Architecture](docs/specs/02_system_architecture_spec.md)
- [Data & Incident Spec](docs/specs/03_data_incident_spec.md)
- [Workflow & Orchestration](docs/specs/04_workflow_orchestration_spec.md)
- [Schema & Contracts](docs/specs/05_schema_contracts_spec.md)
- [Evaluation Spec](docs/specs/06_evaluation_spec.md)
