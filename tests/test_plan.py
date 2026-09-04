"""Tests for runnable-set computation, label filtering, and wave planning."""

from __future__ import annotations

import pytest

from claude_dispatcher import plan, yaml_io


# --- helpers ----------------------------------------------------------------

def _yaml(tasks_block: str) -> dict:
    """Parse a YAML snippet that's just a tasks list. Returns the doc."""
    import io
    from ruamel.yaml import YAML
    y = YAML(typ="rt")
    return y.load(io.StringIO("tasks:\n" + tasks_block))


# --- validation -------------------------------------------------------------

def test_load_tasks_requires_size_label() -> None:
    doc = _yaml(
        "  - key: A\n"
        "    summary: x\n"
        "    description: y\n"
        "    type: Task\n"
        "    labels: [area:schema]\n"  # no size:
    )
    with pytest.raises(plan.ValidationError, match="size:"):
        plan.load_tasks(doc)


def test_load_tasks_rejects_duplicate_keys() -> None:
    doc = _yaml(
        "  - key: A\n"
        "    summary: x\n"
        "    description: y\n"
        "    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: A\n"  # duplicate
        "    summary: x2\n"
        "    description: y2\n"
        "    type: Task\n"
        "    labels: [size:M]\n"
    )
    with pytest.raises(plan.ValidationError, match="duplicate task key"):
        plan.load_tasks(doc)


def test_load_tasks_rejects_unknown_blockedby() -> None:
    doc = _yaml(
        "  - key: A\n"
        "    summary: x\n"
        "    description: y\n"
        "    type: Task\n"
        "    labels: [size:S]\n"
        "    blockedBy: [DOES_NOT_EXIST]\n"
    )
    with pytest.raises(plan.ValidationError, match="DOES_NOT_EXIST"):
        plan.load_tasks(doc)


def test_load_tasks_rejects_cycles() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [B]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    with pytest.raises(plan.ValidationError, match="cycle"):
        plan.load_tasks(doc)


def test_load_tasks_defaults_status_to_todo() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
    )
    tasks = plan.load_tasks(doc)
    assert tasks[0].status == plan.TODO


def test_load_tasks_preserves_explicit_status() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Done\n"
    )
    tasks = plan.load_tasks(doc)
    assert tasks[0].status == plan.DONE


# --- runnable-set -----------------------------------------------------------

def test_runnable_now_picks_no_blocker_tasks() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    tasks = plan.load_tasks(doc)
    assert {t.key for t in plan.runnable_now(tasks)} == {"A"}


def test_runnable_now_unblocks_once_dependency_done() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Done\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    tasks = plan.load_tasks(doc)
    assert {t.key for t in plan.runnable_now(tasks)} == {"B"}


def test_runnable_now_skips_in_progress() -> None:
    """In Progress is not runnable — it's already in flight."""
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: In Progress\n"
    )
    tasks = plan.load_tasks(doc)
    assert plan.runnable_now(tasks) == []


# --- PR-flow ordering (PRF-2) -----------------------------------------------

def _dep_pair(dep_status: str) -> list:
    """A two-task doc: A (the dependency) in `dep_status`, B blockedBy A."""
    doc = _yaml(
        f"  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        f"    labels: [size:S]\n    status: {dep_status}\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    return plan.load_tasks(doc)


def test_runnable_now_branch_mode_requires_done() -> None:
    """branch mode (default): an Awaiting Review dependency does NOT unblock —
    only Done satisfies DISPATCH ordering, exactly as before PRF-2."""
    assert plan.runnable_now(_dep_pair("Awaiting Review")) == []
    assert {t.key for t in plan.runnable_now(_dep_pair("Done"))} == {"B"}


@pytest.mark.parametrize("dep_status", ["Done", "Awaiting Review", "Merged"])
def test_runnable_now_pr_mode_treats_done_or_later_as_satisfied(dep_status: str) -> None:
    """pr mode DISPATCH ordering: Done/Awaiting Review/Merged all unblock the
    dependent (the dependency's commits reach it via the dispatch-time merge)."""
    tasks = _dep_pair(dep_status)
    assert {t.key for t in plan.runnable_now(tasks, integration="pr")} == {"B"}


def test_runnable_now_pr_mode_still_holds_on_unfinished_dependency() -> None:
    """pr mode: a To Do / In Progress dependency does NOT unblock."""
    assert plan.runnable_now(_dep_pair("In Progress"), integration="pr") == []


def test_mergeable_now_requires_awaiting_review_and_merged_deps() -> None:
    """MERGE ordering (PRF-4 building block): a task is mergeable iff it is
    Awaiting Review and every dependency is Merged — a dependency merely
    Awaiting Review satisfies dispatch but NOT merge."""
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Awaiting Review\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Awaiting Review\n    blockedBy: [A]\n"
    )
    tasks = plan.load_tasks(doc)
    # A has no deps and is Awaiting Review → mergeable. B's dep A is only
    # Awaiting Review (not Merged) → NOT mergeable yet.
    assert {t.key for t in plan.mergeable_now(tasks)} == {"A"}

    # Once A is Merged, B (still Awaiting Review) becomes mergeable.
    doc2 = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Merged\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Awaiting Review\n    blockedBy: [A]\n"
    )
    assert {t.key for t in plan.mergeable_now(plan.load_tasks(doc2))} == {"B"}


def test_mergeable_now_ignores_non_awaiting_review() -> None:
    """A Done or To Do task is never mergeable (only Awaiting Review is)."""
    assert plan.mergeable_now(_dep_pair("Done")) == []


# --- wave planning ----------------------------------------------------------

def test_plan_waves_orders_by_dependency() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: C\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
        "  - key: D\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A, B]\n"
    )
    tasks = plan.load_tasks(doc)
    waves = plan.plan_waves(tasks)
    assert [sorted(t.key for t in w.tasks) for w in waves] == [
        ["A", "B"],
        ["C", "D"],
    ]


def test_plan_waves_handles_blocked_root() -> None:
    """A task with status Blocked never lets its dependents reach a wave."""
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    status: Blocked\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    blockedBy: [A]\n"
    )
    tasks = plan.load_tasks(doc)
    waves = plan.plan_waves(tasks)
    assert waves == []
    assert {t.key for t in plan.unreachable(tasks, waves)} == {"B"}


def test_parallelism_estimate() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: C\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
    )
    tasks = plan.load_tasks(doc)
    waves = plan.plan_waves(tasks)
    assert plan.parallelism_estimate(waves) == 3


# --- filtering --------------------------------------------------------------

def test_parse_label_filter_basic() -> None:
    assert plan.parse_label_filter("size:M,area:schema") == [
        ("size", "M"),
        ("area", "schema"),
    ]


def test_parse_label_filter_rejects_bad_clause() -> None:
    with pytest.raises(plan.ValidationError, match="prefix:value"):
        plan.parse_label_filter("size_M")


def test_filter_tasks_by_label() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S, area:schema]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:M, area:rpc]\n"
    )
    tasks = plan.load_tasks(doc)
    filtered = plan.filter_tasks(tasks, [("area", "schema")])
    assert [t.key for t in filtered] == ["A"]


def test_filter_tasks_by_only() -> None:
    doc = _yaml(
        "  - key: A\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:M]\n"
    )
    tasks = plan.load_tasks(doc)
    filtered = plan.filter_tasks(tasks, None, only_keys=["B"])
    assert [t.key for t in filtered] == ["B"]


def _dep_alias_doc(b_row_extra: dict) -> dict:
    base = {"summary": "s", "description": "d", "type": "Story",
            "labels": ["size:S", "type:component"]}
    return {"tasks": [
        {"key": "A", **base},
        {"key": "B", **base, **b_row_extra},
    ]}


def test_dependency_field_aliases_accepted():
    """depends_on / blocked_by / dependsOn parse as blockedBy — a silently
    ignored spelling voided all ordering in the partner-hub Stage B run."""
    import claude_dispatcher.plan as plan_mod
    tasks = plan_mod.load_tasks(_dep_alias_doc({"depends_on": ["A"]}))
    assert next(t for t in tasks if t.key == "B").blocked_by == ["A"]


def test_dependency_field_conflict_rejected():
    import pytest
    import claude_dispatcher.plan as plan_mod
    with pytest.raises(plan_mod.ValidationError):
        plan_mod.load_tasks(_dep_alias_doc({"blockedBy": ["A"], "depends_on": ["A"]}))


# --- declared model floor ---------------------------------------------------
#
# Operator ruling 2026-09-04, as corrected: the financial floor is "nothing
# BELOW Opus" — Opus itself is in. My first reading of it excluded Opus and
# rewrote ten Opus pins down to fable in the wallet worklist. What made that
# silent is that the rule existed only as a comment and a three-entry seal on
# the cascade map: nothing read it at load. Haiku scaffolds already cost 32
# rounds of self-consistency repair on the go dogfood under the same absence.

def _floored(tasks_block: str, allow: str, reason: str = "financial") -> object:
    import io
    from ruamel.yaml import YAML
    y = YAML(typ="rt")
    return y.load(io.StringIO(
        f"model_floor:\n  reason: {reason}\n  allow: {allow}\n"
        "tasks:\n" + tasks_block
    ))


_ROW = (
    "  - key: A\n"
    "    summary: x\n"
    "    description: y\n"
    "    type: Task\n"
    "    labels: [size:S]\n"
)
_ALL = "[claude-opus-5, claude-fable-5-1, gpt-5.6-sol, grok-4.6]"


def test_a_row_inside_the_declared_floor_loads() -> None:
    """Opus is INSIDE the floor -- the point of the correction. A floor that
    refused the very model it names as its bar would be the same bug again."""
    doc = _floored(_ROW + "    model: claude-opus-5\n", _ALL)
    assert [t.model for t in plan.load_tasks(doc)] == ["claude-opus-5"]


def test_a_row_below_the_declared_floor_is_refused() -> None:
    doc = _floored(_ROW + "    model: claude-haiku-4-5-20251001\n", _ALL)
    with pytest.raises(plan.ValidationError, match="outside this run's declared"):
        plan.load_tasks(doc)


def test_an_unpinned_row_is_refused_under_a_declared_floor() -> None:
    """No `model:` means the family CLI's default applies, which no run report
    shows -- the invisible-default trap that put an epic at ~$72/task. A floor
    is a claim about spend, so it cannot hold over a model nobody stated."""
    doc = _floored(_ROW, _ALL)
    with pytest.raises(plan.ValidationError, match="pins no model"):
        plan.load_tasks(doc)


def test_a_floor_the_cascade_could_step_outside_is_refused() -> None:
    """The cascade REWRITES the model on a family change, so checking only the
    authored rows leaves a floor the run can walk out of at rung two."""
    doc = _floored(_ROW + "    model: claude-opus-5\n", "[claude-opus-5]")
    with pytest.raises(plan.ValidationError, match="cross-family cascade"):
        plan.load_tasks(doc)


def test_no_declared_floor_means_no_check() -> None:
    """Every worklist that predates the floor must keep loading, and a dogfood
    run legitimately spends a cheap model. A floor is opt-in per run."""
    import io
    from ruamel.yaml import YAML
    doc = YAML(typ="rt").load(io.StringIO(
        "tasks:\n" + _ROW + "    model: claude-haiku-4-5-20251001\n"))
    assert len(plan.load_tasks(doc)) == 1


def test_an_empty_allow_list_is_a_config_error_not_an_open_floor() -> None:
    """`allow: []` reads as "nothing is permitted"; treating it as "no floor"
    would silently disable the check that was explicitly asked for."""
    doc = _floored(_ROW + "    model: claude-opus-5\n", "[]")
    with pytest.raises(plan.ValidationError, match="declares no 'allow'"):
        plan.load_tasks(doc)


def test_floor_defects_merge_with_the_other_worklist_defects() -> None:
    """One raise site, so an author fixes routing AND structure in one round
    trip -- and so the floor cannot be reported as a role-protocol failure."""
    doc = _floored(
        _ROW + "    model: claude-haiku-4-5-20251001\n"
        "  - key: B\n    summary: x\n    description: y\n    type: Task\n"
        "    labels: [size:S]\n    model: claude-sonnet-5\n", _ALL)
    with pytest.raises(plan.ValidationError) as exc:
        plan.load_tasks(doc)
    msg = str(exc.value)
    assert "A pins model" in msg and "B pins model" in msg, msg
    assert "role check" not in msg, "floor defects are not role-protocol errors"


# --- agent/model family agreement -------------------------------------------

def _routed(agent: str, model: str) -> object:
    import io
    from ruamel.yaml import YAML
    return YAML(typ="rt").load(io.StringIO(
        "tasks:\n" + _ROW + f"    agent: {agent}\n    model: {model}\n"))


def test_a_cross_family_agent_model_pair_is_refused() -> None:
    """The pair that killed WAL-CHAIN-3: claude holding codex's model id. The
    spawn exits 1 in under a second having spent $0.00 and run no turn, which
    the dispatcher can only report as a dead spawn."""
    with pytest.raises(plan.ValidationError, match="belongs to the 'codex' family"):
        plan.load_tasks(_routed("claude", "gpt-5.6-sol"))


def test_a_matching_agent_model_pair_loads() -> None:
    for agent, model in (("claude", "claude-opus-5"), ("codex", "gpt-5.6-sol"),
                         ("grok", "grok-4.6")):
        assert len(plan.load_tasks(_routed(agent, model))) == 1, (agent, model)


def test_an_unrecognised_model_prefix_is_not_a_defect() -> None:
    """A new model must be routable the day it exists. Refusing ids this table
    does not know would make the table a gate on every future model -- the
    KNOWN_EFFORTS mistake, which silently downgraded every codex row."""
    assert len(plan.load_tasks(_routed("claude", "some-unreleased-model"))) == 1


def test_a_bracketed_context_variant_still_matches_its_family() -> None:
    """`claude-opus-5[1m]` is a real pin in the wallet worklist; a prefix test
    that tripped over the suffix would refuse a correct row."""
    assert len(plan.load_tasks(_routed("claude", "claude-opus-5[1m]"))) == 1
