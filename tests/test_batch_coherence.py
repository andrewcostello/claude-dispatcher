"""Unit DF-3 — P2 seals: a batch that mixes roles (or rulebooks) is refused
at PLAN time, through the loader, before anything runs.

**P2. Written by an author who did not write the scaffold and will not write
the body — the separation whose absence produced this project's 24 vacuous
seals.** Every row here drives the PRODUCTION entry point — `plan.load_tasks`,
the one point every consumer of a worklist funnels through (the scaffold's
own measurement: `run`, `resume`, `status`, `bakeoff`, `merge_engine`,
`orchestrator` all reach tasks via it) — never the pure function it fronts.
The D1 wiring lesson (`test_role_protocol_wiring.py`) is applied as law: a
seal that calls `batch_coherence.batch_errors` itself can never notice that
nothing else does, and DF-3-3 owes the body AND the `load_tasks` call in ONE
commit, so the load path is exactly the surface these seals must bind to.

Every citation is ``Measured under:`` `5ca4af4` (tip of
`feat/DF-3-2-...`'s base, carrying the DF-3-1 contract), CPython 3.13,
pytest 9.1.0, 2026-08-13. Nothing is carried from the scaffold's docstring
on trust: both defects, both corrected twins, and both already-refused
worlds below were RE-MEASURED for this file through `yaml_io.loads` +
`plan.load_tasks` on this tree.

The two defects, re-measured for this file
==========================================
  * **Two roles in one batch.** A protocol-legal three-row unit whose
    SCAFFOLD and BODIES rows share ``batch_id: MIX`` loads with **0 errors,
    0 warnings**. One branch, one worktree, one implementer session, two
    roles — `loop_gate.sole_role` would answer ``None`` and the run burns a
    wave on a defect the FILE already contained.
  * **One role, two rulebook pages.** Two ADJUDICATE rows sharing
    ``batch_id: ADJ`` with ``disputed_paths: [docs/a.md]`` vs
    ``[docs/b.md]`` load with **0 errors and exactly 1 warning — W-NO-SEALS
    about the fixture's scaffold row, nothing about the batch**.

The D8-P2 trap, and what every red row does about it
====================================================
The task description names the shape to avoid: D8's P2 once drove its worlds
over a nonexistent ``repo_root``, every world collapsed to one identical
error, and the control "passed" while proving nothing. The discipline here:

  * every fixture is a REAL worklist — YAML text through `yaml_io.loads`,
    loaded by `plan.load_tasks` exactly as production loads it, protocol-
    legal in every respect except the one defect the row injects;
  * every red row runs an in-call CONTROL first: the CORRECTED TWIN — same
    rows, batch relation repaired and nothing else — must LOAD. The control
    holds in BOTH worlds (today and after DF-3-3), so a fixture that is
    broken for an unrelated reason fails the control as a REAL failure and
    can never let the refusal assertion pass vacuously;
  * the refusal assertions then pin the rule id, every member key, and the
    per-rule facts (each row's role / the differing pages) in the refusal
    TEXT — `plan.load_tasks` raises with messages only (`validate` discards
    its internal key/rule pair at the boundary), so a message that does not
    carry its rule id sends the author back to read the module to learn
    which rule fired. Same law the wiring seals already enforce for PO-2.

Expected state of these rows TODAY, stated so nobody infers vacuity
===================================================================
Three GUARD rows are green today and must stay green — they are what makes
the cheap wrong body ("refuse any batch", "guess a role for a broken row")
fail. Six rows are RED at the P1 stub and carried as
``pytest.mark.xfail(condition=<batch_errors still raises the P1 stub>,
raises=..., strict=True)`` — the DF-4-2 mechanism, adopted with one
adjustment forced by this unit's shape:

  * the CONDITION is computed at import time by calling the seam
    (`batch_errors((), ())`), so the marker exists exactly as long as the
    stub does and self-retires the commit DF-3-3 lands, with no test edit
    and no silent XPASS (``strict=True``);
  * ``raises`` cannot be ``NotImplementedError`` here: the stub is NOT on
    the load path (the scaffold refused to wire it — a raising stub there
    breaks every dispatch), so no row ever sees the stub raise. What a red
    row sees today is `plan.load_tasks` RETURNING — the measured defect
    verbatim — which `pytest.raises` reports as ``Failed``. Five rows
    therefore pin ``raises=pytest.fail.Exception``: the ONLY tolerated
    failure is "the defective worklist loaded", and a control assertion
    failing today reports as a real failure, not an xfail. The merge row
    pins ``raises=AssertionError`` and its docstring says exactly why its
    channel differs.
  * rejected: plain red (fails the gate this repo actually runs and poisons
    every concurrent unit's whole-suite baseline until DF-3-3);
    unconditional xfail (unremovable — BODIES is denied ``tests/**``, so a
    marker requiring a P3 edit can never be removed); ``pytest.skip`` on
    stub detection (a skipped row runs NO control, and these controls are
    live re-measurements).

What is deliberately NOT sealed here
====================================
  * `tests/test_loop_gate.py` row 18 stays untouched: it is GREEN today by
    design and reddens exactly once, when DF-3-3 lands — seal dispute P2-3
    assigns that amendment to the landing commit, not to this file.
  * The merged refusal's INTERLEAVE order (batch defects vs role errors) is
    not pinned — the contract pins determinism ("byte-identical output over
    one file"), not a merge layout, and the merge row seals exactly that:
    two independent parses of one file must refuse with identical text.
  * `batch_errors`'s direct signature beyond the probe call — the seals
    bind to the load path (see header); the record and rule ids, which the
    scaffold IMPLEMENTED, are sealed by the first guard row.

Baseline, measured here rather than taken on trust
==================================================
``PYTHONPATH=src python -m pytest tests/ -q -o addopts=""`` under `5ca4af4`
(vendored TypeScript parser present, per unit D8-guard's header):

  * WITHOUT this file: **2534 passed + 13 skipped + 8 xfailed, 0 failed**.
  * WITH this file: **2537 passed + 13 skipped + 14 xfailed, 0 failed**,
    exit 0 — exactly this file's three green rows and six conditioned-red
    rows added, and no row in any other file moved.
"""

from __future__ import annotations

import dataclasses

import pytest

from claude_dispatcher import batch_coherence as bc
from claude_dispatcher import plan as plan_mod
from claude_dispatcher import yaml_io


# --------------------------------------------------------------------------- #
# Worklist fixtures — YAML text, loaded the way production loads it. The
# helpers are `test_role_protocol_wiring.py`'s, re-spelled rather than
# imported: a seal file that imports another seal file's harness goes red
# when THAT file is amended, and P4 amendments to the wiring seals are live.
# --------------------------------------------------------------------------- #


def _row(
    key: str,
    *,
    role: str | None = None,
    blocked_by: tuple[str, ...] = (),
    extra: tuple[str, ...] = (),
) -> str:
    lines = [
        f"  - key: {key}",
        f'    summary: "{key}"',
        f'    description: "row {key}"',
        "    type: Task",
        "    labels: [size:XS]",
    ]
    if role is not None:
        lines.append(f"    role: {role}")
    if blocked_by:
        lines.append("    blockedBy: [" + ", ".join(blocked_by) + "]")
    lines.extend(f"    {line}" for line in extra)
    return "\n".join(lines) + "\n"


def _worklist(*rows: str) -> object:
    return yaml_io.loads("project: T\nepic: DF3\ntasks:\n" + "".join(rows))


def _must_load(doc: object, *, control: str) -> None:
    """In-call CONTROL: this corrected/coherent worklist must LOAD.

    Runs in BOTH worlds. Today it re-measures the fixture's health; after
    DF-3-3 it is what proves the refusal next door is about the batch
    relation and nothing else. A failure here is a REAL failure — it is
    outside every row's ``raises=pytest.fail.Exception`` pin on purpose.
    """
    try:
        plan_mod.load_tasks(doc)
    except plan_mod.ValidationError as exc:  # pragma: no cover - control
        raise AssertionError(
            f"the control failed: {control} must load with 0 errors in both "
            f"worlds, or every refusal next to it proves nothing (the D8-P2 "
            f"trap). It was refused: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# Stub detection for the conditioned xfail markers (header CHOICE block).
# The probe is the contract's own cheapest input: a clean (empty) worklist,
# for which an implemented body must answer `()` and touch nothing.
# --------------------------------------------------------------------------- #


def _is_stub(thunk) -> bool:
    try:
        thunk()
    except NotImplementedError:
        return True
    except BaseException:
        return False
    return False


_STUB = _is_stub(lambda: bc.batch_errors((), ()))

_RED_TODAY = (
    "RED by design at P2: batch_errors is the P1 stub and plan.load_tasks "
    "does not yet call it, so the defective worklist LOADS — the measured "
    "defect itself. The marker is conditioned on the stub and self-retires "
    "when DF-3-3 lands body+wiring in one commit — no test edit. Any "
    "failure other than 'the worklist loaded' reports as real even today."
)


# --------------------------------------------------------------------------- #
# GUARD rows — green today, green forever.
# --------------------------------------------------------------------------- #


def test_the_rule_ids_and_the_defect_record_are_already_implemented() -> None:
    """GUARD — the scaffold's IMPLEMENTED data, sealed as shipped.

    The two rule ids spell the loop's two statuses on purpose (plan-time
    refusal and dispatch-time block must read as one story told twice), and
    `BatchDefect` is `validate`'s own (task_key, rule_id, message) triple
    plus the batch, frozen — DF-3-3 merges these without a translation
    layer, and the eventual operator commit adopts them without reshaping.
    """
    assert bc.RULE_BATCH_ROLE == "BATCH-ROLE"
    assert bc.RULE_BATCH_RULE == "BATCH-RULE"

    defect = bc.BatchDefect(
        task_key="A-1", rule_id=bc.RULE_BATCH_ROLE, batch_id="MIX",
        message="BATCH-ROLE: probe",
    )
    assert (defect.task_key, defect.rule_id, defect.batch_id) == (
        "A-1", "BATCH-ROLE", "MIX",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        defect.task_key = "A-2"  # type: ignore[misc]


def test_coherent_batches_still_load_and_are_never_refused() -> None:
    """GUARD — green today, must stay green after DF-3-3.

    Three worlds the cheapest wrong body ("refuse anything carrying a
    batch_id") would break, measured loading clean under `5ca4af4`:

      * the mixed-role fixture's OWN rows with distinct batch_ids — the
        planner's legal spelling for "same wave, separate sessions";
      * two SCAFFOLD rows of two units sharing one batch — one role, one
        (empty) rulebook pair, coherent;
      * an all-LEGACY batch — LEGACY is a role, so one-role-throughout is
        clean; the refusal of legacy MIXTURES (sealed below) must not
        become a refusal of legacy itself.
    """
    _must_load(_worklist(
        _row("A-1", role="scaffold", extra=("batch_id: MIX-1",)),
        _row("A-2", role="seals", blocked_by=("A-1",)),
        _row("A-3", role="bodies", blocked_by=("A-2",), extra=("batch_id: MIX-2",)),
    ), control="the unit with distinct batch_ids")
    _must_load(_worklist(
        _row("U-1", role="scaffold", extra=("batch_id: TWO",)),
        _row("V-1", role="scaffold", extra=("batch_id: TWO",)),
    ), control="the two-scaffold one-role batch")
    _must_load(_worklist(
        _row("L-1", extra=("batch_id: LEG",)),
        _row("L-2", extra=("batch_id: LEG",)),
    ), control="the all-legacy batch")


def test_a_row_whose_spec_failed_to_parse_is_excluded_from_its_batch() -> None:
    """GUARD — green today AND after DF-3-3, by two different mechanisms.

    A row carrying ``role: [scaffold, seals]`` fails `parse_task_role_spec`
    and the worklist is already refused with that row's OWN error (measured
    under `5ca4af4`: refused, message names X-1 and 'two roles is a typed
    error'). The scaffold's CHOICE: such a row is EXCLUDED from its batch's
    computation — a second defect on the same row would double-report, and
    guessing a role for it would be defaulting, the thing
    `TaskSnapshot.role_specs` refuses one layer down. So no BATCH rule id
    may ever appear in this refusal: today because none exist, after DF-3-3
    because the excluded batch has one parsed member and one role. A body
    that guesses goes red here the commit it lands.
    """
    doc = _worklist(
        _row("S-1", role="scaffold", extra=("batch_id: BRK",)),
        _row("X-1", role="[scaffold, seals]", extra=("batch_id: BRK",)),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    message = str(exc.value)
    assert "X-1" in message, (
        "the refusal must name the broken row — it is the row's own ROW "
        f"error that refuses this worklist: {message}"
    )
    assert bc.RULE_BATCH_ROLE not in message and bc.RULE_BATCH_RULE not in message, (
        "a parse-failed row was counted into its batch: either the body "
        "guessed a role for it (defaulting) or it double-reports a row that "
        f"already carries its own error: {message}"
    )


# --------------------------------------------------------------------------- #
# THE rows — both refusals, end-to-end through plan.load_tasks.
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(_STUB, raises=pytest.fail.Exception, strict=True,
                   reason=_RED_TODAY)
def test_a_batch_mixing_scaffold_and_bodies_is_refused_at_plan_time() -> None:
    """THE first row. A batch spanning two roles is a worklist defect and the
    FILE is refused, before a wave burns on it.

    CONTROL (live in both worlds, judged first): the corrected twin —
    identical rows, ``batch_id: MIX-1`` / ``MIX-2`` — loads. So a refusal
    here can only be about the shared-batch relation.

    Today (measured, `5ca4af4`): the defective worklist loads, 0 errors and
    0 warnings — `pytest.raises` reports Failed, the one exception the
    marker tolerates. Green when DF-3-3 wires `batch_errors` into
    `load_tasks` and this file is refused with a BATCH-ROLE message naming
    every member key and each row's role (the contract's message clause: no
    row invisible in the refusal text). A-2 is NOT a member and must not be
    blamed.

    Falsify: refuse at dispatch instead (`loop_gate` already does — this
    `pytest.raises` around the LOADER stays red); or refuse with a bare
    "invalid worklist" (the rule-id assertion reddens: the refusal must
    carry the rule that fired, the same law the PO-2 wiring seal enforces).
    """
    _must_load(_worklist(
        _row("A-1", role="scaffold", extra=("batch_id: MIX-1",)),
        _row("A-2", role="seals", blocked_by=("A-1",)),
        _row("A-3", role="bodies", blocked_by=("A-2",), extra=("batch_id: MIX-2",)),
    ), control="the corrected twin (distinct batch_ids)")

    doc = _worklist(
        _row("A-1", role="scaffold", extra=("batch_id: MIX",)),
        _row("A-2", role="seals", blocked_by=("A-1",)),
        _row("A-3", role="bodies", blocked_by=("A-2",), extra=("batch_id: MIX",)),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    message = str(exc.value)
    assert bc.RULE_BATCH_ROLE in message, (
        f"the refusal must carry the rule that fired: {message}"
    )
    assert "MIX" in message, f"the refusal must name the batch: {message}"
    assert "A-1" in message and "A-3" in message, (
        f"every member key must appear — no row invisible in the refusal: "
        f"{message}"
    )
    assert "scaffold" in message and "bodies" in message, (
        f"BATCH-ROLE names each member's role, per the contract: {message}"
    )
    assert "A-2" not in message, (
        f"A-2 shares the batch's UNIT, not the batch; blaming it says the "
        f"body computed membership from something other than batch_id: "
        f"{message}"
    )


@pytest.mark.xfail(_STUB, raises=pytest.fail.Exception, strict=True,
                   reason=_RED_TODAY)
def test_a_batch_mixing_two_rulebook_pages_is_refused_at_plan_time() -> None:
    """THE second row — the task description's two-task fixture. One role,
    two rulebook pages: the role resolves, the writable set the one branch
    would be judged under does not.

    CONTROL (both worlds): the corrected twin — identical rows, both
    ``disputed_paths: [docs/a.md]`` — loads (with W-NO-SEALS about the
    fixture's scaffold row, measured; warnings never refuse).

    Today (measured, `5ca4af4`): the defective worklist
    loads with 0 errors and that same single unrelated warning. Green when
    DF-3-3 lands: refused with a BATCH-RULE message naming both member keys
    and the two differing pages — and NOT BATCH-ROLE, because the role here
    is exactly one and blaming roles would send the author to fix the wrong
    field.
    """
    _must_load(_worklist(
        _row("S-1", role="scaffold"),
        _row("J-1", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/a.md]")),
        _row("J-2", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/a.md]")),
    ), control="the corrected twin (identical disputed_paths)")

    doc = _worklist(
        _row("S-1", role="scaffold"),
        _row("J-1", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/a.md]")),
        _row("J-2", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/b.md]")),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    message = str(exc.value)
    assert bc.RULE_BATCH_RULE in message, (
        f"the refusal must carry the rule that fired: {message}"
    )
    assert "ADJ" in message, f"the refusal must name the batch: {message}"
    assert "J-1" in message and "J-2" in message, (
        f"every member key must appear: {message}"
    )
    assert "docs/a.md" in message and "docs/b.md" in message, (
        f"BATCH-RULE names the differing pages, per the contract — without "
        f"them the author diffs two rows by eye to find the field: {message}"
    )
    assert bc.RULE_BATCH_ROLE not in message, (
        f"the role here is exactly one; a BATCH-ROLE defect means the body "
        f"mis-resolved roles or skipped preemption's presupposition: "
        f"{message}"
    )


@pytest.mark.xfail(_STUB, raises=pytest.fail.Exception, strict=True,
                   reason=_RED_TODAY)
def test_the_rule_comparison_is_tuple_equality_not_set_equality() -> None:
    """The scaffold's tuple-over-set CHOICE, sealed so a body cannot
    re-litigate it: two rows spelling the SAME pages in a different ORDER
    are refused.

    Plan time must be at least as strict as the loop it fronts —
    `loop_gate.resolve_inputs` compares the ``(added_immutable_globs,
    disputed_paths)`` pairs by tuple equality, so a worklist this module
    passed and the loop then blocked would re-open the exact gap this unit
    closes. If order-insensitivity is ever wanted it lands in BOTH places
    in one commit, or in neither.

    CONTROL (both worlds): the same two rows with the pages in the SAME
    order load. Today (measured): the order-swapped pair loads too — that
    is the defect. Green when DF-3-3 lands and the swap alone is refused as
    BATCH-RULE. Falsify with a set/frozenset comparison in the body: the
    control stays green and THIS raises nothing, going red.
    """
    _must_load(_worklist(
        _row("S-1", role="scaffold"),
        _row("J-1", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/a.md, docs/b.md]")),
        _row("J-2", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/a.md, docs/b.md]")),
    ), control="the same-order twin")

    doc = _worklist(
        _row("S-1", role="scaffold"),
        _row("J-1", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/a.md, docs/b.md]")),
        _row("J-2", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: ADJ", "disputed_paths: [docs/b.md, docs/a.md]")),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    assert bc.RULE_BATCH_RULE in str(exc.value), (
        f"the refusal must carry the rule that fired: {exc.value}"
    )


@pytest.mark.xfail(_STUB, raises=pytest.fail.Exception, strict=True,
                   reason=_RED_TODAY)
def test_a_legacy_row_in_a_role_carrying_batch_is_two_roles() -> None:
    """LEGACY is a role, not an exemption — the scaffold's reading of
    `sole_role`'s edge, sealed against the tempting shortcut of skipping
    role-less rows.

    W-MIXED's "legal during migration" is about one FILE; a batch is one
    implementer SESSION, and a session cannot wear the legacy hat for one
    row and the scaffold hat for another. CONTROL (both worlds, in the
    guard row above as well): an all-legacy batch loads — refusing legacy
    MIXTURES must not become refusing legacy.

    Today (measured, `5ca4af4`): loads, 0 errors (W-MIXED and W-NO-SEALS
    warn, and warnings never refuse). Green when DF-3-3 lands: refused as
    BATCH-ROLE naming both keys and 'legacy' among the roles — the row with
    no ``role:`` key must be nameable in the refusal, or the author cannot
    see which row dragged the batch.
    """
    _must_load(_worklist(
        _row("L-1", extra=("batch_id: LEG",)),
        _row("L-2", extra=("batch_id: LEG",)),
    ), control="the all-legacy batch")

    doc = _worklist(
        _row("L-1", extra=("batch_id: LEG",)),
        _row("S-1", role="scaffold", extra=("batch_id: LEG",)),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    message = str(exc.value)
    assert bc.RULE_BATCH_ROLE in message, (
        f"the refusal must carry the rule that fired: {message}"
    )
    assert "L-1" in message and "S-1" in message, (
        f"every member key must appear: {message}"
    )
    assert "legacy" in message and "scaffold" in message, (
        f"each member's role must appear, LEGACY included: {message}"
    )


@pytest.mark.xfail(_STUB, raises=pytest.fail.Exception, strict=True,
                   reason=_RED_TODAY)
def test_role_mixture_preempts_rule_mixture_one_defect_per_batch() -> None:
    """BATCH-ROLE preempts BATCH-RULE per batch, and the batch is the unit
    of the fact — one defect, not one per row.

    The fixture is defective BOTH ways: three rows share ``batch_id: PRE``,
    the roles are {scaffold, adjudicate} AND the two adjudicate rows carry
    differing pages. "One rule" presupposes "one role" — the same ordering
    `resolve_inputs` implements (its role raise sits above its rule raise) —
    so the refusal must carry BATCH-ROLE exactly once and BATCH-RULE not at
    all: N copies of one fact is noise at the queue, and a rule defect
    computed across two roles' rulebooks is not a fact. The batch members
    happen to be blocked on each other, which also seals the scaffold's
    static-refusal CHOICE: the relation in the FILE is refused even when
    scheduling could never co-dispatch the rows.

    Today (measured, `5ca4af4`): loads, 0 errors, 1 unrelated warning.
    """
    doc = _worklist(
        _row("S-1", role="scaffold", extra=("batch_id: PRE",)),
        _row("J-1", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: PRE", "disputed_paths: [docs/a.md]")),
        _row("J-2", role="adjudicate", blocked_by=("S-1",),
             extra=("batch_id: PRE", "disputed_paths: [docs/b.md]")),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    message = str(exc.value)
    assert message.count(bc.RULE_BATCH_ROLE) == 1, (
        f"one defect per (batch, rule), anchored to the batch — a count of 0 "
        f"is a missing refusal, more than 1 is per-row noise that lets a "
        f"partial fix read as progress: {message}"
    )
    assert bc.RULE_BATCH_RULE not in message, (
        f"BATCH-ROLE preempts BATCH-RULE: a rule verdict over a mixed-role "
        f"batch compares rulebooks of different roles, which is not a fact: "
        f"{message}"
    )
    assert "S-1" in message and "J-1" in message and "J-2" in message, (
        f"one defect per batch does NOT mean rows go invisible — the message "
        f"names every member: {message}"
    )


@pytest.mark.xfail(_STUB, raises=AssertionError, strict=True,
                   reason=_RED_TODAY)
def test_batch_defects_merge_into_the_same_refusal_deterministically() -> None:
    """Batch defects and role errors are ONE ValidationError, byte-identical
    across independent parses of one file.

    The fixture carries a PO-2 defect (bodies hangs off the scaffold) AND a
    mixed-role batch. The scaffold's wiring clause: batch defects merge
    into the SAME ValidationError `load_tasks` already raises — a second
    raise site would report the file's defects one round trip at a time,
    the exact cost `validate`'s collect-don't-raise design exists to avoid.
    Determinism is the contract's own clause ("byte-identical output over
    one file"), asserted across two separate `yaml_io.loads` parses; the
    interleave layout is deliberately NOT pinned (header).

    MARKER NOTE — this row's ``raises`` pin is ``AssertionError``, wider
    than its siblings', because its failure channel today differs: the
    fixture IS refused today (PO-2, measured under `5ca4af4`), so
    `pytest.raises` succeeds and what fails is the last assertion — the
    refusal text carries no BATCH-ROLE. The tolerated-failure event is kept
    LAST so every prior line (both raises, determinism, PO-2 presence) is
    live today.
    """
    def _doc() -> object:
        return _worklist(
            _row("A-1", role="scaffold", extra=("batch_id: MIX",)),
            _row("A-2", role="seals", blocked_by=("A-1",)),
            _row("A-3", role="bodies", blocked_by=("A-1",),
                 extra=("batch_id: MIX",)),
        )

    with pytest.raises(plan_mod.ValidationError) as first:
        plan_mod.load_tasks(_doc())
    with pytest.raises(plan_mod.ValidationError) as second:
        plan_mod.load_tasks(_doc())
    message = str(first.value)
    assert message == str(second.value), (
        "two loads of one file must refuse with byte-identical text — the "
        "contract's determinism clause, and what makes a refusal diffable "
        "across runs"
    )
    assert "PO-2" in message, (
        f"the control failed: the fixture's role defect must survive the "
        f"merge — a merge that swallows role errors trades one defect for "
        f"another: {message}"
    )
    assert bc.RULE_BATCH_ROLE in message, (
        f"both defect families must arrive in the ONE raise; a worklist "
        f"author fixes everything in one round trip or the merge is not a "
        f"merge: {message}"
    )
