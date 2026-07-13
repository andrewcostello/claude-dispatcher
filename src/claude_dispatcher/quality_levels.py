"""Per-task quality intensity (verify + panel) resolution.

Resolution order (highest wins):
  1. Explicit task field (verify: / panel:)
  2. Design recommendation (optional; Phase 5)
  3. Deterministic floors from risk/size labels
  4. Run-level defaults

Design may raise intensity above the floor; it may not sink below the floor
unless the task explicitly overrides (journal below_floor_override).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

KNOWN_VERIFY = frozenset({"none", "mechanical", "llm", "llm_strict"})
KNOWN_PANEL = frozenset({"never", "auto", "single", "full", "always"})

# Rank for max() comparisons (higher = more scrutiny).
_VERIFY_RANK = {"none": 0, "mechanical": 1, "llm": 2, "llm_strict": 3}
_PANEL_RANK = {"never": 0, "auto": 1, "single": 2, "full": 3, "always": 4}

# Deterministic floors by risk tier.
_FLOORS: dict[str, tuple[str, str]] = {
    # (verify, panel)
    "critical": ("llm_strict", "full"),
    "high": ("llm", "full"),
    "medium": ("llm", "auto"),
    "low": ("mechanical", "never"),
}


@dataclass(frozen=True)
class QualityLevels:
    verify: str
    panel: str
    source: str  # e.g. "task", "design+floor", "floor", "run_default"


def design_required(
    labels: Iterable[str] | None,
    *,
    task_design: bool | None = None,
    blocked_by_count: int = 0,
    description: str = "",
) -> bool:
    """Whether the dispatcher should run a design stage before implement.

    Explicit task_design True/False wins. Otherwise Critical/High risk and
    size L/XL always design; Medium designs when foundation (≥2 dependents
    known only at plan time — callers pass blocked_by_count as *fan-in* is
    not available here; use design:true) or description signals novelty /
    core. XS/S leaves without risk: no.
    """
    if task_design is False:
        return False
    if task_design is True:
        return True
    labs = [str(l).strip().lower() for l in (labels or [])]
    tier = risk_tier(labs)
    if tier in ("critical", "high"):
        return True
    if any(l in ("size:l", "size:xl") for l in labs):
        return True
    if "design" in labs or any(l.endswith(":design") for l in labs):
        return True
    if any(l in ("size:m",) for l in labs):
        desc = (description or "").lower()
        if blocked_by_count >= 0 and any(
            tok in desc for tok in (
                "new contract", "new interface", "state machine",
                "architecture", "skeleton", "novel",
            )
        ):
            return True
        if any(l in ("area:core", "area:skeleton") for l in labs):
            return True
    return False


def risk_tier(labels: Iterable[str] | None) -> str:
    """Map labels to a coarse risk tier for quality floors."""
    labs = [str(l).strip().lower() for l in (labels or [])]
    bare = set()
    for lab in labs:
        if lab in ("critical", "security", "financial"):
            return "critical"
        if ":" in lab:
            bare.add(lab.split(":", 1)[1].strip())
        else:
            bare.add(lab)
        if lab in ("size:l", "size:xl"):
            # Large work gets at least high floor for panel/verify defaults.
            pass
    if bare & {"critical", "security", "financial"}:
        return "critical"
    if "high" in bare or any(lab.endswith(":high") for lab in labs):
        return "high"
    if any(lab in ("size:l", "size:xl") for lab in labs):
        return "high"
    if any(lab in ("size:m",) for lab in labs):
        return "medium"
    return "low"


def _max_level(a: str, b: str, ranks: dict[str, int]) -> str:
    return a if ranks.get(a, 0) >= ranks.get(b, 0) else b


def resolve_quality_levels(
    *,
    labels: Iterable[str] | None,
    task_verify: str | None = None,
    task_panel: str | None = None,
    design_verify: str | None = None,
    design_panel: str | None = None,
    run_verify: str = "llm",
    run_panel: str = "auto",
) -> QualityLevels:
    """Resolve effective verify + panel for one task."""
    tier = risk_tier(labels)
    floor_v, floor_p = _FLOORS[tier]
    rv = run_verify if run_verify in KNOWN_VERIFY else "llm"
    rp = run_panel if run_panel in KNOWN_PANEL else "auto"

    # Start from run defaults, raised to floor — except run-level panel:never
    # is an absolute opt-out unless design/task later raises it.
    verify = _max_level(rv, floor_v, _VERIFY_RANK)
    if rp == "never" and design_panel is None and task_panel is None:
        panel = "never"
        source = "run_never"
    else:
        panel = _max_level(rp, floor_p, _PANEL_RANK)
        source = "floor+run"

    if design_verify in KNOWN_VERIFY:
        verify = _max_level(verify, design_verify, _VERIFY_RANK)
        source = "design+floor"
    if design_panel in KNOWN_PANEL:
        panel = _max_level(panel, design_panel, _PANEL_RANK)
        source = "design+floor"

    if task_verify in KNOWN_VERIFY:
        verify = task_verify
        source = "task"
    if task_panel in KNOWN_PANEL:
        panel = task_panel
        source = "task"

    return QualityLevels(verify=verify, panel=panel, source=source)
