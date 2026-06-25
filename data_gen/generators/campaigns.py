"""Campaign and campaign_daily_metrics generator.

Creates 15 campaigns and their daily performance metrics for the full
simulation period.  Campaign-pause incidents (Day 18, Day 55) are injected
by setting ``status='paused'`` and zeroing metrics on the affected days.

Usage::

    from data_gen.generators.campaigns import generate_campaigns
    campaigns_df, metrics_df = generate_campaigns(products_df)
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from data_gen.generators.constants import (
    CAMPAIGN_CHANNELS,
    END_DATE,
    INCIDENT_CALENDAR,
    NUM_CAMPAIGNS,
    REGIONS,
    SEED,
    START_DATE,
    WEEKDAY_FACTORS,
)

logger = logging.getLogger(__name__)

# Daily budget per campaign (USD)
BUDGET_RANGE: tuple[float, float] = (200.0, 2_000.0)

# CPM (cost per 1,000 impressions)
CPM_RANGE: tuple[float, float] = (3.0, 15.0)

# Baseline CTR range
CTR_RANGE: tuple[float, float] = (0.008, 0.035)

# Baseline conversion rate range
CVR_RANGE: tuple[float, float] = (0.012, 0.04)

# Average order value for campaign-attributed orders ($)
AOV_CAMPAIGN: float = 65.0


def _build_pause_map(
    campaigns_df: pd.DataFrame,
) -> dict[date, set[str]]:
    """Build a lookup from date → set of campaign_ids to pause.

    Selects campaigns that are actually active on the incident date so the
    pause is always visible in the metrics output:
        - Incident 2 (Day 18): highest-budget campaign active on that day.
        - Incident 9 (Day 55): a display-channel campaign active on that day
          (fallback: any active campaign).

    Args:
        campaigns_df: DataFrame of campaign definitions (must have campaign_id,
            channel, daily_budget, start_date, end_date columns).

    Returns:
        Dict mapping calendar date → set of campaign_id strings to pause.
    """
    pause_map: dict[date, set[str]] = {}

    for inc in INCIDENT_CALENDAR:
        if inc["type"] != "campaign_paused":
            continue

        inc_date = START_DATE + timedelta(days=inc["day"] - 1)

        # Active campaigns on the incident date
        active = campaigns_df[
            (pd.to_datetime(campaigns_df["start_date"]).dt.date <= inc_date)
            & (pd.to_datetime(campaigns_df["end_date"]).dt.date >= inc_date)
        ]

        if active.empty:
            continue

        if inc["day"] == 18:
            # Pause the single highest-budget campaign
            top = active.sort_values("daily_budget", ascending=False).iloc[0]
            pause_map[inc_date] = {top["campaign_id"]}
        elif inc["day"] == 55:
            # Prefer display channel; fall back to highest budget
            display = active[active["channel"] == "display"]
            if not display.empty:
                chosen = display.sort_values("daily_budget", ascending=False).iloc[0]
            else:
                chosen = active.sort_values("daily_budget", ascending=False).iloc[0]
            pause_map[inc_date] = {chosen["campaign_id"]}

    return pause_map


def generate_campaign_metrics(
    campaigns_df: pd.DataFrame,
    start_date: date,
    end_date: date,
    seed: int = SEED,
) -> pd.DataFrame:
    """Generate daily performance metrics for existing campaigns over a date range.

    Args:
        campaigns_df: DataFrame of campaign definitions (from generate_campaigns).
        start_date: First date to generate metrics for.
        end_date: Last date to generate metrics for (inclusive).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame matching the ``campaign_daily_metrics`` Postgres table.
    """
    rng = np.random.default_rng(seed)
    pause_map = _build_pause_map(campaigns_df)
    multi_factor_date = START_DATE + timedelta(days=34)  # anchored to original start

    metrics_rows: list[dict] = []

    for _i, camp in campaigns_df.iterrows():
        cpm = float(rng.uniform(*CPM_RANGE))
        base_ctr = float(rng.uniform(*CTR_RANGE))
        base_cvr = float(rng.uniform(*CVR_RANGE))
        camp_start: date = pd.Timestamp(camp["start_date"]).date()
        camp_end: date = pd.Timestamp(camp["end_date"]).date()

        current_date = start_date
        while current_date <= end_date:
            if current_date < camp_start or current_date > camp_end:
                current_date += timedelta(days=1)
                continue

            paused_ids = pause_map.get(current_date, set())
            is_paused = camp["campaign_id"] in paused_ids

            if is_paused:
                metrics_rows.append(
                    {
                        "campaign_id": camp["campaign_id"],
                        "date": current_date,
                        "status": "paused",
                        "impressions": 0,
                        "clicks": 0,
                        "conversions": 0,
                        "spend": 0.0,
                        "attributed_revenue": 0.0,
                        "ctr": None,
                        "conversion_rate": None,
                        "roas": None,
                    }
                )
                current_date += timedelta(days=1)
                continue

            weekday = current_date.weekday()
            wf = WEEKDAY_FACTORS[weekday]
            noise = 1.0 + float(rng.normal(0, 0.05))

            ctr_today = base_ctr
            if camp["channel"] == "social" and current_date == multi_factor_date:
                ctr_today *= 0.50

            spend = round(float(camp["daily_budget"]) * wf * noise, 2)
            impressions = max(1, int(spend / cpm * 1_000 * wf * noise))
            clicks = max(0, int(impressions * ctr_today * (1 + float(rng.normal(0, 0.05)))))
            conversions = max(0, int(clicks * base_cvr * (1 + float(rng.normal(0, 0.05)))))
            attributed_revenue = round(conversions * AOV_CAMPAIGN * (1 + float(rng.normal(0, 0.03))), 2)

            ctr_val = round(clicks / impressions, 6) if impressions > 0 else None
            cvr_val = round(conversions / clicks, 6) if clicks > 0 else None
            roas_val = round(attributed_revenue / spend, 2) if spend > 0 else None

            metrics_rows.append(
                {
                    "campaign_id": camp["campaign_id"],
                    "date": current_date,
                    "status": "active",
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": conversions,
                    "spend": spend,
                    "attributed_revenue": attributed_revenue,
                    "ctr": ctr_val,
                    "conversion_rate": cvr_val,
                    "roas": roas_val,
                }
            )

            current_date += timedelta(days=1)

    return pd.DataFrame(metrics_rows)


def generate_campaigns(
    products: pd.DataFrame,
    seed: int = SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate campaign definitions and daily performance metrics.

    Each campaign is active for a random window within the simulation period.
    CTR drops 50 % on Day 35 for the social-channel campaign (multi-factor
    incident: ad fatigue).

    Args:
        products: DataFrame from ``generate_products()``.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (campaigns_df, metrics_df) where:
            - campaigns_df matches the ``campaigns`` Postgres table.
            - metrics_df matches the ``campaign_daily_metrics`` Postgres table.

    Raises:
        ValueError: If ``products`` is empty.
    """
    if products.empty:
        raise ValueError("products DataFrame is empty")

    rng = np.random.default_rng(seed)

    total_days = (END_DATE - START_DATE).days + 1
    logger.info("Generating %d campaigns", NUM_CAMPAIGNS)

    # -----------------------------------------------------------------------
    # Build campaign definitions
    # -----------------------------------------------------------------------
    campaigns: list[dict] = []
    channels_assigned: list[str] = []

    for i in range(NUM_CAMPAIGNS):
        channel = CAMPAIGN_CHANNELS[i % len(CAMPAIGN_CHANNELS)]
        channels_assigned.append(channel)

        # Random subset of products (2-6 products per campaign)
        n_prods = int(rng.integers(2, 7))
        target_products = products["product_id"].sample(
            n=n_prods, random_state=int(rng.integers(0, 10_000))
        ).tolist()

        # Random subset of regions (1-4)
        n_regions = int(rng.integers(1, len(REGIONS) + 1))
        target_regions = list(
            rng.choice(REGIONS, size=n_regions, replace=False)
        )

        # Campaign window: start anywhere in the simulation year, run 20-60 days
        max_start_offset = total_days - 20  # leave at least 20 days before END_DATE
        campaign_start_offset = int(rng.integers(0, max(1, max_start_offset)))
        duration = int(rng.integers(20, 61))
        camp_start = START_DATE + timedelta(days=campaign_start_offset)
        camp_end = min(
            camp_start + timedelta(days=duration - 1), END_DATE
        )

        budget = round(float(rng.uniform(*BUDGET_RANGE)), 2)

        campaigns.append(
            {
                "campaign_id": f"CAMP-{i + 1:03d}",
                "name": f"{channel.replace('_', ' ').title()} Campaign {i + 1:02d}",
                "channel": channel,
                "target_products": target_products,
                "target_regions": target_regions,
                "start_date": camp_start,
                "end_date": camp_end,
                "daily_budget": budget,
                "status": "completed",
                "created_at": pd.Timestamp(START_DATE),
            }
        )

    campaigns_df = pd.DataFrame(campaigns)

    # Build daily metrics using the shared helper
    metrics_df = generate_campaign_metrics(campaigns_df, START_DATE, END_DATE, seed)

    logger.info(
        "Campaigns generated: %d definitions, %d daily metric rows, %d paused days",
        len(campaigns_df),
        len(metrics_df),
        (metrics_df["status"] == "paused").sum(),
    )
    return campaigns_df, metrics_df
