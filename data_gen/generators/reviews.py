"""Product review generator.

Generates reviews following the model in
docs/specs/03_data_incident_spec.md section 3.7.

Baseline: 8 % of daily orders generate a review.
Average rating baseline: 4.1.

Incident-driven rating drops:
    - Day 50 review surge (Sports & Outdoors): avg rating → 3.2 for 2 days.
    - Stockout incidents: slight rating drop (3.8) for affected products.
    - Shipping delay lag days: rating drops to ~3.5 on Days 26-28.

Usage::

    from data_gen.generators.reviews import generate_reviews
    df = generate_reviews(orders_df, order_items_df, customers_df, products_df)
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from data_gen.generators.constants import (
    AVG_RATING_BASELINE,
    END_DATE,
    INCIDENT_CALENDAR,
    REVIEW_RATE,
    REVIEW_THEMES,
    SEED,
    START_DATE,
)

logger = logging.getLogger(__name__)


def _build_rating_modifier_map() -> dict[date, dict]:
    """Build a per-day lookup of rating adjustments from the incident calendar.

    Args: None

    Returns:
        Dict mapping calendar date → modifier dict with:
            ``avg_rating`` (float): override average rating for that day.
            ``category`` (str | None): if set, only affects products in this category.
    """
    modifier_map: dict[date, dict] = {}

    for inc in INCIDENT_CALENDAR:
        inc_date = START_DATE + timedelta(days=inc["day"] - 1)

        if inc["type"] == "review_surge":
            # 2-day surge window
            for lag in range(0, 2):
                d = inc_date + timedelta(days=lag)
                if d <= END_DATE:
                    modifier_map[d] = {
                        "avg_rating": AVG_RATING_BASELINE - float(inc.get("rating_drop", 0.9)),
                        "category": inc.get("category"),
                    }

        elif inc["type"] == "shipping_delay":
            review_lag_lo = 2
            review_lag_hi = 4
            for lag in range(review_lag_lo, review_lag_hi + 1):
                d = inc_date + timedelta(days=lag)
                if d <= END_DATE:
                    modifier_map[d] = {
                        "avg_rating": 3.5,
                        "category": None,       # affects all products
                    }

        elif inc["type"] in ("inventory_stockout", "multi_factor"):
            modifier_map[inc_date] = {
                "avg_rating": 3.8,
                "category": None,
            }

    return modifier_map


def _rating_to_sentiment(rating: int) -> str:
    """Convert a numeric rating to a sentiment label.

    Args:
        rating: Integer 1-5.

    Returns:
        "positive" (4-5), "neutral" (3), or "negative" (1-2).
    """
    if rating >= 4:
        return "positive"
    if rating == 3:
        return "neutral"
    return "negative"


def generate_reviews(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    seed: int = SEED,
    start_date: date | None = None,
    end_date: date | None = None,
    review_id_start: int = 1,
) -> pd.DataFrame:
    """Generate product reviews for the full simulation period.

    Samples a fraction (REVIEW_RATE) of daily orders to produce reviews.
    Each review is linked to a real order and to the primary product in
    that order.  Ratings are drawn from a distribution centred on the
    day's average-rating baseline, modified by active incidents.

    Args:
        orders: DataFrame from ``generate_orders()``.
        order_items: DataFrame from ``generate_orders()`` (items output).
        customers: DataFrame from ``generate_customers()``.
        products: DataFrame from ``generate_products()``.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame matching the ``reviews`` Postgres table:
        review_id, product_id, customer_id, order_id, rating, title, body,
        sentiment, theme, created_at, created_date.

    Raises:
        ValueError: If required DataFrames are empty.
    """
    for label, df in [("orders", orders), ("order_items", order_items), ("products", products)]:
        if df.empty:
            raise ValueError(f"{label} DataFrame is empty")

    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    _start = start_date or START_DATE
    _end = end_date or END_DATE

    rating_map = _build_rating_modifier_map()

    # Primary product per order: pick the highest-value item
    primary_product = (
        order_items.sort_values("line_total", ascending=False)
        .groupby("order_id")["product_id"]
        .first()
        .reset_index()
        .rename(columns={"product_id": "primary_product_id"})
    )
    orders_enriched = orders.merge(primary_product, on="order_id", how="left")
    product_categories = products.set_index("product_id")["category"].to_dict()

    rows: list[dict] = []
    review_counter: int = review_id_start

    current_date = _start
    while current_date <= _end:
        day_orders = orders_enriched[orders_enriched["created_date"] == current_date]
        if day_orders.empty:
            current_date += timedelta(days=1)
            continue

        n_reviews = max(0, int(len(day_orders) * REVIEW_RATE * (1.0 + float(rng.normal(0, 0.1)))))
        if n_reviews == 0:
            current_date += timedelta(days=1)
            continue

        # Sample which orders get reviews
        review_orders = day_orders.sample(
            n=min(n_reviews, len(day_orders)),
            random_state=int(rng.integers(0, 10_000)),
        )

        modifier = rating_map.get(current_date, {})
        base_avg = modifier.get("avg_rating", AVG_RATING_BASELINE)
        affected_category = modifier.get("category")

        for _, order_row in review_orders.iterrows():
            product_id = order_row.get("primary_product_id")
            if pd.isna(product_id):
                continue

            prod_cat = product_categories.get(product_id, "")

            # Apply rating modifier only if category matches (or modifier is global)
            avg = base_avg
            if affected_category and prod_cat != affected_category:
                avg = AVG_RATING_BASELINE

            # Draw rating: clamp discrete draw from normal distribution
            raw_rating = float(rng.normal(avg, 0.6))
            rating = int(max(1, min(5, round(raw_rating))))

            sentiment = _rating_to_sentiment(rating)
            theme = str(rng.choice(REVIEW_THEMES))

            # Review posted 1-5 days after order creation
            review_lag = int(rng.integers(1, 6))
            created_at = pd.Timestamp(order_row["created_at"]) + pd.Timedelta(days=review_lag)
            review_date = created_at.date()
            if review_date > _end:
                review_date = _end
                created_at = pd.Timestamp(_end)

            rows.append(
                {
                    "review_id": f"REV-{review_counter:06d}",
                    "product_id": product_id,
                    "customer_id": order_row["customer_id"],
                    "order_id": order_row["order_id"],
                    "rating": rating,
                    "title": fake.sentence(nb_words=6).rstrip("."),
                    "body": fake.paragraph(nb_sentences=2),
                    "sentiment": sentiment,
                    "theme": theme,
                    "created_at": created_at,
                    "created_date": review_date,
                }
            )
            review_counter += 1

        current_date += timedelta(days=1)

    df = pd.DataFrame(rows)
    logger.info(
        "Reviews generated: %d total — positive: %d, neutral: %d, negative: %d",
        len(df),
        (df["sentiment"] == "positive").sum(),
        (df["sentiment"] == "neutral").sum(),
        (df["sentiment"] == "negative").sum(),
    )
    return df
