"""Deterministic implementer routing defaults (plan Phase 7).

When a task does not pin ``agent:``, pick a default family from labels/size
and the run's no_claude / implementer settings. Does not replace explicit
``agent:`` pins.
"""

from __future__ import annotations

from typing import Iterable

from . import quality_levels as ql_mod


def default_implementer(
    labels: Iterable[str] | None,
    *,
    run_implementer: str | None = None,
    no_claude: bool = False,
    cheap_first: bool = False,
) -> str:
    """Return claude|grok|… (never empty).

    Rules:
      * Explicit run_implementer wins when set (CLI --implementer / config).
      * no_claude → grok
      * cheap_first (opt-in fleet mode): HARD → claude, else → grok
      * default (legacy / tests): claude for unpinned tasks
    """
    if run_implementer:
        return str(run_implementer).strip().lower()
    if no_claude:
        return "grok"
    if not cheap_first:
        return "claude"
    tier = ql_mod.risk_tier(labels)
    if tier in ("critical", "high"):
        return "claude"
    labs = [str(l).strip().lower() for l in (labels or [])]
    if any(l in ("size:l", "size:xl") for l in labs):
        return "claude"
    return "grok"
