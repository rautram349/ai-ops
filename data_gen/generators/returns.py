"""Returns and refunds generator.

Generates ``returns_refunds`` rows following the lagged return model in
docs/specs/03_data_incident_spec.md sections 3.8 and 6.

Key behaviours:
    - Baseline return rate: 4 % of orders.
    - Returns reference orders from 1–7 days prior (never same-day).
    - Shipping-delay incident (Day 24) → return spike on Days 27–29 (lag +3 to +5).
    - Review surge / product defect (Day 50) → return spike on Days 52–55 (lag +2 to +5).
    - Multi-factor incidents → mild return uptick.

Usage::

    from data_gen.generators.returns import generate_returns
    df = generate_returns(orders_df, customers_df, products_df, order_items_df)
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from data_gen.generators.constants import (
    BASE_RETURN_RATE,
    END_DATE,
    INCIDENT_CALENDAR,
    RETURN_REASONS,
    RETURN_REASON_WEIGHTS,
    SEED,
    START_DATE,
)

logger = logging.getLogger(__name__)

# Return lag: returns are filed this many days after the triggering order
RETURN_LAG_LO: int = 1
RETURN_LAG_HI: int = 7


def _build_return_multiplier_map() -> dict[date, float]:
    """Build a per-day mapping of return-rate multipliers from the incident calendar.

    Args: None

    Returns:
        Dict mapping calendar date → float multiplier applied to the base
        return rate for orders processed on that date.
    """
    mult_map: dict[date, float] = {}

    for inc in INCIDENT_CALENDAR:
        inc_date = START_DATE + timedelta(days=inc["day"] - 1)

        if inc["type"] == "shipping_delay":
            lag_lo, lag_hi = inc.get("return_lag", (3, 5))
            multiplier = inc.get("return_multiplier", 2.0)
            for lag in range(lag_lo, lag_hi + 1):
                d = inc_date + timedelta(days=lag)
                if d <= END_DATE:
                    # Take the max so overlapping incidents don't cancel out
                    mult_map[d] = max(mult_map.get(d, 1.0), multiplier)

        elif inc["type"] == "review_surge":
            multiplier = inc.get("return_multiplier", 2.0)
            for lag in range(2, 6):
                d = inc_date + timedelta(days=lag)
                if d <= END_DATE:
                    mult_map[d] = max(mult_map.get(d, 1.0), multiplier)

        elif inc["type"] == "multi_factor":
            # Mild return uptick on the incident day and day after
            for lag in range(0, 2):
                d = inc_date + timedelta(days=lag)
                if d <= END_DATE:
                    mult_map[d] = max(mult_map.get(d, 1.0), 1.30)

    return mult_map


def generate_returns(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    order_items: pd.DataFrame,
    seed: int = SEED,
    start_date: date | None = None,
    end_date: date | None = None,
    return_id_start: int = 1,
) -> pd.DataFrame:
    """Generate return and refund records for the full simulation period.

    For each day, samples a fraction of orders placed on prior days (1–7 days
    earlier) and marks them as returned.  The return multiplier from the
    incident calendar is applied to the base return rate on affected days.

    Args:
        orders: DataFrame from ``generate_orders()``.
        customers: DataFrame from ``generate_customers()``.
        products: DataFrame from ``generate_products()``.
        order_items: DataFrame from ``generate_orders()`` (items output).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame matching the ``returns_refunds`` Postgres table:
        return_id, order_id, customer_id, product_id, reason, refund_amount,
        status, requested_at, processed_at, requested_date.

    Raises:
        ValueError: If required DataFrames are empty.
    """
    for label, df in [("orders", orders), ("order_items", order_items), ("products", products)]:
        if df.empty:
            raise ValueError(f"{label} DataFrame is empty")

    rng = np.random.default_rng(seed)
    multiplier_map = _build_return_multiplier_map()

    _start = start_date or START_DATE
    _end = end_date or END_DATE

    # Primary product per order (highest value line item)
    primary_product = (
        order_items.sort_values("line_total", ascending=False)
        .groupby("order_id")
        .agg(product_id=("product_id", "first"), refund_amount=("line_total", "first"))
        .reset_index()
    )
    orders_enriched = orders.merge(primary_product, on="order_id", how="left")

    rows: list[dict] = []
    return_counter: int = return_id_start

    current_date = _start
    while current_date <= _end:
        multiplier = multiplier_map.get(current_date, 1.0)
        rate = BASE_RETURN_RATE * multiplier

        # Look back 1–7 days for eligible orders to return today
        for lag in range(RETURN_LAG_LO, RETURN_LAG_HI + 1):
            source_date = current_date - timedelta(days=lag)
            if source_date < _start:
                continue

            source_orders = orders_enriched[
                orders_enriched["created_date"] == source_date
            ]
            if source_orders.empty:
                continue

            # Sample fraction of those orders as returned on current_date
            n_returns = int(len(source_orders) * rate * (1.0 / RETURN_LAG_HI) *
                            (1.0 + float(rng.normal(0, 0.1))))
            if n_returns <= 0:
                continue

            sampled = source_orders.sample(
                n=min(n_returns, len(source_orders)),
                random_state=int(rng.integers(0, 10_000)),
            )

            for _, order_row in sampled.iterrows():
                reason = str(rng.choice(RETURN_REASONS, p=RETURN_REASON_WEIGHTS))
                product_id = order_row.get("product_id")
                if pd.isna(product_id):
                    product_id = str(rng.choice(products["product_id"].tolist()))

                refund_amount = round(float(order_row.get("refund_amount", order_row["final_value"])), 2)
                if pd.isna(refund_amount) or refund_amount <= 0:
                    refund_amount = round(float(order_row["final_value"]) * 0.8, 2)

                hour = int(rng.integers(8, 20))
                minute = int(rng.integers(0, 60))
                requested_at = pd.Timestamp(current_date) + pd.Timedelta(hours=hour, minutes=minute)

                status = str(rng.choice(
                    ["requested", "approved", "refunded", "rejected"],
                    p=[0.10, 0.25, 0.60, 0.05],
                ))
                processed_at = None
                if status in ("approved", "refunded"):
                    process_lag = int(rng.integers(1, 4))
                    processed_at = requested_at + pd.Timedelta(days=process_lag)

                rows.append(
                    {
                        "return_id": f"RET-{return_counter:06d}",
                        "order_id": order_row["order_id"],
                        "customer_id": order_row["customer_id"],
                        "product_id": product_id,
                        "reason": reason,
                        "refund_amount": refund_amount,
                        "status": status,
                        "requested_at": requested_at,
                        "processed_at": processed_at,
                        "requested_date": current_date,
                    }
                )
                return_counter += 1

        current_date += timedelta(days=1)

    df = pd.DataFrame(rows)
    logger.info(
        "Returns generated: %d total — refunded: %d, rejected: %d",
        len(df),
        (df["status"] == "refunded").sum() if not df.empty else 0,
        (df["status"] == "rejected").sum() if not df.empty else 0,
    )
    return df
