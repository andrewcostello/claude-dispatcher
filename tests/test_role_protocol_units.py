"""D1 seals (P2): units, phase order, correlation warnings, dispatch ordering.

Bound to `role_protocol`'s public API, never to a `role` field on `plan.Task`:
P1 deliberately does not model one (a field defaulting to LEGACY while
`load_tasks` does not parse it would assert "legacy" for rows that carry a
role — a fail-open by construction), and P3 may add it only in the commit that
parses it. These fixtures therefore carry the role on `Task.raw`, which is where
the contract says it is read from.

The dispatch-ordering seals derive today's behaviour FROM `plan`'s own
`_DISPATCH_SATISFIED_*` sets rather than hand-listing statuses, so a change to
either module's notion of "Done-or-later" cannot pass unnoticed — the
`test_risk.test_go_table_critical_paths_are_all_authority_paths` pattern applied
to the dispatch table.
"""

from __future__ import annotations

import pytest

from claude_dispatcher import plan
from claude_dispatcher.role_protocol import (
    IMMUTABLE_OVERRIDE_FIELD,
    MANDATORY_PHASE_ORDER,
    Role,
    RoleValidation,
    agent_correlation_warnings,
    dispatch_satisfied_statuses,
    units_of,
    validate,
)


# --------------------------------------------------------------------------- #
# Fixture helpers — a Task whose protocol facts live on `raw`
# --------------------------------------------------------------------------- #


def _task(
    key: str,
    *,
    role: object | None = None,
    blocked_by: tuple[str, ...] = (),
    agent: str | None = None,
    model: str | None = None,
    status: str = plan.TODO,
    extra: dict | None = None,
) -> plan.Task:
    raw: dict = {"key": key, "summary": key, "status": status}
    if role is not None:
        raw["role"] = role
    if blocked_by:
        raw["blockedBy"] = list(blocked_by)
    if agent is not None:
        raw["agent"] = agent
    if model is not None:
        raw["model"] = model
    raw.update(extra or {})
    return plan.Task(
        key=key,
        summary=key,
        description="",
        type="task",
        labels=[],
        blocked_by=list(blocked_by),
        status=status,
        raw=raw,
        model=model,
        agent=agent,
    )


def _unit(prefix: str) -> list[plan.Task]:
    """A complete, legal unit: scaffold -> seals -> bodies."""
    return [
        _task(f"{prefix}-P1", role="scaffold"),
        _task(f"{prefix}-P2", role="seals", blocked_by=(f"{prefix}-P1",)),
        _task(f"{prefix}-P3", role="bodies", blocked_by=(f"{prefix}-P2",)),
    ]


def _errors_for(validation: RoleValidation, key: str) -> list[str]:
    return [e for e in validation.errors if key in e]


# --------------------------------------------------------------------------- #
# The happy path — so every refusal row below is measured against a pass
# --------------------------------------------------------------------------- #


def test_a_complete_unit_validates_with_no_errors_and_no_warnings() -> None:
    """Red now: `validate` raises NotImplementedError.
    Green when: a scaffold->seals->bodies chain validates clean.
    Falsify: any of the PO rules firing on a legal unit reddens this first.
    """
    validation = validate(_unit("D1"))
    assert validation.errors == ()
    assert validation.warnings == ()
    assert validation.ok is True
    assert sorted(s.task_key for s in validation.specs) == ["D1-P1", "D1-P2", "D1-P3"]
    assert [u.unit_id for u in validation.units] == ["D1-P1"]


def test_a_file_of_only_legacy_rows_is_silent() -> None:
    """Every `features/*/tasks.yaml` in this repo is role-less: LEGACY must cost
    nothing — no immutable paths, no ordering obligations, no warnings.

    Red now: NotImplementedError.
    Green when: role-less rows validate clean and appear in no unit.
    Falsify: make an absent `role:` imply an ordering obligation — this reddens.
    """
    tasks = [
        _task("OLD-1"),
        _task("OLD-2", blocked_by=("OLD-1",)),
        _task("OLD-3", blocked_by=("OLD-2",)),
    ]
    validation = validate(tasks)
    assert validation.errors == ()
    assert validation.warnings == ()
    assert validation.units == ()
    assert {s.role for s in validation.specs} == {Role.LEGACY}


# --------------------------------------------------------------------------- #
# Phase-order refusals — one row per rule, PO-1 .. PO-5
# --------------------------------------------------------------------------- #


def test_po1_seals_without_a_direct_scaffold_predecessor_is_refused() -> None:
    """Red now: NotImplementedError.
    Green when: a SEALS task with no SCAFFOLD in its direct blockedBy errors.
    Falsify: delete the PO-1 check — this row goes red.
    """
    tasks = [_task("D1-P2", role="seals")]
    validation = validate(tasks)
    assert not validation.ok
    assert _errors_for(validation, "D1-P2"), validation.errors
    assert any("scaffold" in e.lower() for e in validation.errors), validation.errors


def test_po2_bodies_without_a_direct_seals_predecessor_is_refused() -> None:
    """The edge IS the gate: without it there is nothing for `runnable_now` to
    wait on, so an absent edge must be a refusal, not an empty unit that passes.

    Red now: NotImplementedError.
    Green when: a BODIES task blocked only by the scaffold errors.
    """
    tasks = [
        _task("D1-P1", role="scaffold"),
        _task("D1-P2", role="seals", blocked_by=("D1-P1",)),
        _task("D1-P3", role="bodies", blocked_by=("D1-P1",)),
    ]
    validation = validate(tasks)
    assert not validation.ok
    assert _errors_for(validation, "D1-P3"), validation.errors
    assert any("seals" in e.lower() for e in validation.errors), validation.errors


def test_po2_is_not_satisfied_transitively_through_a_plain_task() -> None:
    """Direct edges only: a transitive path would let a BODIES task satisfy "has
    a seals predecessor" through some other unit's seals while its own unit's
    seals never existed.

    Red now: NotImplementedError.
    Green when: only a directly-named SEALS predecessor satisfies PO-2.
    Falsify: implement PO-2 over transitive reachability — this goes red.
    """
    tasks = [
        _task("D1-P1", role="scaffold"),
        _task("D1-P2", role="seals", blocked_by=("D1-P1",)),
        _task("GLUE", blocked_by=("D1-P2",)),
        _task("D1-P3", role="bodies", blocked_by=("GLUE",)),
    ]
    validation = validate(tasks)
    assert not validation.ok
    assert _errors_for(validation, "D1-P3"), validation.errors


def test_po3_adjudicate_without_a_phase_predecessor_is_refused() -> None:
    """Red now: NotImplementedError.
    Green when: an ADJUDICATE task must name a scaffold/seals/bodies predecessor.
    """
    tasks = [
        _task("OLD-1"),
        _task(
            "D1-P4",
            role="adjudicate",
            blocked_by=("OLD-1",),
            extra={"disputed_paths": ["tests/test_x.py"]},
        ),
    ]
    validation = validate(tasks)
    assert not validation.ok
    assert _errors_for(validation, "D1-P4"), validation.errors


def test_po4_ambiguous_unit_membership_is_refused() -> None:
    """Two seals predecessors resolving to different scaffold roots is a typed
    error, not a silent choice of one.

    Red now: NotImplementedError.
    Green when: the BODIES row naming two units' seals tasks errors.
    """
    tasks = [
        _task("A-P1", role="scaffold"),
        _task("A-P2", role="seals", blocked_by=("A-P1",)),
        _task("B-P1", role="scaffold"),
        _task("B-P2", role="seals", blocked_by=("B-P1",)),
        _task("X-P3", role="bodies", blocked_by=("A-P2", "B-P2")),
    ]
    validation = validate(tasks)
    assert not validation.ok
    assert _errors_for(validation, "X-P3"), validation.errors


def test_po5_phase_inversion_inside_one_unit_is_refused() -> None:
    """A seals task blocked by a sibling BODIES task of its own unit is a phase
    inversion that is not a cycle, so `plan._check_for_cycles` cannot see it.

    Fixture (no cycle): D1-P1 scaffold; D1-P2b seals -> P1; D1-P3 bodies -> P2b;
    D1-P2a seals -> {P1, P3}. P3's unit is D1-P1, so P2a names a later-phase
    task of its OWN unit.

    Red now: NotImplementedError.
    Green when: PO-5 refuses it.
    Falsify: drop PO-5 and rely on cycle detection — this row goes red because
    the graph is acyclic.
    """
    tasks = [
        _task("D1-P1", role="scaffold"),
        _task("D1-P2b", role="seals", blocked_by=("D1-P1",)),
        _task("D1-P3", role="bodies", blocked_by=("D1-P2b",)),
        _task("D1-P2a", role="seals", blocked_by=("D1-P1", "D1-P3")),
    ]
    validation = validate(tasks)
    assert not validation.ok
    assert _errors_for(validation, "D1-P2a"), validation.errors


def test_every_per_row_failure_is_collected_not_raised_on_the_first() -> None:
    """One run must report every broken row; the first must not mask the rest.

    Red now: NotImplementedError propagates instead of being collected.
    Green when: `validate` returns errors for BOTH bad rows.
    Falsify: `raise` on the first per-row failure — the second key is missing.
    """
    tasks = [
        _task("BAD-1", role="scaffolding"),
        _task("BAD-2", role=["scaffold", "seals"]),
        _task("BAD-3", role="legacy"),
    ]
    validation = validate(tasks)
    assert not validation.ok
    for key in ("BAD-1", "BAD-2", "BAD-3"):
        assert _errors_for(validation, key), (key, validation.errors)


def test_errors_are_ordered_by_task_key_and_two_runs_are_byte_identical() -> None:
    """Determinism: two runs over one file produce identical output.

    Red now: NotImplementedError.
    Green when: errors are sorted by task key (and the same twice).
    Falsify: iterate a set — the ordering assertion goes red.
    """
    tasks = [
        _task("Z-1", role="unknown"),
        _task("M-1", role="unknown"),
        _task("A-1", role="unknown"),
    ]
    assert [t.key for t in tasks] != sorted(t.key for t in tasks), (
        "the fixture must be UNsorted or the ordering assertion is vacuous"
    )
    first = validate(tasks)
    second = validate(tasks)
    assert first.errors == second.errors
    assert first.warnings == second.warnings
    keys_in_order = [
        key for key in ("A-1", "M-1", "Z-1") if _errors_for(first, key)
    ]
    positions = [
        min(i for i, e in enumerate(first.errors) if key in e) for key in keys_in_order
    ]
    assert positions == sorted(positions), first.errors


# --------------------------------------------------------------------------- #
# Warnings — reported, never refusing
# --------------------------------------------------------------------------- #


def test_incomplete_unit_warns_but_does_not_refuse() -> None:
    """A worklist is legitimately authored incrementally, so an incomplete unit
    is a warning; refusing would block the first commit of every unit.

    Red now: NotImplementedError.
    Green when: a scaffold with no seals dependent and a seals with no bodies
    dependent each warn, and `ok` stays True.
    """
    scaffold_only = validate([_task("D1-P1", role="scaffold")])
    assert scaffold_only.errors == ()
    assert scaffold_only.ok is True
    assert any("D1-P1" in w for w in scaffold_only.warnings), scaffold_only.warnings

    no_bodies = validate(
        [
            _task("D1-P1", role="scaffold"),
            _task("D1-P2", role="seals", blocked_by=("D1-P1",)),
        ]
    )
    assert no_bodies.errors == ()
    assert any("D1-P2" in w for w in no_bodies.warnings), no_bodies.warnings


def test_redundant_override_entry_warns() -> None:
    """A duplicated protection is invariant 5's failure mode: two globs covering
    one fact let a mutation delete half while the suite stays green.

    Red now: NotImplementedError.
    Green when: an override entry already covered by the role default warns
    (and does not error).
    """
    tasks = _unit("D1")
    tasks[2] = _task(
        "D1-P3",
        role="bodies",
        blocked_by=("D1-P2",),
        extra={IMMUTABLE_OVERRIDE_FIELD: ["**/tests/**"]},
    )
    validation = validate(tasks)
    assert validation.errors == ()
    assert any("D1-P3" in w for w in validation.warnings), validation.warnings


def test_legacy_and_role_carrying_rows_in_one_file_warns() -> None:
    """Legal and expected during migration, worth seeing.

    Red now: NotImplementedError.
    Green when: the mix warns without refusing.
    """
    tasks = [*_unit("D1"), _task("OLD-1")]
    validation = validate(tasks)
    assert validation.errors == ()
    assert validation.ok is True
    assert validation.warnings, "the legacy/role mix must be reported"


# --------------------------------------------------------------------------- #
# units_of — derived from the dependency edges, never declared
# --------------------------------------------------------------------------- #


def test_units_are_keyed_by_their_scaffold_task_and_members_are_derived() -> None:
    """Red now: `units_of` raises NotImplementedError.
    Green when: membership follows the direct blockedBy edges.
    Falsify: group by a key prefix instead — the ADJUDICATE row (whose key does
    not share the prefix) lands in no unit and this goes red.
    """
    tasks = [
        *_unit("D1"),
        _task(
            "DISPUTE-7",
            role="adjudicate",
            blocked_by=("D1-P3",),
            extra={"disputed_paths": ["tests/test_role_protocol_diff.py"]},
        ),
    ]
    units = units_of(tasks)
    assert len(units) == 1
    unit = units[0]
    assert unit.unit_id == "D1-P1"
    assert unit.scaffold_key == "D1-P1"
    assert unit.seals_keys == ("D1-P2",)
    assert unit.bodies_keys == ("D1-P3",)
    assert unit.adjudicate_keys == ("DISPUTE-7",)


def test_units_are_deterministic_and_exclude_legacy_rows() -> None:
    """Red now: NotImplementedError.
    Green when: units sort by unit_id, members sort within a unit, and LEGACY
    rows appear nowhere.
    """
    tasks = [*_unit("Z9"), *_unit("A1"), _task("OLD-1")]
    tasks.append(_task("A1-P3b", role="bodies", blocked_by=("A1-P2",)))
    units = units_of(tasks)
    assert [u.unit_id for u in units] == ["A1-P1", "Z9-P1"]
    a1 = units[0]
    assert a1.bodies_keys == ("A1-P3", "A1-P3b")
    all_members = {
        key
        for u in units
        for key in (u.scaffold_key, *u.seals_keys, *u.bodies_keys, *u.adjudicate_keys)
    }
    assert "OLD-1" not in all_members
    assert units_of(tasks) == units


def test_mandatory_phase_order_is_the_order_units_are_built_from() -> None:
    """The seal that makes the phase table itself falsifiable.

    Red now: `units_of` raises NotImplementedError.
    Green when: the three mandatory phases each populate their own member field.
    Falsify: reorder MANDATORY_PHASE_ORDER — the zip below misaligns.
    """
    units = units_of(_unit("D1"))
    assert MANDATORY_PHASE_ORDER == (Role.SCAFFOLD, Role.SEALS, Role.BODIES)
    unit = units[0]
    assert (unit.scaffold_key, unit.seals_keys, unit.bodies_keys) == (
        "D1-P1",
        ("D1-P2",),
        ("D1-P3",),
    )


# --------------------------------------------------------------------------- #
# agent_correlation_warnings — a warning, never a refusal
# --------------------------------------------------------------------------- #


def test_default_agent_is_required_and_has_no_module_level_guess() -> None:
    """Under `--no-claude` the effective implementer is grok, not claude, so a
    module-level default would make two identical rows compare unequal and the
    warning would silently never fire.

    Red now: `validate` raises NotImplementedError on the second half.
    Green when: the call without `default_agent` is a TypeError and the call
    with it returns a tuple.
    """
    with pytest.raises(TypeError):
        agent_correlation_warnings(RoleValidation())  # type: ignore[call-arg]
    validation = validate(_unit("D1"))
    assert isinstance(
        agent_correlation_warnings(validation, default_agent="claude"), tuple
    )


def test_shared_family_between_seals_and_bodies_warns_once_per_unit() -> None:
    """Red now: NotImplementedError.
    Green when: one warning naming the unit and the shared family.
    """
    tasks = [
        _task("D1-P1", role="scaffold", agent="claude"),
        _task("D1-P2", role="seals", blocked_by=("D1-P1",), agent="grok"),
        _task("D1-P3", role="bodies", blocked_by=("D1-P2",), agent="grok"),
    ]
    warnings = agent_correlation_warnings(validate(tasks), default_agent="claude")
    assert len(warnings) == 1, warnings
    assert "D1-P1" in warnings[0]
    assert "grok" in warnings[0]


def test_cross_family_seals_and_bodies_do_not_warn() -> None:
    """Non-vacuity partner of the row above: the warning must be able NOT to fire.

    Red now: NotImplementedError.
    Green when: different families produce no warning.
    """
    tasks = [
        _task("D1-P1", role="scaffold", agent="claude"),
        _task("D1-P2", role="seals", blocked_by=("D1-P1",), agent="grok"),
        _task("D1-P3", role="bodies", blocked_by=("D1-P2",), agent="claude"),
    ]
    assert agent_correlation_warnings(validate(tasks), default_agent="claude") == ()


def test_absent_agent_resolves_to_the_run_default_before_comparing() -> None:
    """An absent `agent:` and an explicit `agent: claude` are the same family.

    Red now: NotImplementedError.
    Green when: the comparison is on the EFFECTIVE family.
    Falsify: compare `declared_agent` verbatim — the None row compares unequal
    to "claude" and this goes red.
    """
    tasks = [
        _task("D1-P1", role="scaffold"),
        _task("D1-P2", role="seals", blocked_by=("D1-P1",)),
        _task("D1-P3", role="bodies", blocked_by=("D1-P2",), agent="claude"),
    ]
    warnings = agent_correlation_warnings(validate(tasks), default_agent="claude")
    assert len(warnings) == 1, warnings
    assert "claude" in warnings[0]
    # ... and under a grok run default the same rows correlate on grok instead.
    tasks[2] = _task("D1-P3", role="bodies", blocked_by=("D1-P2",))
    grok_warnings = agent_correlation_warnings(validate(tasks), default_agent="grok")
    assert len(grok_warnings) == 1, grok_warnings
    assert "grok" in grok_warnings[0]


def test_a_different_model_tier_does_not_clear_the_correlation_warning() -> None:
    """Same family means correlated failure modes, which is what the warning is
    about; opus-vs-sonnet is not a different family.

    Red now: NotImplementedError.
    Green when: the warning still fires with differing `model:` values.
    """
    tasks = [
        _task("D1-P1", role="scaffold"),
        _task(
            "D1-P2", role="seals", blocked_by=("D1-P1",), agent="claude", model="opus"
        ),
        _task(
            "D1-P3", role="bodies", blocked_by=("D1-P2",), agent="claude", model="sonnet"
        ),
    ]
    warnings = agent_correlation_warnings(validate(tasks), default_agent="claude")
    assert len(warnings) == 1, warnings


def test_correlation_warnings_are_one_per_unit_and_sorted_by_unit_id() -> None:
    """Red now: NotImplementedError.
    Green when: two correlated units yield two warnings, sorted by unit id.
    """
    tasks = [
        _task("Z9-P1", role="scaffold"),
        _task("Z9-P2", role="seals", blocked_by=("Z9-P1",), agent="claude"),
        _task("Z9-P3", role="bodies", blocked_by=("Z9-P2",), agent="claude"),
        _task("A1-P1", role="scaffold"),
        _task("A1-P2", role="seals", blocked_by=("A1-P1",), agent="grok"),
        _task("A1-P3", role="bodies", blocked_by=("A1-P2",), agent="grok"),
    ]
    warnings = agent_correlation_warnings(validate(tasks), default_agent="claude")
    assert len(warnings) == 2, warnings
    assert "A1-P1" in warnings[0]
    assert "Z9-P1" in warnings[1]


# --------------------------------------------------------------------------- #
# dispatch_satisfied_statuses — Role x Role x integration, total
# --------------------------------------------------------------------------- #

_KNOWN_STATUSES = {
    plan.TODO,
    plan.IN_PROGRESS,
    plan.DONE,
    plan.BLOCKED,
    plan.ESCALATED,
    plan.AWAITING_REVIEW,
    plan.MERGED,
}


@pytest.mark.parametrize("integration", ["branch", "pr"])
@pytest.mark.parametrize("dependency", sorted(Role, key=lambda r: r.value))
@pytest.mark.parametrize("dependent", sorted(Role, key=lambda r: r.value))
def test_dispatch_dispatch_is_total_over_role_x_role_x_integration(
    dependent: Role, dependency: Role, integration: str
) -> None:
    """All 5 x 5 x 2 combinations answer with a real status set.

    A combination that falls out of the bottom (returning None, or raising for a
    legal pair) would make `runnable_now` unable to order that edge at all.

    The NOTE that stood here raised (dependency=SEALS, dependent in {SCAFFOLD,
    SEALS, ADJUDICATE, LEGACY}) as a P2 dispute and sealed those eight pairs for
    TOTALITY only. P4 (2026-08-07): the dispute is settled — the P2 ruling of
    2026-08-04 reads "**Any edge whose *dependency* is a `seals` task uses
    `{Merged}` in `pr` mode**, not just seals->bodies. The narrower reading let
    an `adjudicate` task dispatch against an open, unreviewed seals PR — the
    same fail-open the seals->bodies narrowing exists to close." So the sets are
    no longer unstated and are asserted exactly.

    A non-empty subset of seven statuses was satisfiable by almost anything:
    returning `{To Do}` for those eight pairs left the suite green, which is an
    ordering gate that dispatches against a seals task that has not started.

    Red now: NotImplementedError.
    Green when: the dispatch is exhaustive over both roles and both modes, and
    every seals-dependency edge in `pr` mode is exactly `{Merged}`.
    Falsify: widen any seals-dependency edge in pr mode beyond `{Merged}` — the
    row for that pair goes red.
    """
    satisfied = dispatch_satisfied_statuses(
        dependent, dependency, integration=integration
    )
    assert isinstance(satisfied, frozenset)
    assert satisfied, f"{dependent}/{dependency}/{integration} satisfied by nothing"
    assert satisfied <= _KNOWN_STATUSES, satisfied
    if dependency is Role.SEALS and integration == "pr":
        assert satisfied == frozenset({plan.MERGED}), (
            f"{dependent.value} may dispatch against a seals dependency in "
            f"status {sorted(satisfied)}; the 2026-08-04 P2 ruling requires "
            "exactly {'Merged'} for EVERY edge whose dependency is a seals task"
        )


@pytest.mark.parametrize("integration", ["", "PR", "Branch", "worktree", "pr ", "auto"])
def test_unknown_integration_mode_raises_instead_of_picking_a_default_set(
    integration: str,
) -> None:
    """An unknown mode must not silently get branch-mode's (or pr-mode's) set.

    Red now: NotImplementedError, which is not one of the asserted types.
    Green when: an unrecognised integration mode raises.
    Falsify: `if integration == "pr": ... else: branch_set` — every row here
    goes red.
    """
    with pytest.raises((ValueError, TypeError, KeyError)):
        dispatch_satisfied_statuses(Role.BODIES, Role.SEALS, integration=integration)


@pytest.mark.parametrize("integration", ["branch", "pr"])
@pytest.mark.parametrize(
    "dependency",
    sorted((r for r in Role if r is not Role.SEALS), key=lambda r: r.value),
)
@pytest.mark.parametrize("dependent", sorted(Role, key=lambda r: r.value))
def test_every_edge_not_into_seals_keeps_todays_behaviour_exactly(
    dependent: Role, dependency: Role, integration: str
) -> None:
    """The compatibility requirement, derived from `plan`'s own sets.

    LEGACY<->LEGACY is included by construction, which is the byte-identical
    guarantee pre-protocol worklists depend on.

    Red now: NotImplementedError.
    Green when: the answer equals `plan._DISPATCH_SATISFIED_BRANCH` /
    `_DISPATCH_SATISFIED_PR` for every non-SEALS dependency.
    Falsify: narrow any other edge — that row goes red. Change plan's sets
    without changing this module — every row goes red.
    """
    expected = (
        plan._DISPATCH_SATISFIED_PR
        if integration == "pr"
        else plan._DISPATCH_SATISFIED_BRANCH
    )
    assert (
        dispatch_satisfied_statuses(dependent, dependency, integration=integration)
        == expected
    )


def test_legacy_to_legacy_edge_is_byte_identical_to_todays_sets() -> None:
    """Called out on its own because it is the compatibility requirement.

    Red now: NotImplementedError.
    Green when: LEGACY<-LEGACY matches plan's sets in both modes.
    """
    assert dispatch_satisfied_statuses(
        Role.LEGACY, Role.LEGACY, integration="branch"
    ) == plan._DISPATCH_SATISFIED_BRANCH
    assert dispatch_satisfied_statuses(
        Role.LEGACY, Role.LEGACY, integration="pr"
    ) == plan._DISPATCH_SATISFIED_PR


def test_seals_to_bodies_narrows_to_merged_in_pr_mode() -> None:
    """The seals gate is a REVIEW gate, not a code-availability gate: a seals PR
    can still be rejected, and bodies starting against unreviewed seals would
    rebuild the honour system one level up.

    Red now: NotImplementedError.
    Green when: pr mode yields exactly {Merged}.
    Falsify: reuse `_DISPATCH_SATISFIED_PR` for this edge — Awaiting Review
    leaks back in and this goes red.
    """
    pr_set = dispatch_satisfied_statuses(Role.BODIES, Role.SEALS, integration="pr")
    assert pr_set == frozenset({plan.MERGED})
    assert plan.AWAITING_REVIEW not in pr_set
    assert plan.DONE not in pr_set


def test_seals_to_bodies_stays_done_in_branch_mode() -> None:
    """Done is already terminal in branch mode, so the same edge does not narrow.

    Red now: NotImplementedError.
    Green when: branch mode yields exactly {Done}.
    """
    assert dispatch_satisfied_statuses(
        Role.BODIES, Role.SEALS, integration="branch"
    ) == frozenset({plan.DONE})
