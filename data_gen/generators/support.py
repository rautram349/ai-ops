"""Support ticket generator.

Generates customer support tickets for the full simulation period, following
the complaint model in docs/specs/03_data_incident_spec.md section 3.6.

Key behaviours:
    - Baseline complaint rate: 2 % of daily orders.
    - Shipping-delay incident (Day 24) → complaint spike Day 25-27 (lag +1 to +3).
    - Checkout bug incident (Day 40) → payment-category complaint spike same day.
    - Review surge / product defect (Day 50) → product_quality spike Day 50-52.
    - Stockout incidents → availability category spike same day.

Usage::

    from data_gen.generators.support import generate_support_tickets
    df = generate_support_tickets(orders_df, customers_df, products_df)
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from data_gen.generators.constants import (
    COMPLAINT_CATEGORIES,
    COMPLAINT_WEIGHTS,
    END_DATE,
    INCIDENT_CALENDAR,
    SEED,
    SEVERITIES,
    SEVERITY_WEIGHTS,
    START_DATE,
)

logger = logging.getLogger(__name__)

BASE_COMPLAINT_RATE: float = 0.02


def _build_complaint_modifiers() -> dict[date, dict]:
    """Build a per-day map of complaint category multipliers from the incident calendar.

    Args: None

    Returns:
        Dict mapping calendar date → modifier dict with keys:
        ``category_multipliers`` (dict[str, float]) and optional
        ``extra_category`` to override the sampled category.
    """
    modifiers: dict[date, dict] = {}

    for inc in INCIDENT_CALENDAR:
        inc_date = START_DATE + timedelta(days=inc["day"] - 1)

        if inc["type"] == "shipping_delay":
            lag_lo, lag_hi = inc.get("complaint_lag", (1, 3))
            multiplier = inc.get("complaint_multiplier", 3.0)
            for lag in range(lag_lo, lag_hi + 1):
                spike_date = inc_date + timedelta(days=lag)
                if spike_date <= END_DATE:
                    modifiers[spike_date] = {
                        "category_multipliers": {"shipping": multiplier},
                    }

        elif inc["type"] == "checkout_bug":
            multiplier = inc.get("complaint_multiplier", 4.0)
            modifiers[inc_date] = {
                "category_multipliers": {"payment": multiplier},
                "order_count_multiplier": 1.0 - inc.get("failure_rate", 0.15),
            }

        elif inc["type"] in ("inventory_stockout", "multi_factor"):
            modifiers[inc_date] = {
                "category_multipliers": {"availability": 2.5},
            }

        elif inc["type"] == "review_surge":
            # Product quality complaints spike for 3 days
            for lag in range(0, 3):
                spike_date = inc_date + timedelta(days=lag)
                if spike_date <= END_DATE:
                    modifiers[spike_date] = {
                        "category_multipliers": {"product_quality": 3.0},
                    }

    return modifiers


def generate_support_tickets(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    seed: int = SEED,
    start_date: date | None = None,
    end_date: date | None = None,
    ticket_id_start: int = 1,
) -> pd.DataFrame:
    """Generate support tickets for the full simulation period.

    Args:
        orders: DataFrame from ``generate_orders()``.
        customers: DataFrame from ``generate_customers()``.
        products: DataFrame from ``generate_products()``.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame matching the ``support_tickets`` Postgres table:
        ticket_id, customer_id, product_id, order_id, region, category,
        severity, subject, description, status, created_at, resolved_at,
        created_date.

    Raises:
        ValueError: If any required DataFrame is empty.
    """
    if orders.empty:
        raise ValueError("orders DataFrame is empty")
    if customers.empty:
        raise ValueError("customers DataFrame is empty")
    if products.empty:
        raise ValueError("products DataFrame is empty")

    rng = np.random.default_rng(seed)
    Faker()
    Faker.seed(seed)

    _start = start_date or START_DATE
    _end = end_date or END_DATE

    modifiers = _build_complaint_modifiers()

    # Daily order counts for complaint volume calculation
    daily_order_counts = (
        orders.groupby("created_date")["order_id"].count().to_dict()
    )

    # Build helper index structures
    customer_ids = customers["customer_id"].tolist()
    product_ids = products["product_id"].tolist()

    # Pre-index orders by date for linking tickets to real orders
    orders_by_date: dict[date, pd.DataFrame] = {}
    for d, grp in orders.groupby("created_date"):
        orders_by_date[d] = grp

    rows: list[dict] = []
    ticket_counter: int = ticket_id_start

    # Ticket descriptions by category
    templates: dict[str, list[str]] = {
        "shipping": [
            "My order has not arrived yet, it is {days} days late.",
            "Package shows delivered but I never received it.",
            "Shipping was much slower than expected.",
        ],
        "product_quality": [
            "The product I received is defective.",
            "Item does not match the description on the site.",
            "Product broke after first use.",
        ],
        "payment": [
            "My payment failed but I was charged.",
            "Checkout keeps throwing an error.",
            "Double charged for the same order.",
        ],
        "availability": [
            "The item I ordered shows as out of stock.",
            "Order cancelled because product unavailable.",
            "Website shows in stock but order failed.",
        ],
        "other": [
            "I need help with my account.",
            "Please update my shipping address.",
            "Wrong item was added to my cart.",
        ],
    }

    current_date = _start
    while current_date <= _end:
        n_orders = daily_order_counts.get(current_date, 0)
        modifier = modifiers.get(current_date, {})
        cat_multipliers: dict[str, float] = modifier.get("category_multipliers", {})

        n_tickets = max(0, int(n_orders * BASE_COMPLAINT_RATE * (1.0 + float(rng.normal(0, 0.1)))))

        for _ in range(n_tickets):
            # Sample category, applying any multiplier
            weights = list(COMPLAINT_WEIGHTS)
            cat_list = list(COMPLAINT_CATEGORIES)
            for j, cat in enumerate(cat_list):
                if cat in cat_multipliers:
                    weights[j] *= cat_multipliers[cat]
            total_w = sum(weights)
            norm_weights = [w / total_w for w in weights]
            category = str(rng.choice(cat_list, p=norm_weights))

            severity = str(rng.choice(SEVERITIES, p=SEVERITY_WEIGHTS))

            # Link to a real order on the same day if possible
            day_orders = orders_by_date.get(current_date)
            if day_orders is not None and not day_orders.empty:
                order_row = day_orders.sample(1, random_state=int(rng.integers(0, 10_000))).iloc[0]
                order_id = order_row["order_id"]
                customer_id = order_row["customer_id"]
                region = order_row["region"]
            else:
                order_id = None
                customer_id = str(rng.choice(customer_ids))
                region = str(rng.choice(["North", "South", "East", "West"]))

            # Optionally link to a product
            product_id = str(rng.choice(product_ids)) if rng.random() < 0.6 else None

            tmpl_list = templates.get(category, templates["other"])
            description = str(rng.choice(tmpl_list)).format(days=int(rng.integers(2, 8)))
            subject = description[:80]

            hour = int(rng.integers(7, 22))
            minute = int(rng.integers(0, 60))
            created_at = pd.Timestamp(current_date) + pd.Timedelta(hours=hour, minutes=minute)

            # Resolution: 70 % resolved within 1-5 days
            resolved_at = None
            status = "open"
            if rng.random() < 0.70:
                resolve_lag = int(rng.integers(1, 6))
                resolved_at = created_at + pd.Timedelta(days=resolve_lag)
                status = "resolved"

            rows.append(
                {
                    "ticket_id": f"TKT-{ticket_counter:06d}",
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "order_id": order_id,
                    "region": region,
                    "category": category,
                    "severity": severity,
                    "subject": subject,
                    "description": description,
                    "status": status,
                    "created_at": created_at,
                    "resolved_at": resolved_at,
                    "created_date": current_date,
                }
            )
            ticket_counter += 1

        current_date += timedelta(days=1)

    df = pd.DataFrame(rows)
    logger.info(
        "Support tickets generated: %d total, %d resolved",
        len(df),
        (df["status"] == "resolved").sum() if not df.empty else 0,
    )
    return df
