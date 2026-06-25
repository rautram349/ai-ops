"""One-time Langfuse dataset setup script.

Creates the ``ecommerce_ops_brain_evals`` dataset in Langfuse cloud and
uploads all 16 scenario items from ``evals/scenarios/``.

Usage:
    python -m evals.setup_langfuse
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env", override=True)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
DATASET_NAME = "ecommerce_ops_brain_evals"


def main() -> None:
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    host = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"

    if not sk or sk.startswith("sk-lf-..."):
        print("ERROR: LANGFUSE_SECRET_KEY not configured in .env")
        sys.exit(1)

    try:
        from langfuse import Langfuse
    except ImportError:
        print("ERROR: langfuse package not installed. Run: pip install langfuse")
        sys.exit(1)

    lf = Langfuse(secret_key=sk, public_key=pk, host=host)
    print(f"Connected to Langfuse at {host}")

    # Create or get existing dataset
    try:
        lf.create_dataset(
            name=DATASET_NAME,
            description="E-commerce Operations Brain — 16 benchmark eval scenarios",
        )
        print(f"Dataset created: {DATASET_NAME}")
    except Exception as exc:
        # Dataset may already exist — proceed
        print(f"Note: {exc}  (dataset may already exist — continuing)")

    # Load and upload scenario files
    scenario_paths = sorted(SCENARIOS_DIR.glob("scenario_*.json"))
    print(f"\nUploading {len(scenario_paths)} scenarios …")

    for path in scenario_paths:
        with open(path, encoding="utf-8") as f:
            scenario = json.load(f)

        sid = scenario.get("id", path.stem)
        is_multi = scenario.get("multi_turn", False)

        if is_multi:
            # Multi-turn: use first turn's prompt as the dataset item input
            first_prompt = scenario["turns"][0]["prompt"] if scenario.get("turns") else "(multi-turn)"
            item_input = {"message": first_prompt, "multi_turn": True, "turns": [t["prompt"] for t in scenario.get("turns", [])]}
        else:
            item_input = {"message": scenario.get("prompt", "")}

        expected_output = {
            "checks": [
                {"id": c["id"], "type": c["type"], "expected": c.get("expected")}
                for c in (scenario.get("checks") or
                          [c for t in scenario.get("turns", []) for c in t.get("checks", [])])
            ]
        }

        try:
            lf.create_dataset_item(
                dataset_name=DATASET_NAME,
                input=item_input,
                expected_output=expected_output,
                metadata={
                    "scenario_id": sid,
                    "scenario_name": scenario.get("name", ""),
                    "incident_ref": scenario.get("incident_ref"),
                    "max_points": scenario.get("max_points", 0),
                    "multi_turn": is_multi,
                },
            )
            print(f"  ✓ {sid}  —  {scenario.get('name', '')}")
        except Exception as exc:
            print(f"  ✗ {sid}: {exc}")

    lf.flush()
    print(f"\nDone. View dataset at: {host.rstrip('/')}/datasets/{DATASET_NAME}")


if __name__ == "__main__":
    main()
