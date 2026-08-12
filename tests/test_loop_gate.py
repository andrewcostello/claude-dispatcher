"""Unit D8 seals — the post-implementer role check inside the task loop.

**P2. Failing seals plus the pins the scaffold's implemented tables earn.**
The specification is `src/claude_dispatcher/loop_gate.py`'s module docstring;
every ruling this file seals to is argued there and is not relitigated here.

Every citation carries ``Measured under:`` or ``Predicted (unmeasured)
under:``. The revision is ``06176f4`` (`feat/D8-loop-gate`, this file's
parent) unless a row says otherwise. ``06176f4`` differs from the scaffold's
own citation revision ``81591e4`` by exactly one added file — `loop_gate.py` —
so every `orchestrator.py` line number below is the same line under both.

Baseline re-measured here, not taken on trust
=============================================
Measured under `06176f4`, ``PYTHONPATH=src python3 -m pytest -q
-o addopts=""``: **2504 collected == 2491 passed + 13 skipped, 0 failed**, in
150.83 s. The vendored parser was fetched first
(``python3 -m claude_dispatcher.ts_parser_vendor``) because `typescript.js` is
gitignored and a fresh worktree does not otherwise reproduce the baseline.

Corrections to the scaffold's own citations, measured under `06176f4`
=====================================================================
Three line numbers in `loop_gate.py`'s docstring are off by a line or three.
None of them changes a ruling; all three are recorded because this unit's rule
is that a cited line is a measured line.

  * ``wt_mod.merge_dependencies`` is called at orchestrator.py:**1085**, not
    1088 (the scaffold says 1088 in §4 and in its commit message).
  * ``_reset_worktree(wt, pre_spawn_sha, ...)`` is at orchestrator.py:**1230**,
    not 1229.
  * the mechanical gate's own call,
    ``_verify_mechanical_and_maybe_retry``, is at **1415**; 1414 is its
    section comment, which is what the scaffold named as the anchor and is
    correct as an anchor.

Confirmed exactly as cited, measured under `06176f4`: the cascade loop opens
at **1215**; ``pre_spawn_sha = _branch_sha(...)`` is at **1194**;
``feat_baseline_sha`` at **1110**; ``base_sha_before`` at **1127**;
``_resolve_summary`` at **1406**; ``if final_status != plan_mod.DONE: break``
at **1411**.

What this file does NOT claim
=============================
  * **A CLEAN here is not "the branch is role-clean."** §5 of the scaffold
    rules that PR time wins, and no row below treats a loop-time CLEAN as a
    verdict about what will land. Row 20 is that rule as an assertion.
  * **`loop_gate.py` and `orchestrator.py` are not on the floor.** Measured
    under `06176f4`: neither matches any `role_protocol.FLOOR_GLOBS` entry, so
    a BODIES branch may edit both today. Every behavioural row below is judged
    by the very module a BODIES branch could edit; the rows redden when it
    does, but nothing here stops that branch from being *judged by the gate it
    just switched off* in the same run. That is §7's owed P4 commit — two
    `FLOOR_GLOBS` entries plus their rows in
    `tests/test_role_protocol_floor.py`, in one commit — and it is named in
    each affected row's docstring under "Depends on the P4 floor commit".

The vacuity shapes this file was written against
================================================
Named because each one is a measured shape on this codebase and three of them
are live traps in this unit:

  * **a row pinning a transient unimplementedness.** No row below asserts
    ``pytest.raises(NotImplementedError)``. A red that goes green the instant
    a stub gains a body proves nothing about the body.
  * **a fixture that stated only the world the fix wanted.** Every behavioural
    row carries a control judged *in the same call* — the same fixture, driven
    to the opposite answer — so a gate stuck on one verdict cannot pass.
  * **a fixture whose flag named a world and built another.** Row 14 turns
    ``enabled`` off over a branch that is *actually violating*, verified as
    violating by the same call. A NOT_ENABLED row over a clean branch would be
    satisfied identically by a gate that ignores the flag.
  * **a mutation invisible because two implementations return the same
    value.** This is the base-ref trap and it is why rows 1 and 3 exist: on a
    *clean* fixture, ``base_ref=pre_spawn_sha`` and ``base_ref=base_branch``
    return the same CLEAN, and a row built on one would be a transcription of
    the parameter name. Both rows use a fixture on which the two spellings
    return **different verdicts**.
  * **D7's own defect, checked rather than assumed.** D7 implemented its
    verdict tables specifically so a seal author would not seal a vacuous
    stub, and then shipped a real one, because ``x in SomeEnum`` is a VALUE
    lookup on Python 3.12+ and both guards answered permissively for the two
    inputs that had to refuse. **Re-derived here under `06176f4`, Python
    3.13.7, not read off the scaffold's promise:** `loop_gate.py` contains no
    ``in``-against-an-enum-class anywhere (measured by grep), and all three
    dispatches are ``Mapping[...]`` subscripts, which are member lookups.
    Probed directly: ``decision_for("checked_clean")`` and
    ``status_for_verdict("clean")`` both raise `LoopGateError`, while
    ``"checked_clean" in LoopGateStatus`` is ``True`` on this interpreter.
    Rows 10 and 11 keep that probe in the suite so the defect cannot arrive
    later.

Joint satisfiability, and the falsification matrix
==================================================
**Measured under `06176f4`.** A throwaway reference implementation of the two
stubs, plus the orchestrator wiring, the `unblock._STALE_STAMPS` addition and
the `ROW_STAMPS` stamping, was built in a ``cp -a`` clone (with the worktree's
``.git`` FILE removed, so floor and provenance rows do not run there — expected
and not a finding). Against it: **22 passed, 0 failed.** So every row in this
file is satisfiable at once, by one implementation, and no two rows contradict
each other.

Against the tree as it stands: **15 failed, 7 passed.**

Then each row's named mutation was applied to that reference implementation and
the whole file re-run. Every entry below is measured, not predicted; the
"other rows" column is reported rather than trimmed, because a mutation with a
wide blast radius is a fact about how coupled these rows are.

  ===================================================== ===== ================
  mutation applied to the reference implementation      rows  which
  ===================================================== ===== ================
  ``base_ref = base_branch``                                4  1, 2, 3, 15
  ``base_ref = pre_spawn_sha or base_branch``               2  2, 15
  drop the ``policy=`` argument                             2  3, 16
  move the hook below the mechanical gate                   1  4
  ``git reset --hard`` on the violation path                2  6, 17
  ``continue`` on the block path                            1  7
  delete one ``_BLOCKED_REASON_PREFIXES`` row               1  8
  drop `ROW_STAMPS` from ``_STALE_STAMPS``                  1  9
  delete one ``_DECISIONS`` row                             3  8, 10, 16
  rewrite `decision_for` as a value lookup                  1  10
  rewrite `status_for_verdict` as a value lookup            1  11
  NOT_ENABLED → BLOCK                                       4  8, 10, 12, 13
  disabled returns CHECKED_CLEAN                            2  13, 15
  accept ``deadline_seconds`` and ignore it                 1  14
  invent a default deadline and block on it                10  most
  let the policy failure fall through to `check_branch`     1  16
  ``role = sole_role(specs) or specs[0].role``              2  15, 17
  ``if len(roles) > 1`` instead of ``!= 1``                 1  19
  rename ``ROW_STAMPS[0]`` to ``role_diff``                 1  20
  re-spell the stamps as orchestrator literals              1  21
  extract the `check_branch` call into a helper             0  none — by
                                                               design, row 22
  inline reimplementation agreeing on every fixture         1  22
  ===================================================== ===== ================

Two entries in that table are findings rather than confirmations, and both are
recorded in their rows:

  * **the last two.** A behaviour-preserving helper extraction must not redden
    anything, and a *second implementation of the gate* that agrees on every
    fixture in this file reddens exactly one row. Row 22 is that row, and the
    measurement says plainly that no behavioural row here can tell one gate
    from two.
  * **"invent a default deadline"** takes down ten rows. That is not a row
    doing its job well; it is ten rows failing to say what happened. Row 15's
    message is the one that names it.

Which rows need §7's owed P4 floor commit, and in what sense
============================================================
The owed commit is two `FLOOR_GLOBS` entries —
``**/src/claude_dispatcher/loop_gate.py`` and
``**/src/claude_dispatcher/orchestrator.py`` — plus their rows in
``tests/test_role_protocol_floor.py``'s ``_FLOOR_ROWS`` /
``_FLOOR_x_ROLE_ROWS``, in ONE commit, because either half alone is red (the
scaffold measured the globs alone at 1 failed / 182 passed). It is a P4
amendment and it is not in this commit.

**No row in this file needs it to be red today, and no row needs it to go
green.** The dependency is of a different kind and is stated per row under
"Depends on the P4 floor commit":

  * **every row except 4, 7, 9, 18 and 21** is judged by `loop_gate.py` —
    the ten behavioural rows (1, 2, 3, 5, 6, 13, 14, 15, 16, 17) through its
    functions, and rows 8, 10, 11, 12, 19, 20, 22 through its tables and its
    source. A BODIES branch may write that file today (measured: it matches no
    `FLOOR_GLOBS` entry, and `DEFAULT_ROLE_RULES` denies BODIES ``tests/**``
    and the schema paths, not ``src/``). Such a branch reddens these rows,
    which is a caught failure — **but the run judging that branch uses the
    module the branch just edited.** That is the escape only `FLOOR_GLOBS`
    closes, and no seal living in a test file can.
  * **rows 4, 7 and 21** are judged by `orchestrator.py`, likewise unfloored.
    They are what make the wiring falsifiable at all, and they live in
    ``tests/**``, which `DEFAULT_ROLE_RULES` already denies BODIES — so the
    seals are protected and their subject is not.
  * **rows 9 and 18** turn on `unblock.py` and `plan.py` / `role_protocol`
    respectively and do not depend on the floor commit in either sense.

Disputes raised by this file, for P4
====================================
  * **P2-1 (row 21).** This file requires `orchestrator.py` to reference
    `loop_gate.ROW_STAMPS` rather than to re-spell ``"role_diff_loop"``. The
    scaffold names the keys as data "so `unblock` can clear them" but does not
    say the write site must use the constant. Invariant 5 says it must; a P3
    that disagrees should say so rather than quietly writing literals.
  * **P2-2 (row 8).** Reason distinctness is asserted as "no reason is a
    prefix of another", which is stronger than inequality and is not inherited
    from any measured consumer — `unblock` clears by exact key.
  * **P2-3 (row 18).** Row 18 measures that a mixed-role batch loads clean
    today, and §7(b) owes a plan-time refusal that will redden it. The
    amendment belongs to §7(b)'s own commit. Flagged so the redness is not
    mistaken for a regression.
  * **P2-4 (row 15).** DEADLINE_EXCEEDED cannot be produced by any input this
    file can construct, and the row asserts the durable half — a call given no
    deadline may never report one — rather than an unreachability claim that
    would fight §7(e) when it lands. Stated plainly rather than skipped.
  * **P2-5 (the scaffold's citations).** Three line numbers in
    `loop_gate.py`'s docstring are off; corrected above. No ruling changes.
  * **P2-6 (a gap in §7's owed list, found while writing row 9, NOT sealed
    here).** `ROW_STAMPS`'s own docstring justifies the two-key shape by
    pointing at `unblock._DETAIL_FIELDS` — *"a short verdict key plus a
    separate `_detail` key it can excerpt to 400 characters"*. Measured under
    `06176f4`: `_DETAIL_FIELDS` (unblock.py:52) lists four keys and
    ``role_diff_loop_detail`` is not one of them, and `list_blocked` prints
    ONLY the keys in that list (unblock.py:79-85). So as owed, the loop gate
    would write a detail field the review queue never prints — which makes the
    stated reason for splitting the key into two vacuous. §7(c) owes
    `_STALE_STAMPS` and says nothing about `_DETAIL_FIELDS`, so **no row here
    asserts it**: widening a P3's owed list from a seal file is how a seal
    becomes a specification nobody agreed to. Raised for P4 to rule on.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import orchestrator as orch_mod
from claude_dispatcher import plan as plan_mod
from claude_dispatcher import role_protocol as rp_mod
from claude_dispatcher import unblock as unblock_mod
from claude_dispatcher.loop_gate import (
    ROW_STAMPS,
    LoopGateDecision,
    LoopGateError,
    LoopGateStatus,
    blocked_reason,
    check_after_implementer,
    decision_for,
    sole_role,
    status_for_verdict,
)
from claude_dispatcher.loop_gate import (
    _BLOCKED_REASON_PREFIXES,
    _DECISIONS,
    _VERDICT_STATUSES,
)
from claude_dispatcher.role_protocol import DiffVerdict, Role, TaskRoleSpec

_PKG_ROOT = Path(__file__).resolve().parents[1] / "src" / "claude_dispatcher"

#: The statuses that mean "this gate could not answer the question it was
#: asked". Derived here rather than imported so that a row asserting they all
#: BLOCK is not the same expression as the table it judges.
_COULD_NOT_CHECK = (
    LoopGateStatus.CHECKED_UNDETERMINED,
    LoopGateStatus.ROLE_UNRESOLVED,
    # P4 ruling on dispute P3-1, 2026-08-12. The ninth status, and it is listed
    # here for the reason this tuple is derived by hand rather than imported:
    # its job is to name, independently of `_DECISIONS`, every status that
    # means "the gate could not answer". A new blocking status left out of this
    # tuple reddens NOTHING — the loop below only visits what is written here —
    # so omitting it would silently narrow the row that checks they all BLOCK.
    LoopGateStatus.RULE_UNRESOLVED,
    LoopGateStatus.BASE_UNRESOLVED,
    LoopGateStatus.DEADLINE_EXCEEDED,
    LoopGateStatus.GATE_ERROR,
)


# --------------------------------------------------------------------------- #
# Fixture machinery — real git repositories, because the ruling this unit
# turns on is which SHA bounds a diff, and no stub can be wrong about that in
# the way a real repository can.
# --------------------------------------------------------------------------- #


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _sha(cwd: Path, ref: str = "HEAD") -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=str(cwd), check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _new_repo(tmp_path: Path, name: str = "repo") -> Path:
    """A repo on `main` with one commit. The spelling `main` is deliberate: it
    is what `RunConfig.base_branch` names in this dispatcher's own worklists."""
    repo = tmp_path / name
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "base.txt").write_text("seed\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    return repo


def _well_formed_unit(repo: Path) -> str:
    """Build a unit exactly as the dispatcher builds one, and return the SHA
    `orchestrator.py:1194` would have taken.

    Faithful to production in the one respect that matters here, measured
    under `06176f4`:

      * the SEALS task runs on its own branch and commits ``tests/**``;
      * `_run_task` merges it into the BODIES task's worktree branch with
        ``git merge --no-ff`` (`worktree.merge_dependencies`, called at
        orchestrator.py:1085 — *before* the implementer spawns);
      * only then is ``pre_spawn_sha`` taken (orchestrator.py:1194).

    So on every well-formed unit the branch already carries another role's
    ``tests/**`` commits before the body author writes a line. The dependency
    edge is not optional: `role_protocol.validate`'s PO-2 refuses a BODIES row
    that does not name a SEALS row in its ``blockedBy``, so this is the shape
    of *every* legal unit, not an unusual one.
    """
    _git(["checkout", "-q", "-b", "feat/U-seals"], repo)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_u.py").write_text(
        "def test_u():\n    raise AssertionError('unimplemented')\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "seals(U): failing seals"], repo)

    _git(["checkout", "-q", "main"], repo)
    _git(["checkout", "-q", "-b", "feat/U-bodies"], repo)
    _git(["merge", "--no-ff", "-q", "-m", "merge dependency U-SEALS",
          "feat/U-seals"], repo)
    return _sha(repo)


def _spec(key: str, role: Role) -> TaskRoleSpec:
    return TaskRoleSpec(task_key=key, role=role)


def _gate(repo: Path, branch: str, pre_spawn_sha: str | None, *,
          role: Role = Role.BODIES, enabled: bool = True,
          base_branch: str = "main", specs=None, **kw):
    """One hook invocation, with the loop's live state spelled out."""
    return check_after_implementer(
        enabled=enabled,
        repo_root=repo,
        base_branch=base_branch,
        branch_ref=branch,
        pre_spawn_sha=pre_spawn_sha,
        specs=[_spec("U-BODIES", role)] if specs is None else specs,
        **kw,
    )


def _orchestrator_source() -> str:
    return (_PKG_ROOT / "orchestrator.py").read_text(encoding="utf-8")


def _run_task_cascade_loop() -> ast.For:
    """The ``for idx, (attempt_agent, attempt_effort) in enumerate(cascade):``
    node inside `_run_task`, located by AST and never by line number.

    Measured under `06176f4`: `_run_task` opens at 1038 and contains exactly
    two `for` loops, at 1215 and 1799; exactly one of them names ``cascade`` in
    its iterable, and it is the one at 1215 — the cascade loop the scaffold's
    §1 anchors to.
    """
    tree = ast.parse(_orchestrator_source(), filename="orchestrator.py")
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_run_task"
    )
    loops = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.For)
        and any(
            isinstance(m, ast.Name) and m.id == "cascade"
            for m in ast.walk(n.iter)
        )
    ]
    assert len(loops) == 1, (
        f"expected exactly one cascade loop in _run_task, found {len(loops)}; "
        "the analyzer is reading the wrong function and every assertion "
        "derived from it is vacuous"
    )
    return loops[0]


def _call_linenos(node: ast.AST, name: str) -> list[int]:
    """Line numbers of every call to ``name`` inside ``node``, by bare callee
    name — deliberately blind to the receiver's spelling, for the reason
    `tests/test_floor_closure.py::_calls_on_in_package_modules` records: a row
    that pins the local alias is red for a rename that changes nothing and
    green for an alias rebound to something else."""
    found = []
    for m in ast.walk(node):
        if not isinstance(m, ast.Call):
            continue
        f = m.func
        callee = (
            f.id if isinstance(f, ast.Name)
            else f.attr if isinstance(f, ast.Attribute)
            else None
        )
        if callee == name:
            found.append(m.lineno)
    return sorted(found)


# --------------------------------------------------------------------------- #
# §1 — THE BASE-REF RULING, sealed as a defect that would otherwise fire
# --------------------------------------------------------------------------- #


def test_the_gate_judges_the_body_commit_not_the_seals_merged_before_it(
    tmp_path: Path,
) -> None:
    """**Row 1. The base-ref ruling, as the defect it prevents.**

    A row that merely asserted ``pre_spawn_sha`` reaches `check_branch` would
    be a transcription of a parameter name: on a clean branch both spellings
    of the base return CLEAN, so the mutation would be invisible — the fourth
    vacuity shape, "two implementations return the same value". This row is
    built on the one fixture where the two spellings **disagree**, and the
    disagreement is not exotic: it is every well-formed unit this protocol
    can produce.

    HOW PRODUCTION PRODUCES THIS INPUT. Measured under `06176f4` by reading
    `orchestrator._run_task` top to bottom: ``wt_mod.merge_dependencies``
    (line 1085) merges every ``blockedBy`` dependency branch into the task's
    worktree branch, and it runs **before** the implementer spawns;
    ``pre_spawn_sha`` is taken afterwards at line 1194. By PO-2
    (`role_protocol.validate`, refusing a BODIES row that names no SEALS row
    in its ``blockedBy``) the dependency of a BODIES task *is* its unit's
    SEALS task. So the branch carries the seal author's ``tests/**`` commits
    before the body author touches anything, on every legal unit.

    MEASURED, `06176f4`, on this exact fixture shape — the two answers:

        base = pre_spawn_sha  -> CLEAN,     violations []
        base = cfg.base_branch -> VIOLATION, violations ['tests/test_u.py']

    The second answer names the SEAL AUTHOR'S file as the BODY AUTHOR'S
    violation. That is not a rare misfire; it is what the gate would report on
    the first well-formed unit it ever saw, which is the sense in which
    ``cfg.base_branch`` would have made this unit useless on day one.

    THE CONTROL, judged in the same call: the same repository, one commit
    later, where the body author really does edit the seal. From the same
    ``pre_spawn_sha`` that answered CLEAN above, the gate must answer
    VIOLATION. Without it, a gate hardcoded to CLEAN — or one whose diff is
    empty because the base is the branch tip — satisfies the first half
    perfectly.

    RED TODAY: `check_after_implementer` raises NotImplementedError, and this
    row does not assert that. It asserts the two verdicts; the stub cannot
    produce either.
    GREEN WHEN: P3 passes ``pre_spawn_sha`` as `check_branch`'s ``base_ref``.
    FALSIFY (measured, `06176f4`, by reference implementation): pass
    ``base_branch`` there instead — the first assertion reddens with
    CHECKED_VIOLATION over ``tests/test_u.py`` while the control stays green,
    which is the direction that matters (a fixture where both halves move
    together would prove nothing about which ref was used).

    Depends on the P4 floor commit: NO for its own redness, YES for its
    enforceability — a BODIES branch may edit `loop_gate.py` today, and this
    row would redden on that branch while the run judging it used the edited
    module.
    """
    repo = _new_repo(tmp_path)
    pre_spawn_sha = _well_formed_unit(repo)

    (repo / "src").mkdir()
    (repo / "src" / "u.py").write_text("def u():\n    return 1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(U): implement"], repo)

    clean = _gate(repo, "feat/U-bodies", pre_spawn_sha)
    assert clean.status is LoopGateStatus.CHECKED_CLEAN, (
        f"a well-formed unit — SEALS merged in before the spawn, body touching "
        f"only src/ — was judged {clean.status!r}. If it is CHECKED_VIOLATION, "
        f"the diff was bounded by cfg.base_branch and the gate is reporting "
        f"the seal author's tests/** as this branch's violation: {clean.detail}"
    )
    assert clean.decision is LoopGateDecision.PROCEED
    assert clean.verdict is DiffVerdict.CLEAN

    # The control, same fixture, same call: the body really does edit the seal.
    (repo / "tests" / "test_u.py").write_text(
        "def test_u():\n    assert True\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(U): soften the seal"], repo)

    caught = _gate(repo, "feat/U-bodies", pre_spawn_sha)
    assert caught.status is LoopGateStatus.CHECKED_VIOLATION, (
        "the body author rewrote tests/test_u.py after pre_spawn_sha and the "
        f"gate did not see it ({caught.status!r}). Without this half the CLEAN "
        "above is satisfied by a gate that never reads a diff at all"
    )
    assert caught.decision is LoopGateDecision.BLOCK
    assert caught.result is not None
    assert [v.path for v in caught.result.violations] == ["tests/test_u.py"]


def test_a_missing_pre_spawn_sha_blocks_rather_than_falling_back_to_the_base(
    tmp_path: Path,
) -> None:
    """**Row 2. ``None`` → BLOCK, and specifically not the fallback.**

    HOW PRODUCTION PRODUCES THIS INPUT. Measured under `06176f4`:
    ``pre_spawn_sha = _branch_sha(repo_root, wt.branch, log_path, snap.key)``
    at orchestrator.py:1194, and `_branch_sha` returns ``None`` and logs on any
    git failure (line 3235). Nothing downstream of 1194 re-derives it.

    WHY A DISTINCT ROW RATHER THAN A CLAUSE OF ROW 1. A fallback to
    ``cfg.base_branch`` is the shape a P3 body reaches for when a ref is
    missing, and on this fixture it does not merely answer a different
    question — it answers CHECKED_VIOLATION over the seal author's file
    (measured, row 1). So "no fallback" is not a style preference; it is the
    difference between a blocked task with an honest reason and a body author
    blamed for a seal they never touched.

    THE CONTROL, judged in the same call: the same repository and the same
    branch with a real ``pre_spawn_sha`` answers CHECKED_CLEAN. That is what
    distinguishes "BLOCK because this gate refuses an unresolved base" from
    "BLOCK because this gate blocks everything".

    RED TODAY: the stub raises.
    GREEN WHEN: P3 raises from `resolve_inputs` step 2 and
    `check_after_implementer` maps it to BASE_UNRESOLVED.
    FALSIFY (measured, reference implementation): substitute
    ``base_ref = pre_spawn_sha or base_branch`` — the first assertion reddens
    with CHECKED_VIOLATION, naming ``tests/test_u.py``, which is exactly the
    wrong answer the fallback would ship.

    Depends on the P4 floor commit: NO for redness, YES for enforceability.
    """
    repo = _new_repo(tmp_path)
    pre_spawn_sha = _well_formed_unit(repo)
    (repo / "src").mkdir()
    (repo / "src" / "u.py").write_text("def u():\n    return 1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(U): implement"], repo)

    missing = _gate(repo, "feat/U-bodies", None)
    assert missing.status is LoopGateStatus.BASE_UNRESOLVED, (
        f"pre_spawn_sha was None and the gate answered {missing.status!r}. "
        "CHECKED_VIOLATION here means a fallback to cfg.base_branch, which on "
        "this fixture blames the seal author's tests/test_u.py; CHECKED_CLEAN "
        "means a fallback that answers a question nobody asked"
    )
    assert missing.decision is LoopGateDecision.BLOCK
    assert missing.result is None, (
        "BASE_UNRESOLVED must carry no RoleDiffResult: there was no check, and "
        "a result attached to it is a check somebody will read as one"
    )

    resolvable = _gate(repo, "feat/U-bodies", pre_spawn_sha)
    assert resolvable.status is LoopGateStatus.CHECKED_CLEAN, (
        "the control failed: with a real pre_spawn_sha this same fixture must "
        f"reach a verdict, and it answered {resolvable.status!r}. Without it, "
        "the assertion above is satisfied by a gate that blocks everything"
    )


def test_the_policy_comes_from_the_protected_base_though_the_diff_does_not(
    tmp_path: Path,
) -> None:
    """**Row 3. The two refs, and the seam that lets one call carry both.**

    §4's subtlest ruling: ``base_ref`` bounds the DIFF and is a commit on the
    branch under judgement, so `check_branch`'s step 1 — which loads the policy
    from ``base_ref`` when none is given — would take the policy off the branch
    it is judging. Invariant 6. The fix is the ``policy=`` seam `check_branch`
    already publishes, loaded from ``cfg.base_branch``.

    HOW PRODUCTION PRODUCES THIS INPUT. Measured under `06176f4`:
    `merge_dependencies` (orchestrator.py:1085) merges arbitrary dependency
    branches into this worktree branch before the spawn, and nothing filters
    ``.dispatcher.yaml`` out of a dependency's diff. A dependency whose commit
    drops the repo's ``roles:`` section therefore lands on the branch *before*
    ``pre_spawn_sha`` is taken — so the weakened file is part of the base the
    diff is measured from, not part of the body's own work.

    WHY THE FIXTURE DROPS A SECTION RATHER THAN ADDING ONE. Measured, by
    reading `role_policy_from_mapping`: a repo ``roles:`` section may only ADD
    to a role's deny set — narrowing is a typed error. So a branch cannot
    weaken the policy by *writing* one; the only weakening edit expressible is
    the DELETION of an addition the base already carries. That is what this
    fixture does, and it is the reason the row is not a hypothetical.

    MEASURED, `06176f4`, on this exact fixture:

        policy derived from base_ref (a branch commit) -> CLEAN
        policy pinned to cfg.base_branch               -> VIOLATION
                                                          ['config/app.yaml']

    THE CONTROL, judged in the same call: with the same base-pinned policy, a
    body that touches only ``src/`` answers CLEAN. A gate that hardcoded
    VIOLATION, or one whose policy denied everything, fails it.

    RED TODAY: the stub raises.
    GREEN WHEN: P3's `resolve_inputs` calls
    ``load_role_policy_from_base(repo_root, base_branch)`` and
    `check_after_implementer` forwards it to ``policy=``.
    FALSIFY (measured, reference implementation): drop the ``policy=``
    argument so `check_branch` derives it from ``base_ref`` — the first
    assertion reddens with CHECKED_CLEAN while the control stays green.

    Depends on the P4 floor commit: NO for redness, YES for enforceability.
    """
    repo = _new_repo(tmp_path)
    (repo / ".dispatcher.yaml").write_text(
        'roles:\n  bodies:\n    immutable_paths:\n      - "config/**"\n',
        encoding="utf-8",
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base: the repo adds config/** to the bodies deny set"],
         repo)

    _git(["checkout", "-q", "-b", "feat/U-bodies"], repo)
    (repo / ".dispatcher.yaml").write_text("roles: {}\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "a merged dependency drops the roles: section"], repo)
    pre_spawn_sha = _sha(repo)

    (repo / "config").mkdir()
    (repo / "config" / "app.yaml").write_text("k: v\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(U): edit a path the base protects"], repo)

    judged = _gate(repo, "feat/U-bodies", pre_spawn_sha)
    assert judged.status is LoopGateStatus.CHECKED_VIOLATION, (
        f"the gate answered {judged.status!r}. CHECKED_CLEAN means the policy "
        "was loaded from base_ref — a commit on the branch under judgement — "
        "so the branch supplied the rule that judged it, which is invariant "
        f"6's failure: {judged.detail}"
    )
    assert judged.result is not None
    assert [v.path for v in judged.result.violations] == ["config/app.yaml"]

    # The control, same base-pinned policy, same call: ordinary work is CLEAN.
    _git(["checkout", "-q", "-b", "feat/U-bodies-2", pre_spawn_sha], repo)
    (repo / "src").mkdir()
    (repo / "src" / "u.py").write_text("def u():\n    return 1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(U): ordinary work"], repo)

    ordinary = _gate(repo, "feat/U-bodies-2", pre_spawn_sha)
    assert ordinary.status is LoopGateStatus.CHECKED_CLEAN, (
        "the control failed: under the base-pinned policy an ordinary src/ "
        f"commit must be CLEAN and answered {ordinary.status!r}. Without it, "
        "the assertion above is satisfied by a policy that denies everything"
    )


# --------------------------------------------------------------------------- #
# §2 — THE HOOK'S POSITION IN THE CASCADE
# --------------------------------------------------------------------------- #


def test_the_hook_is_inside_the_cascade_loop_and_before_the_mechanical_gate() -> None:
    """**Row 4. The unit's whole content is that a call exists at one place.**

    The scaffold's own note to P2: *"Seal the hook point itself, not the tables
    only … it must locate the call by AST inside `_run_task`, because a call
    anywhere else in `orchestrator.py` is not the hook."* This is D7's
    `test_check_branch_actually_calls_the_reachability_gate` in this unit's
    position, and like it, it is STATIC — it proves the call is written where
    the ruling puts it, not that its answer changes an outcome. Rows 1-3 and 6
    are the behavioural half.

    FOUR claims, each derived from `orchestrator.py`'s source:

      1. `orchestrator` imports `loop_gate`. Measured under `06176f4`: it does
         not today — the string ``loop_gate`` does not occur in the file.
      2. `_run_task` calls `check_after_implementer` **inside the cascade
         loop**. Outside it is the placement §1 rejects on a measured fact:
         `_reset_worktree` discards a rung's diff, so a gate outside the loop
         never sees a rung that violated and was then discarded. Row 5 drives
         that loss.
      3. the call comes **after** `_resolve_summary`. Before it, the gate pays
         for a git diff on every task the agent itself declared Blocked or
         Escalated, which §1 rejects.
      4. the call comes **before** `_verify_mechanical_and_maybe_retry`. After
         it, the mechanical gate's `_retry_for_test_fix` has committed, and the
         gate judges a diff two agents wrote while reporting one agent's key —
         §1's measured rejection, and the reason "before verify" is the ruling
         rather than a preference.

    THE LENS CONTROL, in this same call: the analyzer must find
    `_resolve_summary` and `_verify_mechanical_and_maybe_retry` inside the
    located loop before it may compare anything to them. Measured under
    `06176f4`: the cascade loop is the unique `for` in `_run_task` whose
    iterable names ``cascade`` (there are two loops, at 1215 and 1799);
    `_resolve_summary` is called at 1406 and
    `_verify_mechanical_and_maybe_retry` at 1415 — both inside it. Without the
    control, an analyzer that found no calls at all would pass claims 3 and 4
    vacuously.

    RED TODAY: `orchestrator.py` is untouched; claims 1 and 2 fail together.
    GREEN WHEN: P3 wires the call between orchestrator.py:1411 and 1414.
    FALSIFY (measured, reference implementation): move the wired call below
    the mechanical gate — this row reddens **alone**, 21 of 22 green, with
    both linenos in the message. Every behavioural row in this file stays
    green under that move, because the gate still answers correctly; it just
    answers about a diff two agents wrote. That is the whole reason a static
    positional row exists.

    Depends on the P4 floor commit: NO for redness. YES in the strong sense —
    this is the row a BODIES branch would have to delete to unwire the gate,
    and it lives in `tests/**`, which `DEFAULT_ROLE_RULES` already denies
    BODIES. The floor entries are what protect `orchestrator.py` itself.
    """
    source = _orchestrator_source()
    loop = _run_task_cascade_loop()

    resolve = _call_linenos(loop, "_resolve_summary")
    mechanical = _call_linenos(loop, "_verify_mechanical_and_maybe_retry")
    assert resolve and mechanical, (
        "the analyzer found no _resolve_summary and/or no "
        "_verify_mechanical_and_maybe_retry inside the cascade loop, so it is "
        "reading the wrong node and every ordering claim below is vacuous: "
        f"resolve={resolve} mechanical={mechanical}"
    )

    assert "loop_gate" in source, (
        "orchestrator.py does not name loop_gate at all, so unit D8's gate is "
        "not on the task loop's path. Measured under 06176f4: this is the "
        "state today, and it is the whole content of the unit"
    )

    hook = _call_linenos(loop, "check_after_implementer")
    assert hook, (
        "no call to loop_gate.check_after_implementer inside _run_task's "
        "cascade loop. A call elsewhere in orchestrator.py is not the hook: "
        "outside the loop it sees only the surviving rung (§1), and a rung "
        "that committed to tests/** and was then discarded for an unrelated "
        "quality failure would never be reported at all"
    )
    assert len(hook) == 1, (
        f"the hook is called {len(hook)} times inside the cascade loop "
        f"({hook}); two calls are two answers about one branch and this file "
        "cannot say which one blocks"
    )

    assert min(resolve) < hook[0], (
        f"the hook (line {hook[0]}) runs before _resolve_summary "
        f"(line {min(resolve)}), so it pays for a git diff on every task the "
        "agent itself declared Blocked or Escalated — which already has a "
        "human's attention and a reason"
    )
    assert hook[0] < min(mechanical), (
        f"the hook (line {hook[0]}) runs after _verify_mechanical_and_maybe_"
        f"retry (line {min(mechanical)}), whose _retry_for_test_fix COMMITS. "
        "A gate there judges a diff two agents wrote and reports one agent's "
        "key — §1's measured rejection of 'after the mechanical gate'"
    )


def test_a_rungs_violation_is_destroyed_by_the_reset_the_next_rung_performs(
    tmp_path: Path,
) -> None:
    """**Row 5. Why the hook is INSIDE the cascade: the evidence does not
    survive the loop.**

    §1 rejects "outside the cascade loop, once, after ``break``" on the ground
    that ``_reset_worktree(wt, pre_spawn_sha, ...)`` discards a rung's diff.
    That is an argument until somebody builds the case; this row builds it, and
    it drives the PRODUCTION function — `orchestrator._reset_worktree` itself,
    not a re-spelling of it — so a change to what the reset does reaches this
    row.

    HOW PRODUCTION PRODUCES THIS INPUT. Measured under `06176f4`:
    `_reset_worktree` is called at orchestrator.py:1230, at the top of every
    cascade rung after the first, guarded only by ``if pre_spawn_sha:``. It
    runs ``git reset --hard <pre_spawn_sha>`` then ``git clean -fd`` in the
    worktree, where the task branch is checked out — so the branch ref itself
    moves back. A rung is discarded on any of **seven** escalations, each a
    ``fail_reason = ...`` followed by ``continue``, measured at lines 1314
    (``spawn_failed``), 1330 (``session_exit_code_*``), 1345
    (``summary_missing``), 1428 (``mechanical_verification_failed``), 1452
    (``seal_verification_failed``), 1524 (the verifier's own reason) and 1627
    (``cross_family_panel_block``). Not one of them is a role failure — so a
    rung that violated the role protocol AND failed the mechanical gate is
    discarded for the mechanical reason, and its breach goes with it.

    MEASURED, `06176f4`, on this fixture:

        before _reset_worktree -> VIOLATION,    ['tests/test_s.py']
        after  _reset_worktree -> UNDETERMINED, "git reported no changed paths"

    So a gate placed outside the loop would report, for that rung, neither the
    violation nor an error naming it — it would report "I could not tell",
    about a breach that happened and whose evidence the dispatcher itself
    deleted. The protocol breach is a fact about the agent, not about the
    surviving diff.

    THE CONTROL is the first half, judged in the same call: the same gate over
    the same branch answers CHECKED_VIOLATION before the reset. Without it,
    the second assertion is satisfied by a gate that never finds anything.

    RED TODAY: the stub raises; neither half can be produced.
    GREEN WHEN: `check_after_implementer` reaches `check_branch`.
    FALSIFY (measured, reference implementation): none of the base spellings
    change this row — that is the point. It reddens if the gate stops seeing a
    committed violation at all, and its second half reddens if a future
    `_reset_worktree` stops discarding the rung (in which case the ruling this
    row defends would need re-arguing, which is the signal wanted).

    Depends on the P4 floor commit: NO for redness, YES for enforceability.
    """
    repo = _new_repo(tmp_path)
    _git(["checkout", "-q", "-b", "feat/C"], repo)
    pre_spawn_sha = _sha(repo)

    (repo / "tests").mkdir()
    (repo / "tests" / "test_s.py").write_text(
        "def test_s():\n    pass\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "rung 1: the implementer edits a seal"], repo)

    in_loop = _gate(repo, "feat/C", pre_spawn_sha)
    assert in_loop.status is LoopGateStatus.CHECKED_VIOLATION, (
        "the control failed: the gate must see rung 1's tests/** commit while "
        f"the rung is still on the branch, and it answered {in_loop.status!r}"
    )

    # The production reset, driven by name so that a change to it reaches here.
    class _WT:
        path = repo

    orch_mod._reset_worktree(_WT(), pre_spawn_sha, tmp_path / "run.log", "U-BODIES")

    outside_loop = _gate(repo, "feat/C", pre_spawn_sha)
    assert outside_loop.status is not LoopGateStatus.CHECKED_VIOLATION, (
        "after _reset_worktree the violating commit is gone from the branch, "
        "yet the gate still reports CHECKED_VIOLATION — which would mean it is "
        "reading something other than the branch's current diff"
    )
    assert outside_loop.status is LoopGateStatus.CHECKED_UNDETERMINED, (
        "a gate placed outside the cascade loop sees an EMPTY diff for a rung "
        "that violated and was discarded. The honest answer to an empty diff "
        f"is UNDETERMINED; this gate answered {outside_loop.status!r}. If that "
        "is CHECKED_CLEAN, the discarded breach reads as a pass"
    )
    assert outside_loop.decision is LoopGateDecision.BLOCK


# --------------------------------------------------------------------------- #
# §3 — BLOCKED, NOT CASCADE, NOT FAIL
# --------------------------------------------------------------------------- #


def test_a_violation_blocks_and_the_branch_survives_it(tmp_path: Path) -> None:
    """**Row 6. Blocked keeps the branch, because the diff is the evidence.**

    §2's ruling weighed against failing outright: at the hook the branch
    carries the dependency merges plus a whole implementer session, and a body
    agent that edited a seal has produced something a human needs to READ
    before deciding whether the seal was wrong. So the gate must ANSWER and
    must not act: no reset, no branch deletion, no commit of its own.

    The scaffold rules this explicitly — *"This function ANSWERS; `_run_task`
    acts"* — and rejects performing the block here because that is the
    orchestrator's control flow and its locking discipline.

    THE CONTROL, judged in the same call: the branch tip before and after the
    gate call, plus the violating file still readable on disk. A gate that
    reset the worktree, or that committed a marker, moves one of them.

    RED TODAY: the stub raises.
    GREEN WHEN: `check_after_implementer` returns a BLOCK outcome without
    touching the repository.
    FALSIFY (measured, reference implementation): add a
    ``_reset_worktree``-shaped ``git reset --hard base_ref`` to the violation
    branch of the reference `check_after_implementer` — the tip assertion
    reddens while the status assertion stays green, which is the shape a
    "helpfully clean up the bad rung" edit would take.

    Depends on the P4 floor commit: NO for redness, YES for enforceability —
    this row is the one that notices if the block path grows a side effect,
    and `loop_gate.py` is writable by BODIES today.
    """
    repo = _new_repo(tmp_path)
    _git(["checkout", "-q", "-b", "feat/V"], repo)
    pre_spawn_sha = _sha(repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_v.py").write_text(
        "def test_v():\n    pass\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(V): edits a seal"], repo)

    tip_before = _sha(repo)
    out = _gate(repo, "feat/V", pre_spawn_sha)

    assert out.decision is LoopGateDecision.BLOCK
    assert out.status is LoopGateStatus.CHECKED_VIOLATION
    assert _sha(repo) == tip_before, (
        "the gate moved the branch. Blocked exists to keep the branch, the "
        "worktree and the evidence in front of a human; a gate that resets or "
        "commits has destroyed the diff the human was blocked to read"
    )
    assert (repo / "tests" / "test_v.py").exists(), (
        "the violating file is gone from the working tree after the gate ran"
    )
    assert out.result is not None, (
        "a CHECKED_VIOLATION outcome carrying no RoleDiffResult tells the "
        "review queue that something was wrong and not what"
    )


def test_the_block_path_does_not_escalate_the_cascade() -> None:
    """**Row 7. No cascade, sealed structurally, because the behaviour it
    forbids is a control-flow statement.**

    §2: the loop's other gates escalate to the next implementer rung on
    failure — measured under `06176f4` at the four quality escalations 1428
    (mechanical), 1452 (seal-inversion), 1524 (verifier) and 1627 (panel),
    plus three spawn escalations at 1314, 1330 and 1345. This one must not,
    on two grounds — the next rung's `_reset_worktree` DESTROYS the evidence
    before a human sees it, so the row's ``blocked_reason`` would describe a
    diff that no longer exists; and a role violation is out-of-scope work, not
    weak work, so the same description handed to a stronger model has the same
    scope.

    The forbidden thing is a ``continue`` — that is literally how every other
    gate in this loop escalates (measured under `06176f4`, the cascade loop's
    ``continue`` statements are at lines 1314, 1330, 1345, 1428, 1452, 1524 and
    1627). So this row asserts: **between the hook's call and the mechanical
    gate's call there is no ``continue`` and no ``_reset_worktree``.**

    THE LENS CONTROL, in this same call: the analyzer must find ``continue``
    statements elsewhere in the same loop. Measured: seven of them. An analyzer
    that found none would pass this row while seeing nothing, which is the
    "fixture that stated only the world the fix wanted" shape applied to a
    static reader.

    RED TODAY: the hook is not wired, so the region does not exist and the row
    fails at the same assertion row 4 fails at.
    GREEN WHEN: P3 wires the call and its BLOCK branch breaks out or returns
    rather than continuing.
    FALSIFY (measured, reference implementation): wire the call and give its
    BLOCK branch ``fail_reason = ...; continue`` in the shape the mechanical
    gate uses — this row reddens alone, naming the ``continue``'s line, while
    rows 4 and 6 stay green. That is the mutation this row exists for: it is
    invisible to every behavioural row in this file, because the escalation
    happens in the orchestrator, after the gate has already answered.

    Depends on the P4 floor commit: NO for redness. This row and row 4 are the
    pair that make `orchestrator.py`'s wiring falsifiable, and both live in a
    file BODIES may not write.
    """
    loop = _run_task_cascade_loop()

    all_continues = [n.lineno for n in ast.walk(loop) if isinstance(n, ast.Continue)]
    assert all_continues, (
        "the analyzer found no `continue` anywhere in the cascade loop, so it "
        "cannot see the cascade escalation this row forbids and the assertion "
        "below is vacuous. Measured under 06176f4: there are seven"
    )

    hook = _call_linenos(loop, "check_after_implementer")
    mechanical = _call_linenos(loop, "_verify_mechanical_and_maybe_retry")
    assert hook and mechanical, (
        "no hook call and/or no mechanical gate call inside the cascade loop; "
        f"this row cannot bound a region: hook={hook} mechanical={mechanical}"
    )

    start, end = hook[0], min(mechanical)
    escalations = [ln for ln in all_continues if start < ln < end]
    assert escalations == [], (
        f"a `continue` at {escalations} sits between the loop gate (line "
        f"{start}) and the mechanical gate (line {end}), so a role violation "
        "escalates to the next cascade rung. The next rung begins with "
        "_reset_worktree (orchestrator.py:1230), which discards the diff — so "
        "the blocked row would name a violation whose evidence the dispatcher "
        "deleted before any human read it"
    )
    resets = [ln for ln in _call_linenos(loop, "_reset_worktree") if start < ln < end]
    assert resets == [], (
        f"the loop gate's own region calls _reset_worktree at {resets}, which "
        "discards the very diff a Blocked row exists to preserve"
    )


def test_violation_and_could_not_check_never_share_a_reason() -> None:
    """**Row 8. Six distinct reasons, and none for a task that was not
    blocked.** GREEN TODAY — the scaffold implemented this table under the
    standing exception, and this row is its pin.

    §3: `scripts/check_body_branch.sh` already spends exit 2 on VIOLATION and
    exit 3 on UNDETERMINED, with its own comment that *"a CI job that cannot
    tell 'violation' from 'could not check' will treat one as the other"*. The
    review queue prints ``blocked_reason`` and nothing else on its first line
    (`unblock.list_blocked`), and the human's first question is which of these
    six happened — a misbehaving agent, or a broken environment.

    Three claims, and the third is the one a table-shaped implementation gets
    wrong:

      1. every BLOCKING status has a reason, and they are pairwise distinct;
      2. no PROCEEDING status has one — `blocked_reason` raises rather than
         inventing a string for a task this gate did not block;
      3. the reason table's key set is EXACTLY the blocking set, derived from
         `_DECISIONS` rather than typed out again. A ninth status that blocks
         and has no reason reddens here, instead of reaching a human as an
         empty first line.

    Distinctness is asserted as *no reason is a prefix of another*, not merely
    as inequality: ``role_diff_loop_violation`` and a hypothetical
    ``role_diff_loop_violation_2`` are unequal and would still read as the same
    thing in the place these strings are actually consumed — a queue a human
    SCANS, where `blocked_reason` is the whole first line and the tail is a
    free-text detail. **Measured under `06176f4` so the stronger claim is not
    made:** `unblock` clears stamps by exact key (``row.pop(stamp, None)``,
    unblock.py:130), NOT by prefix. So the prefix rule here is about the
    reader, not about a matcher — and it is a P2 ruling rather than an
    inherited one. Recorded as **dispute P2-2** for P4, with the weaker
    alternative named: plain inequality.

    FALSIFY (measured, `06176f4`): delete the CHECKED_UNDETERMINED row from
    ``_BLOCKED_REASON_PREFIXES`` — claim 3 reddens naming it. Give
    CHECKED_UNDETERMINED the violation's string — claim 1 reddens. Add
    CHECKED_CLEAN to the table — claim 2 reddens.
    """
    blocking = {s for s, d in _DECISIONS.items() if d is LoopGateDecision.BLOCK}
    proceeding = {s for s, d in _DECISIONS.items() if d is LoopGateDecision.PROCEED}
    assert blocking and proceeding, "the decision table has collapsed to one value"

    assert set(_BLOCKED_REASON_PREFIXES) == blocking, (
        "the blocked_reason table is not exactly the blocking statuses. Only "
        f"in the table: {sorted(s.name for s in set(_BLOCKED_REASON_PREFIXES) - blocking)}; "
        f"blocking with no reason: {sorted(s.name for s in blocking - set(_BLOCKED_REASON_PREFIXES))}"
    )

    reasons = {s: blocked_reason(s) for s in sorted(blocking, key=lambda s: s.name)}
    for status, text in reasons.items():
        others = [t for s, t in reasons.items() if s is not status]
        assert not any(t.startswith(text) or text.startswith(t) for t in others), (
            f"{status.name}'s reason {text!r} shares a prefix with another "
            "status's. The review queue prints this line and nothing else, and "
            "a prefix collision makes 'misbehaving agent' and 'broken "
            "environment' the same first line"
        )

    assert blocked_reason(LoopGateStatus.CHECKED_VIOLATION) != blocked_reason(
        LoopGateStatus.CHECKED_UNDETERMINED
    )

    for status in sorted(proceeding, key=lambda s: s.name):
        with pytest.raises(LoopGateError):
            blocked_reason(status)

    detailed = blocked_reason(LoopGateStatus.CHECKED_VIOLATION, "tests/test_u.py")
    assert detailed.startswith(blocked_reason(LoopGateStatus.CHECKED_VIOLATION))
    assert "tests/test_u.py" in detailed


def test_unblock_clears_the_loop_gate_stamps_so_the_retry_re_runs_the_gate() -> None:
    """**Row 9. Unblocking grants a retry, not a waiver — and today it grants a
    waiver.** RED TODAY, and it is §7(c)'s owed P3 edit.

    §2's whole justification for Blocked rather than failed is `unblock`'s
    behaviour: it flips Blocked → To Do, clears the previous attempt's gate
    stamps, and its own closing line says *"All gates re-run: unblocking grants
    a retry, not a waiver"*. That sentence is only true of a stamp that is in
    `_STALE_STAMPS`.

    MEASURED under `06176f4`: `unblock._STALE_STAMPS` (unblock.py:44) lists
    nine keys and neither of `ROW_STAMPS`. So an unblocked row would carry a
    stale ``role_diff_loop`` into its re-run — the exact contradiction that
    list exists to prevent ("so a To Do row doesn't carry contradictory
    'failed' stamps into its re-run").

    THE CONTROL, in this same call: an established gate stamp —
    ``mechanical_verification`` and its ``_detail`` sibling — IS in the list.
    Without it, this row would be satisfied by an ``unblock`` whose list had
    been emptied, and would read as "nothing is stale" rather than "our stamps
    are cleared".

    RED TODAY, measured: ``role_diff_loop`` and ``role_diff_loop_detail`` are
    both absent.
    GREEN WHEN: P3 adds `loop_gate.ROW_STAMPS` to `unblock._STALE_STAMPS`.
    `unblock.py` matches no `FLOOR_GLOBS` entry (measured), so this is a P3
    edit and not a P4 amendment.
    FALSIFY: remove either stamp from the list — this row names the missing
    one.

    Depends on the P4 floor commit: NO.
    """
    stale = set(unblock_mod._STALE_STAMPS)
    assert {"mechanical_verification", "mechanical_verification_detail"} <= stale, (
        "the control failed: unblock._STALE_STAMPS no longer clears the "
        "mechanical gate's stamps either, so this row is asserting against an "
        f"emptied list rather than a populated one: {sorted(stale)}"
    )
    missing = sorted(set(ROW_STAMPS) - stale)
    assert missing == [], (
        f"unblock does not clear {missing}. `dispatcher unblock` prints 'All "
        "gates re-run: unblocking grants a retry, not a waiver', and for this "
        "gate that sentence is false: the To Do row carries the previous "
        "attempt's role_diff_loop verdict into a run that has not re-checked "
        f"it. Cleared today: {sorted(stale)}"
    )


# --------------------------------------------------------------------------- #
# §4 — THE EIGHT STATUSES, NONE READING AS A PASS
# --------------------------------------------------------------------------- #


def test_the_decision_table_is_exactly_the_status_enum_and_is_a_member_lookup(
) -> None:
    """**Row 10. Totality by set equality, and the D7 defect probed rather than
    assumed.** GREEN TODAY.

    D7 implemented its verdict tables precisely so that a seal author would not
    seal a vacuous stub — and then shipped a real defect, because ``x in
    SomeEnum`` is a VALUE lookup on Python 3.12+ and both guards returned the
    permissive answer for the two inputs that had to refuse. The scaffold names
    that defect and tells P2 to use set equality. **This row does not take the
    scaffold's word for it.**

    RE-DERIVED under `06176f4` on Python 3.13.7, not read off a docstring:

      * ``"checked_clean" in LoopGateStatus`` is ``True`` — the trap is live on
        this interpreter, so a guard written with ``in`` would be wrong here
        and not merely wrong in principle;
      * `loop_gate.py` contains no ``in``-against-an-enum-class at all;
      * ``decision_for("checked_clean")`` — the enum's VALUE, the input D7's
        guard let through — raises `LoopGateError`.

    The third bullet is asserted below and is what keeps the finding in the
    suite: if a later hand rewrites `decision_for` as a membership test, the
    value probe stops raising and this row reddens.

    Claim 2 is the asymmetry §2 and §3 rule, as data: EXACTLY TWO statuses
    proceed, and they are NOT_ENABLED and CHECKED_CLEAN. Every "I could not
    check" state blocks. A new member that lands in the permissive column
    reddens here.

    FALSIFY (measured, `06176f4`): delete any row from ``_DECISIONS`` — claim 1
    reddens naming it. Flip CHECKED_UNDETERMINED to PROCEED — claim 2 reddens.
    Rewrite `decision_for` as ``if status in LoopGateStatus: return
    _DECISIONS.get(status, PROCEED)`` — the value probe stops raising, which is
    D7's defect arriving in this module.
    """
    assert set(_DECISIONS) == set(LoopGateStatus), (
        "the decision table is not total over LoopGateStatus. Unmapped: "
        f"{sorted(s.name for s in set(LoopGateStatus) - set(_DECISIONS))}; "
        f"stale: {sorted(getattr(s, 'name', s) for s in set(_DECISIONS) - set(LoopGateStatus))}"
    )
    # 8 -> 9 (P4 ruling on dispute P3-1, 2026-08-12). This bound is a tripwire
    # requiring a ruling, not a prohibition, and its own message says so: "a
    # member added without a ruling gets whichever decision the table happened
    # to give it". `RULE_UNRESOLVED` arrives WITH its ruling (reasoned on the
    # member itself), with its `_DECISIONS` row, with its
    # `_BLOCKED_REASON_PREFIXES` row, and in `_COULD_NOT_CHECK` above — so the
    # three things this bound exists to force all happened before it moved.
    # It is the ONLY row in this file the ruling reddens: P3 measured, and P4
    # re-derived on this tree, that dropping the rule-equivalence guard leaves
    # all 22 rows green, so nothing here binds to the status that refusal
    # raises. That gap is routed to P2 and is not closed by this move.
    assert len(LoopGateStatus) == 9, (
        f"LoopGateStatus has {len(LoopGateStatus)} members, not the nine the "
        "contract enumerates. A member added without a ruling gets whichever "
        "decision the table happened to give it"
    )

    proceeding = {s for s, d in _DECISIONS.items() if d is LoopGateDecision.PROCEED}
    assert proceeding == {
        LoopGateStatus.NOT_ENABLED, LoopGateStatus.CHECKED_CLEAN
    }, (
        f"exactly two statuses may proceed and they are NOT_ENABLED and "
        f"CHECKED_CLEAN; this table proceeds on "
        f"{sorted(s.name for s in proceeding)}"
    )
    for status in _COULD_NOT_CHECK:
        assert decision_for(status) is LoopGateDecision.BLOCK, (
            f"{status.name} means the gate could not answer the question it "
            "was asked, and it PROCEEDS. On this gate the wrong inference is "
            "always 'it passed'"
        )

    # The D7 probe: a VALUE is not a member, and the dispatch must say so.
    assert "checked_clean" in {m.value for m in LoopGateStatus}, (
        "the probe below is only meaningful if 'checked_clean' really is a "
        "LoopGateStatus VALUE; it is not, so this row proves nothing about "
        "the value/member distinction"
    )
    with pytest.raises(LoopGateError):
        decision_for("checked_clean")  # type: ignore[arg-type]


def test_the_verdict_table_is_exactly_the_verdict_enum_and_is_a_member_lookup(
) -> None:
    """**Row 11. The same two claims for `status_for_verdict`.** GREEN TODAY.

    A separate row from row 10 because the two tables fail independently and a
    combined row would let one carry the other: `_VERDICT_STATUSES` is keyed by
    `DiffVerdict`, an enum this package *has already grown members on, twice*
    (the scaffold's own note), and a fourth member must land in the raise
    rather than in a default.

    THE CONTROL, in this same call: each of the three verdicts really does map
    to a distinct status, so a table collapsed to one value fails here rather
    than passing totality.

    FALSIFY (measured, `06176f4`): delete the UNDETERMINED row — claim 1
    reddens. Map VIOLATION to CHECKED_CLEAN — the distinctness control reddens.
    ``status_for_verdict("violation")`` must raise: rewrite the dispatch as a
    value lookup and the probe stops raising.
    """
    assert set(_VERDICT_STATUSES) == set(DiffVerdict), (
        "the verdict table is not total over DiffVerdict. Unmapped: "
        f"{sorted(v.name for v in set(DiffVerdict) - set(_VERDICT_STATUSES))}"
    )
    mapped = [status_for_verdict(v) for v in DiffVerdict]
    assert len(set(mapped)) == len(mapped), (
        f"two DiffVerdict members share a LoopGateStatus: {mapped}. CLEAN and "
        "VIOLATION collapsing is a gate that reports one as the other"
    )
    assert status_for_verdict(DiffVerdict.VIOLATION) is (
        LoopGateStatus.CHECKED_VIOLATION
    )
    assert decision_for(status_for_verdict(DiffVerdict.UNDETERMINED)) is (
        LoopGateDecision.BLOCK
    ), (
        "UNDETERMINED reaches a PROCEED. §3: on the one role whose gate this "
        "is, a check that could not finish is not a pass — and the loop is the "
        "third enforcement point for that same decision"
    )

    with pytest.raises(LoopGateError):
        status_for_verdict("violation")  # type: ignore[arg-type]


def test_proceed_alone_never_means_the_branch_was_checked_and_was_clean() -> None:
    """**Row 12. Two statuses proceed, so the decision alone carries no verdict.**
    GREEN TODAY.

    `LoopGateDecision.PROCEED` is documented as "this gate does not stop the
    task", NOT "the branch is clean" — and the distinction is carried by the
    status, which is why every `LoopGateOutcome` carries both. A caller that
    keeps only the decision cannot tell a checked-clean branch from a run with
    the gate switched off, and §3's default-off ruling makes the second case
    the *common* one.

    This row is the assertion form of the scaffold's warning to P2: *"A CLEAN
    from this gate must never satisfy a seal that means 'the branch is
    role-clean'."*

    FALSIFY (measured, `06176f4`): give NOT_ENABLED a third decision value, or
    map it to BLOCK — either way ``len(proceeding) == 2`` reddens and the
    ambiguity this row asserts stops existing, which is a ruling change and
    should not pass silently.
    """
    proceeding = {s for s, d in _DECISIONS.items() if d is LoopGateDecision.PROCEED}
    assert len(proceeding) == 2 and len(LoopGateDecision) == 2, (
        "PROCEED is no longer ambiguous between 'checked and clean' and 'not "
        "enabled'. That is a ruling change (§5), not a refactor"
    )
    assert LoopGateStatus.NOT_ENABLED in proceeding
    assert LoopGateStatus.CHECKED_CLEAN in proceeding


def test_not_enabled_is_a_named_state_over_a_branch_that_really_is_violating(
    tmp_path: Path,
) -> None:
    """**Row 13. The opt-in flag, tested against a world where it matters.**

    The third vacuity shape measured on this codebase is *a fixture whose flag
    named a world and built another*. A NOT_ENABLED row over a CLEAN branch is
    exactly that: it is satisfied identically by a gate that honours the flag
    and by a gate that ignores it and happened to find nothing. So this row
    turns the flag off over a branch that is **provably violating** — proved by
    the same fixture, in the same call, with the flag on.

    §3 rules the gate opt-in because UNDETERMINED is the common case on a Go
    tree (`ANALYZERS` is ``(GoReachabilityAnalyzer,)``; `branch_reachability`
    records 445 s per sweep, two sweeps per check). The ruling only works if
    NOT_ENABLED is a NAMED, journaled state rather than a silence — "a run with
    the gate off says so on every row rather than looking like a run whose
    every branch was clean".

    Four claims: the status is NOT_ENABLED and not CHECKED_CLEAN; the decision
    is PROCEED; ``result`` is ``None``, because there was no check and a
    `RoleDiffResult` attached to a check that never ran is the vacuous-seal
    shape one layer up; and ``verdict`` is ``None`` for the same reason.

    RED TODAY: the stub raises.
    GREEN WHEN: `check_after_implementer` short-circuits on ``enabled=False``.
    FALSIFY (measured, reference implementation): return
    ``LoopGateOutcome(PROCEED, CHECKED_CLEAN)`` when disabled — claim 1
    reddens while the decision claim stays green, which is precisely the "looks
    like a run whose every branch was clean" failure §3 forbids. Ignore the
    flag entirely — claim 1 reddens with CHECKED_VIOLATION, and the control
    below proves the branch really was violating.

    Depends on the P4 floor commit: NO for redness, YES for enforceability —
    ``enabled`` is a one-line edit away from being ignored, in a file BODIES
    may write today.
    """
    repo = _new_repo(tmp_path)
    _git(["checkout", "-q", "-b", "feat/N"], repo)
    pre_spawn_sha = _sha(repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_n.py").write_text(
        "def test_n():\n    pass\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(N): edits a seal"], repo)

    # The control FIRST, so the world this row names is the world it built.
    on = _gate(repo, "feat/N", pre_spawn_sha, enabled=True)
    assert on.status is LoopGateStatus.CHECKED_VIOLATION, (
        "the control failed: with the gate ON this branch must be a violation, "
        f"and it answered {on.status!r}. A NOT_ENABLED assertion over a branch "
        "that is not violating is satisfied by a gate that ignores the flag"
    )

    off = _gate(repo, "feat/N", pre_spawn_sha, enabled=False)
    assert off.status is LoopGateStatus.NOT_ENABLED, (
        f"the gate was switched off and answered {off.status!r}. "
        "CHECKED_CLEAN here makes a run with the gate off indistinguishable "
        "from a run whose every branch was clean — which is the silence §3's "
        "named state exists to prevent. CHECKED_VIOLATION means the flag was "
        "ignored"
    )
    assert off.decision is LoopGateDecision.PROCEED
    assert off.result is None, (
        "NOT_ENABLED carries a RoleDiffResult, so a check that never ran has "
        "left a record somebody will read as one"
    )
    assert off.verdict is None


def test_a_deadline_is_never_silently_ignored(tmp_path: Path) -> None:
    """**Row 14. `deadline_seconds` is in the signature and must not be a
    decoration.**

    §6 rules that exceeding a per-task deadline is a NAMED state that BLOCKS,
    and that the killable face a real deadline needs does not exist. The
    scaffold's own instruction to P3 is a disjunction and this row seals the
    disjunction rather than picking a branch of it: *"P3 either implements
    §7(e) or raises `LoopGateError` for a non-``None`` value; it may not
    silently ignore it."*

    So: with an already-expired deadline, this row accepts EITHER the refusal
    (`LoopGateError`, the honest "I cannot honour this parameter") OR
    DEADLINE_EXCEEDED (§7(e) landed). What it refuses is the third answer —
    a completed check reported as though no deadline had been asked for.

    WHY THAT THIRD ANSWER IS THE LIKELY ONE. §6 names it explicitly and rejects
    it: timing the call and reporting DEADLINE_EXCEEDED *after* it has already
    completed "measures nothing and blocks a task whose check succeeded". The
    lazier sibling — accept the parameter, never read it — is what a body
    writes when the parameter has no seal.

    THE CONTROL, judged in the same call: the same fixture with
    ``deadline_seconds=None`` reaches a verdict. Without it, a
    `check_after_implementer` that raised `LoopGateError` unconditionally would
    pass.

    RED TODAY: the stub raises `NotImplementedError`, which is neither
    permitted answer, and this row does not catch it.
    GREEN WHEN: P3 raises `LoopGateError` for a non-``None`` deadline (or
    implements §7(e)).
    FALSIFY (measured, reference implementation): accept
    ``deadline_seconds`` and drop it on the floor — the row reddens with
    CHECKED_CLEAN, naming the status it got.

    Depends on the P4 floor commit: NO.
    """
    repo = _new_repo(tmp_path)
    _git(["checkout", "-q", "-b", "feat/D"], repo)
    pre_spawn_sha = _sha(repo)
    (repo / "src").mkdir()
    (repo / "src" / "d.py").write_text("def d():\n    return 1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(D): ordinary work"], repo)

    control = _gate(repo, "feat/D", pre_spawn_sha, deadline_seconds=None)
    assert control.status is LoopGateStatus.CHECKED_CLEAN, (
        "the control failed: with no deadline this fixture must reach a "
        f"verdict, and it answered {control.status!r}. Without it, the "
        "assertion below is satisfied by a gate that refuses everything"
    )

    try:
        expired = _gate(repo, "feat/D", pre_spawn_sha, deadline_seconds=0.0)
    except LoopGateError:
        return  # the scaffold's permitted refusal: the parameter is not faked

    assert expired.status is LoopGateStatus.DEADLINE_EXCEEDED, (
        f"an already-expired deadline produced {expired.status!r}. The two "
        "answers this unit permits are a LoopGateError refusal (the killable "
        "face of §7(e) does not exist) or DEADLINE_EXCEEDED (it does). A "
        "completed check reported as if no deadline had been asked for is the "
        "parameter being decoration"
    )
    assert expired.decision is LoopGateDecision.BLOCK


def test_deadline_exceeded_is_unreachable_from_a_call_given_no_deadline(
    tmp_path: Path,
) -> None:
    """**Row 15. The named-but-unreachable state, asserted rather than
    skipped.**

    The scaffold's instruction: *"`DEADLINE_EXCEEDED` is unreachable until
    §7(e) lands. Assert that it is unreachable rather than skipping it — an
    unreachable named state that nobody asserts is how a state quietly becomes
    reachable with the wrong decision attached."*

    **WHAT I CAN SEAL, AND WHAT I CANNOT — said plainly.** I cannot assert
    "no input produces DEADLINE_EXCEEDED", because §7(e) is owed and the
    assertion would redden the moment the owed work lands — an anti-seal that
    fights its own fix. What is durable, and what this row asserts, is the
    ruling that survives §7(e): **a call that was given no deadline may never
    report one.** That is true today (nothing produces it) and must stay true
    after §7(e) (only a deadline-bearing call may).

    Driven over every status this file can construct with
    ``deadline_seconds=None``: CHECKED_CLEAN, CHECKED_VIOLATION,
    CHECKED_UNDETERMINED, ROLE_UNRESOLVED, BASE_UNRESOLVED and NOT_ENABLED —
    six of the eight. GATE_ERROR is row 16. The eighth is DEADLINE_EXCEEDED
    itself, and the honest statement is that **no seal in this file produces
    it**, because no face of `check_branch` in this package can be interrupted
    (CPython cannot interrupt a call in another thread; §6). Its decision and
    its distinct reason are pinned by rows 8 and 10, so if it does become
    reachable it arrives already refusing.

    THE CONTROL, in this same call: the six drives really do produce six
    distinct statuses, so a gate stuck on one answer fails here rather than
    passing an "is not DEADLINE_EXCEEDED" sweep trivially.

    RED TODAY: the stub raises.
    GREEN WHEN: `check_after_implementer` is implemented.
    FALSIFY (measured, reference implementation): report DEADLINE_EXCEEDED by
    timing the call and comparing against a default deadline invented when
    none was given — the exact shape §6 rejects. Measured: **10 of 22 red**,
    this row among them. The wide blast radius is the honest result and is
    reported rather than trimmed: a gate that blocks on an invented deadline
    breaks every behavioural row at once, and this row is the one whose
    message names the reason instead of reporting an unexpected status.

    Depends on the P4 floor commit: NO.
    """
    repo = _new_repo(tmp_path)
    pre_spawn_sha = _well_formed_unit(repo)
    (repo / "src").mkdir()
    (repo / "src" / "u.py").write_text("def u():\n    return 1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(U): implement"], repo)

    empty_diff_sha = _sha(repo)
    mixed = [_spec("A-BODIES", Role.BODIES), _spec("B-SCAFFOLD", Role.SCAFFOLD)]

    drives = {
        "clean": _gate(repo, "feat/U-bodies", pre_spawn_sha),
        "empty diff": _gate(repo, "feat/U-bodies", empty_diff_sha),
        "role unresolved": _gate(repo, "feat/U-bodies", pre_spawn_sha, specs=mixed),
        "base unresolved": _gate(repo, "feat/U-bodies", None),
        "not enabled": _gate(repo, "feat/U-bodies", pre_spawn_sha, enabled=False),
    }
    (repo / "tests" / "test_u.py").write_text(
        "def test_u():\n    assert True\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(U): edits a seal"], repo)
    drives["violation"] = _gate(repo, "feat/U-bodies", pre_spawn_sha)

    statuses = {name: out.status for name, out in drives.items()}
    assert len(set(statuses.values())) == len(statuses), (
        "the control failed: six different worlds produced fewer than six "
        f"statuses, so the sweep below proves nothing: {statuses}"
    )
    for name, status in statuses.items():
        assert status is not LoopGateStatus.DEADLINE_EXCEEDED, (
            f"the {name!r} drive was given deadline_seconds=None and reported "
            "DEADLINE_EXCEEDED. A deadline nobody asked for is a gate that "
            "blocks a task whose check succeeded (§6)"
        )


def test_an_unreadable_policy_on_the_base_is_a_gate_error_and_not_a_pass(
    tmp_path: Path,
) -> None:
    """**Row 16. GATE_ERROR, driven, so seven of the eight statuses are
    behavioural rather than table-only.**

    GATE_ERROR is documented as covering "the loop's own resolution step and
    nothing else", because `check_branch` never raises — every failure of its
    own arrives as UNDETERMINED. The loop's resolution step has exactly one
    raising call in it: `load_role_policy_from_base(repo_root, base_branch)`,
    §4's policy ruling, which the scaffold specifies as step 3 of
    `resolve_inputs`.

    HOW PRODUCTION PRODUCES THIS INPUT. Measured under `06176f4`:
    `load_role_policy_from_base` raises `repo_config.RepoConfigError` on a
    malformed ``.dispatcher.yaml`` at the base — "there is deliberately no
    fallback to the head copy and none to the defaults". A base branch with a
    broken config is not hypothetical: it is one bad merge on `main`, and every
    task in the run hits it.

    THE DISTINCTION THIS ROW DEFENDS, measured: `check_branch` handed that same
    broken base as ``base_ref`` answers **UNDETERMINED** — so a P3 that let the
    resolution failure fall through to `check_branch` would produce
    CHECKED_UNDETERMINED, which BLOCKS and therefore looks fine. It is not
    fine: §3's ``role_diff_loop_undetermined`` tells the human "read the detail
    — the check could not finish on this branch", and the truth is "fix
    ``.dispatcher.yaml`` on ``main``, and every other task is blocked too".
    Two different human actions behind one reason is exactly what the six
    distinct prefixes exist to prevent.

    THE CONTROL, judged in the same call: with a readable ``.dispatcher.yaml``
    on the base, the identical branch reaches a verdict.

    RED TODAY: the stub raises.
    GREEN WHEN: `check_after_implementer` catches the resolution failure and
    reports GATE_ERROR.
    FALSIFY (measured, reference implementation): let the resolution failure
    reach `check_branch` as an unset policy — this row reddens with
    CHECKED_UNDETERMINED, and every other row in this file stays green.

    Depends on the P4 floor commit: NO.
    """
    repo = _new_repo(tmp_path)
    (repo / ".dispatcher.yaml").write_text(
        "roles:\n  bodies:\n   - [unclosed\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base: .dispatcher.yaml is malformed"], repo)
    _git(["checkout", "-q", "-b", "feat/G"], repo)
    pre_spawn_sha = _sha(repo)
    (repo / "src").mkdir()
    (repo / "src" / "g.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "bodies(G): ordinary work"], repo)

    broken = _gate(repo, "feat/G", pre_spawn_sha)
    assert broken.status is LoopGateStatus.GATE_ERROR, (
        f"the gate answered {broken.status!r}. CHECKED_UNDETERMINED means the "
        "policy resolution failure was allowed to fall through to "
        "check_branch, so a human is told 'the check could not finish on this "
        "branch' when the truth is '.dispatcher.yaml on the base branch is "
        "malformed and every task in this run is blocked'"
    )
    assert broken.decision is LoopGateDecision.BLOCK
    assert broken.result is None, (
        "GATE_ERROR carries a RoleDiffResult, so a check that was never made "
        "has left a record"
    )

    # The control: repair the base, and the identical branch reaches a verdict.
    _git(["checkout", "-q", "main"], repo)
    (repo / ".dispatcher.yaml").write_text("roles: {}\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base: repair the config"], repo)

    repaired = _gate(repo, "feat/G", pre_spawn_sha)
    assert repaired.status is LoopGateStatus.CHECKED_CLEAN, (
        "the control failed: with a readable base config the same branch must "
        f"reach a verdict, and it answered {repaired.status!r}. Without it, "
        "the assertion above is satisfied by a gate that answers GATE_ERROR "
        "for everything"
    )


# --------------------------------------------------------------------------- #
# §5 — MIXED-ROLE BATCHES
# --------------------------------------------------------------------------- #


def test_the_gate_never_picks_a_role_for_a_two_role_branch(tmp_path: Path) -> None:
    """**Row 17. `sole_role` returns ``None`` and the gate refuses rather than
    choosing.**

    §4: a batch group shares ONE worktree, ONE branch and ONE implementer
    session, and `check_branch` takes exactly one role. Picking the primary's
    role would judge unit B's scaffold work under unit A's BODIES rule, and the
    two rules deny different things — so the answer would be wrong in both
    directions on the same branch.

    HOW PRODUCTION PRODUCES THIS INPUT: row 18, which drives the real loader
    and the real `_take_batch_group`.

    Four claims:

      1. `sole_role` over a two-role group is ``None`` (green today — the
         scaffold implemented it under the standing exception);
      2. `sole_role` over an ordinary single-role batch RESOLVES. This is the
         half the scaffold names as the one a raising stub satisfies
         vacuously, and it is here so claim 1 cannot be met by refusing
         everything;
      3. the gate answers ROLE_UNRESOLVED and BLOCKS;
      4. it does **not** answer with either role's verdict. Asserted
         positively: the identical branch, judged as BODIES alone, is
         CHECKED_VIOLATION, and judged as SCAFFOLD alone is CHECKED_CLEAN —
         measured in this same call. So "picked the primary" and "picked the
         other" are both distinguishable from the refusal, and the row cannot
         be satisfied by a coin flip.

    THE FIXTURE PATH IS ``schema/`` AND THAT IS LOAD-BEARING. Measured under
    `06176f4` from `built_in_policy`: BODIES denies ``**/schema/**`` and
    SCAFFOLD does not — the two roles' deny sets differ on exactly this
    prefix and agree on every ``tests/**`` spelling (both delegate to
    `seal_verify.is_test_path`). A first attempt at this row used a
    ``tests/**`` commit and the SCAFFOLD control came back VIOLATION too, so
    the row would have passed while proving only that both roles refuse the
    same thing — the "two implementations return the same value" shape, and
    the reason this fixture is a schema edit: it is *legitimate scaffold work*
    and *forbidden body work*, in one session, on one branch. That is what
    "wrong in both directions at once" means concretely.

    RED TODAY (claims 3 and 4): the stub raises. GREEN TODAY: claims 1 and 2.
    GREEN WHEN: `resolve_inputs` step 1 raises on ``None`` and
    `check_after_implementer` maps it to ROLE_UNRESOLVED.
    FALSIFY (measured, reference implementation): ``role = specs[0].role`` —
    claim 3 reddens with CHECKED_VIOLATION (the BODIES answer). Reverse the
    group and it reddens with CHECKED_CLEAN (the SCAFFOLD answer), which is
    the worse failure and the reason claim 4 pins both.

    Depends on the P4 floor commit: NO for redness. Related to §7(b): a
    plan-time refusal of mixed-role batches is owed and floored (P4); until it
    lands, ROLE_UNRESOLVED is the only thing standing between a mixed batch and
    an unjudgeable branch, which is why this row is behavioural and not a
    table pin.
    """
    repo = _new_repo(tmp_path)
    _git(["checkout", "-q", "-b", "feat/MIX"], repo)
    pre_spawn_sha = _sha(repo)
    (repo / "schema").mkdir()
    (repo / "schema" / "b.sql").write_text(
        "create table b (id int);\n", encoding="utf-8"
    )
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "batch MIX: one session, two units"], repo)

    bodies = _spec("A-BODIES", Role.BODIES)
    scaffold = _spec("B-SCAFFOLD", Role.SCAFFOLD)

    assert sole_role([bodies, scaffold]) is None
    assert sole_role([scaffold, bodies]) is None, (
        "sole_role is order-sensitive: it resolved one ordering of the same "
        "two roles. A branch's role cannot depend on which row the dispatcher "
        "happened to put first"
    )
    assert sole_role([bodies, _spec("A-BODIES-2", Role.BODIES)]) is Role.BODIES, (
        "the control failed: an ORDINARY batch — two rows, one role — must "
        "resolve. A sole_role that refused everything would satisfy the two "
        "assertions above vacuously, which is the half the scaffold names"
    )

    as_bodies = _gate(repo, "feat/MIX", pre_spawn_sha, specs=[bodies])
    as_scaffold = _gate(repo, "feat/MIX", pre_spawn_sha, specs=[scaffold])
    assert as_bodies.status is LoopGateStatus.CHECKED_VIOLATION, (
        "the control failed: this branch must be a VIOLATION under BODIES "
        f"(it commits schema/**, which BODIES denies), and it answered "
        f"{as_bodies.status!r}"
    )
    assert as_scaffold.status is LoopGateStatus.CHECKED_CLEAN, (
        "the control failed: this branch must be CLEAN under SCAFFOLD, and it "
        f"answered {as_scaffold.status!r}. Without both controls, 'the gate "
        "did not pick a role' is indistinguishable from 'the two roles agreed'"
    )

    mixed = _gate(repo, "feat/MIX", pre_spawn_sha, specs=[bodies, scaffold])
    assert mixed.status is LoopGateStatus.ROLE_UNRESOLVED, (
        f"the gate answered {mixed.status!r} for a branch carrying two roles. "
        "CHECKED_VIOLATION means it picked BODIES and blamed unit B's scaffold "
        "author for legitimate schema work; CHECKED_CLEAN means it picked "
        "SCAFFOLD and just granted unit A's body author the schema directory"
    )
    assert mixed.decision is LoopGateDecision.BLOCK
    assert mixed.result is None

    reversed_out = _gate(repo, "feat/MIX", pre_spawn_sha, specs=[scaffold, bodies])
    assert reversed_out.status is LoopGateStatus.ROLE_UNRESOLVED


def test_todays_dispatcher_really_does_hand_one_branch_two_roles() -> None:
    """**Row 18. The reachability proof for row 17's input.** GREEN TODAY.

    Row 17 asserts what the gate does with a two-role group. This row is how I
    know the dispatcher can hand it one — the scaffold's §4 measurement,
    re-derived here rather than quoted, through the REAL loader, the REAL
    validator and the REAL `_take_batch_group`.

    MEASURED under `06176f4`, on the worklist below (unit A complete and Done
    through SEALS, unit B complete and untouched, A's BODIES row and B's
    SCAFFOLD row sharing ``batch_id: MIX``):

        plan.load_tasks           -> accepted
        role_protocol.validate    -> 0 errors, 0 warnings
        plan.runnable_now         -> ['A-BODIES', 'B-SCAFFOLD']
        _take_batch_group         -> group ['A-BODIES', 'B-SCAFFOLD'], rest []
        roles in that one group   -> {BODIES, SCAFFOLD}

    One branch, one worktree, one implementer session, two roles — with the
    worklist passing every plan-time check the protocol has today.

    **THIS ROW IS THE ONE §7(b) WILL REDDEN, and that is intended.** §7(b) owes
    a plan-time refusal of mixed-role batches in `role_protocol.validate`, a
    floored file and therefore a P4 amendment. When it lands, `load_tasks`
    raises here and this row must be amended in that same commit — its redness
    is §7(b)'s own proof that the refusal works. Recorded so that a later
    reader does not mistake the amendment for a seal being weakened.
    Predicted (unmeasured) under a tree where §7(b) has landed: this row fails
    at `plan.load_tasks` with a `ValidationError` naming ``batch_id: MIX``.

    FALSIFY (measured, `06176f4`): give both rows the same role — the
    two-distinct-roles assertion reddens. Give them different ``batch_id``s —
    the one-group assertion reddens with two singletons.
    """
    doc = {"tasks": [
        {"key": "A-SCAFFOLD", "summary": "a scaffold", "description": "d",
         "type": "task", "labels": ["size:S"], "role": "scaffold",
         "status": "Done"},
        {"key": "A-SEALS", "summary": "a seals", "description": "d",
         "type": "task", "labels": ["size:S"], "role": "seals",
         "blockedBy": ["A-SCAFFOLD"], "status": "Done"},
        {"key": "A-BODIES", "summary": "a bodies", "description": "d",
         "type": "task", "labels": ["size:S"], "role": "bodies",
         "blockedBy": ["A-SEALS"], "status": "To Do", "batch_id": "MIX"},
        {"key": "B-SCAFFOLD", "summary": "b scaffold", "description": "d",
         "type": "task", "labels": ["size:S"], "role": "scaffold",
         "status": "To Do", "batch_id": "MIX"},
        {"key": "B-SEALS", "summary": "b seals", "description": "d",
         "type": "task", "labels": ["size:S"], "role": "seals",
         "blockedBy": ["B-SCAFFOLD"], "status": "To Do"},
        {"key": "B-BODIES", "summary": "b bodies", "description": "d",
         "type": "task", "labels": ["size:S"], "role": "bodies",
         "blockedBy": ["B-SEALS"], "status": "To Do"},
    ]}

    tasks = plan_mod.load_tasks(doc)
    validation = rp_mod.validate(tasks)
    assert validation.errors == (), (
        "a mixed-role batch is refused at plan time. If §7(b) has landed, this "
        "row is the one its commit must amend — see the docstring: "
        f"{validation.errors}"
    )
    assert validation.warnings == (), (
        f"the fixture is not a clean worklist and this row is measuring "
        f"something other than the mixed-role case: {validation.warnings}"
    )

    runnable = plan_mod.runnable_now(tasks)
    assert [t.key for t in runnable] == ["A-BODIES", "B-SCAFFOLD"], (
        f"the control failed: both rows must be runnable at once for the "
        f"dispatcher to batch them: {[t.key for t in runnable]}"
    )

    group, rest = orch_mod._take_batch_group(runnable)
    assert [t.key for t in group] == ["A-BODIES", "B-SCAFFOLD"] and rest == [], (
        f"_take_batch_group did not dispatch them as one group: "
        f"group={[t.key for t in group]} rest={[t.key for t in rest]}"
    )

    specs = {s.task_key: s for s in validation.specs}
    group_specs = [specs[t.key] for t in group]
    assert {s.role for s in group_specs} == {Role.BODIES, Role.SCAFFOLD}, (
        f"the group carries {sorted(s.role.value for s in group_specs)}, not "
        "two distinct roles; row 17's input is not reachable from here"
    )
    assert sole_role(group_specs) is None, (
        "the real dispatched group resolved to a single role, so the gate "
        "would judge one unit's work under the other unit's rule"
    )


def test_zero_specs_is_not_one_role() -> None:
    """**Row 19. The empty-sequence row the scaffold asked for.** GREEN TODAY.

    *"`sole_role` deserves an empty-sequence row. Zero specs is not one role,
    and 'the batch had no rows' must not resolve to anything."* A group with no
    specs is a snapshot that lost its rows, not a legacy branch — and the
    difference matters, because `Role.LEGACY` **is** checked (`check_branch`
    rules on it: CLEAN unless a floor path was touched) and the 2026-08-07
    floor ruling turns on exactly that.

    So this row pins both halves: empty resolves to nothing, and a group of
    role-less rows resolves to LEGACY and is therefore checked. The second half
    is the one a "falsy means skip" implementation gets wrong — ``if not
    specs`` and ``if not role`` are one keystroke apart, and `Role.LEGACY` is
    truthy today only because enum members are.

    FALSIFY (measured, `06176f4`): ``if len(roles) > 1: return None`` — the
    empty case then raises `KeyError` on ``roles.pop()`` rather than returning
    ``None``, which is a different failure and reddens here. Map LEGACY to
    ``None`` — the second assertion reddens, and that mutation would rebuild
    the "a floor LEGACY escapes is bypassed by deleting one line" bypass inside
    the loop.
    """
    assert sole_role([]) is None, (
        "an empty group resolved to a role. Zero rows is not one role, and a "
        "snapshot that lost its rows must not be judged as anything"
    )
    legacy = [_spec("OLD-1", Role.LEGACY), _spec("OLD-2", Role.LEGACY)]
    assert sole_role(legacy) is Role.LEGACY, (
        "a group of role-less rows resolved to None instead of LEGACY, so the "
        "gate would skip the call. check_branch RULES on LEGACY — CLEAN unless "
        "a floor path was touched — and skipping it rebuilds the bypass the "
        "2026-08-07 floor ruling closed"
    )
    assert sole_role([_spec("A", Role.BODIES), _spec("B", Role.LEGACY)]) is None


# --------------------------------------------------------------------------- #
# §6 — THE STAMP, AND INVARIANT 1
# --------------------------------------------------------------------------- #


def test_the_stamp_is_the_loop_stamp_and_never_the_pr_time_verdict() -> None:
    """**Row 20. `role_diff_loop`, never `role_diff`.** GREEN TODAY.

    §5 rules that loop time and PR time are not the same check, that they CAN
    disagree, and that PR time wins — it judges the diff that will actually
    land, reads its policy and its ADJUDICATE writable set out of the protected
    base, and re-reads the gate's own code from the base when the checkout
    supplies it. The loop has none of those three properties.

    Loop-CLEAN / PR-VIOLATION is not an edge case; §5 calls it *"expected and
    routine"*, because four spawns commit to this branch after the hook
    (`_retry_for_test_fix`, `_spawn_verifier_iterate`, `_spawn_panel_iterate`,
    and the commit retry) and the dependency merge predates it. So a row
    asserting the loop writes ``role_diff`` would let the loop's verdict
    masquerade as the PR-time one on every branch where they disagree — which
    is most of them.

    Three claims:

      1. `ROW_STAMPS` is exactly the two loop-stamped keys;
      2. no stamp is the bare PR-time name, and none is a PREFIX of it or
        prefixed BY it in a way a prefix-matching consumer would collapse;
      3. every `blocked_reason` prefix is loop-stamped too — the reason string
        is what the review queue prints, and a reason reading
        ``role_diff_violation`` is a reason somebody will treat as the verdict.

    FALSIFY (measured, `06176f4`): rename ``ROW_STAMPS[0]`` to ``role_diff`` —
    claims 1 and 2 redden. Change one prefix to ``role_diff_violation`` —
    claim 3 reddens naming it.
    """
    assert ROW_STAMPS == ("role_diff_loop", "role_diff_loop_detail")
    for stamp in ROW_STAMPS:
        assert stamp != "role_diff", (
            "the loop gate writes the PR-time stamp. §5: a loop CLEAN is not a "
            "waiver for anything, and a stamp that reads like the verdict is a "
            "stamp somebody will treat as one"
        )
        assert stamp.startswith("role_diff_loop"), (
            f"{stamp!r} is not loop-stamped, so a consumer matching on "
            "'role_diff' cannot tell which of the two checks wrote it"
        )
    for status, prefix in _BLOCKED_REASON_PREFIXES.items():
        assert prefix.startswith("role_diff_loop_"), (
            f"{status.name}'s blocked_reason is {prefix!r}, which the review "
            "queue prints as though it were the PR-time verdict"
        )


def test_the_wired_orchestrator_writes_the_loop_stamp_and_not_the_pr_one() -> None:
    """**Row 21. The stamp ruling reaching the row.** RED TODAY.

    Row 20 pins the constant; a constant nothing writes is the "correct,
    complete, and not invoked" shape this whole lineage has been chasing. This
    row asserts the orchestrator actually uses it, and that it never writes the
    bare PR-time key.

    THE LENS CONTROL, in this same call: an established gate stamp —
    ``mechanical_verification`` — IS present as a literal in
    `orchestrator.py`. Measured under `06176f4`. Without it, a reader pointed
    at the wrong file would pass the negative claim and fail only the positive
    one, and the message would blame the wrong thing.

    MEASURED under `06176f4`: neither ``ROW_STAMPS`` nor ``role_diff_loop``
    nor a bare ``"role_diff"`` literal occurs anywhere in `orchestrator.py`.
    So the negative claim is green today for the trivial reason and the
    positive one is red — which is exactly the state before wiring.

    THE POSITIVE CLAIM IS THE CONSTANT, NOT THE STRING, and that is a ruling
    this row makes rather than inherits — recorded as **dispute P2-1** for P4.
    `ROW_STAMPS`'s own docstring says the keys are *"named HERE rather than at
    the write site, because `unblock._STALE_STAMPS` must clear them"*, and two
    places spelling one key is invariant 5's failure mode: a rename would
    clear one and write the other, and the suite would stay green because each
    half is internally consistent. Measured while writing this row: a
    reference orchestrator that wrote the key as a bare local variable name
    satisfied a substring test for ``role_diff_loop`` without referencing the
    constant at all — which is why the substring test is not what is asserted.

    RED TODAY. GREEN WHEN: P3 stamps the row via `loop_gate.ROW_STAMPS`.
    FALSIFY (measured, reference implementation): stamp the row with the
    literal ``"role_diff"`` — the negative claim reddens. Re-spell the keys as
    orchestrator-local literals — the positive claim reddens, which is the
    point: `ROW_STAMPS` exists so `unblock._STALE_STAMPS` (row 9) has exactly
    one name to clear.

    Depends on the P4 floor commit: NO for redness, YES for enforceability of
    `orchestrator.py` itself.
    """
    source = _orchestrator_source()
    assert "mechanical_verification" in source, (
        "the control failed: orchestrator.py does not even contain the "
        "mechanical gate's stamp, so this reader is not looking at the "
        "orchestrator and both claims below are about the wrong file"
    )
    assert '"role_diff"' not in source and "'role_diff'" not in source, (
        "orchestrator.py writes the bare PR-time stamp. §5: PR time judges "
        "what lands and reads its policy and its own code from the protected "
        "base; the loop has none of those properties and must not sign its "
        "answer with the other check's name"
    )
    assert "ROW_STAMPS" in source, (
        f"orchestrator.py never references loop_gate.ROW_STAMPS, so the row "
        f"the gate blocks either carries no record of which gate did it, or "
        f"carries one spelled a second time here. Two spellings of "
        f"{ROW_STAMPS!r} is invariant 5: a rename clears one key and writes "
        "the other, and unblock._STALE_STAMPS (row 9) stays green while "
        "clearing nothing"
    )


def test_the_loop_reaches_the_same_check_branch_the_pr_gate_reaches() -> None:
    """**Row 22. Invariant 1: one callable, so the three enforcement points
    cannot disagree about a RULE.** RED TODAY.

    `check_branch`'s own contract names its callers: *"`scripts/
    check_body_branch.sh` (PR time and CI) and the orchestrator's task loop …
    One callable, so a PR-time pass and a task-loop pass can never disagree."*
    §5 rules that the two checks may disagree about a BRANCH — different base,
    different diff, differently-sourced policy — and that is fine and expected.
    What they may never disagree about is the rule, and the only mechanism for
    that is being the same function.

    This is a static claim about `loop_gate.py`, deliberately: the behavioural
    rows above would all stay green against a `check_after_implementer` that
    reimplemented the path check itself and happened to agree on these
    fixtures. That is the "two implementations return the same value" vacuity
    shape at module scale, and the fixtures in this file are exactly the ones a
    reimplementation would be written to satisfy.

    IT IS A CLOSURE WALK, NOT A DIRECT-CALL TEST, and that is deliberate. The
    walk seeds at `check_after_implementer` and follows calls to functions
    defined in `loop_gate.py` itself, the shape
    `tests/test_floor_closure.py::_delegation_closure` uses. Measured while
    writing this row: a direct-call assertion reddens when P3 factors the call
    into a private helper — behaviourally identical code, a false refusal with
    no override, and exactly the kind of seal that gets waived once and then
    always. The closure tolerates the helper and still catches the
    reimplementation.

    THE LENS CONTROL, in this same call: the walk must reach at least one
    in-module function before it may conclude anything about what is missing.

    Two claims: the closure reaches `check_branch`, and it reaches
    `resolve_inputs` — the second because §4's whole ruling about WHICH ref
    goes in WHICH slot lives in `resolve_inputs`, and a
    `check_after_implementer` that assembled its own arguments inline would be
    a second place those rulings are spelled.

    RED TODAY: `check_after_implementer` is a stub whose body is one `raise`,
    so the control fails first and says so.
    GREEN WHEN: P3 implements the docstring's four steps.
    FALSIFY (measured, reference implementation): move the `check_branch` call
    into a module-private helper that `check_after_implementer` calls — this
    row stays GREEN, which is the false-refusal it was rewritten to avoid.
    Replace the call with an inline path comparison built from
    `changed_paths_between` + `evaluate_changed_paths` that agrees with
    `check_branch` on every fixture in this file — this row reddens **alone**,
    21 of 22 green. That measurement is the row's whole justification, and it
    is uncomfortable rather than reassuring: every behavioural row in this file
    is satisfied by a second implementation of the gate, because the fixtures
    here are the fixtures such an implementation would be written against.
    This is the only row that sees it.

    Depends on the P4 floor commit: NO.
    """
    source = (_PKG_ROOT / "loop_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="loop_gate.py")
    functions = {
        n.name: n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def _callees(node: ast.AST) -> set[str]:
        out = set()
        for m in ast.walk(node):
            if isinstance(m, ast.Call):
                f = m.func
                name = (
                    f.id if isinstance(f, ast.Name)
                    else f.attr if isinstance(f, ast.Attribute)
                    else None
                )
                if name:
                    out.add(name)
        return out

    seen: set[str] = set()
    frontier = ["check_after_implementer"]
    reached: set[str] = set()
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        node = functions.get(current)
        if node is None:
            continue
        for name in _callees(node):
            reached.add(name)
            if name in functions:
                frontier.append(name)

    assert reached & set(functions), (
        "the walk seeded at check_after_implementer reaches no function "
        "defined in loop_gate.py at all — it is still the scaffold's single "
        f"`raise NotImplementedError`. Reached: {sorted(reached)}"
    )
    assert "check_branch" in reached, (
        "nothing on the path out of check_after_implementer calls "
        "role_protocol.check_branch. Invariant 1: the PR gate, CI and the task "
        "loop must reach ONE callable, or the three enforcement points can "
        "disagree about the RULE and not merely about the branch. Reached: "
        f"{sorted(reached)}"
    )
    assert "resolve_inputs" in reached, (
        "check_after_implementer assembles its own check_branch arguments "
        "instead of calling resolve_inputs, so §4's rulings about which ref "
        f"goes in which slot are spelled in two places: {sorted(reached)}"
    )
