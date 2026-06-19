"""Customer base generator.

Generates 5,000 customers distributed across four regions according to the
region order-share weights in docs/specs/03_data_incident_spec.md section 2.2.

Usage::

    from data_gen.generators.customers import generate_customers
    df = generate_customers()
"""

import logging

import numpy as np
import pandas as pd
from faker import Faker

from data_gen.generators.constants import (
    NUM_CUSTOMERS,
    REGIONS,
    REGION_WEIGHTS,
    SEED,
    START_DATE,
)

logger = logging.getLogger(__name__)


def generate_customers(seed: int = SEED) -> pd.DataFrame:
    """Generate the customer base as a DataFrame.

    Each customer is assigned a region proportional to the REGION_WEIGHTS,
    a realistic name and unique email via Faker, and a registration date
    between one year before and the simulation start date.

    Args:
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns matching the ``customers`` Postgres table:
        customer_id, name, email, region, registered_at, total_orders,
        total_spent.

        ``total_orders`` and ``total_spent`` are initialised to 0 here and
        updated by the orders generator after all orders are created.
    """
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    logger.info("Generating %d customers (seed=%d)", NUM_CUSTOMERS, seed)

    # Assign regions according to share weights
    region_counts = rng.multinomial(NUM_CUSTOMERS, REGION_WEIGHTS)
    regions: list[str] = []
    for region, count in zip(REGIONS, region_counts):
        regions.extend([region] * int(count))
    rng.shuffle(regions)

    rows: list[dict] = []
    seen_emails: set[str] = set()

    for i in range(NUM_CUSTOMERS):
        name = fake.name()

        # Generate a unique email
        base_email = fake.email()
        email = base_email
        suffix = 1
        while email in seen_emails:
            email = f"{base_email.split('@')[0]}+{suffix}@{base_email.split('@')[1]}"
            suffix += 1
        seen_emails.add(email)

        # Registration date: 365 days before start to start date
        days_before = int(rng.integers(0, 366))
        registered_at = pd.Timestamp(START_DATE) - pd.Timedelta(days=days_before)

        rows.append(
            {
                "customer_id": f"CUST-{i + 1:05d}",
                "name": name,
                "email": email,
                "region": regions[i],
                "registered_at": registered_at.date(),
                "total_orders": 0,      # populated by orders generator
                "total_spent": 0.00,    # populated by orders generator
            }
        )

    df = pd.DataFrame(rows)
    logger.info(
        "Customers generated — region breakdown: %s",
        df["region"].value_counts().to_dict(),
    )
    return df
