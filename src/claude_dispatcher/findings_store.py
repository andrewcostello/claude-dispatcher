"""Panel findings, persisted where the NEXT author can read them (D-56).

Findings are recorded per task; prompts are built per row from `snap.description`
alone. So a panel that found a real defect on a scaffold produced no input to the
seals task that would pin it, or the body that would fix it. Measured on DF-1-1:
nine findings, three families naming ONE defect, and the author about to seal
that constructor never saw them.

Scope is deliberately the NARROW version D-56 named: a task inherits the findings
of the tasks it directly names in `blockedBy`, not every finding in the run.
Injecting everything would bloat prompts on units where the findings are
irrelevant, which is why the wide version was rejected.

Stored under `<runs_dir>/findings/<TASK_KEY>.json` — run-independent on purpose.
A dependency usually ran in an EARLIER run than the task inheriting from it, so a
per-run path would make the common case unreadable. Rewritten whole on each
panel, so the file always describes that task's latest review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SUBDIR = "findings"
#: Bound on what one dependency contributes to a downstream prompt. Findings are
#: model-written prose and a runaway panel must not be able to crowd out the diff.
MAX_PER_DEP = 12
MAX_CHARS = 600


@dataclass(frozen=True)
class Finding:
    family: str
    severity: str
    location: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "family": self.family, "severity": self.severity,
            "location": self.location, "description": self.description,
        }


def path_for(runs_dir: str | Path, task_key: str) -> Path:
    return Path(runs_dir) / SUBDIR / f"{task_key}.json"


def record(
    runs_dir: str | Path, task_key: str, findings: Iterable[Finding],
) -> Path | None:
    """Persist ``task_key``'s findings. Returns the path, or None if there were
    none — an empty file would read as "reviewed and clean" on a task whose panel
    never ran, which is a different fact.
    """
    items = [f.as_dict() for f in findings]
    if not items:
        return None
    p = path_for(runs_dir, task_key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"task_key": task_key, "findings": items}, indent=1),
                 encoding="utf-8")
    return p


def load(runs_dir: str | Path, task_key: str) -> list[Finding]:
    """Findings recorded for ``task_key``; empty when absent or unreadable.

    Never raises: this feeds a PROMPT. A malformed findings file must not stop a
    task from being dispatched — the cost of missing context is a weaker prompt,
    the cost of raising is a task that cannot run at all.
    """
    p = path_for(runs_dir, task_key)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return [
            Finding(
                family=str(f.get("family") or "?"),
                severity=str(f.get("severity") or "?"),
                location=str(f.get("location") or ""),
                description=str(f.get("description") or ""),
            )
            for f in doc.get("findings") or []
        ]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def render_for_prompt(
    runs_dir: str | Path, dependency_keys: Iterable[str],
) -> str:
    """The block appended to a task's description, or "" when nothing applies.

    Empty string rather than a "no findings" notice: a task whose dependencies
    were clean should read exactly as it did before this existed.
    """
    blocks: list[str] = []
    for key in dependency_keys:
        found = load(runs_dir, key)
        if not found:
            continue
        lines = [f"#### Recorded on {key}"]
        for f in found[:MAX_PER_DEP]:
            where = f" ({f.location})" if f.location else ""
            desc = f.description[:MAX_CHARS]
            lines.append(f"- **{f.severity}** [{f.family}]{where} — {desc}")
        if len(found) > MAX_PER_DEP:
            lines.append(f"- ...and {len(found) - MAX_PER_DEP} more on {key}.")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return (
        "\n\n### Review findings inherited from this task's dependencies\n\n"
        "An independent multi-family panel raised these against the work you are "
        "building on. They are NOT accusations against you and they are not "
        "instructions to fix that work in place — the phase that owns it may have "
        "already landed. Read them as known defects in your inputs: a SEALS task "
        "should pin the ones its rows can express, and a BODIES task should avoid "
        "reproducing them. If one is wrong, say so.\n\n"
        + "\n\n".join(blocks)
    )
