"""Product catalogue generator.

Generates 75 products across 6 categories following the power-law demand
distribution defined in docs/specs/03_data_incident_spec.md section 2.3.

Power-law tiers:
    - Top 10  products (tier A): ~50 % of revenue → high base_daily_demand
    - Next 20 products (tier B): ~30 % of revenue → medium base_daily_demand
    - Remaining 45 products (tier C): ~20 % of revenue → low base_daily_demand

Usage::

    from data_gen.generators.products import generate_products
    df = generate_products()   # returns a pandas DataFrame
"""

import logging
from datetime import date

import numpy as np
import pandas as pd

from data_gen.generators.constants import (
    CATEGORIES,
    NUM_PRODUCTS,
    SEED,
    START_DATE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demand tier boundaries (1-based product rank within global product list)
# ---------------------------------------------------------------------------

TIER_A_COUNT: int = 10   # top 10 → high demand
TIER_B_COUNT: int = 20   # next 20 → medium demand
# remaining 45 → low demand

# Base daily demand ranges per tier (units / day)
TIER_DEMAND: dict[str, tuple[int, int]] = {
    "A": (60, 120),
    "B": (20,  59),
    "C": (2,   19),
}

# Tier assignment is determined by global rank once all products are assembled.
# Products within a category are sorted by price descending before ranking so
# expensive Electronics aren't all lumped into the low tier.


# ---------------------------------------------------------------------------
# Curated product names — one entry per product slot, ordered to match the
# loop in generate_products() (i.e. insertion order within each category).
# Counts must match CATEGORIES exactly: 12+18+15+12+10+8 = 75.
# ---------------------------------------------------------------------------

_PRODUCT_NAMES: dict[str, list[str]] = {
    "Electronics": [
        "ProSound Wireless Headphones",
        "UltraView 4K Monitor",
        "SwiftCharge USB-C Hub",
        "NanoBook Laptop Stand",
        "ClearCam Webcam Pro",
        "EchoBeat Bluetooth Speaker",
        "PixelPad Drawing Tablet",
        "VaultDrive External SSD",
        "AirFlow CPU Cooler",
        "SmartLink WiFi Extender",
        "ZenKeys Mechanical Keyboard",
        "BrightBar LED Desk Light",
    ],
    "Clothing": [
        "Alpine Fleece Hoodie",
        "Urban Stretch Chinos",
        "CloudSoft Crew T-Shirt",
        "Summit Windbreaker Jacket",
        "Coastal Linen Shirt",
        "FitFlex Performance Joggers",
        "Heritage Denim Jeans",
        "Breeze Polo Shirt",
        "ThermalCore Base Layer",
        "Weekend Canvas Shorts",
        "StudioKnit Cardigan",
        "EverSoft Bamboo Socks (3-Pack)",
        "MidLayer Down Vest",
        "Trailhead Cargo Pants",
        "Luxe Modal Loungewear Set",
        "ClassicWeave Oxford Shirt",
        "ActiveDry Running Tee",
        "UrbanEdge Bomber Jacket",
    ],
    "Home & Kitchen": [
        "PureBreeze HEPA Air Purifier",
        "QuickBrew Espresso Maker",
        "ChefEdge Chef's Knife Set",
        "NestWarm Electric Blanket",
        "ClearStore Vacuum Organizer Bags",
        "SteadyPour Gooseneck Kettle",
        "FreshSeal Glass Food Containers (6-Set)",
        "SlimLine Dish Drying Rack",
        "AromaMist Ultrasonic Diffuser",
        "DeepClean Spin Mop System",
        "GrillMaster Cast Iron Pan",
        "EcoWash Laundry Sheets (60-Pack)",
        "TranquilSleep Weighted Blanket",
        "NutriBlend Personal Blender",
        "OakGrove Bamboo Cutting Board",
    ],
    "Beauty & Personal Care": [
        "GlowRx Vitamin C Serum",
        "HydraLift Moisturising Cream",
        "PureMist Facial Spray",
        "SilkSmooth Hair Mask",
        "DefyAge Retinol Eye Cream",
        "CleanSlate Micellar Water",
        "SunGuard SPF 50 Tinted Sunscreen",
        "RevitaScalp Shampoo",
        "BalancePro Toner Pads",
        "DeepDetox Charcoal Face Wash",
        "NailRx Strengthening Treatment",
        "LipLux Hydrating Lip Balm",
    ],
    "Sports & Outdoors": [
        "TrailBlazer Hiking Backpack 40L",
        "FlexCore Yoga Mat",
        "IronGrip Adjustable Dumbbell Set",
        "SpeedRun GPS Running Watch",
        "HydroFlow Insulated Water Bottle",
        "CorePress Resistance Bands Kit",
        "CampLight Solar Lantern",
        "WaveRider Swim Goggles",
        "SkyReach Trekking Pole Pair",
        "SweatBlock Cooling Towel",
    ],
    "Books & Media": [
        "The Pragmatic Entrepreneur (Hardcover)",
        "Deep Systems Thinking (Paperback)",
        "Python for Data Science — 3rd Ed.",
        "Mindful Leadership Journal",
        "World History Atlas — Premium Edition",
        "Learn Watercolour Painting Kit + Book",
        "The Great Classics Box Set (10 Books)",
        "Productivity Planner — Annual Edition",
    ],
}


def _assign_tier(rank: int) -> str:
    """Return the demand tier label for a product's 1-based global rank.

    Args:
        rank: 1-based position in the global product list sorted by tier priority.

    Returns:
        "A", "B", or "C".
    """
    if rank <= TIER_A_COUNT:
        return "A"
    if rank <= TIER_A_COUNT + TIER_B_COUNT:
        return "B"
    return "C"


def generate_products(seed: int = SEED) -> pd.DataFrame:
    """Generate the full product catalogue as a DataFrame.

    Follows the power-law demand distribution: top 10 products have
    high base_daily_demand, next 20 medium, remaining 45 low.

    Args:
        seed: Random seed for reproducibility. Defaults to the global SEED.

    Returns:
        DataFrame with columns matching the ``products`` Postgres table:
        product_id, name, category, subcategory, price, cost, margin_pct,
        launch_date, is_active, base_daily_demand, campaign_sensitivity,
        price_sensitivity, created_at.

    Raises:
        ValueError: If CATEGORIES don't sum to NUM_PRODUCTS.
    """
    expected_total = sum(count for _, count, *_ in CATEGORIES)
    if expected_total != NUM_PRODUCTS:
        raise ValueError(
            f"CATEGORIES product counts sum to {expected_total}, expected {NUM_PRODUCTS}"
        )

    rng = np.random.default_rng(seed)
    logger.info("Generating %d products (seed=%d)", NUM_PRODUCTS, seed)

    rows: list[dict] = []
    product_counter: int = 1

    for cat_name, cat_count, price_lo, price_hi, margin_lo, margin_hi in CATEGORIES:
        for i in range(cat_count):
            price = round(float(rng.uniform(price_lo, price_hi)), 2)
            margin = round(float(rng.uniform(margin_lo, margin_hi)), 4)
            cost = round(price * (1.0 - margin), 2)

            # Products launched between 6 months before start and start date
            launch_offset_days = int(rng.integers(0, 180))
            launch_date: date = date(
                START_DATE.year,
                START_DATE.month,
                START_DATE.day,
            )
            launch_date = pd.Timestamp(START_DATE) - pd.Timedelta(days=launch_offset_days)
            launch_date = launch_date.date()

            rows.append(
                {
                    "product_id": f"PROD-{product_counter:03d}",
                    "name": _PRODUCT_NAMES[cat_name][i],
                    "category": cat_name,
                    "subcategory": None,
                    "price": price,
                    "cost": cost,
                    "margin_pct": round(margin * 100, 2),
                    "launch_date": launch_date,
                    "is_active": True,
                    # Demand assigned after global tier ranking
                    "_price_for_sort": price,
                    "campaign_sensitivity": round(float(rng.uniform(0.2, 0.9)), 2),
                    "price_sensitivity": round(float(rng.uniform(0.2, 0.9)), 2),
                    "created_at": pd.Timestamp(START_DATE),
                }
            )
            product_counter += 1

    df = pd.DataFrame(rows)

    # -------------------------------------------------------------------
    # Assign demand tiers based on global rank (sort by price desc as proxy
    # for revenue importance before tiers are fixed).
    # -------------------------------------------------------------------
    df = df.sort_values("_price_for_sort", ascending=False).reset_index(drop=True)
    df["_tier"] = [_assign_tier(rank + 1) for rank in range(len(df))]

    demands: list[int] = []
    for _, row in df.iterrows():
        lo, hi = TIER_DEMAND[row["_tier"]]
        demands.append(int(rng.integers(lo, hi + 1)))

    df["base_daily_demand"] = demands

    # Drop internal helpers and restore original sort order by product_id
    df = df.drop(columns=["_price_for_sort", "_tier"])
    df = df.sort_values("product_id").reset_index(drop=True)

    logger.info(
        "Products generated — tier A: %d, tier B: %d, tier C: %d",
        (df["base_daily_demand"] >= TIER_DEMAND["A"][0]).sum(),
        ((df["base_daily_demand"] >= TIER_DEMAND["B"][0]) &
         (df["base_daily_demand"] < TIER_DEMAND["A"][0])).sum(),
        (df["base_daily_demand"] < TIER_DEMAND["B"][0]).sum(),
    )
    return df
