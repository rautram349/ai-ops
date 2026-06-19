"""Shared simulation constants for all data generators.

All numeric parameters match the values defined in
docs/specs/03_data_incident_spec.md.  Any change to scale or shape should
be made here only — individual generators import from this module.
"""

import datetime

# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------

START_DATE: datetime.date = datetime.date(2025, 4, 14)
END_DATE: datetime.date = datetime.date(2026, 4, 13)
SEED: int = 42

# ---------------------------------------------------------------------------
# Business-world scale
# ---------------------------------------------------------------------------

NUM_PRODUCTS: int = 75
NUM_CUSTOMERS: int = 25_000
NUM_CAMPAIGNS: int = 52

# ---------------------------------------------------------------------------
# Regions and their order-share weights
# ---------------------------------------------------------------------------

REGIONS: list[str] = ["North", "South", "East", "West"]
REGION_WEIGHTS: list[float] = [0.30, 0.25, 0.25, 0.20]

# ---------------------------------------------------------------------------
# Product categories: (name, count, price_lo, price_hi, margin_lo, margin_hi)
# ---------------------------------------------------------------------------

CATEGORIES: list[tuple] = [
    ("Electronics",            12, 50.00,  300.00, 0.15, 0.25),
    ("Clothing",               18, 15.00,   80.00, 0.40, 0.60),
    ("Home & Kitchen",         15, 10.00,  120.00, 0.30, 0.50),
    ("Beauty & Personal Care", 12,  8.00,   60.00, 0.50, 0.70),
    ("Sports & Outdoors",      10, 20.00,  150.00, 0.25, 0.40),
    ("Books & Media",           8,  5.00,   35.00, 0.30, 0.45),
]

# ---------------------------------------------------------------------------
# Weekday demand/traffic multipliers (Mon=0 … Sun=6)
# ---------------------------------------------------------------------------

WEEKDAY_FACTORS: list[float] = [1.00, 1.05, 1.05, 1.00, 0.95, 0.85, 0.80]

# ---------------------------------------------------------------------------
# Monthly seasonal demand multipliers (1=Jan … 12=Dec)
# ---------------------------------------------------------------------------

MONTHLY_FACTORS: dict[int, float] = {
    1: 0.72,   # Jan — post-holiday slump
    2: 0.78,   # Feb
    3: 0.88,   # Mar — spring pickup
    4: 0.92,   # Apr
    5: 0.95,   # May
    6: 0.90,   # Jun — early summer dip
    7: 0.85,   # Jul
    8: 0.88,   # Aug — back-to-school
    9: 0.93,   # Sep
    10: 1.05,  # Oct — pre-holiday ramp
    11: 1.95,  # Nov — Black Friday peak
    12: 1.65,  # Dec — holiday
}

# ---------------------------------------------------------------------------
# One-day holiday spikes: (month, day) → order multiplier
# ---------------------------------------------------------------------------

HOLIDAY_SPIKES: dict[tuple, float] = {
    (11, 28): 4.2,   # Black Friday 2025
    (12,  1): 3.1,   # Cyber Monday 2025
    (12, 24): 2.5,   # Christmas Eve
    (12, 26): 1.8,   # Boxing Day
    ( 1,  1): 1.4,   # New Year's Day 2026
    ( 2, 14): 1.6,   # Valentine's Day
    ( 3, 17): 1.3,   # St Patrick's Day
    ( 4,  5): 1.5,   # Easter Sunday 2026
}

# ---------------------------------------------------------------------------
# Traffic baseline
# ---------------------------------------------------------------------------

BASE_DAILY_SESSIONS: int = 15_000

# Traffic channels and their approximate share
TRAFFIC_CHANNELS: list[str] = [
    "organic", "paid_search", "social", "display", "direct", "email"
]
CHANNEL_WEIGHTS: list[float] = [0.30, 0.25, 0.20, 0.10, 0.10, 0.05]

# ---------------------------------------------------------------------------
# Order parameters
# ---------------------------------------------------------------------------

DAILY_ORDER_BASELINE_LO: int = 300
DAILY_ORDER_BASELINE_HI: int = 800
ITEMS_PER_ORDER_LO: int = 1
ITEMS_PER_ORDER_HI: int = 5
AOV_LO: float = 45.0
AOV_HI: float = 85.0

ORDER_STATUSES: list[str] = ["completed", "processing", "cancelled", "returned"]
ORDER_STATUS_WEIGHTS: list[float] = [0.90, 0.05, 0.03, 0.02]

PAYMENT_STATUSES: list[str] = ["paid", "pending", "failed", "refunded"]
PAYMENT_STATUS_WEIGHTS: list[float] = [0.92, 0.03, 0.02, 0.03]

# ---------------------------------------------------------------------------
# Support / complaints
# ---------------------------------------------------------------------------

BASE_COMPLAINT_RATE: float = 0.02       # 2 % of daily orders
COMPLAINT_CATEGORIES: list[str] = [
    "shipping", "product_quality", "payment", "availability", "other"
]
COMPLAINT_WEIGHTS: list[float] = [0.40, 0.30, 0.10, 0.10, 0.10]
SEVERITIES: list[str] = ["low", "medium", "high", "critical"]
SEVERITY_WEIGHTS: list[float] = [0.50, 0.30, 0.15, 0.05]

# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

REVIEW_RATE: float = 0.08               # 8 % of daily orders generate a review
AVG_RATING_BASELINE: float = 4.1
REVIEW_SENTIMENTS: list[str] = ["positive", "neutral", "negative"]
REVIEW_THEMES: list[str] = ["quality", "shipping", "value", "experience"]

# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------

BASE_RETURN_RATE: float = 0.04          # 4 % baseline return rate
RETURN_REASONS: list[str] = [
    "defective", "wrong_item", "not_as_described", "changed_mind", "late_delivery"
]
RETURN_REASON_WEIGHTS: list[float] = [0.25, 0.15, 0.20, 0.25, 0.15]

# ---------------------------------------------------------------------------
# Campaign channels
# ---------------------------------------------------------------------------

CAMPAIGN_CHANNELS: list[str] = ["paid_search", "social", "display", "email"]

# ---------------------------------------------------------------------------
# Seeded incident calendar
# Each entry: (day_offset, incident_type, memory_tag, **kwargs)
# day_offset is 1-based from START_DATE.
# ---------------------------------------------------------------------------

INCIDENT_CALENDAR: list[dict] = [
    # ── Apr–Jun 2025 (original 10 incidents) ─────────────────────────────────
    {
        "day": 11, "type": "inventory_stockout",
        "tag": "stockout_top_sellers",
        "stockout_hours": 14, "affected_tier": "top2_electronics",
        "sales_drop_pct": 0.13,
    },
    {
        "day": 18, "type": "campaign_paused",
        "tag": "campaign_disruption",
        "traffic_drop_pct": 0.20, "order_drop_pct": 0.165,
    },
    {
        "day": 24, "type": "shipping_delay",
        "tag": "shipping_delay",
        "region": "North", "delay_days_lo": 3, "delay_days_hi": 5,
        "complaint_multiplier": 3.0, "return_multiplier": 2.0,
        "complaint_lag": (1, 3), "return_lag": (3, 5),
    },
    {
        "day": 30, "type": "missed_promotion",
        "tag": "missed_promotion",
        "category": "Home & Kitchen", "expected_discount_pct": 0.20,
    },
    {
        "day": 35, "type": "multi_factor",
        "tag": "stockout_campaign_overlap",
        "sales_drop_pct": 0.225,
        "stockout_hours": 16, "affected_tier": "top3_beauty",
        "campaign_ctr_drop": 0.50,
    },
    {
        "day": 40, "type": "checkout_bug",
        "tag": "checkout_issue",
        "bug_hours": 6, "failure_rate": 0.15,
        "complaint_multiplier": 4.0,
    },
    {
        "day": 45, "type": "inventory_stockout",
        "tag": "stockout_top_sellers",
        "stockout_hours": 10, "affected_tier": "top2_electronics",
        "sales_drop_pct": 0.13,
    },
    {
        "day": 50, "type": "review_surge",
        "tag": "quality_issue",
        "category": "Sports & Outdoors",
        "rating_drop": 0.90, "return_multiplier": 2.0,
        "conversion_drop": 0.175,
    },
    {
        "day": 55, "type": "campaign_paused",
        "tag": "campaign_disruption",
        "region": "East", "traffic_drop_pct": 0.18, "order_drop_pct": 0.15,
    },
    {
        "day": 60, "type": "multi_factor",
        "tag": "multi_factor_gradual",
        "sales_drop_pct": 0.125,
        "inventory_low": True, "campaign_cpc_high": True,
        "delivery_complaint_lift": 0.20,
    },
    # ── Jun–Aug 2025 ──────────────────────────────────────────────────────────
    {
        "day": 75, "type": "shipping_delay",
        "tag": "shipping_delay",
        "region": "South", "delay_days_lo": 2, "delay_days_hi": 4,
        "complaint_multiplier": 2.5, "return_multiplier": 1.8,
        "complaint_lag": (1, 2), "return_lag": (2, 4),
    },
    {
        "day": 90, "type": "inventory_stockout",
        "tag": "stockout_top_sellers",
        "stockout_hours": 18, "affected_tier": "top2_electronics",
        "sales_drop_pct": 0.15,
    },
    {
        "day": 110, "type": "campaign_paused",
        "tag": "campaign_disruption",
        "traffic_drop_pct": 0.22, "order_drop_pct": 0.18,
    },
    {
        "day": 130, "type": "review_surge",
        "tag": "quality_issue",
        "category": "Clothing",
        "rating_drop": 0.85, "return_multiplier": 1.9,
        "conversion_drop": 0.14,
    },
    # ── Sep–Oct 2025 ──────────────────────────────────────────────────────────
    {
        "day": 155, "type": "checkout_bug",
        "tag": "checkout_issue",
        "bug_hours": 8, "failure_rate": 0.18,
        "complaint_multiplier": 3.5,
    },
    {
        "day": 180, "type": "missed_promotion",
        "tag": "missed_promotion",
        "category": "Electronics", "expected_discount_pct": 0.15,
    },
    {
        "day": 200, "type": "multi_factor",
        "tag": "stockout_campaign_overlap",
        "sales_drop_pct": 0.20,
        "stockout_hours": 12, "affected_tier": "top3_clothing",
        "campaign_ctr_drop": 0.40,
    },
    # ── Nov 2025 — Black Friday / Cyber Monday ────────────────────────────────
    {
        "day": 218, "type": "campaign_paused",
        "tag": "campaign_disruption",
        "traffic_drop_pct": 0.25, "order_drop_pct": 0.20,
    },
    {
        "day": 228, "type": "inventory_stockout",
        "tag": "stockout_top_sellers",
        "stockout_hours": 22, "affected_tier": "top2_electronics",
        "sales_drop_pct": 0.18,
    },
    {
        "day": 231, "type": "inventory_stockout",
        "tag": "stockout_top_sellers",
        "stockout_hours": 16, "affected_tier": "top3_beauty",
        "sales_drop_pct": 0.14,
    },
    # ── Dec 2025 ──────────────────────────────────────────────────────────────
    {
        "day": 245, "type": "shipping_delay",
        "tag": "shipping_delay",
        "region": "West", "delay_days_lo": 4, "delay_days_hi": 7,
        "complaint_multiplier": 4.0, "return_multiplier": 2.5,
        "complaint_lag": (1, 3), "return_lag": (4, 7),
    },
    {
        "day": 260, "type": "checkout_bug",
        "tag": "checkout_issue",
        "bug_hours": 5, "failure_rate": 0.12,
        "complaint_multiplier": 3.0,
    },
    # ── Jan–Feb 2026 ──────────────────────────────────────────────────────────
    {
        "day": 280, "type": "review_surge",
        "tag": "quality_issue",
        "category": "Home & Kitchen",
        "rating_drop": 0.80, "return_multiplier": 2.2,
        "conversion_drop": 0.16,
    },
    {
        "day": 300, "type": "campaign_paused",
        "tag": "campaign_disruption",
        "region": "North", "traffic_drop_pct": 0.19, "order_drop_pct": 0.16,
    },
    # ── Mar–Apr 2026 ──────────────────────────────────────────────────────────
    {
        "day": 320, "type": "inventory_stockout",
        "tag": "stockout_top_sellers",
        "stockout_hours": 12, "affected_tier": "top2_electronics",
        "sales_drop_pct": 0.12,
    },
    {
        "day": 340, "type": "shipping_delay",
        "tag": "shipping_delay",
        "region": "East", "delay_days_lo": 2, "delay_days_hi": 5,
        "complaint_multiplier": 2.8, "return_multiplier": 1.7,
        "complaint_lag": (1, 2), "return_lag": (2, 4),
    },
    {
        "day": 355, "type": "multi_factor",
        "tag": "multi_factor_gradual",
        "sales_drop_pct": 0.13,
        "inventory_low": True, "campaign_cpc_high": True,
        "delivery_complaint_lift": 0.18,
    },
    {
        "day": 360, "type": "missed_promotion",
        "tag": "missed_promotion",
        "category": "Beauty & Personal Care", "expected_discount_pct": 0.18,
    },
]
