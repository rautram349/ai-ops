"""Shared utilities used by multiple graph nodes."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog

from ai_ops_engine.graph.state import ToolCallRecord

logger = structlog.get_logger(__name__)

# ── Date helpers ──────────────────────────────────────────────────────────────

# Cap at the last date for which data was generated.
_DATA_END = date(2026, 4, 13)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _today() -> str:
    return min(date.today(), _DATA_END).isoformat()


def _days_ago(n: int) -> str:
    ref = min(date.today(), _DATA_END)
    return (ref - timedelta(days=n)).isoformat()


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)```$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


# ── Formatting helpers ────────────────────────────────────────────────────────


def _summarise_domain_findings(findings: list[dict]) -> str:
    """Format domain findings for LLM context."""
    parts = []
    for f in findings:
        domain = f.get("domain", "unknown")
        tools = f.get("tools_called", [])
        results = f.get("tool_results", [])
        part = f"=== {domain.upper()} (tools: {', '.join(tools)}) ==="
        for tr in results:
            if tr.get("error"):
                part += f"\n  [{tr['tool']}] ERROR: {tr['error']}"
            else:
                try:
                    result_str = json.dumps(tr["result"], default=str)[:1500]
                except Exception:
                    result_str = str(tr.get("result", ""))[:1500]
                part += f"\n  [{tr['tool']}] {result_str}"
        parts.append(part)
    return "\n\n".join(parts) if parts else "(no findings)"


def _summarise_tool_results(records: list[ToolCallRecord]) -> str:
    """Serialise tool results into a compact string for LLM prompts."""
    parts = []
    for r in records:
        if r.get("error"):
            parts.append(f"[{r['tool']}] ERROR: {r['error']}")
        else:
            try:
                result_str = json.dumps(r["result"], default=str)[:2000]
            except Exception:
                result_str = str(r["result"])[:2000]
            parts.append(f"[{r['tool']}] {result_str}")
    return "\n\n".join(parts) if parts else "(no data)"
