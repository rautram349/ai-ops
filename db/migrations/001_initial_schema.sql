-- =============================================================================
-- Migration: 001_initial_schema.sql
-- Description: Initial schema for E-commerce Operations Brain
-- Tables:
--   Business data (10): products, customers, orders, order_items,
--                        inventory_daily, campaigns, campaign_daily_metrics,
--                        support_tickets, reviews, returns_refunds, daily_traffic
--   Agent system  (8):  conversations, messages, runs, run_steps, tool_calls,
--                        approval_requests, executed_actions, incidents
-- Extensions: pgvector (for semantic incident memory search)
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector for embedding column


-- ===========================================================================
-- SECTION 1: BUSINESS DATA TABLES
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- products
-- Core product catalogue. Base demand and sensitivity coefficients are used
-- by the data generator to derive realistic order volumes.
-- ---------------------------------------------------------------------------
CREATE TABLE products (
    product_id              VARCHAR(10)     PRIMARY KEY,           -- e.g. "PROD-001"
    name                    VARCHAR(200)    NOT NULL,
    category                VARCHAR(50)     NOT NULL,              -- Electronics, Clothing, Home & Kitchen, Beauty, Sports, Books
    subcategory             VARCHAR(100),
    price                   DECIMAL(10,2)   NOT NULL,
    cost                    DECIMAL(10,2)   NOT NULL,
    margin_pct              DECIMAL(5,2)    NOT NULL,
    launch_date             DATE            NOT NULL,
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    base_daily_demand       INTEGER         NOT NULL,              -- expected units/day under normal conditions
    campaign_sensitivity    DECIMAL(3,2)    NOT NULL DEFAULT 0.5,  -- 0.0–1.0
    price_sensitivity       DECIMAL(3,2)    NOT NULL DEFAULT 0.5,  -- 0.0–1.0
    created_at              TIMESTAMP       NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- customers
-- 5 000-record customer base spread across four regions.
-- ---------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id     VARCHAR(10)     PRIMARY KEY,                   -- e.g. "CUST-00001"
    name            VARCHAR(200)    NOT NULL,
    email           VARCHAR(200)    NOT NULL,
    region          VARCHAR(20)     NOT NULL,                      -- North, South, East, West
    registered_at   DATE            NOT NULL,
    total_orders    INTEGER         NOT NULL DEFAULT 0,
    total_spent     DECIMAL(12,2)   NOT NULL DEFAULT 0
);


-- ---------------------------------------------------------------------------
-- orders
-- One row per placed order. created_date is denormalised from created_at for
-- efficient date-range queries without timezone conversion.
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    order_id        VARCHAR(15)     PRIMARY KEY,                   -- e.g. "ORD-0000001"
    customer_id     VARCHAR(10)     NOT NULL REFERENCES customers(customer_id),
    region          VARCHAR(20)     NOT NULL,                      -- North, South, East, West
    created_at      TIMESTAMP       NOT NULL,
    order_value     DECIMAL(10,2)   NOT NULL,
    discount_amount DECIMAL(10,2)   NOT NULL DEFAULT 0,
    final_value     DECIMAL(10,2)   NOT NULL,                      -- order_value - discount_amount
    item_count      INTEGER         NOT NULL,
    status          VARCHAR(20)     NOT NULL,                      -- completed, processing, cancelled, returned
    payment_status  VARCHAR(20)     NOT NULL,                      -- paid, pending, failed, refunded
    campaign_id     VARCHAR(10),                                   -- nullable; set if order is campaign-attributed
    created_date    DATE            NOT NULL                       -- denormalised for fast daily queries
);

CREATE INDEX idx_orders_created_date ON orders(created_date);
CREATE INDEX idx_orders_region       ON orders(region);
CREATE INDEX idx_orders_status       ON orders(status);
CREATE INDEX idx_orders_customer     ON orders(customer_id);
CREATE INDEX idx_orders_campaign     ON orders(campaign_id) WHERE campaign_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- order_items
-- Line items within each order. Tracks per-item discount separately.
-- ---------------------------------------------------------------------------
CREATE TABLE order_items (
    order_item_id   SERIAL          PRIMARY KEY,
    order_id        VARCHAR(15)     NOT NULL REFERENCES orders(order_id),
    product_id      VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    quantity        INTEGER         NOT NULL CHECK (quantity > 0),
    unit_price      DECIMAL(10,2)   NOT NULL,
    discount_pct    DECIMAL(5,2)    NOT NULL DEFAULT 0,
    line_total      DECIMAL(10,2)   NOT NULL
);

CREATE INDEX idx_order_items_order   ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);


-- ---------------------------------------------------------------------------
-- inventory_daily
-- One row per (product, region, day). stockout_hours records partial-day
-- unavailability; lost_demand is estimated units that could not be fulfilled.
-- ---------------------------------------------------------------------------
CREATE TABLE inventory_daily (
    id              SERIAL          PRIMARY KEY,
    product_id      VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    region          VARCHAR(20)     NOT NULL,
    date            DATE            NOT NULL,
    opening_stock   INTEGER         NOT NULL,
    units_received  INTEGER         NOT NULL DEFAULT 0,
    units_sold      INTEGER         NOT NULL DEFAULT 0,
    units_returned  INTEGER         NOT NULL DEFAULT 0,
    closing_stock   INTEGER         NOT NULL,
    stockout_hours  DECIMAL(4,1)    NOT NULL DEFAULT 0,            -- hours product was unavailable that day
    lost_demand     INTEGER         NOT NULL DEFAULT 0,            -- estimated units lost to stockout
    UNIQUE (product_id, region, date)
);

CREATE INDEX idx_inventory_date     ON inventory_daily(date);
CREATE INDEX idx_inventory_product  ON inventory_daily(product_id);
CREATE INDEX idx_inventory_stockout ON inventory_daily(stockout_hours) WHERE stockout_hours > 0;


-- ---------------------------------------------------------------------------
-- campaigns
-- Marketing campaign definitions. target_products and target_regions are
-- stored as text arrays to avoid a separate junction table for this read-heavy
-- analytics use case.
-- ---------------------------------------------------------------------------
CREATE TABLE campaigns (
    campaign_id     VARCHAR(10)     PRIMARY KEY,                   -- e.g. "CAMP-001"
    name            VARCHAR(200)    NOT NULL,
    channel         VARCHAR(50)     NOT NULL,                      -- paid_search, social, display, email
    target_products TEXT[],                                        -- array of product_ids
    target_regions  TEXT[],                                        -- array of region names
    start_date      DATE            NOT NULL,
    end_date        DATE,
    daily_budget    DECIMAL(10,2)   NOT NULL,
    status          VARCHAR(20)     NOT NULL,                      -- active, paused, completed, scheduled
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- campaign_daily_metrics
-- Aggregated performance metrics per campaign per day. Derived KPIs (ctr,
-- conversion_rate, roas) are stored denormalised to avoid repeated calculation
-- in agent queries.
-- ---------------------------------------------------------------------------
CREATE TABLE campaign_daily_metrics (
    id                  SERIAL          PRIMARY KEY,
    campaign_id         VARCHAR(10)     NOT NULL REFERENCES campaigns(campaign_id),
    date                DATE            NOT NULL,
    status              VARCHAR(20)     NOT NULL,                  -- active, paused (status on that specific day)
    impressions         INTEGER         NOT NULL,
    clicks              INTEGER         NOT NULL,
    conversions         INTEGER         NOT NULL,
    spend               DECIMAL(10,2)   NOT NULL,
    attributed_revenue  DECIMAL(10,2)   NOT NULL,
    ctr                 DECIMAL(6,4),                              -- click-through rate (clicks / impressions)
    conversion_rate     DECIMAL(6,4),                              -- conversions / clicks
    roas                DECIMAL(6,2),                              -- attributed_revenue / spend
    UNIQUE (campaign_id, date)
);

CREATE INDEX idx_campaign_metrics_date     ON campaign_daily_metrics(date);
CREATE INDEX idx_campaign_metrics_campaign ON campaign_daily_metrics(campaign_id);


-- ---------------------------------------------------------------------------
-- support_tickets
-- Customer support cases. Linked to customer + optionally to a product/order.
-- ---------------------------------------------------------------------------
CREATE TABLE support_tickets (
    ticket_id       VARCHAR(15)     PRIMARY KEY,                   -- e.g. "TKT-000001"
    customer_id     VARCHAR(10)     NOT NULL REFERENCES customers(customer_id),
    product_id      VARCHAR(10)     REFERENCES products(product_id),              -- nullable
    order_id        VARCHAR(15)     REFERENCES orders(order_id),                  -- nullable
    region          VARCHAR(20)     NOT NULL,
    category        VARCHAR(50)     NOT NULL,                      -- shipping, product_quality, payment, availability, other
    severity        VARCHAR(10)     NOT NULL,                      -- low, medium, high, critical
    subject         VARCHAR(300)    NOT NULL,
    description     TEXT,
    status          VARCHAR(20)     NOT NULL DEFAULT 'open',       -- open, in_progress, resolved, closed
    created_at      TIMESTAMP       NOT NULL,
    resolved_at     TIMESTAMP,
    created_date    DATE            NOT NULL
);

CREATE INDEX idx_tickets_date     ON support_tickets(created_date);
CREATE INDEX idx_tickets_category ON support_tickets(category);
CREATE INDEX idx_tickets_severity ON support_tickets(severity);
CREATE INDEX idx_tickets_status   ON support_tickets(status);


-- ---------------------------------------------------------------------------
-- reviews
-- Product reviews submitted by customers. sentiment and theme are pre-computed
-- from review text by the data generator (no NLP needed at query time).
-- ---------------------------------------------------------------------------
CREATE TABLE reviews (
    review_id       VARCHAR(15)     PRIMARY KEY,                   -- e.g. "REV-000001"
    product_id      VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    customer_id     VARCHAR(10)     NOT NULL REFERENCES customers(customer_id),
    order_id        VARCHAR(15)     REFERENCES orders(order_id),                  -- nullable
    rating          INTEGER         NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title           VARCHAR(200),
    body            TEXT,
    sentiment       VARCHAR(10)     NOT NULL,                      -- positive, neutral, negative
    theme           VARCHAR(50),                                   -- quality, shipping, value, experience
    created_at      TIMESTAMP       NOT NULL,
    created_date    DATE            NOT NULL
);

CREATE INDEX idx_reviews_date      ON reviews(created_date);
CREATE INDEX idx_reviews_product   ON reviews(product_id);
CREATE INDEX idx_reviews_sentiment ON reviews(sentiment);
CREATE INDEX idx_reviews_rating    ON reviews(rating);


-- ---------------------------------------------------------------------------
-- returns_refunds
-- Return and refund requests against orders.
-- ---------------------------------------------------------------------------
CREATE TABLE returns_refunds (
    return_id       VARCHAR(15)     PRIMARY KEY,                   -- e.g. "RET-000001"
    order_id        VARCHAR(15)     NOT NULL REFERENCES orders(order_id),
    customer_id     VARCHAR(10)     NOT NULL REFERENCES customers(customer_id),
    product_id      VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    reason          VARCHAR(100)    NOT NULL,                      -- defective, wrong_item, not_as_described, changed_mind, late_delivery
    refund_amount   DECIMAL(10,2)   NOT NULL,
    status          VARCHAR(20)     NOT NULL,                      -- requested, approved, refunded, rejected
    requested_at    TIMESTAMP       NOT NULL,
    processed_at    TIMESTAMP,
    requested_date  DATE            NOT NULL
);

CREATE INDEX idx_returns_date      ON returns_refunds(requested_date);
CREATE INDEX idx_returns_product   ON returns_refunds(product_id);
CREATE INDEX idx_returns_reason    ON returns_refunds(reason);


-- ---------------------------------------------------------------------------
-- daily_traffic
-- Web traffic aggregated by (date, region, channel).
-- ---------------------------------------------------------------------------
CREATE TABLE daily_traffic (
    id                          SERIAL          PRIMARY KEY,
    date                        DATE            NOT NULL,
    region                      VARCHAR(20)     NOT NULL,
    channel                     VARCHAR(50)     NOT NULL,          -- organic, paid_search, social, display, direct, email
    sessions                    INTEGER         NOT NULL,
    unique_visitors             INTEGER         NOT NULL,
    bounce_rate                 DECIMAL(5,4),
    avg_session_duration_sec    INTEGER,
    UNIQUE (date, region, channel)
);

CREATE INDEX idx_traffic_date    ON daily_traffic(date);
CREATE INDEX idx_traffic_channel ON daily_traffic(channel);


-- ===========================================================================
-- SECTION 2: AGENT SYSTEM TABLES
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- conversations
-- Top-level container for a user session. One conversation can span multiple
-- turns and multiple LangGraph runs.
-- ---------------------------------------------------------------------------
CREATE TABLE conversations (
    conversation_id UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(300),
    started_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_activity   TIMESTAMP       NOT NULL DEFAULT NOW(),
    status          VARCHAR(20)     NOT NULL DEFAULT 'active',     -- active, archived
    metadata        JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_conversations_status   ON conversations(status);
CREATE INDEX idx_conversations_activity ON conversations(last_activity DESC);


-- ---------------------------------------------------------------------------
-- messages
-- Individual chat turns within a conversation.
-- structured_response stores the machine-readable JSON payload from assistant
-- turns (intent, domain_data, recommendations, approval_required, etc.).
-- ---------------------------------------------------------------------------
CREATE TABLE messages (
    message_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID        NOT NULL REFERENCES conversations(conversation_id),
    role                VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content             TEXT        NOT NULL,
    structured_response JSONB,                                     -- populated for assistant messages only
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);


-- ---------------------------------------------------------------------------
-- runs
-- One row per LangGraph graph invocation. Links back to the conversation and
-- message that triggered it. Langfuse trace IDs are stored in metadata.
-- ---------------------------------------------------------------------------
CREATE TABLE runs (
    run_id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID        NOT NULL REFERENCES conversations(conversation_id),
    message_id          UUID        REFERENCES messages(message_id),
    intent              VARCHAR(30),
    status              VARCHAR(30) NOT NULL DEFAULT 'running',    -- running, completed, failed, paused_for_approval
    started_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMP,
    total_duration_ms   INTEGER,
    total_llm_calls     INTEGER     NOT NULL DEFAULT 0,
    total_tool_calls    INTEGER     NOT NULL DEFAULT 0,
    total_tokens        INTEGER     NOT NULL DEFAULT 0,
    error               TEXT,
    metadata            JSONB       NOT NULL DEFAULT '{}'          -- stores langfuse_trace_id etc.
);

CREATE INDEX idx_runs_conversation ON runs(conversation_id);
CREATE INDEX idx_runs_status       ON runs(status);
CREATE INDEX idx_runs_started      ON runs(started_at DESC);


-- ---------------------------------------------------------------------------
-- run_steps
-- One row per LangGraph node execution within a run. Used for local audit;
-- the authoritative trace is in Langfuse.
-- ---------------------------------------------------------------------------
CREATE TABLE run_steps (
    step_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES runs(run_id),
    node_name       VARCHAR(100) NOT NULL,                         -- e.g. "classify_intent", "sales_agent"
    step_order      INTEGER     NOT NULL,
    input_summary   TEXT,
    output_summary  TEXT,
    started_at      TIMESTAMP   NOT NULL,
    completed_at    TIMESTAMP,
    duration_ms     INTEGER,
    llm_calls       INTEGER     NOT NULL DEFAULT 0,
    tokens_used     INTEGER     NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',        -- running, completed, failed
    error           TEXT
);

CREATE INDEX idx_run_steps_run ON run_steps(run_id, step_order);


-- ---------------------------------------------------------------------------
-- tool_calls
-- Records every MCP tool invocation made during a run. is_write=TRUE flags
-- calls that need HITL approval.
-- ---------------------------------------------------------------------------
CREATE TABLE tool_calls (
    tool_call_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES runs(run_id),
    step_id         UUID        REFERENCES run_steps(step_id),
    tool_name       VARCHAR(100) NOT NULL,
    server_name     VARCHAR(50) NOT NULL,                          -- metrics-mcp, inventory-mcp, marketing-mcp, support-mcp
    arguments       JSONB       NOT NULL,
    response        JSONB,
    is_write        BOOLEAN     NOT NULL DEFAULT FALSE,
    duration_ms     INTEGER,
    status          VARCHAR(20) NOT NULL DEFAULT 'success',        -- success, error
    error           TEXT,
    called_at       TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tool_calls_run  ON tool_calls(run_id);
CREATE INDEX idx_tool_calls_step ON tool_calls(step_id);
CREATE INDEX idx_tool_calls_write ON tool_calls(is_write) WHERE is_write = TRUE;


-- ---------------------------------------------------------------------------
-- approval_requests
-- Human-in-the-loop approval queue. The graph pauses here (LangGraph
-- checkpointing) until a human approves or rejects via the API.
-- ---------------------------------------------------------------------------
CREATE TABLE approval_requests (
    approval_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES runs(run_id),
    conversation_id UUID        NOT NULL REFERENCES conversations(conversation_id),
    action_type     VARCHAR(50) NOT NULL,                          -- restock, pause_campaign, apply_discount, create_ticket
    target_entities JSONB       NOT NULL,                          -- {product_ids: [...], campaign_ids: [...], ...}
    reason          TEXT        NOT NULL,
    expected_impact TEXT,
    risk_level      VARCHAR(10) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    reversible      BOOLEAN     NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',        -- pending, approved, rejected
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    decided_at      TIMESTAMP,
    decided_by      VARCHAR(100),
    decision_note   TEXT
);

CREATE INDEX idx_approvals_status       ON approval_requests(status);
CREATE INDEX idx_approvals_conversation ON approval_requests(conversation_id);
CREATE INDEX idx_approvals_created      ON approval_requests(created_at DESC);


-- ---------------------------------------------------------------------------
-- executed_actions
-- Audit log of every approved action that was actually executed.
-- ---------------------------------------------------------------------------
CREATE TABLE executed_actions (
    execution_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    approval_id     UUID        NOT NULL REFERENCES approval_requests(approval_id),
    run_id          UUID        NOT NULL REFERENCES runs(run_id),
    action_type     VARCHAR(50) NOT NULL,
    tool_name       VARCHAR(100) NOT NULL,
    arguments       JSONB       NOT NULL,
    result          JSONB,
    success         BOOLEAN     NOT NULL,
    error           TEXT,
    executed_at     TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_executed_actions_approval ON executed_actions(approval_id);
CREATE INDEX idx_executed_actions_run      ON executed_actions(run_id);


-- ---------------------------------------------------------------------------
-- incidents
-- Persisted memory of diagnosed incidents. The embedding column enables
-- semantic similarity search so the agent can recall "have we seen this
-- before?" across past conversations.
-- ---------------------------------------------------------------------------
CREATE TABLE incidents (
    incident_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID        REFERENCES conversations(conversation_id),
    incident_date       DATE        NOT NULL,
    incident_type       VARCHAR(50) NOT NULL,                      -- inventory_stockout, campaign_paused, shipping_delay, etc.
    title               VARCHAR(300) NOT NULL,
    summary             TEXT        NOT NULL,
    affected_domains    TEXT[]      NOT NULL,                      -- e.g. ['sales', 'inventory']
    affected_products   TEXT[],
    affected_regions    TEXT[],
    root_causes         JSONB       NOT NULL,                      -- [{cause, confidence, domains}, ...]
    actions_taken       JSONB,                                     -- [{action_type, target, outcome}, ...]
    outcome_summary     TEXT,
    confidence          DECIMAL(3,2),
    resolved            BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMP,

    -- pgvector column — 1536 dims matches text-embedding-3-small output
    embedding           vector(1536)
);

CREATE INDEX idx_incidents_date ON incidents(incident_date);
CREATE INDEX idx_incidents_type ON incidents(incident_type);

-- IVFFlat index for approximate nearest-neighbour search on the embedding.
-- lists=20 is appropriate for a small-to-medium incident corpus (<10k rows).
-- Rebuild with a higher lists value if the corpus grows beyond ~100k rows.
CREATE INDEX idx_incidents_embedding
    ON incidents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 20);


-- ===========================================================================
-- SECTION 3: HELPER VIEWS
-- ===========================================================================

-- Daily sales summary — used frequently by the sales agent
CREATE VIEW v_daily_sales AS
SELECT
    o.created_date                          AS date,
    o.region,
    COUNT(DISTINCT o.order_id)              AS order_count,
    COUNT(DISTINCT o.customer_id)           AS unique_customers,
    SUM(o.final_value)                      AS revenue,
    SUM(o.discount_amount)                  AS total_discounts,
    AVG(o.final_value)                      AS avg_order_value,
    SUM(CASE WHEN o.status = 'returned'  THEN 1 ELSE 0 END)  AS returns,
    SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END)  AS cancellations
FROM orders o
GROUP BY o.created_date, o.region;

-- Pending approvals queue — used by the approval API endpoint
CREATE VIEW v_pending_approvals AS
SELECT
    ar.approval_id,
    ar.run_id,
    ar.conversation_id,
    ar.action_type,
    ar.target_entities,
    ar.reason,
    ar.expected_impact,
    ar.risk_level,
    ar.reversible,
    ar.created_at,
    r.intent          AS run_intent,
    r.started_at      AS run_started_at
FROM approval_requests ar
JOIN runs r ON r.run_id = ar.run_id
WHERE ar.status = 'pending'
ORDER BY ar.created_at ASC;


COMMIT;
