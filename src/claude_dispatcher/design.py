"""Optional design stage before implement (plan Phase 5).

Deterministic ``design_required`` lives in quality_levels. This module:
  * builds a design-worker prompt
  * parses design output + Recommendation block (verify/panel)
  * runs the design worker via spawn_agent (any family)
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import quality_levels as ql_mod
from . import spawn as spawn_mod


@dataclass
class DesignRecommendation:
    selected: str | None = None
    verify: str | None = None
    panel: str | None = None
    rationale: str = ""
    raw: str = ""


_REC_BLOCK = re.compile(
    r"##\s*Recommendation\s*\n(.*?)(?=\n##\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_FIELD = re.compile(
    r"^[-*]\s*(selected|verify|panel|rationale)\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_design_recommendation(text: str) -> DesignRecommendation:
    """Extract ## Recommendation fields; tolerant of missing blocks."""
    rec = DesignRecommendation(raw=text or "")
    if not text:
        return rec
    m = _REC_BLOCK.search(text)
    block = m.group(1) if m else text
    for fm in _FIELD.finditer(block):
        key = fm.group(1).strip().lower()
        val = fm.group(2).strip()
        if key == "selected":
            rec.selected = val.split()[0] if val else None
        elif key == "verify":
            v = val.split()[0].lower().strip("`'\"")
            if v in ql_mod.KNOWN_VERIFY:
                rec.verify = v
        elif key == "panel":
            p = val.split()[0].lower().strip("`'\"")
            if p in ql_mod.KNOWN_PANEL:
                rec.panel = p
        elif key == "rationale":
            rec.rationale = val
    return rec


def build_design_prompt(
    *,
    task_key: str,
    task_summary: str,
    task_description: str,
    labels: list[str],
    summary_path: Path,
) -> str:
    """Prompt for the design worker (not Tasker; single-orchestrator)."""
    labs = ", ".join(labels)
    return f"""\
You are a design worker under the dispatcher (not an implementer, not Tasker).
Produce 2 competing designs for the task below, then a Recommendation block.

## Task
- Key: {task_key}
- Summary: {task_summary}
- Labels: {labs}

## Description
{task_description}

## Required output format

## Designs
### Design A
(approach, key types/seams, trade-offs)

### Design B
(approach, key types/seams, trade-offs)

## Recommendation
- selected: A
- verify: mechanical | llm | llm_strict | none
- panel: never | auto | single | full | always
- rationale: one paragraph why this design and these quality levels

Also write the same content to: {summary_path}
Use **Status:** Done in a one-line header when writing the file.
"""


def run_design(
    *,
    agent: str,
    cwd: Path,
    env: dict,
    task_key: str,
    task_summary: str,
    task_description: str,
    labels: list[str],
    timeout_seconds: int = 600,
    claude_bin: str = "claude",
    log: Callable[[str], None] = lambda _m: None,
) -> DesignRecommendation:
    """Spawn a design worker; return parsed recommendation (best-effort)."""
    out_path = Path(env.get("SUMMARY_PATH", str(cwd / ".design-summary.md")))
    # Design writes to a sibling path so it doesn't clobber implementer summary.
    design_summary = out_path.parent / f"{task_key}-design.md"
    design_env = dict(env)
    design_env["SUMMARY_PATH"] = str(design_summary)
    prompt = build_design_prompt(
        task_key=task_key,
        task_summary=task_summary,
        task_description=task_description,
        labels=labels,
        summary_path=design_summary,
    )
    log(f"  {task_key} design stage: agent={agent}")
    try:
        res = spawn_mod.spawn_agent(
            agent=agent,
            cwd=cwd,
            env=design_env,
            prompt=prompt,
            claude_bin=claude_bin,
            timeout_seconds=timeout_seconds,
        )
    except Exception as e:
        log(f"  {task_key} design stage failed: {e}")
        return DesignRecommendation(raw=f"error: {e}")

    text = ""
    if design_summary.exists():
        try:
            text = design_summary.read_text(encoding="utf-8")
        except OSError:
            text = res.stdout or ""
    else:
        text = res.stdout or ""
    # Persist a copy next to the run summary when possible.
    try:
        if text and not design_summary.exists():
            design_summary.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return parse_design_recommendation(text)
