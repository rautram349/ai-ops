"""Main data generation ai_ops_engine for E-commerce Operations Brain.

Calls all domain generators in dependency order, then loads every DataFrame
into Postgres using psycopg2 COPY (via ``pandas.to_sql`` with a raw
connection) for maximum throughput.  Also exports CSV backups to
``data_gen/output/``.

Dependency order:
    1.  products          — no dependencies
    2.  customers         — no dependencies
    3.  campaigns         — depends on products
    4.  orders            — depends on products, customers
        order_items       — produced alongside orders
        customers (upd.)  — total_orders / total_spent fields populated
    5.  inventory         — depends on products, order_items
    6.  traffic           — no runtime dependencies (incident calendar only)
    7.  support_tickets   — depends on orders, customers, products
    8.  reviews           — depends on orders, order_items, customers, products
    9.  returns_refunds   — depends on orders, customers, products, order_items

Usage::

    # Run from project root:
    python -m data_gen.generate

    # Skip CSV export:
    python -m data_gen.generate --no-csv

    # Re-run without re-generating (just reload existing CSVs into Postgres):
    python -m data_gen.generate --from-csv

    # Wipe the business tables before loading (idempotent re-run):
    python -m data_gen.generate --truncate

Environment:
    DATABASE_URL_SYNC — psycopg2 DSN (read from .env or shell)
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

from data_gen.generators.campaigns import generate_campaigns
from data_gen.generators.constants import SEED
from data_gen.generators.customers import generate_customers
from data_gen.generators.inventory import generate_inventory
from data_gen.generators.orders import generate_orders
from data_gen.generators.products import generate_products
from data_gen.generators.returns import generate_returns
from data_gen.generators.reviews import generate_reviews
from data_gen.generators.support import generate_support_tickets
from data_gen.generators.traffic import generate_traffic

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

OUTPUT_DIR: Path = Path(__file__).parent / "output"

# ---------------------------------------------------------------------------
# Table load configuration
# Table name → (DataFrame attr name, list of columns in insertion order,
#               truncate-cascade order)
# Defined separately so we can drive the truncate/load loop generically.
# ---------------------------------------------------------------------------

# Business-data tables must be truncated in reverse FK order.
TRUNCATE_ORDER: list[str] = [
    "returns_refunds",
    "reviews",
    "support_tickets",
    "campaign_daily_metrics",
    "campaigns",
    "order_items",
    "orders",
    "inventory_daily",
    "daily_traffic",
    "customers",
    "products",
]


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------


def _get_connection(database_url: str) -> psycopg2.extensions.connection:
    """Open and return a psycopg2 connection.

    Args:
        database_url: Full psycopg2-compatible DSN string.

    Returns:
        Open psycopg2 connection object.

    Raises:
        SystemExit: If the connection cannot be established.
    """
    try:
        conn = psycopg2.connect(database_url)
        logger.debug("Database connection established")
        return conn
    except psycopg2.OperationalError as exc:
        logger.critical("Cannot connect to the database: %s", exc)
        sys.exit(1)


def _truncate_tables(conn: psycopg2.extensions.connection) -> None:
    """Truncate all business-data tables in safe reverse-FK order.

    Uses TRUNCATE … RESTART IDENTITY CASCADE so sequences reset and all
    FK-dependent rows are also cleared.

    Args:
        conn: Open psycopg2 connection (must not be in a transaction).
    """
    conn.autocommit = False
    table_list = ", ".join(TRUNCATE_ORDER)
    logger.warning("Truncating tables: %s", table_list)
    with conn.cursor() as cur:
        cur.execute(
            f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"
        )
    conn.commit()
    logger.info("Tables truncated")


def _load_df(
    conn: psycopg2.extensions.connection,
    df: pd.DataFrame,
    table: str,
    chunk_size: int = 10_000,
) -> None:
    """Insert a DataFrame into a Postgres table using parameterized executemany.

    Processes rows in chunks to keep memory overhead low.  Each chunk runs
    inside its own transaction so a failure only rolls back the current chunk.

    Args:
        conn: Open psycopg2 connection.
        df: DataFrame whose column names exactly match the target table columns.
        table: Target Postgres table name.
        chunk_size: Number of rows per batch insert.

    Raises:
        psycopg2.Error: If any batch fails; the failing chunk is rolled back.
    """
    if df.empty:
        logger.warning("Skipping load for '%s' — DataFrame is empty", table)
        return

    cols = list(df.columns)
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(cols)
    insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    total = len(df)
    loaded = 0

    # Replace pandas NaN/NaT with None so psycopg2 sends SQL NULL.
    # Cast to object dtype first to prevent NaN from surviving as float in
    # typed columns (e.g. nullable TIMESTAMP cols read as float by pandas).
    df_clean = df.astype(object).where(pd.notnull(df), None)

    # Columns whose values look like Python/numpy list reprs must be converted
    # to plain Python lists before psycopg2 can send them as Postgres arrays.
    # Handles both "['A', 'B']" and "[np.str_('A'), np.str_('B')]" formats.
    import re as _re

    def _parse_list_col(v: object) -> object:
        if not isinstance(v, str) or not v.startswith("["):
            return v
        # Extract every single-quoted token regardless of numpy wrappers
        return _re.findall(r"'([^']*)'", v)

    list_cols = [
        c for c in df_clean.columns
        if df_clean[c].dropna().apply(
            lambda v: isinstance(v, str) and v.startswith("[")
        ).any()
    ]
    for lc in list_cols:
        df_clean[lc] = df_clean[lc].apply(_parse_list_col)

    for start in range(0, total, chunk_size):
        chunk = df_clean.iloc[start : start + chunk_size]
        rows = [tuple(row) for row in chunk.itertuples(index=False, name=None)]
        try:
            with conn.cursor() as cur:
                cur.executemany(insert_sql, rows)
            conn.commit()
            loaded += len(rows)
            logger.debug("  %s: loaded %d / %d rows", table, loaded, total)
        except psycopg2.Error as exc:
            conn.rollback()
            logger.error(
                "Failed to load chunk [%d:%d] into '%s': %s",
                start, start + chunk_size, table, exc,
            )
            raise

    logger.info("Loaded %d rows into '%s'", total, table)


def _save_csv(df: pd.DataFrame, name: str) -> None:
    """Export a DataFrame to a CSV file in the output directory.

    Args:
        df: DataFrame to export.
        name: Base filename (without extension), e.g. ``"products"``.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.csv"
    df.to_csv(path, index=False)
    logger.info("CSV exported: %s (%d rows)", path, len(df))


def _load_csv(name: str) -> pd.DataFrame:
    """Load a previously exported CSV from the output directory.

    Args:
        name: Base filename (without extension).

    Returns:
        DataFrame loaded from the CSV.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
    """
    path = OUTPUT_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    df = pd.read_csv(path, low_memory=False)
    logger.info("CSV loaded: %s (%d rows)", path, len(df))
    return df


# ---------------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------------


def run_generation(seed: int = SEED) -> dict[str, pd.DataFrame]:
    """Execute all generators in dependency order.

    Args:
        seed: Random seed passed to every generator for reproducibility.

    Returns:
        Dict mapping table name → DataFrame for every generated table.
    """
    logger.info("=== Starting data generation (seed=%d) ===", seed)
    t0 = time.perf_counter()

    # Step 1 — Products (no dependencies)
    logger.info("Step 1/9  Generating products …")
    products = generate_products(seed=seed)

    # Step 2 — Customers (no dependencies)
    logger.info("Step 2/9  Generating customers …")
    customers = generate_customers(seed=seed)

    # Step 3 — Campaigns (depends on products)
    logger.info("Step 3/9  Generating campaigns …")
    campaigns, campaign_metrics = generate_campaigns(products, seed=seed)

    # Step 4 — Orders + order_items (depends on products, customers)
    logger.info("Step 4/9  Generating orders and order items …")
    orders, order_items, customers = generate_orders(products, customers, seed=seed)

    # Attach region to order_items for inventory generator
    order_region = orders[["order_id", "region", "created_date"]].copy()
    order_items = order_items.merge(order_region, on="order_id", how="left")

    # Step 5 — Inventory (depends on products, order_items)
    logger.info("Step 5/9  Generating inventory …")
    inventory = generate_inventory(products, order_items, seed=seed)

    # Step 6 — Traffic (incident calendar only)
    logger.info("Step 6/9  Generating daily traffic …")
    traffic = generate_traffic(seed=seed)

    # Step 7 — Support tickets (depends on orders, customers, products)
    logger.info("Step 7/9  Generating support tickets …")
    support = generate_support_tickets(orders, customers, products, seed=seed)

    # Step 8 — Reviews (depends on orders, order_items, customers, products)
    logger.info("Step 8/9  Generating reviews …")
    reviews = generate_reviews(orders, order_items, customers, products, seed=seed)

    # Step 9 — Returns (depends on orders, customers, products, order_items)
    logger.info("Step 9/9  Generating returns …")
    returns = generate_returns(orders, customers, products, order_items, seed=seed)

    elapsed = time.perf_counter() - t0
    logger.info("=== Data generation complete in %.1f s ===", elapsed)

    return {
        "products": products,
        "customers": customers,
        "campaigns": campaigns,
        "campaign_daily_metrics": campaign_metrics,
        "orders": orders,
        "order_items": order_items,
        "inventory_daily": inventory,
        "daily_traffic": traffic,
        "support_tickets": support,
        "reviews": reviews,
        "returns_refunds": returns,
    }


def load_from_csv() -> dict[str, pd.DataFrame]:
    """Load all previously generated DataFrames from CSV files.

    Args: None

    Returns:
        Dict mapping table name → DataFrame (same structure as
        :func:`run_generation`).

    Raises:
        FileNotFoundError: If any expected CSV is missing.
    """
    logger.info("=== Loading data from CSV files ===")
    names = [
        "products", "customers", "campaigns", "campaign_daily_metrics",
        "orders", "order_items", "inventory_daily", "daily_traffic",
        "support_tickets", "reviews", "returns_refunds",
    ]
    return {name: _load_csv(name) for name in names}


# ---------------------------------------------------------------------------
# Postgres load pipeline
# ---------------------------------------------------------------------------


def load_to_postgres(
    conn: psycopg2.extensions.connection,
    data: dict[str, pd.DataFrame],
    truncate: bool = False,
) -> None:
    """Load all DataFrames into Postgres in FK-safe order.

    Args:
        conn: Open psycopg2 connection to the application database.
        data: Dict of table name → DataFrame (from :func:`run_generation`).
        truncate: If True, truncate all business tables before loading.

    Raises:
        psycopg2.Error: If any load operation fails.
    """
    if truncate:
        _truncate_tables(conn)

    logger.info("=== Loading data into Postgres ===")
    t0 = time.perf_counter()

    # FK-safe insertion order (parents before children)
    load_order: list[str] = [
        "products",
        "customers",
        "campaigns",
        "orders",
        "order_items",
        "campaign_daily_metrics",
        "inventory_daily",
        "daily_traffic",
        "support_tickets",
        "reviews",
        "returns_refunds",
    ]

    # Columns to load per table (exclude any internal helper columns).
    # If a table's DataFrame has extra columns, only the listed ones are sent.
    table_columns: dict[str, list[str]] = {
        "products": [
            "product_id", "name", "category", "subcategory", "price", "cost",
            "margin_pct", "launch_date", "is_active", "base_daily_demand",
            "campaign_sensitivity", "price_sensitivity", "created_at",
        ],
        "customers": [
            "customer_id", "name", "email", "region", "registered_at",
            "total_orders", "total_spent",
        ],
        "campaigns": [
            "campaign_id", "name", "channel", "target_products", "target_regions",
            "start_date", "end_date", "daily_budget", "status", "created_at",
        ],
        "orders": [
            "order_id", "customer_id", "region", "created_at", "order_value",
            "discount_amount", "final_value", "item_count", "status",
            "payment_status", "campaign_id", "created_date",
        ],
        "order_items": [
            "order_id", "product_id", "quantity", "unit_price",
            "discount_pct", "line_total",
        ],
        "campaign_daily_metrics": [
            "campaign_id", "date", "status", "impressions", "clicks",
            "conversions", "spend", "attributed_revenue", "ctr",
            "conversion_rate", "roas",
        ],
        "inventory_daily": [
            "product_id", "region", "date", "opening_stock", "units_received",
            "units_sold", "units_returned", "closing_stock", "stockout_hours",
            "lost_demand",
        ],
        "daily_traffic": [
            "date", "region", "channel", "sessions", "unique_visitors",
            "bounce_rate", "avg_session_duration_sec",
        ],
        "support_tickets": [
            "ticket_id", "customer_id", "product_id", "order_id", "region",
            "category", "severity", "subject", "description", "status",
            "created_at", "resolved_at", "created_date",
        ],
        "reviews": [
            "review_id", "product_id", "customer_id", "order_id", "rating",
            "title", "body", "sentiment", "theme", "created_at", "created_date",
        ],
        "returns_refunds": [
            "return_id", "order_id", "customer_id", "product_id", "reason",
            "refund_amount", "status", "requested_at", "processed_at",
            "requested_date",
        ],
    }

    for table in load_order:
        df = data.get(table)
        if df is None:
            logger.warning("No data for table '%s' — skipping", table)
            continue

        cols = table_columns.get(table)
        if cols:
            missing = [c for c in cols if c not in df.columns]
            if missing:
                logger.warning(
                    "Table '%s' is missing expected columns: %s", table, missing
                )
            present = [c for c in cols if c in df.columns]
            df = df[present]

        _load_df(conn, df, table)

    elapsed = time.perf_counter() - t0
    logger.info("=== Postgres load complete in %.1f s ===", elapsed)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_csvs(data: dict[str, pd.DataFrame]) -> None:
    """Export all DataFrames to CSV files in data_gen/output/.

    Args:
        data: Dict of table name → DataFrame.
    """
    logger.info("=== Exporting CSV backups to %s ===", OUTPUT_DIR)
    for name, df in data.items():
        _save_csv(df, name)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed namespace with attributes:
            no_csv (bool): skip CSV export.
            from_csv (bool): skip generation, load from existing CSVs.
            truncate (bool): truncate tables before loading.
            seed (int): random seed override.
    """
    parser = argparse.ArgumentParser(
        description="Generate simulation data and load into Postgres."
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        dest="no_csv",
        help="Skip CSV export (data is only loaded into Postgres).",
    )
    parser.add_argument(
        "--from-csv",
        action="store_true",
        dest="from_csv",
        help="Skip generation; reload data from existing CSV files in data_gen/output/.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate all business tables before loading (idempotent re-run).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Random seed (default: {SEED}).",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        dest="no_db",
        help="Generate and export CSVs only; do not load into Postgres.",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for the data generation pipeline.

    Loads .env, generates (or reloads) all data, optionally exports CSVs,
    and loads into Postgres.

    Raises:
        SystemExit: With exit code 1 on any unrecoverable error.
    """
    load_dotenv()
    args = _parse_args()

    # ------------------------------------------------------------------
    # Step 1: Generate (or reload from CSV)
    # ------------------------------------------------------------------
    try:
        if args.from_csv:
            data = load_from_csv()
        else:
            data = run_generation(seed=args.seed)
    except Exception as exc:
        logger.exception("Data generation failed: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 2: Export CSVs (unless suppressed)
    # ------------------------------------------------------------------
    if not args.no_csv and not args.from_csv:
        try:
            export_csvs(data)
        except Exception as exc:
            logger.error("CSV export failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Step 3: Load into Postgres (unless suppressed)
    # ------------------------------------------------------------------
    if args.no_db:
        logger.info("--no-db flag set; skipping Postgres load")
        return

    database_url = os.getenv("DATABASE_URL_SYNC")
    if not database_url:
        logger.critical(
            "DATABASE_URL_SYNC is not set. "
            "Copy .env.example to .env and fill in the value."
        )
        sys.exit(1)

    conn = _get_connection(database_url)
    try:
        load_to_postgres(conn, data, truncate=args.truncate)
    except Exception as exc:
        logger.exception("Postgres load failed: %s", exc)
        conn.close()
        sys.exit(1)
    finally:
        conn.close()

    logger.info("Done.")


if __name__ == "__main__":
    main()
