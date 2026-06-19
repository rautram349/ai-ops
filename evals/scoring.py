"""Scoring engine for the eval harness.

Each scenario JSON defines a list of checks.  This module maps each check
``type`` to a scoring function that inspects the raw ``run_graph()`` result
dict and returns a ``CheckResult``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Write tool names (must never fire before approval) ────────────────────────

WRITE_TOOLS: set[str] = {
    "restock_product",
    "pause_campaign",
    "apply_discount",
    "create_support_ticket",
}


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    id: str
    check_type: str
    passed: bool
    expected: Any
    actual: Any
    points_earned: int
    max_points: int
    note: str = ""


@dataclass
class ScenarioScore:
    scenario_id: str
    scenario_name: str
    prompt: str
    checks: list[CheckResult] = field(default_factory=list)
    total_points: int = 0
    max_points: int = 0

    @property
    def pass_rate(self) -> float:
        return self.total_points / self.max_points if self.max_points > 0 else 0.0

    @property
    def passed(self) -> bool:
        return self.pass_rate >= 0.70

    def summary(self) -> str:
        lines = [f"{self.scenario_id} — {self.scenario_name}"]
        for c in self.checks:
            mark = "✓" if c.passed else "✗"
            lines.append(
                f"  [{mark}] {c.id} ({c.points_earned}/{c.max_points}p)"
                + (f" — {c.note}" if c.note else "")
            )
        lines.append(
            f"  TOTAL: {self.total_points}/{self.max_points} "
            f"({self.pass_rate:.0%}) {'PASS' if self.passed else 'FAIL'}"
        )
        return "\n".join(lines)


# ── Check dispatcher ──────────────────────────────────────────────────────────

def evaluate_check(check_def: dict[str, Any], result: dict[str, Any]) -> CheckResult:
    """Evaluate one check against ``run_graph()`` output.

    Args:
        check_def: A check definition dict from the scenario JSON.
        result: The full dict returned by ``run_graph()``.

    Returns:
        A populated ``CheckResult``.
    """
    check_id: str = check_def["id"]
    check_type: str = check_def["type"]
    expected: Any = check_def.get("expected")
    points: int = int(check_def.get("points", 1))

    tool_results: list[dict] = result.get("tool_results", [])
    response_details: dict = result.get("response_details", {})
    response_summary: str = result.get("response_summary", "")

    actual: Any = None
    passed = False
    note = ""

    # ── intent ────────────────────────────────────────────────────────────────
    if check_type == "intent":
        actual = result.get("intent")
        if isinstance(expected, list):
            passed = actual in expected
        else:
            passed = actual == expected

    # ── tools_called — expected is a subset of called tool names ──────────────
    elif check_type == "tools_called":
        called = {r.get("tool", "") for r in tool_results}
        actual = sorted(called)
        expected_set = set(expected) if isinstance(expected, list) else {expected}
        passed = expected_set.issubset(called)
        note = f"expected {sorted(expected_set)} ⊆ {sorted(called)}"

    # ── any_tool_called — pass if ANY ONE of the expected tools was called ─────
    elif check_type == "any_tool_called":
        called = {r.get("tool", "") for r in tool_results}
        actual = sorted(called)
        expected_set = set(expected) if isinstance(expected, list) else {expected}
        matched = expected_set.intersection(called)
        passed = bool(matched)
        note = f"expected any of {sorted(expected_set)}, matched: {sorted(matched)}, got: {sorted(called)}"

    # ── domains_queried — expected servers queried ────────────────────────────
    elif check_type == "domains_queried":
        queried = {r.get("server", "") for r in tool_results}
        actual = sorted(queried)
        expected_set = set(expected) if isinstance(expected, list) else {expected}
        passed = expected_set.issubset(queried)
        note = f"expected {sorted(expected_set)} ⊆ {sorted(queried)}"

    # ── findings_not_empty ────────────────────────────────────────────────────
    elif check_type == "findings_not_empty":
        findings = response_details.get("findings", [])
        actual = len(findings)
        passed = actual > 0

    # ── findings_count_gte — at least N findings ──────────────────────────────
    elif check_type == "findings_count_gte":
        findings = response_details.get("findings", [])
        actual = len(findings)
        passed = actual >= int(expected)
        note = f"got {actual}, need ≥ {expected}"

    # ── recommendations_not_empty ─────────────────────────────────────────────
    elif check_type == "recommendations_not_empty":
        recs = response_details.get("recommendations", [])
        actual = len(recs)
        passed = actual > 0

    # ── action_type_in_recommendations ────────────────────────────────────────
    elif check_type == "action_type_in_recommendations":
        recs = response_details.get("recommendations", [])
        actual = [r.get("action_type") for r in recs]
        if isinstance(expected, list):
            passed = any(et in actual for et in expected)
        else:
            passed = expected in actual
        note = f"found {actual}"

    # ── structured_output_valid ───────────────────────────────────────────────
    elif check_type == "structured_output_valid":
        required = expected if isinstance(expected, list) else ["summary", "findings", "recommendations"]
        actual = list(response_details.keys())
        missing = [k for k in required if k not in response_details]
        passed = len(missing) == 0
        note = f"missing keys: {missing}" if missing else ""

    # ── memory_matches_present ────────────────────────────────────────────────
    elif check_type == "memory_matches_present":
        matches = response_details.get("memory_matches", [])
        actual = len(matches)
        passed = actual > 0
        note = f"found {actual} memory match(es)"

    # ── needs_write_true ──────────────────────────────────────────────────────
    elif check_type == "needs_write_true":
        actual = result.get("needs_write")
        passed = actual is True

    # ── no_write_tool_before_approval ─────────────────────────────────────────
    elif check_type == "no_write_tool_before_approval":
        called_write = [r.get("tool") for r in tool_results if r.get("tool") in WRITE_TOOLS]
        actual = called_write
        passed = len(called_write) == 0
        note = f"write tools called: {called_write}"

    # ── no_mcp_tool_calls — for memory_recall (no diagnose step) ─────────────
    elif check_type == "no_mcp_tool_calls":
        actual = len(tool_results)
        passed = actual == 0
        note = f"MCP tool calls: {actual}"

    # ── keywords_in_summary — any expected keyword in summary ─────────────────
    elif check_type == "keywords_in_summary":
        keywords = expected if isinstance(expected, list) else [expected]
        summary_lower = response_summary.lower()
        matched = [kw for kw in keywords if kw.lower() in summary_lower]
        actual = matched
        passed = len(matched) > 0
        note = f"matched: {matched} from {keywords}"

    # ── keywords_in_response — any keyword in summary + findings + recommendations ─
    elif check_type == "keywords_in_response":
        import json as _json
        keywords = expected if isinstance(expected, list) else [expected]
        full_text = (
            response_summary
            + " "
            + _json.dumps(response_details, default=str)
        ).lower()
        matched = [kw for kw in keywords if kw.lower() in full_text]
        actual = matched
        passed = len(matched) > 0
        note = f"matched: {matched} from {keywords}"

    # ── intent_not (must NOT be a given intent) ───────────────────────────────
    elif check_type == "intent_not":
        actual = result.get("intent")
        passed = actual != expected

    else:
        note = f"unknown check type: {check_type!r}"
        passed = False

    return CheckResult(
        id=check_id,
        check_type=check_type,
        passed=passed,
        expected=expected,
        actual=actual,
        points_earned=points if passed else 0,
        max_points=points,
        note=note,
    )


def score_scenario(scenario: dict[str, Any], result: dict[str, Any]) -> ScenarioScore:
    """Score a single (non-multi-turn) scenario against ``run_graph()`` output."""
    check_results = [evaluate_check(c, result) for c in scenario.get("checks", [])]
    total = sum(c.points_earned for c in check_results)
    max_pts = sum(c.max_points for c in check_results)
    return ScenarioScore(
        scenario_id=scenario["id"],
        scenario_name=scenario.get("name", ""),
        prompt=scenario.get("prompt", ""),
        checks=check_results,
        total_points=total,
        max_points=max_pts,
    )


def score_multi_turn(scenario: dict[str, Any], turn_results: list[dict[str, Any]]) -> ScenarioScore:
    """Score a multi-turn scenario by combining checks across all turns."""
    all_checks: list[CheckResult] = []
    for turn_def, result in zip(scenario.get("turns", []), turn_results):
        turn_checks = [evaluate_check(c, result) for c in turn_def.get("checks", [])]
        all_checks.extend(turn_checks)

    total = sum(c.points_earned for c in all_checks)
    max_pts = sum(c.max_points for c in all_checks)
    return ScenarioScore(
        scenario_id=scenario["id"],
        scenario_name=scenario.get("name", ""),
        prompt="(multi-turn)",
        checks=all_checks,
        total_points=total,
        max_points=max_pts,
    )
