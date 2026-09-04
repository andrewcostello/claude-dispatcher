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

from .quality_levels import CASCADE_FAMILY_MODEL, KNOWN_PANEL, KNOWN_VERIFY

TODO = "To Do"
IN_PROGRESS = "In Progress"
DONE = "Done"
BLOCKED = "Blocked"
ESCALATED = "Escalated"
# PR-flow lifecycle (PRF-2). In `pr` integration mode Done is no longer
# terminal: a task that passes every gate has its PR auto-raised against the
# run's feature branch and moves to `Awaiting Review`; PRF-4 later flips it to
# `Merged` once the PR lands. Neither status occurs in `branch` mode.
AWAITING_REVIEW = "Awaiting Review"
MERGED = "Merged"

TERMINAL = {DONE, BLOCKED, ESCALATED}

# Implementer agents the dispatcher can spawn as a Tasker. "claude" is the
# default; codex/grok/gemini are cross-family CLIs run in their headless
# agentic mode via spawn.spawn_agent(). Kept in sync with spawn.AGENT_SPECS.
# kimi/glm/deepseek are ENDPOINT agents: the claude CLI re-pointed at an
# Anthropic-compatible provider endpoint (see endpoint_agents.ENDPOINT_AGENTS).
KNOWN_AGENTS = frozenset(
    {"claude", "codex", "grok", "gemini", "kimi", "glm", "deepseek"}
)

# Per-task reasoning/effort knob (maps to claude --effort, grok --effort,
# codex model_reasoning_effort). gemini/agy has no flag and ignores it.
#
# THE SETS DIFFER PER AGENT and the union is what a row may carry. Measured
# 2026-09-02 by probing each CLI: codex accepts low|medium|high|xhigh|max|ultra
# and rejects anything else, so a global three-value set silently DOWNGRADED
# every codex row — an operator whose config asks for xhigh had it validated
# down to high, losing two reasoning tiers with only a validation error to
# explain it. `low` is also codex's own default, not medium.
KNOWN_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})

#: What each family actually accepts. An effort outside its agent's set is a
#: refusal rather than a downgrade: passing an unknown value to the CLI fails
#: the spawn, and quietly substituting a different tier makes the row's
#: recorded effort a lie.
AGENT_EFFORTS: dict[str, frozenset[str]] = {
    "claude": frozenset({"low", "medium", "high"}),
    "codex": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
    # Probed 2026-09-02: grok's own refusal names its set — "unknown effort
    # level 'max'; use one of: xhigh, high, medium, low". It takes xhigh and not
    # max/ultra, so it sits between claude and codex rather than beside either.
    "grok": frozenset({"low", "medium", "high", "xhigh"}),
}

# Per-task quality intensity sets: KNOWN_VERIFY / KNOWN_PANEL imported above.

# DISPATCH ordering — the statuses of a blockedBy dependency that let its
# dependents be dispatched ("Done-or-later"). In `branch` mode that is just
# Done. In `pr` mode Done is no longer terminal, but a dependency in Awaiting
# Review (or Merged) has already produced its commits, which reach the
# dependent's worktree via the dispatch-time dependency merge (INT-4) — so any
# of Done/Awaiting Review/Merged satisfies dispatch ordering.
_DISPATCH_SATISFIED_BRANCH = frozenset({DONE})
_DISPATCH_SATISFIED_PR = frozenset({DONE, AWAITING_REVIEW, MERGED})


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
    #: Globs/directories this task OWNS. A change outside them is a scope
    #: excursion (see `scope_excursion`). Empty means the row declared no
    #: ownership, which is opt-in silence, NOT "owns nothing".
    owns: list[str] = field(default_factory=list)
    # Optional per-task IMPLEMENTER agent override. One of KNOWN_AGENTS;
    # absent/empty -> "claude" (the default Tasker). When set to a cross-family
    # CLI (codex/grok/gemini), the dispatcher spawns that agent's headless
    # agentic mode in the worktree via spawn.spawn_agent() instead of
    # `claude --print`. Lets the bake-off route each task to the agent with the
    # best outcome/cost. Distinct from `model` (which only swaps the Claude
    # model tier on the default claude agent).
    agent: str | None = None
    # Optional per-task reasoning effort (low|medium|high). Plumbed to each
    # CLI's effort flag by spawn_agent. Absent → CLI default. The quality
    # cascade may bump effort to "high" before switching agents.
    effort: str | None = None
    # Optional batch grouping: co-runnable tasks sharing a batch_id dispatch
    # as one work unit — one worktree / one implementer session (see
    # docs/task-batching.md and orchestrator._take_batch_group).
    batch_id: str | None = None
    # Optional quality intensity overrides (Phase 4). None → resolved from
    # floors / run defaults / design recommendations.
    verify: str | None = None
    panel: str | None = None
    # Optional design-stage pin (Phase 5). True/False force on/off; None →
    # design_required() heuristics.
    design: bool | None = None

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

    @property
    def is_merged(self) -> bool:
        return self.status == MERGED


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
        owns = _as_str_list(row.get("owns"))
        model_val = row.get("model")
        model = str(model_val).strip() if model_val else None
        if model == "":
            model = None
        agent_val = row.get("agent")
        agent = str(agent_val).strip().lower() if agent_val else None
        if not agent:
            agent = None
        elif agent not in KNOWN_AGENTS:
            raise ValidationError(
                f"tasks[{idx}] ({key}) has unknown agent {agent!r}; "
                f"must be one of {', '.join(sorted(KNOWN_AGENTS))}"
            )
        effort_val = row.get("effort")
        effort = str(effort_val).strip().lower() if effort_val else None
        if effort == "":
            effort = None
        elif effort is not None and effort not in KNOWN_EFFORTS:
            raise ValidationError(
                f"tasks[{idx}] ({key}) has unknown effort {effort!r}; "
                f"must be one of {', '.join(sorted(KNOWN_EFFORTS))}"
            )
        elif effort is not None:
            allowed = AGENT_EFFORTS.get(agent or "claude")
            if allowed is not None and effort not in allowed:
                raise ValidationError(
                    f"tasks[{idx}] ({key}) has effort {effort!r}, which "
                    f"{agent or 'claude'} does not accept; it takes "
                    f"{', '.join(sorted(allowed))}"
                )
        batch_id_val = row.get("batch_id")
        batch_id = str(batch_id_val).strip() if batch_id_val else None
        if batch_id == "":
            batch_id = None
        verify_val = row.get("verify")
        verify = str(verify_val).strip().lower() if verify_val else None
        if verify == "":
            verify = None
        elif verify is not None and verify not in KNOWN_VERIFY:
            raise ValidationError(
                f"tasks[{idx}] ({key}) has unknown verify {verify!r}; "
                f"must be one of {', '.join(sorted(KNOWN_VERIFY))}"
            )
        panel_val = row.get("panel")
        panel = str(panel_val).strip().lower() if panel_val else None
        if panel == "":
            panel = None
        elif panel is not None and panel not in KNOWN_PANEL:
            raise ValidationError(
                f"tasks[{idx}] ({key}) has unknown panel {panel!r}; "
                f"must be one of {', '.join(sorted(KNOWN_PANEL))}"
            )
        design_raw = row.get("design")
        design: bool | None
        if design_raw is None or design_raw == "":
            design = None
        elif isinstance(design_raw, bool):
            design = design_raw
        else:
            s = str(design_raw).strip().lower()
            if s in ("true", "yes", "1", "on"):
                design = True
            elif s in ("false", "no", "0", "off"):
                design = False
            else:
                raise ValidationError(
                    f"tasks[{idx}] ({key}) has unknown design {design_raw!r}; "
                    f"must be true/false"
                )
        tasks.append(
            Task(
                key=key,
                summary=str(row["summary"]),
                description=str(row["description"]),
                type=str(row["type"]),
                labels=labels,
                blocked_by=_dependency_list(row, idx, key),
                status=str(row.get("status", TODO)),
                raw=row,
                model=model,
                owns=owns,
                agent=agent,
                effort=effort,
                batch_id=batch_id,
                verify=verify,
                panel=panel,
                design=design,
            )
        )

    _validate_blocked_by(tasks)

    # Plan-time enforcement of the build protocol (D1). This is THE point at
    # which a worklist that breaks phase order or declares a narrowing
    # `immutable_paths:` is refused — before `load_tasks` returns, so a failing
    # worklist never partially plans (invariant 2). `role_protocol.validate`
    # collects errors for EVERY row rather than raising on the first, and all
    # of them are reported here: raising on `errors[0]` would throw that away
    # and cost one round trip per broken row.
    #
    # Imported inside the function on purpose: `role_protocol` reads
    # `plan.Task`, so a module-level import in either direction is a cycle
    # (that module's own TYPE_CHECKING note names this call site as the
    # reason). `preflight.run_preflight` imports `spawn` the same way.
    from . import batch_coherence as batch_coherence_mod
    from . import role_protocol as role_protocol_mod

    validation = role_protocol_mod.validate(tasks)
    # Batch coherence (unit DF-3): a batch whose rows do not share one role,
    # or share a role and not a rule, is a worklist defect, and this is the
    # one point every load funnels through. The defects merge into the SAME
    # ValidationError as the role errors — one raise site, so a worklist
    # author fixes every defect in one round trip. `validate`'s specs already
    # exclude rows whose parse failed; each of those carries its own ROW
    # error above, which is why the exclusion masks nothing.
    batch_defects = batch_coherence_mod.batch_errors(tasks, validation.specs)
    # A declared capability floor joins the same raise: a worklist that both
    # breaks phase order and routes below its floor should report both.
    floor = model_floor(doc)
    floor_defects = _model_floor_errors(floor, tasks) if floor else []
    # Unlike the floor, this one is unconditional: a cross-family (agent, model)
    # pair is never intentional, so there is nothing for a run to declare.
    mismatches = _agent_model_mismatches(tasks)
    if validation.errors or batch_defects or floor_defects or mismatches:
        merged = (list(validation.errors)
                  + [d.message for d in batch_defects]
                  + floor_defects + mismatches)
        raise ValidationError(
            "this worklist was refused "
            f"({len(merged)} error(s)):\n  - " + "\n  - ".join(merged)
        )
    return tasks


#: Which family owns a model-id prefix. A model id belongs to exactly ONE
#: family, so an (agent, model) pair from different families is a config error
#: the CLI can only report as a rejection.
#:
#: Deliberately partial: an id matching no prefix is NOT a defect. A new model
#: must be routable the day it exists, and refusing unknown ids here would make
#: this table a gate on every future one.
_MODEL_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude-", "claude"),
    ("gpt-", "codex"),
    ("o3", "codex"),
    ("o4", "codex"),
    ("grok-", "grok"),
    ("gemini-", "gemini"),
    ("kimi-", "kimi"),
    ("glm-", "glm"),
    ("deepseek-", "deepseek"),
)


def model_family(model: str | None) -> str | None:
    """The family that owns `model`, or None when no prefix claims it."""
    if not model:
        return None
    lowered = model.strip().lower()
    for prefix, family in _MODEL_FAMILY_PREFIXES:
        if lowered.startswith(prefix):
            return family
    return None


def _agent_model_mismatches(tasks: list[Task]) -> list[str]:
    """Rows whose `agent` and `model` belong to different families.

    Measured 2026-09-04, WAL-CHAIN-3: the cascade moved codex@max -> claude@high
    and left `model: gpt-5.6-sol` in place, so the claude CLI was handed codex's
    id. The spawn exited 1 in 952ms having spent $0.00 and run no turn, and the
    dispatcher read that as a failed spawn and Blocked the task -- sixteen
    minutes after its own verifier said VERIFIED with 0 gaps.

    The cascade no longer creates the pair, but a worklist can still carry one:
    the same run needed a hand-repair commit ("repair agent/model mismatches the
    cascade left") for rows already written to YAML. Refusing at load makes that
    unshippable, and costs nothing when the prefix is unrecognised.
    """
    errors: list[str] = []
    for task in tasks:
        family = model_family(task.model)
        if family is None or task.agent is None or family == task.agent:
            continue
        errors.append(
            f"{task.key} routes agent {task.agent!r} to model {task.model!r}, "
            f"which belongs to the {family!r} family; the {task.agent!r} CLI "
            f"rejects it in under a second, spending nothing and looking like "
            f"a dead spawn"
        )
    return errors


def model_floor(doc: Any) -> tuple[frozenset[str], str] | None:
    """The run's declared model allow-list, or None when it declares none.

    A capability floor is a per-RUN property, not a dispatcher-wide constant: a
    dogfood run legitimately spends haiku, and a financial run legitimately
    refuses it. So the run declares its own set and this module enforces it.

    Absent key -> no check, so every existing worklist keeps loading.
    """
    if not isinstance(doc, dict) or "model_floor" not in doc:
        return None
    val = doc["model_floor"]
    if val is None:
        return None
    if not isinstance(val, dict):
        raise ValidationError(
            "'model_floor' must be a mapping with an 'allow' list, got "
            f"{type(val).__name__}: {val!r}"
        )
    allow = _as_str_list(val.get("allow"))
    if not allow:
        raise ValidationError(
            "'model_floor' declares no 'allow' models; remove the key to run "
            "without a floor rather than declaring an empty one"
        )
    reason = str(val.get("reason") or "").strip()
    return frozenset(allow), reason


def _model_floor_errors(
    floor: tuple[frozenset[str], str], tasks: list[Task],
) -> list[str]:
    """Every way this worklist could spend a model outside its declared floor.

    Two routes out of the floor, and only the first is obvious:

    1. A row pins a model below it. An UNPINNED row is the same defect: no
       `model:` means the family CLI's own default applies, which is invisible
       in a run report and is what put an epic at ~$72/task in July 2026. A
       declared floor is a claim about what the run spends, so it cannot hold
       over rows whose model nobody stated.
    2. The CASCADE rewrites the model when it changes family, so a floor the
       cascade can step outside is not a floor. Checked against the map rather
       than clamped at cascade time: failing at load is one edit, while
       silently substituting a model mid-run hides the misconfiguration in the
       place it costs most.

    Returns messages rather than raising so they merge into the single
    ValidationError at the end of `load_tasks` — one round trip per author.
    """
    allow, reason = floor
    because = f" ({reason})" if reason else ""
    errors: list[str] = []
    for task in tasks:
        if task.model is None:
            errors.append(
                f"{task.key} pins no model, but this run declares a "
                f"model_floor{because}; an unpinned row runs the CLI default, "
                f"which the floor cannot vouch for. Pin one of: "
                f"{', '.join(sorted(allow))}"
            )
        elif task.model not in allow:
            errors.append(
                f"{task.key} pins model {task.model!r}, outside this run's "
                f"declared model_floor{because}. Allowed: "
                f"{', '.join(sorted(allow))}"
            )
    outside = {
        family: model
        for family, model in CASCADE_FAMILY_MODEL.items()
        if model not in allow
    }
    if outside:
        named = ", ".join(f"{f} -> {m}" for f, m in sorted(outside.items()))
        errors.append(
            f"the cross-family cascade would run a model outside this run's "
            f"declared model_floor{because}: {named}. A cascade rung that "
            f"leaves the floor makes the floor advisory; add the model to "
            f"'allow' or change CASCADE_FAMILY_MODEL"
        )
    return errors


def feature_prd(doc: Any) -> str | None:
    """Return the top-level ``prd:`` path the Planner emits as the feature's
    intent oracle (read by the final feature review). None when absent or a
    present-but-blank string. A present ``prd:`` that is NOT a string (a list /
    mapping / number) is a config error and raises ValidationError — consistent
    with the rest of this module's strict field handling, and so a malformed prd
    is caught loudly rather than silently stringified. Pure function of `doc`.
    """
    if not isinstance(doc, dict) or "prd" not in doc:
        return None
    val = doc["prd"]
    if val is None:
        return None
    if not isinstance(val, str):
        raise ValidationError(
            f"'prd' must be a string path, got {type(val).__name__}: {val!r}"
        )
    stripped = val.strip()
    return stripped or None


# Accepted spellings for the dependency field. `blockedBy` is canonical;
# the aliases exist because a silently-ignored misspelling voids a whole
# worklist's ordering (partner-hub Stage B, 2026-07-10: `depends_on` parsed
# as nothing, a dependent dispatched against a Blocked dependency's absent
# code and had to be killed mid-spawn). Unknown near-misses are an ERROR,
# never a no-op.
_DEP_FIELD_CANONICAL = "blockedBy"
_DEP_FIELD_ALIASES = ("blockedBy", "blocked_by", "depends_on", "dependsOn")


def _dependency_list(row: dict, idx: int, key: str) -> list[str]:
    present = [f for f in _DEP_FIELD_ALIASES if row.get(f) is not None]
    if len(present) > 1:
        raise ValidationError(
            f"tasks[{idx}] ({key}) sets {' and '.join(present)}; "
            f"use only {_DEP_FIELD_CANONICAL!r}"
        )
    if not present:
        return []
    return _as_str_list(row.get(present[0]))


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


def runnable_now(tasks: list[Task], *, integration: str = "branch") -> list[Task]:
    """Tasks runnable on the dispatcher's current view of the YAML (DISPATCH
    ordering).

    A task is runnable iff:
      - its own status is To Do (default), AND
      - every blockedBy key resolves to a dependency whose status satisfies
        DISPATCH ordering — "Done-or-later".

    In ``branch`` mode (default) "Done-or-later" is just Done, exactly as
    before. In ``pr`` mode it widens to Done/Awaiting Review/Merged (PRF-2):
    a dependency whose PR is open-but-unmerged has still produced its commits,
    which reach this task's worktree via the dispatch-time dependency merge.

    "Done-or-later" is answered **per edge** by
    :func:`role_protocol.dispatch_satisfied_statuses`, not by one set chosen
    per call: an edge whose DEPENDENCY is a ``seals`` task narrows back to
    ``{Merged}`` in ``pr`` mode (2026-08-04 P2 ruling), because the seals gate
    is a review gate rather than a code-availability gate. The narrowing is
    keyed on the dependency, never on the waiter — an Awaiting-Review seals
    task has not finished its phase no matter who is waiting on it. Every
    other edge, including every role-less (LEGACY) one, keeps today's
    behaviour byte-identically; ``_DISPATCH_SATISFIED_BRANCH`` /
    ``_DISPATCH_SATISFIED_PR`` are still the source of those two sets and are
    read back out of this module by that function.
    """
    # Imported inside the function for the same reason `load_tasks` does it:
    # `role_protocol` reads `plan.Task`, so a module-level import is a cycle.
    from . import role_protocol as role_protocol_mod

    # Roles come off the rows through role_protocol's ONE parser. A row whose
    # `role:` does not parse is deliberately NOT ordered as though it were
    # role-less: `load_tasks` refuses such a worklist, so reaching here means
    # the loader was bypassed, and guessing LEGACY is exactly how a typo would
    # buy a task its way out of the gate. `parse_role_field` raises instead.
    roles = {
        t.key: role_protocol_mod.parse_role_field(t.raw or {}, task_key=t.key)
        for t in tasks
    }

    by_key = {t.key: t for t in tasks}
    runnable: list[Task] = []
    for t in tasks:
        if not t.is_runnable_status:
            continue
        # An unrecognised `integration` is refused by the per-edge call, not
        # here: a task with no blockedBy edges has no ordering to get wrong,
        # and both modes answer it identically.
        if all(
            by_key[dep].status
            in role_protocol_mod.dispatch_satisfied_statuses(
                roles[t.key], roles[dep], integration=integration
            )
            for dep in t.blocked_by
        ):
            runnable.append(t)
    return runnable


def mergeable_now(tasks: list[Task]) -> list[Task]:
    """Tasks whose PR is ready to MERGE (MERGE ordering, `pr` mode — PRF-4).

    Distinct from :func:`runnable_now`'s DISPATCH ordering: a task is
    mergeable iff its own status is Awaiting Review (its PR is open) AND every
    blockedBy dependency is already ``Merged``. A dependency that is merely
    Awaiting Review satisfies *dispatch* but NOT *merge* — its PR must land
    first so this task's PR merges on top of merged dependency code, not
    unmerged code. PRF-2 ships this building block; PRF-4 consumes it to drive
    the merge step.
    """
    by_key = {t.key: t for t in tasks}
    out: list[Task] = []
    for t in tasks:
        if t.status != AWAITING_REVIEW:
            continue
        if all(by_key[dep].is_merged for dep in t.blocked_by):
            out.append(t)
    return out


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
