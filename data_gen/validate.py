"""Data validation script — sanity checks from data spec section 8.

Reads all generated CSVs from data_gen/output/ and verifies every rule
defined in docs/specs/03_data_incident_spec.md section 8 (Data Validation Rules)
plus a set of quantitative checks against the sample snapshots in section 10.

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.

Usage::

    python -m data_gen.validate
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"

# ---------------------------------------------------------------------------
# Colours for terminal output
# ---------------------------------------------------------------------------

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
WARN = f"{YELLOW}WARN{RESET}"

# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------

failures: list[str] = []
warnings: list[str] = []


def check(label: str, condition: bool, detail: str = "", warn_only: bool = False) -> None:
    """Log a single check result and accumulate failures / warnings.

    Args:
        label: Short description of the check being performed.
        condition: True = check passed.
        detail: Extra context appended to the log line.
        warn_only: If True a failure is logged as WARN, not FAIL.
    """
    suffix = f" — {detail}" if detail else ""
    if condition:
        logger.info("%s  %s%s", PASS, label, suffix)
    elif warn_only:
        logger.warning("%s  %s%s", WARN, label, suffix)
        warnings.append(label)
    else:
        logger.error("%s  %s%s", FAIL, label, suffix)
        failures.append(label)


# ---------------------------------------------------------------------------
# Load CSVs
# ---------------------------------------------------------------------------


def load_all() -> dict[str, pd.DataFrame]:
    """Load all generated CSV files from the output directory.

    Returns:
        Dict mapping table name → DataFrame.

    Raises:
        SystemExit: If any required CSV is missing.
    """
    names = [
        "products", "customers", "orders", "order_items",
        "inventory_daily", "campaigns", "campaign_daily_metrics",
        "support_tickets", "reviews", "returns_refunds", "daily_traffic",
    ]
    data: dict[str, pd.DataFrame] = {}
    for name in names:
        path = OUTPUT_DIR / f"{name}.csv"
        if not path.exists():
            logger.critical("Missing CSV: %s", path)
            sys.exit(1)
        data[name] = pd.read_csv(path, low_memory=False)
        logger.debug("Loaded %s (%d rows)", name, len(data[name]))
    return data


# ---------------------------------------------------------------------------
# Individual sanity checks
# ---------------------------------------------------------------------------


def check_no_impossible_sales(orders: pd.DataFrame, inventory: pd.DataFrame) -> None:
    """Rule: Zero units sold for products with zero inventory on that day/region.

    Args:
        orders: orders DataFrame.
        inventory: inventory_daily DataFrame.
    """
    zero_stock = inventory[inventory["opening_stock"] == 0][
        ["product_id", "region", "date"]
    ].copy()
    zero_stock["date"] = pd.to_datetime(zero_stock["date"]).dt.date

    # We check at the inventory level: closing_stock should not be negative
    neg_closing = (inventory["closing_stock"] < 0).sum()
    check(
        "No negative closing_stock in inventory",
        neg_closing == 0,
        detail=f"{neg_closing} rows with closing_stock < 0",
    )

    # units_sold must never exceed opening_stock + units_received
    available = inventory["opening_stock"] + inventory["units_received"]
    over_sold = (inventory["units_sold"] > available).sum()
    check(
        "No units_sold exceeding available stock",
        over_sold == 0,
        detail=f"{over_sold} rows where units_sold > opening + received",
    )


def check_campaign_consistency(
    campaign_metrics: pd.DataFrame, campaigns: pd.DataFrame
) -> None:
    """Rule: No attributed revenue when campaign status is paused.

    Args:
        campaign_metrics: campaign_daily_metrics DataFrame.
        campaigns: campaigns DataFrame.
    """
    paused = campaign_metrics[campaign_metrics["status"] == "paused"]
    bad_revenue = paused[paused["attributed_revenue"].fillna(0) > 0]
    check(
        "No attributed_revenue on paused campaign days",
        len(bad_revenue) == 0,
        detail=f"{len(bad_revenue)} rows with attributed_revenue > 0 while paused",
    )

    bad_clicks = paused[paused["clicks"].fillna(0) > 0]
    check(
        "No clicks on paused campaign days",
        len(bad_clicks) == 0,
        detail=f"{len(bad_clicks)} rows with clicks > 0 while paused",
    )

    # At least 2 campaigns show at least one paused day (incidents #2 and #9)
    paused_campaigns = paused["campaign_id"].nunique()
    check(
        "At least 2 campaigns have paused days (incidents #2 and #9)",
        paused_campaigns >= 2,
        detail=f"{paused_campaigns} distinct campaigns had paused days",
    )


def check_power_law(products: pd.DataFrame, orders: pd.DataFrame, order_items: pd.DataFrame) -> None:
    """Rule: Top 10 products contribute ~50% of revenue on normal days.

    Uses total revenue across all days as a proxy since individual-day slices
    are noisy.

    Args:
        products: products DataFrame.
        orders: orders DataFrame.
        order_items: order_items DataFrame.
    """
    # Revenue per product = sum of line_total
    rev_by_product = (
        order_items.groupby("product_id")["line_total"]
        .sum()
        .reset_index()
        .sort_values("line_total", ascending=False)
    )
    total_rev = rev_by_product["line_total"].sum()
    top10_rev = rev_by_product.head(10)["line_total"].sum()
    top10_pct = top10_rev / total_rev * 100

    check(
        "Top 10 products contribute ≥ 40% of total revenue (power-law)",
        top10_pct >= 40,
        detail=f"top-10 share = {top10_pct:.1f}%  (spec target ~50%)",
    )

    top30_rev = rev_by_product.head(30)["line_total"].sum()
    top30_pct = top30_rev / total_rev * 100
    check(
        "Top 30 products contribute ≥ 75% of total revenue",
        top30_pct >= 75,
        detail=f"top-30 share = {top30_pct:.1f}%  (spec target ~80%)",
    )


def check_incident_visibility(orders: pd.DataFrame) -> None:
    """Rule: Incident days show measurable deviation from baseline.

    Checks Day 11 (stockout), Day 18 (campaign pause), Day 35 (multi-factor),
    Day 40 (checkout bug) by comparing weekday-normalised daily order counts to
    a 10-day pre-window, excluding other known incident days from the window so
    that adjacent incidents do not contaminate the baseline.

    Args:
        orders: orders DataFrame.
    """
    from data_gen.generators.constants import INCIDENT_CALENDAR, START_DATE, WEEKDAY_FACTORS

    START = START_DATE
    orders["created_date"] = pd.to_datetime(orders["created_date"]).dt.date
    daily = orders.groupby("created_date")["order_id"].count().reset_index()
    daily.columns = ["date", "order_count"]
    daily_map = dict(zip(daily["date"], daily["order_count"]))

    # Build a set of all incident dates so they can be excluded from baselines.
    all_incident_dates: set[date] = {
        START + timedelta(days=inc["day"] - 1) for inc in INCIDENT_CALENDAR
    }

    incident_days = [
        (11, f"{START + timedelta(days=10)} — Day 11 (stockout)"),
        (18, f"{START + timedelta(days=17)} — Day 18 (campaign pause)"),
        (35, f"{START + timedelta(days=34)} — Day 35 (multi-factor)"),
        (40, f"{START + timedelta(days=39)} — Day 40 (checkout bug)"),
    ]

    for day_offset, label in incident_days:
        incident_date = START + timedelta(days=day_offset - 1)
        incident_wf = WEEKDAY_FACTORS[incident_date.weekday()]

        # Weekday-normalised baseline: look back up to 10 days, skip other
        # incident days so they don't distort the reference.
        norm_counts: list[float] = []
        for d in range(1, 11):
            candidate = incident_date - timedelta(days=d)
            if candidate < START:
                break
            if candidate in all_incident_dates:
                continue  # skip contaminated days
            raw = daily_map.get(candidate, 0)
            candidate_wf = WEEKDAY_FACTORS[candidate.weekday()]
            # Normalise to "what would this day's count be on the incident weekday?"
            norm_counts.append(raw / candidate_wf * incident_wf)

        if not norm_counts:
            continue
        baseline = sum(norm_counts) / len(norm_counts)
        incident_count = daily_map.get(incident_date, 0)

        if baseline == 0:
            continue

        drop_pct = (baseline - incident_count) / baseline * 100
        check(
            f"Measurable order drop on {label}",
            drop_pct >= 5,
            detail=f"drop = {drop_pct:.1f}%  baseline={baseline:.0f}  incident_day={incident_count}",
        )


def check_lagged_signals(
    support: pd.DataFrame, returns: pd.DataFrame, orders: pd.DataFrame
) -> None:
    """Rule: Complaint/return spikes appear AFTER shipping-delay incident (Day 24).

    Shipping delay on Day 24 (Feb 24):
        - Complaints should spike Day 25–27.
        - Returns should spike Day 27–29.

    Args:
        support: support_tickets DataFrame.
        returns: returns_refunds DataFrame.
        orders: orders DataFrame (for baseline calculation).
    """
    from data_gen.generators.constants import START_DATE
    incident_date = START_DATE + timedelta(days=23)  # Day 24

    support["created_date"] = pd.to_datetime(support["created_date"]).dt.date
    returns["requested_date"] = pd.to_datetime(returns["requested_date"]).dt.date

    # Complaint spike: days 25–27
    spike_range = [
        incident_date + timedelta(days=d) for d in range(1, 4)
    ]
    pre_range = [
        incident_date - timedelta(days=d) for d in range(1, 4)
    ]

    spike_complaints = support[support["created_date"].isin(spike_range)].shape[0]
    pre_complaints = support[support["created_date"].isin(pre_range)].shape[0]

    check(
        "Shipping-delay complaint spike on Days 25–27 (lagged)",
        spike_complaints >= pre_complaints,
        detail=(
            f"spike window={spike_complaints} tickets  "
            f"pre-window={pre_complaints} tickets"
        ),
    )

    # Return spike: days 27–29
    return_spike_range = [
        incident_date + timedelta(days=d) for d in range(3, 6)
    ]
    return_pre_range = [
        incident_date - timedelta(days=d) for d in range(3, 6)
    ]
    spike_returns = returns[returns["requested_date"].isin(return_spike_range)].shape[0]
    pre_returns = returns[returns["requested_date"].isin(return_pre_range)].shape[0]

    check(
        "Shipping-delay return spike on Days 27–29 (lagged)",
        spike_returns > pre_returns,
        detail=(
            f"spike window={spike_returns} returns  "
            f"pre-window={pre_returns} returns"
        ),
    )

    # Rule: returns must reference orders from PRIOR days (never same-day)
    orders["created_date"] = pd.to_datetime(orders["created_date"]).dt.date
    order_dates = orders.set_index("order_id")["created_date"].to_dict()

    returns_with_order_date = returns.copy()
    returns_with_order_date["order_created_date"] = returns_with_order_date["order_id"].map(order_dates)
    same_day = returns_with_order_date[
        returns_with_order_date["requested_date"] == returns_with_order_date["order_created_date"]
    ]
    check(
        "No returns filed on the same day as the triggering order",
        len(same_day) == 0,
        detail=f"{len(same_day)} same-day return(s) found",
    )


def check_region_consistency(orders: pd.DataFrame) -> None:
    """Rule: Regional order share roughly matches targets (±5 %).

    Targets: North 30%, South 25%, East 25%, West 20%.

    Args:
        orders: orders DataFrame.
    """
    targets = {"North": 0.30, "South": 0.25, "East": 0.25, "West": 0.20}
    actual = orders["region"].value_counts(normalize=True)

    for region, target in targets.items():
        actual_share = actual.get(region, 0.0)
        within_tolerance = abs(actual_share - target) <= 0.05
        check(
            f"Region '{region}' share ≈ {target*100:.0f}% (±5%)",
            within_tolerance,
            detail=f"actual = {actual_share*100:.1f}%",
        )


def check_weekday_pattern(orders: pd.DataFrame) -> None:
    """Rule: Weekdays have higher average order volume than weekends.

    Args:
        orders: orders DataFrame.
    """
    orders["created_date"] = pd.to_datetime(orders["created_date"]).dt.date
    orders["weekday"] = pd.to_datetime(orders["created_date"]).dt.dayofweek
    daily = orders.groupby(["created_date", "weekday"])["order_id"].count().reset_index()
    daily.columns = ["date", "weekday", "order_count"]

    weekday_avg = daily[daily["weekday"] < 5]["order_count"].mean()
    weekend_avg = daily[daily["weekday"] >= 5]["order_count"].mean()

    check(
        "Weekday avg orders > weekend avg orders",
        weekday_avg > weekend_avg,
        detail=f"weekday avg={weekday_avg:.0f}  weekend avg={weekend_avg:.0f}",
    )


def check_return_timing(returns: pd.DataFrame, orders: pd.DataFrame) -> None:
    """Rule: Returns reference orders from previous days, not same day.

    This is the same check as in check_lagged_signals but surfaces it
    as an explicit named rule from the spec.

    Args:
        returns: returns_refunds DataFrame.
        orders: orders DataFrame.
    """
    # Already checked in check_lagged_signals; surfaced again for spec completeness
    check(
        "Return timing check (duplicate guard — already checked in lagged signals)",
        True,
        detail="covered by check_lagged_signals",
        warn_only=True,
    )


def check_incident_stockouts(inventory: pd.DataFrame) -> None:
    """Rule: Day 11 and Day 45 show stockout_hours > 0 for Electronics top-2.

    Args:
        inventory: inventory_daily DataFrame.
    """
    from data_gen.generators.constants import START_DATE

    inventory["date"] = pd.to_datetime(inventory["date"]).dt.date

    for day_offset, label in [
        (10, f"Day 11 ({START_DATE + timedelta(days=10)})"),
        (44, f"Day 45 ({START_DATE + timedelta(days=44)})"),
    ]:
        target_date = START_DATE + timedelta(days=day_offset)
        stockout_rows = inventory[
            (inventory["date"] == target_date) & (inventory["stockout_hours"] > 0)
        ]
        check(
            f"Stockout events present on {label}",
            len(stockout_rows) > 0,
            detail=f"{len(stockout_rows)} (product, region) pairs with stockout_hours > 0",
        )

    # Global: total stockout events should be in a reasonable range
    total_stockouts = (inventory["stockout_hours"] > 0).sum()
    check(
        "Total stockout events in plausible range (> 0)",
        total_stockouts > 0,
        detail=f"{total_stockouts} (product, region, day) stockout rows",
    )


def check_schema_completeness(data: dict[str, pd.DataFrame]) -> None:
    """Rule: Row counts are non-zero and plausible for all tables.

    Args:
        data: Dict of table name → DataFrame.
    """
    expected_minimums = {
        "products": 75,
        "customers": 5_000,
        "orders": 10_000,
        "order_items": 15_000,
        "inventory_daily": 1_000,
        "campaigns": 15,
        "campaign_daily_metrics": 100,
        "support_tickets": 200,
        "reviews": 500,
        "returns_refunds": 100,
        "daily_traffic": 1_000,
    }
    for table, minimum in expected_minimums.items():
        df = data.get(table, pd.DataFrame())
        check(
            f"'{table}' has ≥ {minimum:,} rows",
            len(df) >= minimum,
            detail=f"actual = {len(df):,}",
        )


def check_referential_integrity(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
) -> None:
    """Rule: All FKs in order_items resolve to existing orders and products.

    Args:
        orders: orders DataFrame.
        order_items: order_items DataFrame.
        products: products DataFrame.
        customers: customers DataFrame.
    """
    valid_order_ids = set(orders["order_id"])
    valid_product_ids = set(products["product_id"])
    valid_customer_ids = set(customers["customer_id"])

    orphan_items = order_items[~order_items["order_id"].isin(valid_order_ids)]
    check(
        "All order_items.order_id resolve to orders",
        len(orphan_items) == 0,
        detail=f"{len(orphan_items)} orphan items",
    )

    unknown_products = order_items[~order_items["product_id"].isin(valid_product_ids)]
    check(
        "All order_items.product_id resolve to products",
        len(unknown_products) == 0,
        detail=f"{len(unknown_products)} unknown product refs",
    )

    unknown_customers = orders[~orders["customer_id"].isin(valid_customer_ids)]
    check(
        "All orders.customer_id resolve to customers",
        len(unknown_customers) == 0,
        detail=f"{len(unknown_customers)} unknown customer refs",
    )


def check_memory_repeat_pattern(inventory: pd.DataFrame) -> None:
    """Rule: Day 11 and Day 45 stockouts share the same affected product_ids.

    This validates the 'repeat incident' memory test scenario: the agent
    should detect that the same top-2 Electronics products stocked out twice.

    Args:
        inventory: inventory_daily DataFrame.
    """
    from data_gen.generators.constants import START_DATE
    inventory["date"] = pd.to_datetime(inventory["date"]).dt.date

    day11 = START_DATE + timedelta(days=10)
    day45 = START_DATE + timedelta(days=44)

    stockout_11 = set(
        inventory[(inventory["date"] == day11) & (inventory["stockout_hours"] > 0)]["product_id"]
    )
    stockout_45 = set(
        inventory[(inventory["date"] == day45) & (inventory["stockout_hours"] > 0)]["product_id"]
    )

    overlap = stockout_11 & stockout_45
    check(
        "Day 11 and Day 45 stockouts share at least 1 product (repeat incident memory test)",
        len(overlap) > 0,
        detail=f"shared products = {overlap}",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all sanity checks and print a summary.

    Raises:
        SystemExit: With exit code 1 if any check failed.
    """
    logger.info("=== Data Validation — spec section 8 sanity checks ===")
    data = load_all()

    products = data["products"]
    customers = data["customers"]
    orders = data["orders"]
    order_items = data["order_items"]
    inventory = data["inventory_daily"]
    campaigns = data["campaigns"]
    campaign_metrics = data["campaign_daily_metrics"]
    support = data["support_tickets"]
    reviews = data["reviews"]
    returns = data["returns_refunds"]
    traffic = data["daily_traffic"]

    # ------------------------------------------------------------------
    # Spec section 8 rules
    # ------------------------------------------------------------------
    logger.info("\n--- Rule 1: No impossible sales ---")
    check_no_impossible_sales(orders, inventory)

    logger.info("\n--- Rule 2: Campaign consistency ---")
    check_campaign_consistency(campaign_metrics, campaigns)

    logger.info("\n--- Rule 3: Power-law revenue distribution ---")
    check_power_law(products, orders, order_items)

    logger.info("\n--- Rule 4: Incident visibility ---")
    check_incident_visibility(orders)

    logger.info("\n--- Rule 5: Lagged signals ---")
    check_lagged_signals(support, returns, orders)

    logger.info("\n--- Rule 6: Region consistency ---")
    check_region_consistency(orders)

    logger.info("\n--- Rule 7: Weekday pattern ---")
    check_weekday_pattern(orders)

    logger.info("\n--- Rule 8: Return timing ---")
    check_return_timing(returns, orders)

    # ------------------------------------------------------------------
    # Additional structural checks
    # ------------------------------------------------------------------
    logger.info("\n--- Additional: Schema completeness ---")
    check_schema_completeness(data)

    logger.info("\n--- Additional: Referential integrity ---")
    check_referential_integrity(orders, order_items, products, customers)

    logger.info("\n--- Additional: Seeded stockout events ---")
    check_incident_stockouts(inventory)

    logger.info("\n--- Additional: Memory repeat pattern (Days 11 & 45) ---")
    check_memory_repeat_pattern(inventory)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("\n" + "=" * 60)
    if failures:
        logger.error(
            "RESULT: %d check(s) FAILED, %d warning(s)\n  Failed: %s",
            len(failures), len(warnings), "\n  Failed: ".join(failures),
        )
        sys.exit(1)
    else:
        logger.info(
            "RESULT: ALL CHECKS PASSED (%d warning(s))",
            len(warnings),
        )


if __name__ == "__main__":
    main()
