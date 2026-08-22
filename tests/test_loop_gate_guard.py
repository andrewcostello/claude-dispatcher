"""Unit D8-guard — the three rows that make the loop gate GUARDED, not merely wired.

**P2. The rows `tests/test_loop_gate.py`'s own P4 routing block owes, written
by a P2 because a P4 that writes the seal its own rulings are judged by is the
circular oracle this protocol opens by naming.** Row 22's strengthening is the
fourth owed item and it lives in `tests/test_loop_gate.py` beside the row it
strengthens; the amendment is recorded in that file's header and in row 22's
own docstring.

Every citation carries ``Measured under:`` or ``Predicted (unmeasured) under:``.
The revision is ``9d21ef0`` (`feat/D1-role-protocol`, this branch's base and the
D8 merge commit) unless a line says otherwise.

Baseline re-measured here, not taken on trust
=============================================
Measured under `9d21ef0` in a fresh worktree, ``PYTHONPATH=src python3 -m
pytest -q -o addopts=""``: **2526 collected == 2513 passed + 13 skipped, 0
failed**, in 152.32 s. The vendored TypeScript parser was fetched first
(``PYTHONPATH=src python3 -m claude_dispatcher.ts_parser_vendor`` →
``ts-parser-vendor OK typescript 5.9.3``) because `typescript.js` and
`LICENSE.typescript.txt` are gitignored and a fresh worktree does not otherwise
reproduce the baseline. ``-o addopts=""`` is required: `pyproject.toml` carries
``-ra -q``, which doubles to ``-qq`` and suppresses the summary line.
``role_protocol.FLOOR_GLOBS`` is **17** entries.

**Re-measured with this file present, same invocation:** 2529 collected ==
**2516 passed + 13 skipped, 0 failed**, in 150.53 s. Exactly the three rows
below are added and nothing else moved — no row in any other file reddens,
including the three journal-sequence rows the P3-2 ruling amended, which this
file reads but never rewrites.

THE STATE THESE ROWS FOUND, AND IT IS NOT THE STATE THEY WERE COMMISSIONED FOR
=============================================================================
**Dispute D8G-1, and it is the first thing a reader of this file must know.**
The commission says :data:`~claude_dispatcher.loop_gate.LoopGateStatus.
RULE_UNRESOLVED` *"does not exist yet"* and that row 23 below *"will be red
against a missing member, and that is correct"*.

**Measured under `9d21ef0`, not predicted:** it exists.
``LoopGateStatus`` has NINE members and ``RULE_UNRESOLVED`` is the sixth
(loop_gate.py:1095); :data:`~claude_dispatcher.loop_gate._DECISIONS` maps it to
BLOCK (1121); :data:`~claude_dispatcher.loop_gate._BLOCKED_REASON_PREFIXES`
gives it ``role_diff_loop_rule_unresolved`` (1168); and
:func:`~claude_dispatcher.loop_gate.resolve_inputs` already raises it from the
rule-equivalence guard at loop_gate.py:1450-1461. The P4 ruling on dispute P3-1
landed the member in the same commit that wrote the routing block asking for
this row. Probed directly::

    len(LoopGateStatus) == 9
    _BLOCKED_REASON_PREFIXES[LoopGateStatus.RULE_UNRESOLVED]
        == 'role_diff_loop_rule_unresolved'

**So all three rows in this file are GREEN today, and that is the correct
state.** It is stated here rather than buried because a reader who expects red
and finds green will assume the rows are vacuous, and they are not: each one
reddens under the specific mutation the routing block measured leaves
`tests/test_loop_gate.py` **22-of-22 green**. These are not seals against a
missing body. They are seals against a body that exists, is correct, and is
covered by nothing — which is precisely the vacuity shape this unit's own
non-vacuity list calls *"a mutation invisible because two implementations
return the same value"*, and precisely why the routing block called D8 *"wired
but not guarded"* rather than *"unfinished"*.

The distinction matters for what happens next, so it is spelled out: a row that
is red because a member is missing goes green when somebody adds the member,
and proves nothing about the member's behaviour. A row that is green today and
red under a named mutation is the only shape that can catch the three defects
the P4 measured. **No row below asserts an unimplementedness**, which is this
codebase's measured trap "a row pinning a transient unimplementedness".

The three mutations these rows exist for, re-derived here
========================================================
Each mutation was applied to a `git clone` of this worktree (never a ``cp -a``
of a linked worktree: that inherits the `.git` POINTER FILE, so a git command
inside the copy mutates the real repository — it has bitten three agents this
session) and `tests/test_loop_gate.py` re-run whole. **Measured under
`9d21ef0`, reproducing the P3's and the P4's numbers exactly:**

  ======================================================= ============ ==========
  mutation                                                before       after
  ======================================================= ============ ==========
  drop the rule-equivalence guard (`resolve_inputs`)      22 passed    **23**
  never WRITE the row stamp, still reference `ROW_STAMPS`  22 passed    **24, 25**
  hardcode ``enabled=True`` at the call site               22 passed    **25**
  ======================================================= ============ ==========

"before" is `tests/test_loop_gate.py` alone; "after" names the rows that redden
over both files, out of 25. Two entries are wider than commissioned and are
reported rather than trimmed, because a mutation's blast radius is a fact about
how coupled the rows are:

  * the stamp mutation takes row 25 as well as row 24 — row 25 asserts each
    world's ROW STAMP alongside its payload, so a run that stamps nothing fails
    there too. That coupling is deliberate: a row that read only the journal
    would pass while the record a human adjudicates from stayed empty.
  * two further mutations, run because row 22's strengthening had to be
    falsified in both directions and they touch this file:

    ====================================================== =============== ====
    mutation                                               test_loop_gate  here
    ====================================================== =============== ====
    inline reimplementation agreeing on every fixture       22 red          24
    `check_branch` called AND the verdict decided inline    22 red          —
    extract the `check_branch` call into a helper           all green       —
    ====================================================== =============== ====

    Row 24 reddens under the first through its detail CONTROL, not through a
    claim about `check_branch`: the reimplementation drops the reason string
    `check_branch` carries, so the fixture stops exercising the
    ``role_diff_loop_detail`` write and the control says exactly that. It is
    reported because it is real, not claimed as coverage this row designed for.

And what each mutation reddens is restated in each row's own FALSIFY block,
measured the same way.

**Why two of these are not "just wiring", quoted from the rulings rather than
restated.** A hardcoded ``True`` runs `check_branch` on every task of every
repository, including the Go tree where `branch_reachability`'s own P4 ruling
records *445 s per sweep and two sweeps per check* — of the order of fifteen
minutes per BODIES branch — and rules the gate must not go in front of it. A
stamp never written leaves `dispatcher blocked` unable to say why a row was
blocked and leaves `unblock._STALE_STAMPS` clearing keys nothing ever set,
which is the review queue this unit's whole Blocked design depends on.

The non-vacuity shapes this file was written against
====================================================
  * **a mutation invisible because two implementations return the same
    value.** The shape of all three defects. Row 25's answer is the one worth
    reading: the gate-off run and the gate-on run BOTH end ``Done`` with
    decision ``proceed``, so no assertion about the DECISION can tell them
    apart. The rows the P3-2 ruling amended pin the event's TYPE and its
    POSITION and stay green under the hardcode for exactly that reason. Row 25
    pins the PAYLOAD, and drives both worlds in one call.
  * **a fixture that stated only the world the fix wanted.** Every row carries
    an in-test control judged in the same call — row 23 drives the
    rule-EQUIVALENT batch through the same hook, row 24 checks an established
    stamp (`mechanical_verification`) is present on the same row, row 25 runs
    both flag states.
  * **a row pinning a transient unimplementedness.** None below. See D8G-1.

Which rows a BODY could turn green alone, and which need a P4
=============================================================
**None of them could be turned green by a body, and none of them needs to be.**
Measured under `9d21ef0`: `role_protocol.FLOOR_GLOBS` is 17 entries and
includes ``**/src/claude_dispatcher/loop_gate.py`` (16) and
``**/src/claude_dispatcher/orchestrator.py`` (17). §7's owed floor commit
LANDED. So:

  * **row 23**'s subject is `loop_gate.py` — floored. Any repair is a P4
    amendment, for every role, and no ADJUDICATE declaration buys it back
    (`FLOOR_RATIONALE`: a change to a floored path is *"a reviewed edit on the
    protected base"*).
  * **rows 24 and 25**'s subject is `orchestrator.py`'s call site, stamp write
    and `RunConfig` flag — floored, plus `cli.py` (unfloored) for the flag's
    surface only. The load-bearing half is floored, so P4.
  * **row 22** (strengthened in `tests/test_loop_gate.py`) judges
    `loop_gate.py` — floored. P4.

That is a statement about who may REPAIR them, not about who owes work: all
three are green, so nothing is owed today. What the floor buys is that the
`orchestrator.py` and `loop_gate.py` escape the D8 seal file's header names —
*"the run judging that branch uses the module the branch just edited"* — is
closed for these rows in a way it was not for the original 22.

Joint satisfiability
====================
**Measured under `9d21ef0`.** These three rows plus the strengthened row 22
plus the original 21 all pass against one implementation — the tree as it
stands: **25 passed, 0 failed** over
``tests/test_loop_gate.py tests/test_loop_gate_guard.py``. No two rows
contradict each other, and the reference implementation is not a throwaway: it
is the shipped one, which is a stronger joint-satisfiability result than a
purpose-built stub and is available only because these rows guard a body that
already exists.

The throwaway reference implementation was still built and run, because "the
shipped code passes" is a weaker claim than it looks: it does not show that a
DIFFERENT implementation could satisfy all 25, and a set of rows satisfiable by
exactly one program is a transcription of that program. Measured under
`9d21ef0` in a `git clone` (never a ``cp -a`` of the linked worktree — that
inherits the `.git` POINTER FILE and a git command inside the copy mutates the
real repository): the helper-extraction variant, which moves the `check_branch`
call into a module-private `_run_check` and threads its result back, is a
second, textually different implementation of the hook and it passes **25, 0
failed**. So the 25 rows admit more than one program, and the two they admit
differ in exactly the way row 22's false-refusal note says they must be allowed
to.

Disputes raised by this file, for P4
====================================
  * **D8G-1 (the commission's premise).** ``RULE_UNRESOLVED`` exists; the rows
    are green today. Reasoned above.
  * **D8G-2 (row 24, the stamp's value).** The commission asks the row to
    assert the YAML row carries ``ROW_STAMPS[0]`` *"with the expected VALUE"*.
    This file refuses to spell that value as a literal and asserts instead that
    it EQUALS the ``role_diff_loop_gate`` journal payload's ``status`` for the
    same task. A literal would be satisfied by an orchestrator that stamps a
    constant, which is the defect one step along from the one being closed; the
    journal is hash-chained and append-only and is the record the P3-2 ruling
    already established as this gate's durable witness. Raised because it is a
    strengthening of the commission, not a narrowing of it.
  * **D8G-3 (row 25, and it is a real gap this file does NOT close).** Row 25
    proves the flag reaches the gate's ANSWER. It does not prove the flag
    reaches `check_branch`'s COST, which is the ruling's actual concern — the
    fifteen minutes per BODIES branch. A gate that ran the sweep and then
    reported ``not_enabled`` would pass row 25. Closing it needs a call-count
    or wall-clock assertion over a seam this unit does not publish
    (`check_branch` takes a ``run=`` seam; `check_after_implementer`
    deliberately does not forward one — its own CHOICE block rules that out for
    the scaffold and leaves it to P3, which did not add it). Named rather than
    silently left out, and NOT sealed here: adding a seam from a seal file is
    how a seal becomes a specification nobody agreed to.
"""

from __future__ import annotations

from pathlib import Path

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import orchestrator as orch_mod
from claude_dispatcher import unblock as unblock_mod
from claude_dispatcher import yaml_io
from claude_dispatcher.loop_gate import (
    ROW_STAMPS,
    LoopGateDecision,
    LoopGateStatus,
    blocked_reason,
    check_after_implementer,
    sole_role,
)
from claude_dispatcher.role_protocol import Role, TaskRoleSpec

# The live-run harness, imported rather than rebuilt. `tests/test_capstone.py`
# and `tests/test_d5_floor.py` establish that spelling in this suite. Rebuilding
# it would be a second fixture for one fact (invariant 5) and would let this
# file's rows drift from the sequences the P3-2 ruling amended.
from test_orchestrator_journal import (  # noqa: F401
    _args,
    _events,
    _patch_spawn,
    _reset_reviewers,
    _types_for,
    repo,
)

# The real-git fixture machinery the D8 seal file already establishes. Row 23
# uses a REAL repository rather than a path that does not exist, for the reason
# its own control block gives: over a nonexistent repo_root every world
# collapses to GATE_ERROR, and a control that cannot reach a verdict is not a
# control.
from test_loop_gate import _git, _new_repo, _sha  # noqa: F401


# --------------------------------------------------------------------------- #
# ROW 23 — the rule-equivalence refusal, in its own name, through the hook
# --------------------------------------------------------------------------- #


def _adjudicate(key: str, disputed: tuple[str, ...]) -> TaskRoleSpec:
    """An ADJUDICATE row whose ``disputed_paths:`` IS its writable set."""
    return TaskRoleSpec(
        task_key=key, role=Role.ADJUDICATE, disputed_paths=disputed,
    )


def _two_path_adjudicate_branch(tmp_path: Path) -> tuple[Path, str]:
    """A real branch that touched TWO paths, and the SHA before it did.

    Shaped so that neither ADJUDICATE row's writable set covers the whole diff:
    row A disputes ``alpha.py``, row B disputes ``beta.py``, and the branch
    touched both. That is what makes the mutation's consequence VISIBLE rather
    than merely different — judged under ``specs[0]`` alone, exactly one of the
    two rows' legitimate, declared work is reported as a violation.
    """
    repo_dir = _new_repo(tmp_path, "adjudicate")
    pre_spawn = _sha(repo_dir)
    _git(["checkout", "-q", "-b", "feat/U-adjudicate"], repo_dir)
    pkg = repo_dir / "src" / "claude_dispatcher"
    pkg.mkdir(parents=True)
    (pkg / "alpha.py").write_text("ALPHA = 1\n", encoding="utf-8")
    (pkg / "beta.py").write_text("BETA = 1\n", encoding="utf-8")
    _git(["add", "."], repo_dir)
    _git(["commit", "-q", "-m", "adj(U): the two disputed modules"], repo_dir)
    return repo_dir, pre_spawn


def test_two_adjudicate_rows_with_different_writable_sets_are_refused_by_name(
    tmp_path: Path,
) -> None:
    """**Row 23. The rule-equivalence refusal has its own status, and the hook
    is what produces it.** GREEN TODAY — see D8G-1; red under the mutation it
    names.

    Measured under `9d21ef0`, and it is the whole reason this row exists:
    dropping the rule-equivalence guard from
    :func:`~claude_dispatcher.loop_gate.resolve_inputs` leaves
    `tests/test_loop_gate.py` **22 of 22 green**. Nothing in that file covers
    the refusal. With the guard dropped the gate falls through to ``specs[0]``
    and judges row B's disputed work under row A's writable set — the P4's own
    words, *"wrong in both directions on the same branch"*: legitimate work
    reported as a violation, and unauthorised work cleared.

    **THROUGH THE HOOK, NOT THROUGH `sole_role`, and this row asserts the
    difference rather than assuming it.** The P4 ruling is explicit that the
    refusal does not live in :func:`~claude_dispatcher.loop_gate.sole_role`,
    which returns a role for this input. So the first claim below is that
    ``sole_role`` RESOLVES these two specs — to ``Role.ADJUDICATE`` — and the
    refusal still happens. A row that reached for ``sole_role`` and found
    ``None`` would be measuring the mixed-role defect a second time and would
    stay green under the mutation.

    **WHY A NINTH STATUS AND NOT A WORDING CHANGE**, restated only far enough
    to say what is asserted: :data:`~claude_dispatcher.loop_gate.
    _BLOCKED_REASON_PREFIXES` is keyed by STATUS and is what
    `unblock.list_blocked` prints, so two defects sharing a status share a
    queue label. §4 already set the standard that a human must be able to tell
    "your worklist batches two roles" from a different defect. This row asserts
    the two labels are distinct AND that neither is a prefix of the other — the
    property row 8 of `tests/test_loop_gate.py` asserts for the table, checked
    here on the two strings a human actually reads.

    **THE FIXTURE IS A REAL REPOSITORY, and that is a correction of this row's
    own first draft.** Driven over a `repo_root` that does not exist, every
    world collapses to :data:`LoopGateStatus.GATE_ERROR` — the policy load
    raises before the refusal is reached — so the control passed while proving
    nothing and the mutation reddened the row for the wrong reason. Measured
    under `9d21ef0` before the fix: with the guard dropped the row failed
    reporting ``GATE_ERROR``, not the verdict the wrong writable set produces.
    The branch below touches TWO paths and each row disputes ONE of them, so
    the mutation's consequence is visible in the verdict itself.

    THE CONTROL, in this same call and on the same fixture: the same two rows
    made rule-EQUIVALENT — both disputing BOTH paths — resolve and reach a real
    CLEAN. Without it a gate that blocked every multi-row batch, or one that
    had simply broken, would satisfy every positive claim below. The control is
    the half that says the refusal is about the RULE and not about the row
    count. Repeated rows carrying the same rule are the ordinary batch and
    `sole_role`'s own docstring rules they must resolve normally.

    GREEN TODAY. FALSIFY (measured under `9d21ef0`, in a `git clone`):

      * replace ``if len(rules) != 1:`` with ``if False:`` in `resolve_inputs`
        — `tests/test_loop_gate.py` stays **22 passed** and THIS ROW reddens
        reporting ``CHECKED_VIOLATION``: the gate stopped refusing, fell
        through to ``specs[0]``, and reported row B's declared, authorised
        ``beta.py`` as row A's violation. The refusal is not fastidiousness;
        the alternative answer is wrong.
      * raise the refusal through ``ROLE_UNRESOLVED`` instead — the two-label
        claim reddens, which is the P4's ruling as an assertion.

    Depends on the P4 floor commit: LANDED. `loop_gate.py` is
    `FLOOR_GLOBS` entry 16 (measured), so a body cannot repair or defeat this
    row's subject; any change to it is a P4 amendment.
    """
    repo_dir, pre_spawn = _two_path_adjudicate_branch(tmp_path)
    both = ("src/claude_dispatcher/alpha.py", "src/claude_dispatcher/beta.py")

    def _hook(specs):
        return check_after_implementer(
            enabled=True,
            repo_root=repo_dir,
            base_branch="main",
            branch_ref="feat/U-adjudicate",
            pre_spawn_sha=pre_spawn,
            specs=list(specs),
        )

    a = _adjudicate("U-ADJ-A", ("src/claude_dispatcher/alpha.py",))
    b = _adjudicate("U-ADJ-B", ("src/claude_dispatcher/beta.py",))

    # THE CONTROL FIRST, so a broken fixture cannot be read as a refusal.
    # Same two rows, same role, same everything except that they now share one
    # rule — and the shared rule covers the whole diff, so the gate reaches a
    # real CLEAN rather than merely "not RULE_UNRESOLVED".
    same = (_adjudicate("U-ADJ-A", both), _adjudicate("U-ADJ-B", both))
    control = _hook(same)
    assert control.status is LoopGateStatus.CHECKED_CLEAN, (
        "the control failed: two rows that share BOTH a role and a rule, whose "
        "shared writable set covers every path on the branch, did not reach a "
        f"CLEAN verdict — got {control.status!r} ({control.detail[:250]!r}). "
        "Either this gate is refusing on the row COUNT rather than on the "
        "rule, or the fixture never reaches check_branch at all; both make "
        "every positive claim below vacuous. sole_role over the control "
        f"specs: {sole_role(same)!r}"
    )

    # 1. The role IS resolved. The refusal is not sole_role's.
    assert sole_role([a, b]) is Role.ADJUDICATE, (
        "sole_role does not resolve two ADJUDICATE rows to one role, so this "
        "row would be measuring the mixed-role defect a second time and would "
        "stay green under the mutation it exists to catch. The P4 ruling on "
        "dispute P3-1 is explicit that the rule-equivalence refusal is NOT in "
        f"sole_role: got {sole_role([a, b])!r}"
    )

    # 2. The hook refuses, in its own name.
    out = _hook([a, b])
    assert out.status is LoopGateStatus.RULE_UNRESOLVED, (
        "two ADJUDICATE rows differing ONLY in disputed_paths — i.e. in the "
        "field that IS each row's writable set — did not produce "
        "RULE_UNRESOLVED. The gate resolved a rule it does not have, so one "
        "row's work is being judged under the other row's set: legitimate "
        "work reported as a violation and unauthorised work cleared, on the "
        f"same branch. Got status={out.status!r} decision={out.decision!r} "
        f"detail={out.detail[:300]!r}"
    )
    assert out.decision is LoopGateDecision.BLOCK, (
        f"RULE_UNRESOLVED did not BLOCK (got {out.decision!r}). Four of the "
        "loop's states mean 'the gate could not answer the question it was "
        "asked' and every one of them blocks; a PROCEED here is the "
        "vacuous-seal shape §3 refuses — a row stamped by a check that never "
        "ran, which the next reader takes for a verdict"
    )
    assert out.result is None, (
        "RULE_UNRESOLVED carries a RoleDiffResult, so check_branch RAN — but "
        "the whole ruling is that there is no one rule to run it under. "
        f"result={out.result!r}"
    )

    # 3. The queue label is distinct, because the queue is keyed by status.
    rule_reason = blocked_reason(LoopGateStatus.RULE_UNRESOLVED, out.detail)
    role_reason = blocked_reason(LoopGateStatus.ROLE_UNRESOLVED, "")
    rule_prefix = rule_reason.split(":")[0]
    role_prefix = role_reason.split(":")[0]
    assert rule_prefix != role_prefix, (
        "the mixed-role defect and the mixed-rule defect print the SAME label "
        f"in the review queue ({rule_prefix!r}). They are two different things "
        "to fix — a mixed-role batch is a protocol error, while two ADJUDICATE "
        "rows with different disputed_paths may each be perfectly legal and "
        "merely unable to share a branch — and _BLOCKED_REASON_PREFIXES is "
        "keyed by STATUS precisely so a human can tell them apart"
    )
    assert not rule_prefix.startswith(role_prefix), (
        f"{rule_prefix!r} starts with {role_prefix!r}. Inequality is not "
        "enough: a reader scanning `dispatcher blocked` for the mixed-role "
        "label matches both, which is the collapse the ninth status was "
        "ruled to prevent"
    )
    assert not role_prefix.startswith(rule_prefix), (
        f"{role_prefix!r} starts with {rule_prefix!r} — same argument, other "
        "direction"
    )

    # 4. And the two really are different worlds, driven in this same call, so
    #    the distinctness above is not a fact about two strings nobody reaches.
    mixed = _hook([a, TaskRoleSpec(task_key="U-BODIES", role=Role.BODIES)])
    assert mixed.status is LoopGateStatus.ROLE_UNRESOLVED, (
        "the control failed in the other direction: a genuinely mixed-ROLE "
        f"batch reported {mixed.status!r}. If both defects report the same "
        "status then the ninth member is decorative and claim 3 above is "
        "comparing two labels the gate never actually produces"
    )
    assert mixed.status is not out.status, (
        "the mixed-role batch and the mixed-rule batch produce the SAME "
        f"status ({out.status!r}), so no queue label can distinguish them "
        "however distinct the strings in the table are"
    )


# --------------------------------------------------------------------------- #
# ROWS 24 and 25 — a real run: the stamp is written, and the flag is honoured
# --------------------------------------------------------------------------- #


def _row(repo_dir: Path, key: str) -> dict:
    rows = yaml_io.load(repo_dir / "tasks.yaml")["tasks"]
    return next(r for r in rows if r["key"] == key)


def _gate_events(repo_dir: Path, key: str) -> list[journal_mod.JournalEvent]:
    return [
        e for e in _events(repo_dir)
        if e.event_type == "role_diff_loop_gate" and e.task_key == key
    ]


def test_the_orchestrator_really_writes_the_stamp_the_gate_returned(
    repo: Path, monkeypatch,
) -> None:
    """**Row 24. `ROW_STAMPS` reaches the task's YAML row, carrying the gate's
    own answer.** GREEN TODAY — see D8G-1; red under the mutation it names.

    Measured under `9d21ef0`: making `orchestrator._run_task` never WRITE the
    row stamp, while still REFERENCING
    :data:`~claude_dispatcher.loop_gate.ROW_STAMPS`, leaves
    `tests/test_loop_gate.py` **22 of 22 green**. Row 21 of that file reads
    `orchestrator.py`'s SOURCE for the reference and is satisfied by the dead
    constant; no row drives the write. That is the *"correct, complete, and not
    invoked"* shape this whole lineage has been chasing, arriving one level
    below the call site row 4 pins.

    What the absence costs, and it is not cosmetic: `unblock.list_blocked`
    prints `blocked_reason` and the keys in `_DETAIL_FIELDS`, and
    `unblock._STALE_STAMPS` POPS both `ROW_STAMPS` on every unblock. With no
    write, `dispatcher blocked` cannot say which gate blocked a row and
    `_STALE_STAMPS` clears keys nothing ever set — the review queue this
    unit's whole Blocked design depends on, mute.

    **THE VALUE IS NOT A LITERAL — dispute D8G-2.** The stamp is asserted equal
    to the ``role_diff_loop_gate`` journal payload's ``status`` for the SAME
    task, not to a hardcoded string. A literal is satisfied by an orchestrator
    that stamps a constant, which is the defect one step along from this one.
    The journal is hash-chained and append-only and the P3-2 ruling already
    established it as this gate's durable witness — so binding the erasable
    record to the durable one is the strongest claim available without adding a
    seam.

    THE CONTROLS, all judged in this same call:

      * the row carries `mechanical_verification` — an ESTABLISHED gate stamp.
        Without it a reader pointed at the wrong YAML, or at a task that never
        dispatched, would fail the positive claim and blame the wrong thing.
      * exactly ONE ``role_diff_loop_gate`` event exists for the task, so there
        is a single unambiguous answer to compare the stamp against.
      * the stamp's value is a real :class:`LoopGateStatus` member value, by
        member lookup — a stamp that is a named state, not free text.

    GREEN TODAY. FALSIFY (measured under `9d21ef0`, in a `git clone`):

      * guard the stamp write with ``if False and role_loop is not None:`` —
        `tests/test_loop_gate.py` stays **22 passed**, this row reddens on the
        missing key.
      * stamp a literal instead of ``role_loop.status.value`` — the
        stamp-equals-payload claim reddens.

    Depends on the P4 floor commit: LANDED. `orchestrator.py` is `FLOOR_GLOBS`
    entry 17 (measured), so the write site is P4-only.
    """
    _patch_spawn(monkeypatch)
    rc = orch_mod.execute(_args(repo, only="SMOKE-A", enable_role_loop_gate=True))
    assert rc == 0, "the fixture run did not complete; every claim below is vacuous"

    row = _row(repo, "SMOKE-A")

    # CONTROL: an established gate stamp is on this row.
    assert "mechanical_verification" in row, (
        "the control failed: the dispatched row carries no "
        "`mechanical_verification` stamp either, so this reader is looking at "
        "a row no gate ever wrote and the claims below are about the wrong "
        f"object. Row keys: {sorted(row)}"
    )

    # CONTROL: exactly one gate answer to compare against.
    evs = _gate_events(repo, "SMOKE-A")
    assert len(evs) == 1, (
        f"expected exactly one role_diff_loop_gate event for SMOKE-A, found "
        f"{len(evs)}. With none there is nothing to compare the stamp to; with "
        "several the comparison below picks one arbitrarily"
    )
    payload = evs[0].payload

    # 1. The verdict stamp exists and is the gate's own answer.
    assert ROW_STAMPS[0] in row, (
        f"the task's row carries no {ROW_STAMPS[0]!r} key. The gate ran (the "
        f"journal says {payload.get('status')!r}) and said so to an "
        "append-only file nobody greps, while the row a human reads in "
        "`dispatcher blocked` records nothing. `unblock._STALE_STAMPS` then "
        f"clears a key that was never set. Row keys: {sorted(row)}"
    )
    assert row[ROW_STAMPS[0]] == payload["status"], (
        f"the row stamp ({row[ROW_STAMPS[0]]!r}) is not the status the gate "
        f"reported to the journal ({payload['status']!r}) for the same task. "
        "The stamp is being written from something other than the gate's "
        "answer — a literal, a default, or a stale variable — and the row a "
        "human adjudicates from disagrees with the hash-chained record"
    )
    assert row[ROW_STAMPS[0]] in {s.value for s in LoopGateStatus}, (
        f"the row stamp {row[ROW_STAMPS[0]]!r} is not any LoopGateStatus "
        "value. Every one of this gate's answers is a NAMED state; a stamp "
        "outside the enum is a state somebody will infer, and on this gate the "
        "wrong inference is always 'it passed'"
    )

    # 2. The detail stamp: written exactly when the gate produced a detail,
    #    and an excerpt of that detail when written. Stated as a biconditional
    #    rather than as "the key is present", because the write site is
    #    deliberately conditional (`if role_loop.detail:`) and an unconditional
    #    claim would falsely refuse an answer that legitimately has no detail —
    #    the row would then be pinning this fixture rather than the rule.
    #
    #    The two records are truncated by different constants
    #    (`mechanical_verify.TAIL_CHARS` = 2000 for the row, 1000 for the
    #    payload, measured under `9d21ef0`), so they are compared on a common
    #    prefix rather than for equality.
    if payload["detail"]:
        assert ROW_STAMPS[1] in row, (
            f"the gate produced a detail ({payload['detail'][:120]!r}) and the "
            f"task's row carries no {ROW_STAMPS[1]!r} key. `ROW_STAMPS`'s own "
            "justification for splitting one stamp into a short verdict key "
            "plus an excerptable detail key is `unblock._DETAIL_FIELDS`, which "
            "prints exactly this key — so without the write, that "
            "justification is vacuous and `dispatcher blocked` shows a label "
            "with nothing behind it"
        )
        assert row[ROW_STAMPS[1]][:80] == payload["detail"][:80], (
            f"the row's detail stamp ({row[ROW_STAMPS[1]][:120]!r}) is not the "
            f"gate's detail ({payload['detail'][:120]!r}); the erasable record "
            "a human adjudicates from and the hash-chained one disagree about "
            "the same answer"
        )
    else:
        assert ROW_STAMPS[1] not in row, (
            f"the gate produced no detail and the row carries "
            f"{row.get(ROW_STAMPS[1])!r} anyway — a detail written from "
            "something other than the gate's answer"
        )

    # CONTROL for claim 2: this fixture must actually drive a detail out of the
    # gate, or the biconditional above is judged only in its absent half and
    # the write site is never exercised. If this ever fails, the fixture has
    # stopped reaching the detail — fix the fixture, not the claim.
    assert payload["detail"], (
        "the control failed: the gate answered "
        f"{payload['status']!r} with an EMPTY detail on this fixture, so the "
        f"{ROW_STAMPS[1]!r} write branch was never exercised and claim 2 above "
        "passed on its absent half alone. Either the fixture no longer reaches "
        "a detail-carrying answer, or the gate has stopped carrying "
        "`check_branch`'s reason forward"
    )

    # 3. Never the bare PR-time key. §5: PR time judges what lands.
    assert "role_diff" not in row, (
        "the row carries a bare `role_diff` key. §5 rules that PR time is the "
        "check that judges what lands — it reads its policy and its own code "
        "from the protected base and the loop has neither property — so a "
        "loop-time answer must not be signed with the other check's name"
    )

    # 4. What is written is exactly what `unblock` clears. This is the half
    #    that makes row 9 of test_loop_gate.py non-vacuous: that row pins the
    #    constant into `_STALE_STAMPS`; this one proves the keys it clears are
    #    keys that are actually set.
    written = {k for k in ROW_STAMPS if k in row}
    assert written, "no ROW_STAMPS key was written at all; see claim 1"
    assert written <= set(unblock_mod._STALE_STAMPS), (
        f"the orchestrator writes {sorted(written - set(unblock_mod._STALE_STAMPS))} "
        "and `dispatcher unblock` does not clear it, so an unblocked row "
        "carries the previous attempt's loop verdict into its re-run — "
        "'unblocking grants a retry, not a waiver' reversed"
    )


def test_the_run_flag_reaches_the_gates_answer_and_not_only_the_event(
    repo: Path, monkeypatch, tmp_path: Path,
) -> None:
    """**Row 25. The gate is opt-in per run — measured in the PAYLOAD, which is
    the thing the P3-2 amendment does not pin.** GREEN TODAY — see D8G-1; red
    under the mutation it names.

    Measured under `9d21ef0`: hardcoding ``enabled=True`` at the call site
    leaves `tests/test_loop_gate.py` **22 of 22 green**, and — the measurement
    the P4 added because the P3-2 ruling might have been thought to close this
    — leaves the three journal-sequence rows that ruling amended
    (`test_full_run_journal_chain_and_sequence`,
    `test_single_task_exact_sequence`,
    `test_no_config_skips_and_preserves_done_flow`) green too. They pin the
    event's TYPE and its POSITION and never its payload. The amendment proves
    the gate SPEAKS on every task; it proves nothing about what it SAYS.

    **AND NO ASSERTION ABOUT THE DECISION CAN CLOSE IT EITHER.** Measured on
    this fixture: gate off → ``not_enabled`` / ``proceed`` / task ``Done``;
    gate on → ``checked_clean`` / ``proceed`` / task ``Done``. Both worlds
    proceed, both finish Done, and the only difference visible anywhere is the
    STATUS in the payload and in the row stamp. That is this codebase's
    measured vacuity shape *"a mutation invisible because two implementations
    return the same value"* in its purest form, and it is why this row drives
    BOTH flag states in one call rather than asserting a single world.

    Why the default must stay off, so the row is not read as a preference: §3
    and `branch_reachability`'s own P4 ruling record **445 s per whole-tree
    sweep and two sweeps per `check_branch` call** — of the order of fifteen
    minutes per BODIES branch on the primary target — and rule that the gate
    must not go in front of that repository until the base sweep can be cached.
    A hardcoded ``True`` overrules that silently, in a file no body may edit
    and therefore in a change nobody reviews as a policy change.

    THE CONTROLS, judged in this same call:

      * both runs emit exactly one ``role_diff_loop_gate`` event for the task,
        at the SAME index in the task's own event sequence. So the difference
        the row asserts is a difference in what the gate said, never the event
        appearing or moving — which is exactly the axis the P3-2 amendment
        already covers and this row must not re-measure.
      * each run's row stamp is asserted alongside its payload, so a run whose
        payload and stamp disagree fails here rather than passing both halves.

    GREEN TODAY. FALSIFY (measured under `9d21ef0`, in a `git clone`): replace
    ``enabled=bool(getattr(cfg, "enable_role_loop_gate", False))`` with
    ``enabled=True`` at orchestrator.py:1476 — `tests/test_loop_gate.py` stays
    **22 passed**, the three amended journal rows stay green, and THIS ROW
    reddens on the gate-off half, reporting ``checked_clean`` where
    ``not_enabled`` is owed.

    Dispute D8G-3, stated in the header and repeated here because it is a limit
    of this very row: this proves the flag reaches the gate's ANSWER, not that
    it reaches `check_branch`'s COST. A gate that swept and then reported
    ``not_enabled`` would pass.

    Depends on the P4 floor commit: LANDED. The call site is in
    `orchestrator.py`, `FLOOR_GLOBS` entry 17 (measured) — P4-only.
    """
    _patch_spawn(monkeypatch)

    # The second world's repository is forked PRISTINE, before world 1 runs:
    # a run flips its rows to Done in `tasks.yaml`, and `runnable_now` would
    # not dispatch a Done row again — so a copy taken afterwards would produce
    # a run that judged nothing and an "identical" answer that is really two
    # absences. Measured while writing this row: taken after world 1, world 2
    # emits ZERO role_diff_loop_gate events.
    repo2 = _fresh_repo_like(repo, tmp_path)

    # --- world 1: default config. The flag is off unless a run turns it on. ---
    rc_off = orch_mod.execute(_args(repo, only="SMOKE-A"))
    assert rc_off == 0, "the gate-off fixture run did not complete"
    off_row = _row(repo, "SMOKE-A")
    off_evs = _gate_events(repo, "SMOKE-A")
    off_seq = _types_for(_events(repo), "SMOKE-A")

    assert len(off_evs) == 1, (
        f"the control failed: {len(off_evs)} role_diff_loop_gate events for "
        "SMOKE-A with the gate off. The P3-2 ruling requires exactly one per "
        "task whether or not the gate ran, so this row cannot tell a payload "
        "difference from an emit difference"
    )
    assert off_evs[0].payload["status"] == LoopGateStatus.NOT_ENABLED.value, (
        "a run that did NOT pass --enable-role-loop-gate reported "
        f"{off_evs[0].payload['status']!r} rather than "
        f"{LoopGateStatus.NOT_ENABLED.value!r}. The flag is not reaching the "
        "gate: `check_branch` ran on a run that did not ask for it. On a Go "
        "tree that is 445 s per sweep, twice per check, per BODIES branch — "
        "the cost §3 and branch_reachability's P4 ruling both refuse"
    )
    assert off_evs[0].payload["verdict"] is None, (
        "the gate-off payload carries a verdict "
        f"({off_evs[0].payload['verdict']!r}), so a check was made on a run "
        "that did not enable one. NOT_ENABLED means the question was never "
        "put; a verdict here means it was"
    )
    assert off_row.get(ROW_STAMPS[0]) == LoopGateStatus.NOT_ENABLED.value, (
        f"the gate-off row stamp is {off_row.get(ROW_STAMPS[0])!r}. §3's "
        "default-off ruling only works if a run with the gate off SAYS so on "
        "every row — otherwise it is indistinguishable from a run whose every "
        "branch was clean, which is the silence NOT_ENABLED exists not to be"
    )

    # --- world 2: the same fixture, the same task, the flag on. --------------
    rc_on = orch_mod.execute(
        _args(repo2, only="SMOKE-A", enable_role_loop_gate=True)
    )
    assert rc_on == 0, "the gate-on fixture run did not complete"
    on_row = _row(repo2, "SMOKE-A")
    on_evs = _gate_events(repo2, "SMOKE-A")
    on_seq = _types_for(_events(repo2), "SMOKE-A")

    assert len(on_evs) == 1, (
        f"the control failed: {len(on_evs)} role_diff_loop_gate events for "
        "SMOKE-A with the gate on"
    )
    # CONTROL: both worlds really dispatched and finished the task, so the
    # payload difference below is a difference between two answers rather than
    # between an answer and a run that did nothing.
    assert off_row["status"] == on_row["status"] == "Done", (
        "the control failed: the two worlds did not both dispatch SMOKE-A to "
        f"Done (off={off_row['status']!r}, on={on_row['status']!r}). A world "
        "that never ran the task has no gate answer, and comparing it to one "
        "that did proves nothing about the flag"
    )

    # CONTROL: the event's POSITION is identical across both worlds. This is
    # the axis the P3-2 amendment pins, and this row must differ from it on the
    # payload alone or it is re-measuring somebody else's seal.
    assert "role_diff_loop_gate" in off_seq and "role_diff_loop_gate" in on_seq
    assert (off_seq.index("role_diff_loop_gate")
            == on_seq.index("role_diff_loop_gate")), (
        f"the gate's event sits at index {off_seq.index('role_diff_loop_gate')} "
        f"with the flag off and {on_seq.index('role_diff_loop_gate')} with it "
        "on. The flag must change what the gate SAYS, never where it speaks — "
        "the position is what the P3-2 amendment pins and it must not move"
    )

    # THE PAYLOAD, which is the whole content of this row.
    assert on_evs[0].payload["status"] != LoopGateStatus.NOT_ENABLED.value, (
        "a run that DID pass --enable-role-loop-gate still reported "
        f"{LoopGateStatus.NOT_ENABLED.value!r}. The flag reaches the event but "
        "not the gate: opt-in that never opts in is a gate that is wired and "
        "never runs"
    )
    assert on_evs[0].payload["verdict"] is not None, (
        "the gate-on payload carries no verdict "
        f"(status={on_evs[0].payload['status']!r}), so `check_branch` was "
        "never reached on a run that asked for it"
    )
    assert on_row.get(ROW_STAMPS[0]) == on_evs[0].payload["status"], (
        f"the gate-on row stamp ({on_row.get(ROW_STAMPS[0])!r}) disagrees with "
        f"the journal ({on_evs[0].payload['status']!r})"
    )

    # AND THE TWO WORLDS DIFFER. Stated as its own claim so the failure message
    # names the actual defect rather than one of its symptoms.
    assert off_evs[0].payload["status"] != on_evs[0].payload["status"], (
        "the same fixture, the same task and the same code produced the same "
        f"gate status ({off_evs[0].payload['status']!r}) with the flag off and "
        "with it on. --enable-role-loop-gate does not reach the gate at all, "
        "and no assertion about the event's type, its position, the task's "
        "decision or its final status can see it: measured, both worlds "
        "PROCEED and both finish Done"
    )


def _fresh_repo_like(repo: Path, tmp_path: Path) -> Path:
    """A second, independent copy of the `repo` fixture's tree.

    A copy rather than a second `repo` fixture instance because pytest gives
    one fixture value per test and this row must judge TWO runs in ONE call —
    the whole point being that neither world's answer means anything without
    the other. Copied with `shutil.copytree` and re-initialised as its own git
    repository, so nothing here ever touches the first run's history.

    Nested one level deeper (``tmp_path/second/repo``) for the reason the
    `repo` fixture's own docstring records: `_args` derives ``--worktree-base``
    from ``repo.parent``, so two repositories sharing a parent would collide on
    the same ``wt/worktree-SMOKE-A`` directory and the second run would judge
    the first run's checkout.
    """
    import shutil
    import subprocess

    dst = tmp_path / "second" / "repo"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo, dst, ignore=shutil.ignore_patterns(".git", "_runs"))
    subprocess.run(["git", "init", "-q", "-b", "main", str(dst)],
                   check=True, capture_output=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "config", k, v], cwd=dst,
                       check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=dst, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=dst,
                   check=True, capture_output=True)
    return dst
