"""D1 wiring seals (P2, second pass): the call sites, not the pure functions.

Why this file exists, stated plainly, because the reason is the whole design:
`role_protocol` is a library, and a five-seat panel returned REJECT on both D1
slices with twelve findings saying one thing — **it has almost no production
call sites**. `grep -rn role_protocol src/claude_dispatcher/plan.py
src/claude_dispatcher/orchestrator.py` returns nothing. The module's own
docstring says otherwise ("Wired by P3 — each claim here has its call site"),
and that sentence is false for three of its five entries.

The seal-level cause is visible in the existing D1 seals and is not a fault in
their authors: **every one of them binds to the pure function.** A seal that
calls `validate()` itself can never notice that nothing else does, and 4,645
lines of them stayed green while the protocol was enforced by a human reading
diffs. So no seal in this file may call the pure function it is about. Each one
goes through the production entry point — `plan.load_tasks`,
`plan.runnable_now`, `role_protocol.main` — and fails *because the wiring is
absent*, not because a helper misbehaves.

What is sealed here, and what "red" means for each:

  1. `plan.load_tasks` refuses a worklist `role_protocol.validate` rejects.
     Red because `load_tasks` never calls `validate`.
  2. A NARROWING `immutable_paths:` override is refused at plan time — through
     `load_tasks`, never by calling `validate_override` directly. Red twice
     over: `load_tasks` does not call `validate`, and `validate` does not call
     `validate_override`, so the one narrowing the module claims to refuse at
     plan time is accepted today.
  3. `plan.runnable_now` consults `dispatch_satisfied_statuses`. Red because it
     reads its module-level `_DISPATCH_SATISFIED_*` sets instead, so a bodies
     task dispatches against an open, unreviewed seals PR — the seals→bodies
     `{Merged}` narrowing (2026-08-04 P2 ruling) is never consulted, and that
     narrowing is the entire point of phase ordering.
  4. `role_protocol.main` builds and applies a `TaskRoleSpec`. Red because it
     passes none, so the CI script can never clear an `adjudicate` branch (no
     writable set ⇒ UNDETERMINED) and never applies a per-task
     `immutable_paths:` addition.
  5. The "Wired by P3" claim itself is checked mechanically, so the docstring
     cannot drift back into a lie.

Three GUARD rows are green today and say so in their own docstrings. They are
here because the cheapest wiring that satisfies a seal above is a wrong one —
"reject every `immutable_paths:`", "narrow every edge to {Merged}" — and a
guard is what makes the cheap version fail. They are not seals; they must be
green before and after.

Fixture note: every row is built through `yaml_io.loads` and `plan.load_tasks`
rather than by constructing `plan.Task` by hand, because `Task.raw` IS the
interface `role_protocol` reads roles off (P1 deliberately added no `role`
field), and a hand-built `raw` is a fixture that cannot notice a loader that
stopped passing the row through.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import plan as plan_mod
from claude_dispatcher import role_protocol, yaml_io
from claude_dispatcher.role_protocol import (
    DiffVerdict,
    ExitCode,
    Role,
    RoleDiffResult,
    TaskRoleSpec,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
PKG_ROOT = SRC_ROOT / "claude_dispatcher"


# --------------------------------------------------------------------------- #
# Worklist fixtures — YAML text, loaded the way production loads it
# --------------------------------------------------------------------------- #


def _row(
    key: str,
    *,
    role: str | None = None,
    blocked_by: tuple[str, ...] = (),
    status: str | None = None,
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
    if status is not None:
        lines.append(f'    status: "{status}"')
    lines.extend(f"    {line}" for line in extra)
    return "\n".join(lines) + "\n"


def _worklist(*rows: str) -> object:
    return yaml_io.loads("project: T\nepic: D1\ntasks:\n" + "".join(rows))


def _legal_unit(
    *,
    seals_extra: tuple[str, ...] = (),
    bodies_extra: tuple[str, ...] = (),
    scaffold_status: str | None = None,
    seals_status: str | None = None,
    bodies_status: str | None = None,
) -> object:
    """scaffold → seals → bodies, protocol-legal in every other respect.

    Every phase-order rule holds, so a refusal from `load_tasks` over this
    worklist can only be the one thing the caller injected.
    """
    return _worklist(
        _row("D1-1", role="scaffold", status=scaffold_status),
        _row("D1-2", role="seals", blocked_by=("D1-1",), status=seals_status,
             extra=seals_extra),
        _row("D1-3", role="bodies", blocked_by=("D1-2",), status=bodies_status,
             extra=bodies_extra),
    )


# --------------------------------------------------------------------------- #
# 1. plan.load_tasks refuses what role_protocol.validate rejects
# --------------------------------------------------------------------------- #


def test_load_tasks_refuses_a_worklist_role_validation_rejects() -> None:
    """The plan-time enforcement point, through the loader that is the only
    way a worklist enters the dispatcher.

    PO-2 is the rule chosen deliberately: a bodies task with no seals task in
    its direct `blockedBy` is legal to `plan` (the key resolves, there is no
    cycle) and illegal to the protocol. Nothing but `validate` can refuse it,
    so this row cannot pass by accident.

    Red now: `load_tasks` returns three Tasks. It never calls `validate`, so
    plan-time role validation is dead code and the worklist plans happily.
    Green when: `load_tasks` calls `role_protocol.validate` after
    `_validate_blocked_by` and raises `ValidationError` on `.errors`, before
    it returns — a worklist that fails role validation never partially plans.
    Falsify: collect the errors and print them instead of raising — the
    `pytest.raises` goes red, which is the point: a warning is not a refusal.
    """
    doc = _worklist(
        _row("D1-1", role="scaffold"),
        _row("D1-2", role="seals", blocked_by=("D1-1",)),
        # bodies hangs off the SCAFFOLD, not the seals task: no edge to gate on.
        _row("D1-3", role="bodies", blocked_by=("D1-1",)),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    assert "PO-2" in str(exc.value), (
        "the refusal must carry the rule that fired; 'invalid worklist' sends "
        "the author back to read 3,177 lines to find out which"
    )
    assert "D1-3" in str(exc.value)


def test_load_tasks_reports_every_broken_row_not_only_the_first() -> None:
    """`validate` collects errors for ALL rows rather than raising on the
    first, so one run reports every broken row. A loader that raises on the
    first error it finds throws that away and costs one round trip per row.

    Red now: no refusal at all.
    Green when: both offending keys appear in the one ValidationError.
    Falsify: raise on `validation.errors[0]` — the second key is missing and
    this goes red while the seal above stays green.
    """
    doc = _worklist(
        _row("D1-1", role="scaffold"),
        _row("D1-2", role="seals", blocked_by=("D1-1",)),
        _row("D1-3", role="bodies", blocked_by=("D1-1",)),
        _row("D1-4", role="bodies", blocked_by=("D1-1",)),
    )
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    message = str(exc.value)
    assert "D1-3" in message and "D1-4" in message


def test_a_legacy_only_worklist_still_loads_unchanged() -> None:
    """GUARD — green today, must stay green.

    Every `features/*/tasks.yaml` in this repo predates the protocol and
    carries no `role:`. LEGACY must behave exactly as today: no immutable
    paths, no ordering obligations, no refusal. This is what stops the wiring
    above from being implemented as "refuse anything unfamiliar".
    """
    doc = _worklist(
        _row("L-1"),
        _row("L-2", blocked_by=("L-1",)),
    )
    tasks = plan_mod.load_tasks(doc)
    assert [t.key for t in tasks] == ["L-1", "L-2"]


# --------------------------------------------------------------------------- #
# 2. A narrowing override is refused AT PLAN TIME, through load_tasks
# --------------------------------------------------------------------------- #


def test_a_narrowing_immutable_paths_override_is_refused_at_plan_time() -> None:
    """The one narrowing the module claims plan time refuses.

    `immutable_paths:` has no subtraction syntax, so the expressible attack is
    an entry SHAPED like a removal (`!tests/**`). `_reject_negation_shape`
    catches it — but only from `validate_override`, and nothing on the
    plan-time path calls `validate_override`. Today this worklist loads, and
    the bodies task believes it has been granted an exemption from the seals
    it is about to be judged by.

    Note what this row does NOT do: it never calls `validate_override`, and it
    never calls `validate`. Calling either is how the existing seals stayed
    green over an unwired module. The only entry point here is `load_tasks`.

    Red now: `load_tasks` accepts it — `parse_task_role_spec` takes
    `!tests/**` as a non-blank string, and the negation-shape check lives one
    unreached call away.
    Green when: `load_tasks` → `validate` → `validate_override` (against the
    built-in policy) refuses it before the worklist plans.
    Falsify: make `validate` skip specs whose override is non-empty — this
    goes red and the guard below stays green.
    """
    doc = _legal_unit(bodies_extra=('immutable_paths: ["!tests/**"]',))
    with pytest.raises(plan_mod.ValidationError) as exc:
        plan_mod.load_tasks(doc)
    message = str(exc.value)
    assert "shaped like a removal" in message, (
        "the refusal must be the narrowing rule, not some other error the "
        "fixture tripped: a message that does not name the shape leaves the "
        "author guessing, and leaves this seal unable to tell which rule fired"
    )
    assert "D1-3" in message


def test_an_additive_immutable_paths_override_still_loads() -> None:
    """GUARD — green today, must stay green.

    An override may only ADD, and adding is the legitimate, documented use of
    the field. The cheapest way to pass the seal above is "refuse any row that
    carries `immutable_paths:`"; this row is what makes that cheap version
    fail. `docs/**` is not in BODIES' default deny set, so it is a real
    addition rather than a redundant one (which would only warn).
    """
    doc = _legal_unit(bodies_extra=('immutable_paths: ["docs/**"]',))
    tasks = plan_mod.load_tasks(doc)
    assert [t.key for t in tasks] == ["D1-1", "D1-2", "D1-3"]


# --------------------------------------------------------------------------- #
# 3. plan.runnable_now consults dispatch_satisfied_statuses
# --------------------------------------------------------------------------- #


def _runnable_keys(doc: object, *, integration: str) -> list[str]:
    tasks = plan_mod.load_tasks(doc)
    return [t.key for t in plan_mod.runnable_now(tasks, integration=integration)]


def test_bodies_does_not_dispatch_against_an_unmerged_seals_pr() -> None:
    """The seals gate is a REVIEW gate, not a code-availability gate.

    `pr` mode widens "Done-or-later" to {Done, Awaiting Review, Merged}
    because an Awaiting-Review dependency's commits already exist and reach
    the dependent's worktree. `dispatch_satisfied_statuses` narrows exactly
    one edge back to {Merged} — a dependency that is a SEALS task — on the
    2026-08-04 P2 ruling's reasoning: §2a's P2 is done when the seals are
    committed RED **and reviewed**, and a seals PR can still be rejected.
    Letting bodies start against unreviewed seals rebuilds the honour system
    one level up, and the honour system is what produced 24 vacuous seals.

    The intended cost is stated in the contract and is not a defect: in `pr`
    mode a unit serialises across two PR merges.

    Red now: `runnable_now` reads `plan._DISPATCH_SATISFIED_PR` directly,
    Awaiting Review is in it, and D1-3 dispatches against an open, unreviewed
    seals PR. `dispatch_satisfied_statuses` is never consulted.
    Green when: `runnable_now` asks `dispatch_satisfied_statuses` per
    `blockedBy` edge, with the roles read off the rows.
    Falsify: consult it but ignore the dependency's role — the narrowing
    disappears and this goes red.
    """
    doc = _legal_unit(
        scaffold_status="Merged",
        seals_status="Awaiting Review",
        bodies_status="To Do",
    )
    assert "D1-3" not in _runnable_keys(doc, integration="pr")


def test_the_seals_gate_opens_once_the_seals_pr_has_landed() -> None:
    """GUARD — green today, must stay green.

    The narrowing is to {Merged}, not to "never". A wiring that blocks bodies
    behind a seals dependency unconditionally would pass the seal above and
    deadlock every unit in `pr` mode.
    """
    doc = _legal_unit(
        scaffold_status="Merged",
        seals_status="Merged",
        bodies_status="To Do",
    )
    assert "D1-3" in _runnable_keys(doc, integration="pr")


def test_the_narrowing_belongs_to_the_dependency_not_to_the_waiter() -> None:
    """The 2026-08-04 P2 ruling, widening what P1 wrote: the narrowing is keyed
    on the DEPENDENCY being a SEALS task, not on the (BODIES ← SEALS) pair.

    P1's prose left (dependency=SEALS, dependent ∈ {SCAFFOLD, SEALS,
    ADJUDICATE, LEGACY}) unstated. The property belongs to the dependency —
    seals are done when committed RED **and reviewed** — so an Awaiting-Review
    seals task has not finished its phase no matter who is waiting on it.
    Answering those pairs with the wide pr-mode set would make the gate depend
    on the waiter's role, which is not where the fact lives.

    A role-less (LEGACY) waiter is the sharpest of those pairs and the one a
    migration actually produces, so it is the one sealed here.

    Red now: the module-level pr set admits Awaiting Review for every edge.
    Green when: the edge is answered by the dependency's role.
    Falsify: key the narrowing on `dependent_role is Role.BODIES` — the seal
    above stays green and this goes red.
    """
    doc = _worklist(
        _row("D1-1", role="scaffold", status="Merged"),
        _row("D1-2", role="seals", blocked_by=("D1-1",), status="Awaiting Review"),
        _row("L-9", blocked_by=("D1-2",), status="To Do"),
    )
    assert "L-9" not in _runnable_keys(doc, integration="pr")


def test_branch_mode_and_role_less_edges_are_byte_identical_to_today() -> None:
    """GUARD — green today, must stay green.

    Two compatibility facts in one row, both of which the crude fix ("narrow
    everything to {Merged}") breaks:

      * a LEGACY → LEGACY edge in `pr` mode still dispatches on Awaiting
        Review. Every worklist in this repo is that shape.
      * `branch` mode is unchanged: Done is already terminal there, so the
        seals edge does not narrow.
    """
    legacy_doc = _worklist(
        _row("L-1", status="Awaiting Review"),
        _row("L-2", blocked_by=("L-1",), status="To Do"),
    )
    assert "L-2" in _runnable_keys(legacy_doc, integration="pr")

    branch_doc = _legal_unit(
        scaffold_status="Done",
        seals_status="Done",
        bodies_status="To Do",
    )
    assert "D1-3" in _runnable_keys(branch_doc, integration="branch")


# --------------------------------------------------------------------------- #
# 4. main builds and applies a TaskRoleSpec
# --------------------------------------------------------------------------- #
#
# THE CLI SHAPE THIS SEAL ESTABLISHES, and why P2 had to choose one:
#
#   check_body_branch <base> <branch> <role> [--tasks PATH --task-key KEY]
#
# `main` cannot build a `TaskRoleSpec` out of <base> <branch> <role>: nothing
# in those three names a task row. Some input has to be added, and a seal has
# to name it or it seals nothing. Constraints that fixed the choice:
#
#   * `test_main_requires_exactly_three_positional_arguments` (an existing
#     seal, not weakened here) pins the POSITIONAL arity at three, so the row
#     must arrive as options.
#   * `--tasks` is a REPO-RELATIVE path read out of <base>'s object store, not
#     the working tree. The working tree is the branch under judgement, and an
#     `adjudicate` row's `disputed_paths:` IS its writable set — a branch that
#     supplied its own row would widen its own gate by editing one line. That
#     is invariant 6 (a branch may not supply the policy that judges it) by
#     another route, and it already cost this script the PYTHONSAFEPATH fix.
#     `test_the_row_is_read_from_the_base_not_from_the_branch_under_judgement`
#     is the seal for it.
#   * both options or neither: half a row is not a row.
#
# If P3 disputes the spelling (`--task-key` vs `--task`, or a different way of
# naming the row), that is a seal amendment and escalates to P4 — it is not a
# body agent's edit. The MECHANISM being sealed is not the spelling: it is that
# `main` builds a spec, reads it from the base, and hands it to `check_branch`.


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


TASKS_REL = "features/d1/tasks.yaml"


@pytest.fixture
def repo_with_rows(tmp_path: Path) -> Path:
    """A repo on `main` whose base commit carries a D1 worklist.

    The adjudicate row's writable set is `docs/**`; the bodies row adds
    `docs/**` to its deny set. Same glob, opposite meaning, on purpose: it is
    the same one path that proves the spec was applied for either role.
    """
    repo = tmp_path / "repo"
    (repo / "features" / "d1").mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "features" / "d1" / "tasks.yaml").write_text(
        "project: T\nepic: D1\ntasks:\n"
        + _row("D1-1", role="scaffold")
        + _row("D1-2", role="seals", blocked_by=("D1-1",))
        + _row(
            "D1-3",
            role="bodies",
            blocked_by=("D1-2",),
            extra=('immutable_paths: ["docs/**"]',),
        )
        + _row(
            "D1-4",
            role="adjudicate",
            blocked_by=("D1-2",),
            extra=('disputed_paths: ["docs/**"]',),
        ),
        encoding="utf-8",
    )
    (repo / "base.txt").write_text("seed\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    return repo


def _branch_adding(repo: Path, name: str, files: dict[str, str]) -> None:
    _git(["checkout", "-q", "-b", name], repo)
    for rel, text in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", f"work on {name}"], repo)


def test_main_builds_a_task_role_spec_from_the_named_row(
    monkeypatch: pytest.MonkeyPatch, repo_with_rows: Path
) -> None:
    """`main` passes `check_branch` a spec, or the row's declarations are
    decoration.

    Red now: `main` accepts three positional arguments and nothing else, so
    this returns USAGE (64) and `check_branch` is never reached — and even
    called correctly it would pass `spec=None`.
    Green when: the named row is parsed into a `TaskRoleSpec` and handed to
    `check_branch`.
    Falsify: build the spec and drop it on the floor — `captured` has no
    `spec` and this goes red.
    """
    captured: dict[str, object] = {}

    def _stub(*args: object, **kwargs: object) -> RoleDiffResult:
        captured["args"] = args
        captured.update(kwargs)
        return RoleDiffResult(
            verdict=DiffVerdict.CLEAN,
            role=Role.BODIES,
            base_ref="main",
            branch_ref="feat/x",
            checked_paths=("docs/x.md",),
        )

    monkeypatch.setattr(role_protocol, "check_branch", _stub)
    monkeypatch.chdir(repo_with_rows)

    code = role_protocol.main(
        ["main", "feat/x", "bodies", "--tasks", TASKS_REL, "--task-key", "D1-3"]
    )
    assert code == ExitCode.OK.value

    spec = captured.get("spec")
    assert isinstance(spec, TaskRoleSpec), (
        f"main must hand check_branch the row's TaskRoleSpec; got {spec!r}"
    )
    assert spec.task_key == "D1-3"
    assert spec.role is Role.BODIES
    assert "docs/**" in spec.added_immutable_globs


def test_an_adjudicate_branch_can_be_cleared(repo_with_rows: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a spec, ADJUDICATE is UNDETERMINED by construction: its writable
    set lives on the row, and `check_branch` will not guess "nothing" (a wrong
    CLEAN for an empty diff) or "anything". So today the CI script can never
    clear an adjudicate branch — the most constrained role is the one role the
    gate cannot answer for, which reads to an operator as the gate being broken
    and is the shortest path to it being switched off.

    Red now: USAGE (64) — the options do not exist.
    Green when: the row's `disputed_paths: ["docs/**"]` becomes the allow-only
    set and a branch that touched only `docs/` exits 0.
    Falsify: pass the spec but let `check_branch` fall back to the policy's
    (empty) ADJUDICATE globs — every path violates and this returns 2.
    """
    _branch_adding(repo_with_rows, "feat/adj", {"docs/ruling.md": "the ruling\n"})
    monkeypatch.chdir(repo_with_rows)

    code = role_protocol.main(
        ["main", "feat/adj", "adjudicate", "--tasks", TASKS_REL, "--task-key", "D1-4"]
    )
    assert code == ExitCode.OK.value


def test_a_per_task_immutable_paths_addition_is_actually_applied(
    repo_with_rows: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row said `docs/**` was not this bodies task's to touch. Unless the
    spec reaches `check_branch`, the branch is judged by the default BODIES
    rule alone — which says nothing about `docs/**` — and the declaration is a
    comment.

    This is the row that distinguishes "a spec was passed" from "a spec was
    applied": with the default rule the same diff is CLEAN.

    Red now: USAGE (64).
    Green when: VIOLATION (2), because `effective_rule` unions the row's
    addition into BODIES' deny set.
    Falsify: pass `spec=None` while keeping the options — the diff comes back
    CLEAN (0) and this goes red.
    """
    _branch_adding(repo_with_rows, "feat/bodies", {"docs/note.md": "note\n"})
    monkeypatch.chdir(repo_with_rows)

    code = role_protocol.main(
        ["main", "feat/bodies", "bodies", "--tasks", TASKS_REL, "--task-key", "D1-3"]
    )
    assert code == ExitCode.VIOLATION.value, (
        "the row's own immutable_paths addition must reach the verdict; "
        "0 here means the declaration was decorative"
    )


def test_the_row_is_read_from_the_base_not_from_the_branch_under_judgement(
    repo_with_rows: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A branch may not supply the gate that judges it.

    An `adjudicate` row's `disputed_paths:` IS its writable set, so a `main`
    that read the row from the working tree would let the branch grant itself
    any path by editing one line — including the line that grants it. This
    branch does exactly that: it rewrites its own row to add `src/**` and the
    worklist file itself, then writes `src/x.py`.

    Read from the base, the effective writable set is still `docs/**`, both
    changed paths violate it, and the answer is 2. Read from the working tree,
    everything the branch touched is in its own allow list and the answer is 0
    — a gate that clears whatever it is pointed at.

    Red now: USAGE (64).
    Green when: VIOLATION (2).
    Falsify: read the tasks file off disk with `yaml_io.load(Path(rel))` — the
    three rows above stay green (they never tamper) and only this goes red,
    which is why the tamper lives in its own row.
    """
    tampered = (
        "project: T\nepic: D1\ntasks:\n"
        + _row("D1-1", role="scaffold")
        + _row("D1-2", role="seals", blocked_by=("D1-1",))
        + _row(
            "D1-4",
            role="adjudicate",
            blocked_by=("D1-2",),
            extra=(f'disputed_paths: ["docs/**", "src/**", "{TASKS_REL}"]',),
        )
    )
    _branch_adding(
        repo_with_rows,
        "feat/tamper",
        {TASKS_REL: tampered, "src/x.py": "x = 1\n"},
    )
    monkeypatch.chdir(repo_with_rows)

    code = role_protocol.main(
        ["main", "feat/tamper", "adjudicate", "--tasks", TASKS_REL,
         "--task-key", "D1-4"]
    )
    assert code == ExitCode.VIOLATION.value, (
        "the branch rewrote its own disputed_paths; a gate that honours that "
        "is not a gate"
    )


def test_a_task_key_that_names_no_row_is_never_a_pass(
    repo_with_rows: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"I could not find the row" must not be answered with "no spec, carry
    on" — that is the fail-open shape, and it is reachable by a typo.

    Red now: USAGE (64) is returned for the wrong reason (the options are
    unrecognised), so this row is green today. It is kept as a GUARD on the
    implementation the seals above force: once the options exist, an unknown
    key must still be refused rather than silently degrading to `spec=None`.
    Green when: a non-zero, non-verdict-of-CLEAN code. Which of USAGE /
    UNDETERMINED is not pinned — both are defensible, exactly as the existing
    `legacy` row leaves it open.
    """
    _branch_adding(repo_with_rows, "feat/typo", {"docs/note.md": "note\n"})
    monkeypatch.chdir(repo_with_rows)

    code = role_protocol.main(
        ["main", "feat/typo", "bodies", "--tasks", TASKS_REL, "--task-key", "D1-99"]
    )
    assert code != ExitCode.OK.value
    assert code in {ExitCode.USAGE.value, ExitCode.UNDETERMINED.value}


@pytest.mark.parametrize(
    "options",
    [
        ["--tasks", TASKS_REL],
        ["--task-key", "D1-3"],
    ],
)
def test_half_a_row_reference_is_a_usage_error(
    repo_with_rows: Path, monkeypatch: pytest.MonkeyPatch, options: list[str]
) -> None:
    """GUARD on the same implementation: `--tasks` without `--task-key` (or the
    reverse) names no row. Answering it by ignoring the option given is how a
    caller comes to believe a spec was applied when none was.

    Green today for the wrong reason (unknown options); green afterwards for
    the right one.
    """
    monkeypatch.chdir(repo_with_rows)
    code = role_protocol.main(["main", "feat/x", "bodies", *options])
    assert code == ExitCode.USAGE.value


# --------------------------------------------------------------------------- #
# 5. The "Wired by P3" claim cannot drift back into a lie
# --------------------------------------------------------------------------- #
#
# `role_protocol.py`'s docstring says: "Wired by P3 (invariant 7 — each claim
# here has its call site)" and then lists five. Three of the five have no call
# site, and one of those three (`orchestrator.run`) names a function that does
# not exist in that module at all. That sentence is a claim with no mechanism,
# in the unit built to eliminate claims with no mechanism — so it gets a
# mechanism.
#
# The check parses the claim list out of the docstring and resolves each claim
# against the source. It deliberately does NOT re-state the five claims as a
# hand-written table keyed on subject: a table would be a second copy of the
# docstring, and the two would drift — which is the failure mode this whole
# module is about. What IS pinned by hand is the minimum set of role_protocol
# FUNCTIONS that must be claimed wired, so the section cannot be made to pass
# by deleting a bullet. Pinning targets rather than subjects leaves P3 free to
# correct `orchestrator.run` to whatever function actually holds the call.

#: The role_protocol functions the docstring must claim a call site for. A
#: removal here is a plan amendment, not a body agent's edit.
REQUIRED_WIRED_TARGETS = frozenset({
    "validate",
    "dispatch_satisfied_statuses",
    "agent_correlation_warnings",
    "role_policy_from_mapping",
    "main",
})

_CLAIM_BULLET = re.compile(r"^ {2}\* (.*)$")
_SUBJECT = re.compile(r"^`([^`]+)`\s*(?:→|->)")
_TARGET = re.compile(r":func:`([A-Za-z_][A-Za-z0-9_]*)`")


def _wired_claims() -> list[tuple[str, str]]:
    """(subject, target) for every bullet under "Wired by P3".

    Returns [] when the section cannot be found — which is itself a failure,
    asserted in its own row below rather than silently yielding zero claims to
    check. A parser that returns an empty list on a reworded docstring is the
    vacuity trap for this seal.
    """
    doc = role_protocol.__doc__ or ""
    lines = doc.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if "Wired by P3" in line), None
    )
    if start is None:
        return []

    claims: list[tuple[str, str]] = []
    current: list[str] | None = None
    for line in lines[start + 1:]:
        bullet = _CLAIM_BULLET.match(line)
        if bullet:
            if current is not None:
                claims.append(tuple(current))  # type: ignore[arg-type]
            text = bullet.group(1).strip()
            subject = _SUBJECT.match(text)
            target = _TARGET.search(text)
            current = [
                subject.group(1) if subject else "",
                target.group(1) if target else "",
            ]
            continue
        if current is not None and line.startswith("    ") and line.strip():
            # A continuation line: the target often lands on the second line.
            if not current[1]:
                target = _TARGET.search(line)
                if target:
                    current[1] = target.group(1)
            continue
        if line.strip() and not line.startswith("  "):
            break  # the section ended (e.g. the "NOT wired" paragraph)
    if current is not None:
        claims.append(tuple(current))  # type: ignore[arg-type]
    return claims


def _call_site_failure(subject: str, target: str) -> str | None:
    """Why `subject` does not call `target`, or None when it does."""
    if not subject or not target:
        return f"unparseable claim (subject={subject!r} target={target!r})"
    if not hasattr(role_protocol, target):
        return f"claims :func:`{target}`, which role_protocol does not define"

    if subject.endswith(".sh"):
        script = REPO_ROOT / subject
        if not script.is_file():
            return f"{subject} does not exist"
        text = script.read_text(encoding="utf-8")
        if "claude_dispatcher.role_protocol" not in text:
            return f"{subject} does not exec the role_protocol entrypoint"
        return None

    module_name, _, func_name = subject.rpartition(".")
    if not module_name:
        return f"{subject!r} is not a <module>.<function> subject"
    source = PKG_ROOT / f"{module_name}.py"
    if not source.is_file():
        return f"{subject} names module {module_name!r}, which does not exist"
    text = source.read_text(encoding="utf-8")
    if "role_protocol" not in text:
        return (
            f"{module_name}.py never mentions role_protocol, so "
            f"{subject} cannot be calling :func:`{target}`"
        )
    tree = ast.parse(text)
    fn = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ),
        None,
    )
    if fn is None:
        return f"{subject} names a function {module_name}.py does not define"
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        name = (
            called.attr
            if isinstance(called, ast.Attribute)
            else called.id if isinstance(called, ast.Name)
            else None
        )
        if name == target:
            return None
    return f"{subject} contains no call to :func:`{target}`"


def test_the_wired_by_p3_section_is_machine_readable_and_claims_every_target() -> None:
    """The seal above this one is only as good as its parser: a docstring
    reword that stops the section parsing would silently check nothing, and a
    deleted bullet would make a false claim true by removing it.

    Red now: green, in fact — today the section parses and names all five
    targets. This row is the anti-vacuity guard for the next one, not a seal
    on the wiring, and it is what stops "delete the bullet" from being a legal
    way to make the next row pass.
    """
    claims = _wired_claims()
    assert claims, (
        "the 'Wired by P3' claim list no longer parses. It is checked "
        "mechanically; a format it cannot read is a claim with no mechanism "
        "again. Keep the '  * `subject` → ... :func:`target`' shape, or amend "
        "this parser in the same commit (a P4 seal amendment)."
    )
    targets = {target for _subject, target in claims}
    missing = sorted(REQUIRED_WIRED_TARGETS - targets)
    assert not missing, (
        f"the docstring no longer claims a call site for {missing}. A claim is "
        "not made true by deleting it: these are the unit's five enforcement "
        "points, and dropping one from the contract is a plan amendment."
    )


def test_every_wired_by_p3_claim_has_its_call_site() -> None:
    """"Wired by P3 (invariant 7 — each claim here has its call site)."

    Red now, three ways:
      * `plan.load_tasks` → `validate`: plan.py does not mention role_protocol.
      * `plan.runnable_now` → `dispatch_satisfied_statuses`: same file, same
        reason.
      * `orchestrator.run` → `agent_correlation_warnings`: orchestrator.py
        defines no `run` at all (the entry point is `execute`), so the claim
        names a function that does not exist AND makes a call that does not
        happen.
    Green when: each claimed subject really calls its claimed target. P3 may
    correct a subject that was written wrong (`orchestrator.run`) as long as
    the corrected subject holds the call.
    Falsify: point a claim at a function that does not call its target — this
    reddens; that is the whole mechanism.
    """
    failures = [
        f"  * {subject or '<unparseable>'}: {reason}"
        for subject, target in _wired_claims()
        if (reason := _call_site_failure(subject, target)) is not None
    ]
    assert not failures, (
        "role_protocol's docstring claims call sites that do not exist:\n"
        + "\n".join(failures)
        + "\n\nA library with no call sites enforces nothing, and a docstring "
        "that says it does is worse than silence: it is the self-report this "
        "unit exists to replace."
    )
