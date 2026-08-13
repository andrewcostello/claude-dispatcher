"""Unit DF-3 — a batch that mixes roles (or rulebooks) is refused at PLAN time.

**P1 scaffold. This module is CONTRACT plus the implemented data (the two
rule ids and the defect record); the one control-flow function is a stub.
P2 (DF-3-2) writes the seals, P3 (DF-3-3) the body and the wiring, P4
(DF-3-4) adjudicates what cannot land from the task system.**

Every citation below is `Measured under:` `24e72f0` (the base of
`feat/DF-3-1-...`), CPython 3.13.7, git 2.51.0, 2026-08-13, re-measured for
this scaffold rather than carried from the D8 reports — unless a line says
otherwise.

Why this unit exists — measured during D8, re-measured here
===========================================================
A batch group shares ONE worktree, ONE branch and ONE implementer session
(`orchestrator._take_batch_group`; the combined prompt says "All succeed or
all fail together"), and `loop_gate.check_branch` judges that one branch
under exactly one role. Two defects let a worklist promise otherwise, and
both load clean today:

  * **Two roles in one batch.** A three-row worklist — unit A's SCAFFOLD row
    and its BODIES row sharing ``batch_id: MIX`` — loads through
    `plan.load_tasks` + `role_protocol.validate` with **0 errors and 0
    warnings**, and `loop_gate.sole_role` over the batch's two specs answers
    ``None``: one branch, two roles, judgeable under neither.
  * **One role, two rulebook pages.** Two ADJUDICATE rows sharing
    ``batch_id: ADJ`` with ``disputed_paths: [docs/a.md]`` vs
    ``[docs/b.md]`` load with **0 errors and 1 warning — and the warning is
    W-NO-SEALS about the fixture's scaffold row, nothing about the batch**.
    `sole_role` answers ``Role.ADJUDICATE``: the role resolves; the writable
    set the branch would be judged under does not.

The loop gate already refuses both at DISPATCH time —
:data:`~claude_dispatcher.loop_gate.LoopGateStatus.ROLE_UNRESOLVED` for the
first, :data:`~claude_dispatcher.loop_gate.LoopGateStatus.RULE_UNRESOLVED`
for the second (the ninth status, P4's ruling on dispute P3-1, 2026-08-12).
But a worklist defect caught at dispatch time is a defect caught after the
planner is gone: the run burns a wave, the queue shows a BLOCK the file
itself promised, and the fix is a worklist edit that plan time could have
demanded before anything ran. §7(b) of the loop gate's design (extended by
the same P4 ruling) owes BOTH refusals to plan time. This module is their
contract.

The two rules
=============
:data:`RULE_BATCH_ROLE` — **a batch whose rows do not share exactly one
role.** Mirrors :func:`~claude_dispatcher.loop_gate.sole_role` exactly,
including its edges: :data:`~claude_dispatcher.role_protocol.Role.LEGACY`
IS a role, so an all-legacy batch is one role and clean, and a batch mixing
a legacy row with a role-carrying row is two roles and refused — the batch
is one implementer session, and W-MIXED's "legal during migration" is about
one FILE, not one branch.

:data:`RULE_BATCH_RULE` — **a batch whose rows share a role and not a
rule.** The comparison is the pair `loop_gate.resolve_inputs` compares —
``(spec.added_immutable_globs, spec.disputed_paths)`` — by TUPLE equality,
spelled the same on purpose. CHOICE — rejected: set equality (forgiving two
rows that spell the same globs in a different order). Plan time must be at
least as strict as the loop it fronts; a worklist this module passes that
the loop then blocks re-opens the exact gap this unit closes. If order-
insensitivity is ever wanted it lands in BOTH places in one commit or in
neither.

:data:`RULE_BATCH_ROLE` **preempts** :data:`RULE_BATCH_RULE` per batch: a
mixed-role batch gets the role defect only, because "one rule" presupposes
"one role" — the same ordering `resolve_inputs` implements (its role raise
sits above its rule raise), kept so the plan-time and dispatch-time answers
to one worklist never name different defects.

Where the rules live, and why not where they belong
===================================================
The durable home is ONE more error family inside `role_protocol.validate` —
its own docstring rules "one entrypoint, because two callables that both
decide 'is this worklist protocol-legal' would diverge (invariant 1)". That
home is closed to this task system twice over: `role_protocol.py` is on
:data:`~claude_dispatcher.role_protocol.FLOOR_GLOBS` (glob 3 of 17), and
DF-3-4's authoring measurement found it cannot even be named in
``disputed_paths:`` — the gate refuses the declaration itself. So:

  * the RULES live here, a new unfloored module — pure data and one pure
    function of the worklist, importable by seals without a dispatcher
    fixture (the same reason `loop_gate.resolve_inputs` takes five scalars
    rather than a `RunConfig`);
  * the WIRING is one call in `plan.load_tasks`, immediately after
    `role_protocol.validate`, merging these defects into the SAME
    `ValidationError` — plan.py is unfloored, and load_tasks is the point
    every road already funnels through. Measured on this tree: every
    consumer of the worklist (`run`, `resume`, `status`, `bakeoff`,
    `merge_engine`, `orchestrator`) reaches tasks via `plan.load_tasks`,
    and the ONE direct `role_protocol.validate` call outside it
    (orchestrator.py:524) runs on `load_tasks`'s own output and reads only
    ``.warnings``. No error path bypasses the composition point.
  * CHOICE — rejected: implementing the rules inline in `plan.load_tasks`.
    The seals would then need a full loadable YAML document to drive one
    rule, and the rules would be invisible to the operator commit that
    eventually moves them home.
  * CHOICE — rejected: landing the wiring in THIS scaffold commit. The stub
    below raises, and a raising stub on the live load path breaks every
    dispatch including this unit's own remaining tasks. The wiring lands
    with the body in DF-3-3's ONE commit — half of it alone is either a
    broken loader (stub wired) or a silent no-op (body unwired), and both
    halves red is the falsifiable shape. The owed call site is marked in
    plan.py in as many words.

**The named divergence window, accepted rather than hidden:** until an
operator (P4-handed, outside this task system — exactly as every floored
edit of the 2026-08 effort was handed over) lands the one-line delegation
into `role_protocol.validate`, a caller invoking `validate` DIRECTLY sees
no batch defects. Measured above: today that caller reads warnings only,
off an already-loaded worklist. Invariant 1 is bent here, not broken — one
REFUSAL point, two rule sources — and the bend is recorded on both sides of
the seam.

What this unit does NOT change
==============================
The loop states stay. :data:`~claude_dispatcher.loop_gate.LoopGateStatus.
ROLE_UNRESOLVED` and :data:`~claude_dispatcher.loop_gate.LoopGateStatus.
RULE_UNRESOLVED` remain reachable and BLOCK — they are the net for a
worklist that reaches the dispatcher another way (an edited file between
load and dispatch, a snapshot that lost rows). The DEADLINE_EXCEEDED rule,
applied unchanged: a state made unreachable by an upstream fix is named and
asserted unreachable, never deleted. And row 18 of the loop gate's seal
file (`test_todays_dispatcher_really_does_hand_one_branch_two_roles`) is
GREEN today by design and reddens exactly once, when DF-3-3 lands — seal
dispute P2-3 assigns that amendment to the landing commit, and this
scaffold's author may not touch tests/ at all (the DF-4-1 lesson: a
scaffold that writes the seals it will be judged by re-creates the circular
oracle).

Scope CHOICES a body author must not re-litigate
================================================
  * **The refusal is STATIC — on the shared ``batch_id`` relation in the
    file — not on computed co-runnability.** Rejected alternative: refuse
    only batches whose rows could co-dispatch (same wave). Runnability is
    RUN state — statuses flip between loads (`unblock` alone rewrites
    them), waves recompute, and `docs/task-batching.md` lets leftover rows
    run as singletons — so a scheduling-dependent refusal answers
    differently for one file on two days. And a batch_id spanning roles is
    a defect of INTENT even when scheduling happens to separate the rows:
    one batch means one implementer session, and the protocol's whole
    authorship model (the seal author must not see the scaffold author's
    reasoning) forbids one session wearing two roles. A planner who wants
    the rows in one wave has a spelling for it: distinct batch_ids.
  * **One defect per (batch, rule), anchored to the batch's
    lexicographically-first task key** — not one per row. The batch is the
    unit of the fact; N copies of one fact is noise at the queue and lets a
    partial fix read as progress. The MESSAGE names every member key (and,
    for BATCH-ROLE, each row's role; for BATCH-RULE, the two differing
    pages), so no row is invisible in the refusal text.
  * **Rows whose spec failed to parse are excluded from their batch's
    computation.** Such a row already carries its own ROW error from
    `role_protocol.validate` and the worklist is already refused; a second
    defect on the same row would double-report, and guessing a role for it
    would be defaulting — the thing `TaskSnapshot.role_specs` deliberately
    refuses one layer down.
  * **Rows with an empty/absent ``batch_id`` are not a batch** and are
    never examined here — plan.py already normalises ``""`` to ``None``.

Determinism: the returned tuple is ordered by (task_key, rule_id,
batch_id), matching `role_protocol.validate`'s "byte-identical output over
one file" clause, so the merged refusal text is stable under re-runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # imports for annotations only — plan imports this
    # module's caller-to-be, and role_protocol reads plan.Task, so runtime
    # imports in either direction here would re-create the cycle plan.py's
    # own load_tasks comment documents.
    from .plan import Task
    from .role_protocol import TaskRoleSpec


#: Rule id for "a batch whose rows do not share exactly one role". The
#: spelling echoes the loop's ROLE_UNRESOLVED so the plan-time refusal and
#: the dispatch-time block read as one story told twice.
RULE_BATCH_ROLE = "BATCH-ROLE"

#: Rule id for "a batch whose rows share a role and not a rule" — differing
#: ``immutable_paths:`` / ``disputed_paths:`` additions. Echoes
#: RULE_UNRESOLVED, the ninth status, for the same reason.
RULE_BATCH_RULE = "BATCH-RULE"


@dataclass(frozen=True)
class BatchDefect:
    """One batch-coherence refusal, in `role_protocol.validate`'s grammar.

    ``task_key`` / ``rule_id`` / ``message`` are the exact triple `validate`
    collects internally, so the DF-3-3 wiring merges these into the same
    sorted, deterministic refusal without a translation layer — and so the
    eventual operator commit that moves the rules into `validate` can adopt
    them without reshaping anything. ``batch_id`` rides along because the
    defect is the BATCH's, and the anchor row (the lexicographically first
    key — see the module docstring's one-defect-per-batch CHOICE) is a sort
    key, not the culprit.
    """

    task_key: str
    rule_id: str
    batch_id: str
    message: str


def batch_errors(
    tasks: Sequence[Task],
    specs: Sequence[TaskRoleSpec],
) -> tuple[BatchDefect, ...]:
    """Every batch-coherence defect in ``tasks``, or ``()`` for a clean file.

    Pure function of its arguments: ``tasks`` supplies the ``batch_id``
    relation (specs do not carry it), ``specs`` supply each row's role and
    its two rulebook fields, joined by task key. The intended call site
    passes `role_protocol.validate`'s own ``.specs`` — already parsed,
    already excluding rows whose parse failed (each of those carries its
    own ROW error, which is why exclusion here masks nothing).

    Contract (each clause is reasoned in the module docstring):

      * rows sharing one non-empty ``batch_id`` and not exactly one
        :class:`~claude_dispatcher.role_protocol.Role` →
        one :data:`RULE_BATCH_ROLE` defect naming every member key and its
        role; LEGACY is a role, not an exemption;
      * rows sharing one ``batch_id`` and one role whose
        ``(added_immutable_globs, disputed_paths)`` pairs are not all
        tuple-equal → one :data:`RULE_BATCH_RULE` defect naming every
        member key and the differing pages;
      * :data:`RULE_BATCH_ROLE` preempts :data:`RULE_BATCH_RULE` per batch;
      * result ordered by (task_key, rule_id, batch_id).

    P1 STUB — P3 (DF-3-3) writes the body AND the `plan.load_tasks` call in
    one commit; neither half lands alone. Seals (DF-3-2) drive the loaded
    worklist end-to-end: the two measured fixtures above load with 0 errors
    today and must be refused once the body lands.
    """
    raise NotImplementedError(
        "DF-3 P1 scaffold: batch_errors is contract only — P3 (DF-3-3) "
        "writes the body and wires it into plan.load_tasks in the same "
        "commit. Do NOT wire this stub into the load path ahead of the "
        "body: a raising stub there breaks every dispatch, including this "
        "unit's own."
    )
