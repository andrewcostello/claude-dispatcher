"""Runnable-set computation and dispatch planning.

A task is runnable iff:
  - its status is "To Do" (or absent — defaults to To Do), AND
  - every key in its blockedBy list is the key of a task with status "Done".

The plan() function returns a deterministic list of waves: each wave is the
set of tasks that become simultaneously runnable once the prior waves complete.
The first wave is what the dispatcher dispatches initially; later waves are
informational (they show what's unlocked next).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable


TODO = "To Do"
IN_PROGRESS = "In Progress"
DONE = "Done"
BLOCKED = "Blocked"
ESCALATED = "Escalated"

TERMINAL = {DONE, BLOCKED, ESCALATED}


class ValidationError(ValueError):
    """Raised when the YAML structure does not match the expected schema."""


@dataclass
class Task:
    """A view of one task row from the YAML, with the fields the planner needs."""

    key: str
    summary: str
    description: str
    type: str
    labels: list[str]
    blocked_by: list[str]
    status: str
    raw: Any  # the underlying ruamel mapping — so writes go back to the right row
    # Optional per-task model override. When set, the dispatcher passes
    # `--model <value>` to `claude --print` for this task only. Useful when
    # a task is well-suited to a cheaper / faster model (e.g. trivial
    # documentation or simple migrations on Sonnet; intricate state-machine
    # work on Opus). Absent or empty → use whatever the run-level
    # --claude-extra-args supplies (or the CLI's default).
    model: str | None = None

    @property
    def size_label(self) -> str | None:
        for lbl in self.labels:
            if lbl.startswith("size:"):
                return lbl.split(":", 1)[1]
        return None

    @property
    def is_runnable_status(self) -> bool:
        return self.status == TODO

    @property
    def is_done(self) -> bool:
        return self.status == DONE


def _as_str_list(value: Any) -> list[str]:
    """Coerce a ruamel sequence (or None) to a plain list[str].

    ruamel returns its own CommentedSeq; for read-only iteration this works
    but we want a stable list for membership checks and sorting.
    """
    if value is None:
        return []
    return [str(item) for item in value]


def load_tasks(doc: Any) -> list[Task]:
    """Pull a list of Task views out of a parsed YAML document.

    The YAML root must be a mapping with a "tasks" key whose value is a sequence
    of mappings; each mapping must have at minimum key, summary, description,
    type, and labels (with a size: label present).
    """
    if not isinstance(doc, dict) or "tasks" not in doc:
        raise ValidationError("YAML root must be a mapping with a 'tasks' key")
    raw_tasks = doc["tasks"]
    if raw_tasks is None:
        return []

    tasks: list[Task] = []
    seen_keys: set[str] = set()
    size_pattern = re.compile(r"^size:(XS|S|M|L|XL)$")

    for idx, row in enumerate(raw_tasks):
        if not isinstance(row, dict):
            raise ValidationError(f"tasks[{idx}] is not a mapping")
        missing = [f for f in ("key", "summary", "description", "type", "labels") if f not in row]
        if missing:
            raise ValidationError(
                f"tasks[{idx}] missing required fields: {', '.join(missing)}"
            )
        labels = _as_str_list(row.get("labels"))
        if not any(size_pattern.match(lbl) for lbl in labels):
            raise ValidationError(
                f"tasks[{idx}] ({row.get('key')}) has no size: label "
                f"(must be size:XS|S|M|L|XL)"
            )
        key = str(row["key"])
        if key in seen_keys:
            raise ValidationError(f"duplicate task key: {key}")
        seen_keys.add(key)
        model_val = row.get("model")
        model = str(model_val).strip() if model_val else None
        if model == "":
            model = None
        tasks.append(
            Task(
                key=key,
                summary=str(row["summary"]),
                description=str(row["description"]),
                type=str(row["type"]),
                labels=labels,
                blocked_by=_as_str_list(row.get("blockedBy")),
                status=str(row.get("status", TODO)),
                raw=row,
                model=model,
            )
        )

    _validate_blocked_by(tasks)
    return tasks


def _validate_blocked_by(tasks: list[Task]) -> None:
    """Reject blockedBy references that don't resolve to a task in the file."""
    known = {t.key for t in tasks}
    for t in tasks:
        for dep in t.blocked_by:
            if dep not in known:
                raise ValidationError(
                    f"task {t.key}.blockedBy references unknown key {dep!r}"
                )
    _check_for_cycles(tasks)


def _check_for_cycles(tasks: list[Task]) -> None:
    """Reject blockedBy graphs with cycles. Dispatcher would deadlock otherwise."""
    by_key = {t.key: t for t in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(k: str, stack: list[str]) -> None:
        if k in visited:
            return
        if k in visiting:
            chain = " → ".join(stack[stack.index(k):] + [k])
            raise ValidationError(f"blockedBy cycle: {chain}")
        visiting.add(k)
        stack.append(k)
        for dep in by_key[k].blocked_by:
            visit(dep, stack)
        stack.pop()
        visiting.discard(k)
        visited.add(k)

    for t in tasks:
        visit(t.key, [])


# --- filtering ---------------------------------------------------------------


def parse_label_filter(spec: str | None) -> list[tuple[str, str]]:
    """Parse a --filter "size:M,area:schema" string into label tuples.

    Returns a list of (prefix, value) pairs. An empty/None spec returns [].
    """
    if not spec:
        return []
    out: list[tuple[str, str]] = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if ":" not in raw:
            raise ValidationError(f"bad filter clause {raw!r} (expected prefix:value)")
        prefix, value = raw.split(":", 1)
        out.append((prefix.strip(), value.strip()))
    return out


def filter_tasks(
    tasks: Iterable[Task],
    label_filter: list[tuple[str, str]] | None = None,
    only_keys: Iterable[str] | None = None,
) -> list[Task]:
    """Apply --filter and --only restrictions, in that order."""
    out = list(tasks)
    if label_filter:
        wanted = {f"{p}:{v}" for p, v in label_filter}
        out = [t for t in out if wanted.issubset(set(t.labels))]
    if only_keys:
        only = set(only_keys)
        out = [t for t in out if t.key in only]
    return out


# --- planning ----------------------------------------------------------------


@dataclass
class Wave:
    """A set of tasks that become runnable together."""

    index: int
    tasks: list[Task] = field(default_factory=list)


def runnable_now(tasks: list[Task]) -> list[Task]:
    """Tasks runnable on the dispatcher's current view of the YAML.

    A task is runnable iff:
      - its own status is To Do (default), AND
      - every blockedBy key resolves to a task whose status is Done.
    """
    by_key = {t.key: t for t in tasks}
    runnable: list[Task] = []
    for t in tasks:
        if not t.is_runnable_status:
            continue
        if all(by_key[dep].is_done for dep in t.blocked_by):
            runnable.append(t)
    return runnable


def plan_waves(tasks: list[Task]) -> list[Wave]:
    """Simulate dispatch waves: pretend each runnable task lands Done, then
    recompute. Produces an ordered list of waves for the dry-run output.

    Does NOT mutate the input tasks. Tasks with non-To-Do, non-Done status
    (e.g., Blocked) are treated as roadblocks for anything depending on them —
    they never resolve, and their dependents never enter a wave.
    """
    by_key = {t.key: t for t in tasks}
    sim_status = {t.key: t.status for t in tasks}
    waves: list[Wave] = []
    while True:
        wave = Wave(index=len(waves) + 1)
        for t in tasks:
            if sim_status[t.key] != TODO:
                continue
            if all(sim_status[dep] == DONE for dep in t.blocked_by):
                wave.tasks.append(t)
        if not wave.tasks:
            break
        for t in wave.tasks:
            sim_status[t.key] = DONE
        waves.append(wave)
    return waves


def parallelism_estimate(waves: list[Wave]) -> int:
    """The max wave width across the plan — how parallel the work CAN go."""
    return max((len(w.tasks) for w in waves), default=0)


def unreachable(tasks: list[Task], waves: list[Wave]) -> list[Task]:
    """Tasks that are To Do but never appear in any wave.

    Indicates a blockedBy chain that depends on a Blocked / Escalated task —
    or that the user has frozen partway through a chain. Surface these in the
    dispatch plan so the human sees the dead ends.
    """
    reachable = {t.key for w in waves for t in w.tasks}
    return [
        t for t in tasks
        if t.is_runnable_status and t.key not in reachable
    ]
