"""Inventory (inventory_daily) generator.

Simulates daily stock levels per (product, region) pair for the full
simulation period, applying the inventory constraint model from
docs/specs/03_data_incident_spec.md section 3.3.

Stockout incidents cause ``stockout_hours`` > 0 and record ``lost_demand``
(units that could not be fulfilled).  The two Electronics stockouts on
Day 11 and Day 45 are injected deterministically.

Usage::

    from data_gen.generators.inventory import generate_inventory
    df = generate_inventory(products_df, orders_items_df)
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from data_gen.generators.constants import (
    END_DATE,
    INCIDENT_CALENDAR,
    REGIONS,
    REGION_WEIGHTS,
    SEED,
    START_DATE,
)

logger = logging.getLogger(__name__)

# Initial stock per (product, region) — generous enough to avoid
# accidental stockouts on non-incident days.
INITIAL_STOCK_DAYS: int = 30        # start with ~30 days of demand
RESTOCK_THRESHOLD_DAYS: int = 5     # auto-restock when stock < 5 days of demand
RESTOCK_TO_DAYS: int = 25           # restock up to ~25 days of demand


def _incident_stockout_products(
    incident: dict, products: pd.DataFrame
) -> list[str]:
    """Return the product_ids that are forced to stock out for a given incident.

    Args:
        incident: Entry from INCIDENT_CALENDAR.
        products: Products DataFrame, sorted by base_daily_demand desc.

    Returns:
        List of product_id strings that should hit zero stock on the incident day.
    """
    tier = incident.get("affected_tier", "")
    cat_filter = incident.get("category")
    result: list[str] = []

    if "top2_electronics" in tier:
        elec = products[products["category"] == "Electronics"].sort_values(
            "base_daily_demand", ascending=False
        )
        result = elec["product_id"].head(2).tolist()
    elif "top3_beauty" in tier:
        beauty = products[products["category"] == "Beauty & Personal Care"].sort_values(
            "base_daily_demand", ascending=False
        )
        result = beauty["product_id"].head(3).tolist()
    elif cat_filter:
        cat_prods = products[products["category"] == cat_filter].sort_values(
            "base_daily_demand", ascending=False
        )
        result = cat_prods["product_id"].head(5).tolist()

    return result


def generate_inventory(
    products: pd.DataFrame,
    order_items: pd.DataFrame,
    seed: int = SEED,
    start_date: date | None = None,
    end_date: date | None = None,
    initial_stock: dict[tuple[str, str], int] | None = None,
) -> pd.DataFrame:
    """Generate daily inventory records for all (product, region) pairs.

    For each day, computes:
        - ``units_sold`` from the order_items DataFrame (ground truth)
        - ``closing_stock`` = opening_stock + units_received - units_sold + units_returned
        - ``stockout_hours`` and ``lost_demand`` on incident days

    Auto-restocks when stock falls below RESTOCK_THRESHOLD_DAYS of demand to
    prevent artificial stockouts on non-incident days.

    Args:
        products: DataFrame from ``generate_products()``.
        order_items: DataFrame from ``generate_orders()`` (order_items_df).
        seed: Random seed.
        start_date: Override start date (defaults to constants.START_DATE).
        end_date: Override end date (defaults to constants.END_DATE).
        initial_stock: Dict mapping (product_id, region) -> opening stock
            for the first day; if provided, overrides the calculated starting stock.

    Returns:
        DataFrame with columns matching the ``inventory_daily`` Postgres table:
        product_id, region, date, opening_stock, units_received, units_sold,
        units_returned, closing_stock, stockout_hours, lost_demand.

    Raises:
        ValueError: If ``products`` or ``order_items`` DataFrames are empty.
    """
    if products.empty:
        raise ValueError("products DataFrame is empty")
    if order_items.empty:
        raise ValueError("order_items DataFrame is empty")

    _start = start_date or START_DATE
    _end = end_date or END_DATE

    rng = np.random.default_rng(seed)

    # Build incident stockout lookup: date → list of product_ids to zero out
    stockout_map: dict[date, list[str]] = {}
    stockout_hours_map: dict[date, dict[str, float]] = {}
    for inc in INCIDENT_CALENDAR:
        if "stockout_hours" in inc:
            inc_date = START_DATE + timedelta(days=inc["day"] - 1)
            affected = _incident_stockout_products(inc, products)
            if affected:
                stockout_map[inc_date] = affected
                hours = float(inc["stockout_hours"])
                stockout_hours_map[inc_date] = {pid: hours for pid in affected}

    # Pre-join order_items with orders to get date per item.
    # order_items has order_id; we need created_date.
    # Pass through a date lookup built from order_items' index.
    # The orders generator puts created_date on orders, not items.
    # We rely on the calling script to attach created_date to order_items if needed.
    # Here we accept order_items as-is; if created_date is missing we skip daily
    # sold-count attribution (inventory becomes approximate).
    has_date = "created_date" in order_items.columns

    # Sales per (product_id, region, date) — aggregated from order_items+orders
    if has_date:
        daily_sales_agg = (
            order_items.groupby(["product_id", "region", "created_date"])["quantity"]
            .sum()
        )
        # Pre-build a dict for O(1) lookup: (pid, region, date) -> units_sold
        daily_sales_dict: dict[tuple, int] = {
            k: int(v) for k, v in daily_sales_agg.items()
        }
    else:
        logger.warning(
            "order_items lacks 'created_date'; daily sold counts will use estimated demand"
        )
        daily_sales_dict = {}

    rows: list[dict] = []

    for _, product in products.iterrows():
        pid: str = product["product_id"]
        daily_demand: int = int(product["base_daily_demand"])

        for region in REGIONS:
            # Region share of demand
            region_idx = REGIONS.index(region)
            region_share = REGION_WEIGHTS[region_idx]
            regional_demand = max(1, int(daily_demand * region_share))

            # Opening stock: from initial_stock dict (extension) or default formula
            opening = (
                initial_stock.get((pid, region), int(regional_demand * INITIAL_STOCK_DAYS))
                if initial_stock is not None
                else int(regional_demand * INITIAL_STOCK_DAYS)
            )

            current_date = _start
            while current_date <= _end:
                # Look up actual units sold this day (from orders)
                if has_date:
                    units_sold = daily_sales_dict.get((pid, region, current_date), 0)
                else:
                    noise = 1.0 + float(rng.normal(0, 0.1))
                    units_sold = max(0, int(regional_demand * noise))

                units_received: int = 0
                stockout_hours: float = 0.0
                lost_demand: int = 0
                units_returned: int = max(0, int(rng.poisson(regional_demand * 0.02)))

                # Auto-restock trigger
                if opening < regional_demand * RESTOCK_THRESHOLD_DAYS:
                    units_received = int(regional_demand * RESTOCK_TO_DAYS) - opening
                    units_received = max(units_received, 0)

                # Inject stockout for incident days
                if current_date in stockout_map and pid in stockout_map[current_date]:
                    stockout_hours = stockout_hours_map[current_date].get(pid, 0.0)
                    # Force opening to zero for this product on the incident day
                    units_sold = 0
                    lost_demand = regional_demand
                    units_received = 0  # emergency restock arrives next day
                    opening = 0

                # Clamp units_sold to available stock
                available = opening + units_received
                if units_sold > available:
                    lost_demand = units_sold - available
                    units_sold = available
                    stockout_hours = max(stockout_hours, round(float(rng.uniform(4, 12)), 1))

                closing = opening + units_received - units_sold + units_returned

                rows.append(
                    {
                        "product_id": pid,
                        "region": region,
                        "date": current_date,
                        "opening_stock": opening,
                        "units_received": units_received,
                        "units_sold": units_sold,
                        "units_returned": units_returned,
                        "closing_stock": closing,
                        "stockout_hours": round(stockout_hours, 1),
                        "lost_demand": lost_demand,
                    }
                )

                opening = closing
                current_date += timedelta(days=1)

    df = pd.DataFrame(rows)
    logger.info(
        "Inventory generated: %d rows, %d stockout events",
        len(df),
        (df["stockout_hours"] > 0).sum(),
    )
    return df
