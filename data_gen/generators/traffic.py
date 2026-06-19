"""Daily web traffic generator.

Generates rows for the ``daily_traffic`` table following the traffic model in
docs/specs/03_data_incident_spec.md section 3.1.

For each (date, region, channel) combination the generator computes:
    - Sessions based on baseline, weekday factor, campaign lift, and noise.
    - Unique visitors ≈ 70–85 % of sessions.
    - Bounce rate and avg session duration with light noise.

Incident modifiers:
    - Campaign-pause incidents reduce paid_search / display traffic on the
      affected day.
    - Checkout bug (Day 40) does not affect traffic (traffic is normal but
      conversion fails — captured in orders).

Usage::

    from data_gen.generators.traffic import generate_traffic
    df = generate_traffic(campaigns_df, campaign_metrics_df)
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from data_gen.generators.constants import (
    BASE_DAILY_SESSIONS,
    CHANNEL_WEIGHTS,
    END_DATE,
    INCIDENT_CALENDAR,
    REGIONS,
    REGION_WEIGHTS,
    SEED,
    START_DATE,
    TRAFFIC_CHANNELS,
    WEEKDAY_FACTORS,
)

logger = logging.getLogger(__name__)

# Bounce rate range (fraction 0–1)
BOUNCE_RATE_LO: float = 0.30
BOUNCE_RATE_HI: float = 0.65

# Avg session duration in seconds
AVG_SESSION_DURATION_LO: int = 60
AVG_SESSION_DURATION_HI: int = 300

# Unique visitor ratio relative to sessions
UNIQUE_VISITOR_RATIO_LO: float = 0.70
UNIQUE_VISITOR_RATIO_HI: float = 0.85


def _build_traffic_modifier_map() -> dict[date, dict]:
    """Build a per-day mapping of channel-level traffic multipliers.

    Campaign-pause incidents reduce the paid_search or display channel
    contribution on the affected day.

    Args: None

    Returns:
        Dict mapping calendar date → dict with key ``channel_multipliers``
        (dict[str, float]).
    """
    modifier_map: dict[date, dict] = {}

    for inc in INCIDENT_CALENDAR:
        if inc["type"] != "campaign_paused":
            continue
        inc_date = START_DATE + timedelta(days=inc["day"] - 1)
        drop = inc.get("traffic_drop_pct", 0.20)

        if inc["day"] == 18:
            # Highest-spend paid_search campaign paused
            modifier_map[inc_date] = {
                "channel_multipliers": {"paid_search": 1.0 - drop},
            }
        elif inc["day"] == 55:
            # Display campaign paused, concentrated in East region
            modifier_map[inc_date] = {
                "channel_multipliers": {"display": 1.0 - drop},
                "region_filter": "East",
            }

    return modifier_map


def generate_traffic(
    seed: int = SEED,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Generate daily web traffic records for all (date, region, channel) pairs.

    Args:
        seed: Random seed for reproducibility.
        start_date: Override start date (defaults to constants.START_DATE).
        end_date: Override end date (defaults to constants.END_DATE).

    Returns:
        DataFrame matching the ``daily_traffic`` Postgres table:
        date, region, channel, sessions, unique_visitors, bounce_rate,
        avg_session_duration_sec.
    """
    _start = start_date or START_DATE
    _end = end_date or END_DATE

    rng = np.random.default_rng(seed)
    modifier_map = _build_traffic_modifier_map()

    rows: list[dict] = []

    current_date = _start
    while current_date <= _end:
        weekday = current_date.weekday()
        wf = WEEKDAY_FACTORS[weekday]
        modifier = modifier_map.get(current_date, {})
        channel_multipliers: dict[str, float] = modifier.get("channel_multipliers", {})
        region_filter: str | None = modifier.get("region_filter")

        for region, r_weight in zip(REGIONS, REGION_WEIGHTS):
            for channel, c_weight in zip(TRAFFIC_CHANNELS, CHANNEL_WEIGHTS):
                noise = 1.0 + float(rng.normal(0, 0.05))

                # Apply incident channel modifier (region-filtered if needed)
                ch_mult = 1.0
                if channel in channel_multipliers:
                    if region_filter is None or region == region_filter:
                        ch_mult = channel_multipliers[channel]

                sessions = max(
                    1,
                    int(
                        BASE_DAILY_SESSIONS
                        * r_weight
                        * c_weight
                        * wf
                        * ch_mult
                        * noise
                    ),
                )

                uv_ratio = float(rng.uniform(UNIQUE_VISITOR_RATIO_LO, UNIQUE_VISITOR_RATIO_HI))
                unique_visitors = max(1, int(sessions * uv_ratio))

                bounce_rate = round(
                    float(rng.uniform(BOUNCE_RATE_LO, BOUNCE_RATE_HI)), 4
                )
                avg_session_duration = int(
                    rng.integers(AVG_SESSION_DURATION_LO, AVG_SESSION_DURATION_HI + 1)
                )

                rows.append(
                    {
                        "date": current_date,
                        "region": region,
                        "channel": channel,
                        "sessions": sessions,
                        "unique_visitors": unique_visitors,
                        "bounce_rate": bounce_rate,
                        "avg_session_duration_sec": avg_session_duration,
                    }
                )

        current_date += timedelta(days=1)

    df = pd.DataFrame(rows)
    logger.info(
        "Traffic generated: %d rows across %d days, %d regions, %d channels",
        len(df),
        (_end - _start).days + 1,
        len(REGIONS),
        len(TRAFFIC_CHANNELS),
    )
    return df
