"""Order and order-item generator.

Simulates discrete orders for every day in the date range using the
top-down demand model from docs/specs/03_data_incident_spec.md section 3.4.

Key behaviours:
    - Daily order volume is modulated by weekday factor and incident modifiers.
    - Products are sampled proportional to their ``base_daily_demand``.
    - Customers are sampled proportional to their region share.
    - Incident modifiers (sales drops, checkout bug) reduce order counts on
      the affected day.
    - Returns the ``orders`` and ``order_items`` DataFrames, and also a
      mutated copy of ``customers`` with ``total_orders`` / ``total_spent``
      populated.

Usage::

    from data_gen.generators.orders import generate_orders
    orders_df, items_df, customers_df = generate_orders(products_df, customers_df)
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from data_gen.generators.constants import (
    HOLIDAY_SPIKES,
    INCIDENT_CALENDAR,
    ITEMS_PER_ORDER_HI,
    ITEMS_PER_ORDER_LO,
    MONTHLY_FACTORS,
    ORDER_STATUS_WEIGHTS,
    ORDER_STATUSES,
    PAYMENT_STATUS_WEIGHTS,
    PAYMENT_STATUSES,
    REGION_WEIGHTS,
    REGIONS,
    SEED,
    START_DATE,
    END_DATE,
    WEEKDAY_FACTORS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-day baseline: converted from spec's 300–800 range.
# We fix baseline at 500 orders/day and let weekday factor + noise vary it.
# ---------------------------------------------------------------------------
BASELINE_ORDERS_PER_DAY: int = 500


def _build_incident_index() -> dict[date, dict]:
    """Build a lookup from calendar date to the incident active on that day.

    Args: None

    Returns:
        Dict mapping ``date`` → incident dict from INCIDENT_CALENDAR.
        Only one incident per day is stored; if two coincide the last one wins
        (spec has no overlapping incidents on the same exact day).
    """
    index: dict[date, dict] = {}
    for inc in INCIDENT_CALENDAR:
        incident_date = START_DATE + timedelta(days=inc["day"] - 1)
        index[incident_date] = inc
    return index


def _order_count_for_day(
    day: date, incident_index: dict[date, dict], rng: np.random.Generator
) -> int:
    """Calculate how many orders to generate for a given simulation day.

    Applies weekday factor and any incident-driven order-count reduction.

    Args:
        day: The calendar date being simulated.
        incident_index: Lookup from date → incident dict.
        rng: Seeded random generator.

    Returns:
        Integer number of orders to produce for the day.
    """
    weekday = day.weekday()  # 0=Mon … 6=Sun
    wf = WEEKDAY_FACTORS[weekday]
    noise = 1.0 + float(rng.normal(0, 0.05))
    count = int(BASELINE_ORDERS_PER_DAY * wf * noise)

    month_factor = MONTHLY_FACTORS.get(day.month, 1.0)
    holiday_factor = HOLIDAY_SPIKES.get((day.month, day.day), 1.0)
    count = int(count * month_factor * holiday_factor)

    incident = incident_index.get(day)
    if incident:
        drop = incident.get("order_drop_pct") or incident.get("sales_drop_pct", 0.0)
        if drop:
            count = int(count * (1.0 - drop))
        if incident["type"] == "checkout_bug":
            # Checkout bug causes additional conversion failure
            failure_rate = incident.get("failure_rate", 0.15)
            count = int(count * (1.0 - failure_rate))

    return max(count, 1)


def generate_orders(
    products: pd.DataFrame,
    customers: pd.DataFrame,
    seed: int = SEED,
    start_date: date | None = None,
    end_date: date | None = None,
    order_id_start: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate orders and order-items for the full simulation period.

    Iterates day by day from START_DATE to END_DATE, generating realistic
    orders based on product demand weights, region shares, and incident
    modifiers.

    Args:
        products: DataFrame produced by ``generate_products()``.
        customers: DataFrame produced by ``generate_customers()``.
        seed: Random seed for reproducibility.
        start_date: Override start date (defaults to constants.START_DATE).
        end_date: Override end date (defaults to constants.END_DATE).

    Returns:
        Tuple of (orders_df, order_items_df, customers_df) where customers_df
        has ``total_orders`` and ``total_spent`` populated.

    Raises:
        ValueError: If ``products`` or ``customers`` DataFrames are empty.
    """
    if products.empty:
        raise ValueError("products DataFrame is empty")
    if customers.empty:
        raise ValueError("customers DataFrame is empty")

    _start = start_date or START_DATE
    _end = end_date or END_DATE

    rng = np.random.default_rng(seed)
    incident_index = _build_incident_index()

    logger.info("Generating orders from %s to %s", _start, _end)

    # Pre-compute sampling weights for products and build region-customer maps
    demand_weights = products["base_daily_demand"].values.astype(float)
    demand_weights /= demand_weights.sum()

    # Map region → list of customer indices in that region
    region_customer_map: dict[str, list[int]] = {r: [] for r in REGIONS}
    for idx, row in customers.iterrows():
        region_customer_map[row["region"]].append(idx)

    orders_rows: list[dict] = []
    items_rows: list[dict] = []
    order_counter: int = order_id_start
    item_counter: int = 1

    # Accumulators for customer aggregates
    cust_orders: dict[str, int] = {cid: 0 for cid in customers["customer_id"]}
    cust_spent: dict[str, float] = {cid: 0.0 for cid in customers["customer_id"]}

    current_date = _start
    while current_date <= _end:
        day_order_count = _order_count_for_day(current_date, incident_index, rng)

        for _ in range(day_order_count):
            # Assign region
            region = rng.choice(REGIONS, p=REGION_WEIGHTS)

            # Pick customer from region
            cust_pool = region_customer_map[region]
            if not cust_pool:
                cust_pool = list(range(len(customers)))
            cust_idx = int(rng.choice(cust_pool))
            customer_id = customers.loc[cust_idx, "customer_id"]

            # Pick 1–ITEMS_PER_ORDER_HI products (power-law biased)
            n_items = int(rng.integers(ITEMS_PER_ORDER_LO, ITEMS_PER_ORDER_HI + 1))
            chosen_product_indices = rng.choice(
                len(products), size=n_items, replace=False, p=demand_weights
            )

            order_value = 0.0
            discount_amount = 0.0
            order_id = f"ORD-{order_counter:07d}"

            for pid_idx in chosen_product_indices:
                product = products.iloc[pid_idx]
                qty = int(rng.integers(1, 4))
                unit_price = float(product["price"])
                discount_pct = round(float(rng.choice([0.0, 0.05, 0.10, 0.20],
                                                      p=[0.70, 0.15, 0.10, 0.05])), 2)
                line_total = round(unit_price * qty * (1.0 - discount_pct), 2)
                order_value += unit_price * qty
                discount_amount += unit_price * qty * discount_pct

                items_rows.append(
                    {
                        "order_item_id": item_counter,
                        "order_id": order_id,
                        "product_id": product["product_id"],
                        "quantity": qty,
                        "unit_price": unit_price,
                        "discount_pct": discount_pct * 100,
                        "line_total": line_total,
                    }
                )
                item_counter += 1

            order_value = round(order_value, 2)
            discount_amount = round(discount_amount, 2)
            final_value = round(order_value - discount_amount, 2)

            status = str(rng.choice(ORDER_STATUSES, p=ORDER_STATUS_WEIGHTS))
            payment_status = str(rng.choice(PAYMENT_STATUSES, p=PAYMENT_STATUS_WEIGHTS))

            # Random hour within business day for timestamp
            hour = int(rng.integers(8, 22))
            minute = int(rng.integers(0, 60))
            created_at = pd.Timestamp(current_date) + pd.Timedelta(
                hours=hour, minutes=minute
            )

            orders_rows.append(
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "region": region,
                    "created_at": created_at,
                    "order_value": order_value,
                    "discount_amount": discount_amount,
                    "final_value": final_value,
                    "item_count": n_items,
                    "status": status,
                    "payment_status": payment_status,
                    "campaign_id": None,
                    "created_date": current_date,
                }
            )

            cust_orders[customer_id] = cust_orders.get(customer_id, 0) + 1
            cust_spent[customer_id] = cust_spent.get(customer_id, 0.0) + final_value

            order_counter += 1

        current_date += timedelta(days=1)

    orders_df = pd.DataFrame(orders_rows)
    items_df = pd.DataFrame(items_rows)

    # Update customer aggregates
    customers = customers.copy()
    customers["total_orders"] = customers["customer_id"].map(cust_orders).fillna(0).astype(int)
    customers["total_spent"] = customers["customer_id"].map(cust_spent).fillna(0.0).round(2)

    logger.info(
        "Orders generated: %d orders, %d line items over %d days",
        len(orders_df),
        len(items_df),
        (END_DATE - START_DATE).days + 1,
    )
    return orders_df, items_df, customers
