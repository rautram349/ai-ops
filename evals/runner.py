"""Async eval runner — calls ``run_graph()`` directly and scores each scenario.

Usage:
    # Run a single scenario
    python -m evals.runner --scenario scenario_01

    # Run all scenarios (default)
    python -m evals.runner

    # Run all and push scores to Langfuse
    python -m evals.runner --all --langfuse

    # Run without pushing scores to Langfuse
    python -m evals.runner --no-langfuse

Results are saved as timestamped JSON in evals/results/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Rich for pretty terminal output ──────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich import print as rprint
    _RICH = True
except ImportError:
    _RICH = False
    Console = None  # type: ignore[assignment,misc]

# ── Project root on sys.path ──────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env", override=True)

from ai_ops_engine.graph.builder import run_graph
from evals.scoring import (
    ScenarioScore,
    score_scenario,
    score_multi_turn,
)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
RESULTS_DIR = Path(__file__).parent / "results"


# ── Langfuse helper ───────────────────────────────────────────────────────────

def _get_langfuse_client():
    """Return a Langfuse client if env vars are configured, else None."""
    try:
        sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        host = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        if not sk or sk.startswith("sk-lf-...") or not pk or pk.startswith("pk-lf-..."):
            return None
        from langfuse import Langfuse
        return Langfuse(secret_key=sk, public_key=pk, host=host)
    except Exception:
        return None


def _push_score(
    lf,
    scenario_score: ScenarioScore,
    trace_id: str | None,
    scenario_id: str,
) -> None:
    """Push eval score to Langfuse. Silently skips on any error."""
    if lf is None or trace_id is None:
        return
    try:
        lf.create_score(
            trace_id=trace_id,
            name=f"eval_{scenario_id}",
            value=scenario_score.pass_rate,
            comment=f"{scenario_score.total_points}/{scenario_score.max_points}p — "
                    + ("PASS" if scenario_score.passed else "FAIL"),
        )
    except Exception:
        pass


# ── Scenario runner ───────────────────────────────────────────────────────────

async def run_single_scenario(
    scenario: dict[str, Any],
    lf=None,
) -> tuple[ScenarioScore, dict[str, Any]]:
    """Run one scenario (single or multi-turn) and return score + raw result."""
    is_multi = scenario.get("multi_turn", False)

    if is_multi:
        turns = scenario.get("turns", [])
        turn_results: list[dict[str, Any]] = []
        conversation_history: list[dict] = []
        last_trace_id: str | None = None

        for turn_def in turns:
            prompt: str = turn_def["prompt"]
            result = await run_graph(
                user_query=prompt,
                conversation_history=conversation_history,
            )
            last_trace_id = result.get("langfuse_trace_id")
            turn_results.append(result)
            conversation_history.append({"role": "user", "content": prompt})
            conversation_history.append({"role": "assistant", "content": result.get("response_summary", "")})

        scenario_score = score_multi_turn(scenario, turn_results)
        _push_score(lf, scenario_score, last_trace_id, scenario["id"])
        raw = {"turns": [{"intent": r.get("intent"), "needs_write": r.get("needs_write")} for r in turn_results]}

    else:
        prompt = scenario["prompt"]
        result = await run_graph(user_query=prompt)
        scenario_score = score_scenario(scenario, result)
        _push_score(lf, scenario_score, result.get("langfuse_trace_id"), scenario["id"])
        raw = {
            "intent": result.get("intent"),
            "needs_write": result.get("needs_write"),
            "tool_results_count": len(result.get("tool_results", [])),
            "tools_called": [r.get("tool") for r in result.get("tool_results", [])],
            "response_summary_snippet": result.get("response_summary", "")[:300],
        }

    return scenario_score, raw


def _load_scenario(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_results(
    run_dir: Path,
    scenario_id: str,
    score: ScenarioScore,
    raw: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "scenario_id": scenario_id,
        "scenario_name": score.scenario_name,
        "total_points": score.total_points,
        "max_points": score.max_points,
        "pass_rate": round(score.pass_rate, 4),
        "passed": score.passed,
        "checks": [
            {
                "id": c.id,
                "type": c.check_type,
                "passed": c.passed,
                "expected": c.expected,
                "actual": c.actual,
                "points_earned": c.points_earned,
                "max_points": c.max_points,
                "note": c.note,
            }
            for c in score.checks
        ],
        "raw_result_snapshot": raw,
    }
    out_path = run_dir / f"{scenario_id}.json"
    out_path.write_text(json.dumps(output, default=str, indent=2), encoding="utf-8")


def _print_summary_table(scores: list[ScenarioScore], elapsed_s: float) -> None:
    """Print a Rich table summary (or plain text fallback)."""
    grand_total = sum(s.total_points for s in scores)
    grand_max = sum(s.max_points for s in scores)
    rate = grand_total / grand_max if grand_max > 0 else 0.0

    if _RICH:
        console = Console()
        table = Table(title="Eval Harness Results", show_lines=True)
        table.add_column("Scenario", style="cyan", no_wrap=True)
        table.add_column("Name", style="white")
        table.add_column("Score", justify="right")
        table.add_column("Pass%", justify="right")
        table.add_column("Result", justify="center")

        for s in scores:
            result_str = "[green]PASS[/green]" if s.passed else "[red]FAIL[/red]"
            table.add_row(
                s.scenario_id,
                s.scenario_name[:40],
                f"{s.total_points}/{s.max_points}",
                f"{s.pass_rate:.0%}",
                result_str,
            )

        console.print(table)
        console.print(
            f"\n[bold]GRAND TOTAL:[/bold] {grand_total}/{grand_max} "
            f"({rate:.0%})  |  Elapsed: {elapsed_s:.1f}s"
        )
    else:
        print("\n" + "=" * 60)
        print("EVAL HARNESS RESULTS")
        print("=" * 60)
        for s in scores:
            status = "PASS" if s.passed else "FAIL"
            print(f"  {s.scenario_id:<20} {s.total_points:>3}/{s.max_points:<3}  {s.pass_rate:.0%}  {status}")
        print("=" * 60)
        print(f"GRAND TOTAL: {grand_total}/{grand_max} ({rate:.0%})  |  {elapsed_s:.1f}s")


# ── CLI ───────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    lf = _get_langfuse_client() if args.langfuse else None
    if lf:
        print("Langfuse: connected (will push scores)")
    elif args.langfuse:
        print("Langfuse: env vars not configured — running without scoring push")
    else:
        print("Langfuse: disabled (--no-langfuse)")

    # Collect scenario files
    selected = getattr(args, "scenarios", None) or []
    if args.all or not selected:
        paths = sorted(SCENARIOS_DIR.glob("scenario_*.json"))
    else:
        paths = []
        for s in selected:
            name = s if s.endswith(".json") else f"{s}.json"
            paths.append(SCENARIOS_DIR / name)

    if not paths:
        print(f"No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / ts

    all_scores: list[ScenarioScore] = []
    t_start = asyncio.get_event_loop().time()

    for path in paths:
        scenario = _load_scenario(path)
        sid = scenario.get("id", path.stem)
        print(f"\nRunning {sid} — {scenario.get('name', '')} …", end="", flush=True)

        try:
            score, raw = await run_single_scenario(scenario, lf=lf)
            _save_results(run_dir, sid, score, raw)
            all_scores.append(score)
            status = "✓ PASS" if score.passed else "✗ FAIL"
            print(f"  {score.total_points}/{score.max_points}p  {status}")

            if args.verbose:
                print(score.summary())

        except Exception as exc:
            print(f"  ERROR: {exc}")
            if args.verbose:
                traceback.print_exc()

    elapsed = asyncio.get_event_loop().time() - t_start
    if all_scores:
        _print_summary_table(all_scores, elapsed)

    if lf:
        try:
            lf.flush()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E-commerce Ops Brain Eval Runner")
    scenario_group = parser.add_mutually_exclusive_group()
    scenario_group.add_argument("--scenario", "-s", action="append", dest="scenarios", help="Scenario ID or filename (e.g. scenario_01); repeat to run multiple")
    scenario_group.add_argument("--all", action="store_true", help="Run all scenarios")

    langfuse_group = parser.add_mutually_exclusive_group()
    langfuse_group.add_argument("--langfuse", "-l", dest="langfuse", action="store_true", default=True, help="Push scores to Langfuse (default)")
    langfuse_group.add_argument("--no-langfuse", dest="langfuse", action="store_false", help="Disable Langfuse score push")

    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-check breakdown")
    args = parser.parse_args()
    asyncio.run(main(args))
