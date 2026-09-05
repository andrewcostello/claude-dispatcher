r"""Seals: a run that did not finish is not a run that went RED.

THE FAMILY
----------
`test_seal_verify_failopen.py` closed the paths where the seal gate reports a
*judgement about the change* it never made. This file closes the one place it
reports a *judgement about the suite* it never made, and the sibling sweep
that was supposed to catch it did not, because the sweep never looks at the
suite's outcome at all.

`run_seal_inversion` reverts the fix, runs the repo's test command, and reads
one bit off the result:

    if result.passed:   -> "failed"  (suite stayed GREEN — vacuous seal)
    return              -> "passed"  (suite went red — the seal is real)

`MechanicalVerifyResult.passed` is `exit_code == 0`, and that module's own
docstring says `exit_code` is `None` "when no exit code exists: the command
timed out and was killed, or it never launched". So *not green* is being read
as *red*, and there are four different facts arriving on one channel:

    the suite ran and exited 0        -> "failed"   (correct)
    the suite ran and exited non-0    -> "passed"   (correct)
    the suite was killed at the bound -> "passed"   <- WRONG, and live
    the suite never started at all    -> "passed"   <- WRONG, and live

`passed` is the gate's certificate that the seal is real; the orchestrator
proceeds on it and the journal records "suite went red without the fix".
A suite that never finished is not a suite that went red, and a suite that
never started is not a suite at all.

WHAT WAS MEASURED (2026-08-10, worktree at `9ceb6d4`, real repositories,
driven through the production entry points, `__pycache__` cleared first)
---------------------------------------------------------------------------
    input                                  outcome   detail
    ------------------------------------   -------   ----------------------------
    inverted suite hangs, killed at 2s     passed    suite went red without the
                                                     fix (exit=None)
    inverted suite cannot be exec'd        passed    suite went red without the
                                                     fix (exit=None)
    inverted suite exits 1 (control)       passed    suite went red without the
                                                     fix (exit=1)
    inverted suite exits 0 (control)       failed    suite stayed GREEN ...

The first two are the whole subject of this file. Note what the journal
keeps: the sentence is the same one a real red run gets, and the only trace
of the difference is `exit=None` inside it — the `timed out after 2s` /
`failed to launch` annotation `mechanical_verify` writes goes to the run log
and to `output_tail`, neither of which reaches the result, the journal, or
the orchestrator's decision.

A fifth fact was measured and is NOT sealed here — see DISPUTES.

THE SECOND `skipped` PRODUCER
-----------------------------
The sibling file names two producers of the gate's outcome vocabulary
(`_outcomes_seal_verify_can_emit` and `_outcomes_verify_seal_can_return`) but
its stands-down invariant, `test_the_gate_stands_down_only_on_the_two_
applicability_judgements`, reads only the first: it parses
`seal_verify.run_seal_inversion` and enumerates the two `skipped` reasons
there. Producer two is `orchestrator._verify_seal`, and it stands down on a
step that FAILED:

    try:
        repo_cfg = repo_config_mod.load(wt.path)
    except repo_config_mod.RepoConfigError:
        repo_cfg = None
    if repo_cfg is None or repo_cfg.test is None:
        _emit_event(..., {"outcome": "skipped", "reason": "no test command"})
        return "skipped", None

An unreadable config is journaled as "no test command" — a positive claim
about the repo, made when the repo's `.dispatcher.yaml` declares one and the
loader simply refused the file. Measured 2026-08-10 against a repo whose
config is `test: sh tests/run.sh` plus a `roles:` section the loader rejects:
`_verify_seal` returns `("skipped", None)` and journals `reason: "no test
command"`, while `repo_config.load` on the good twin returns exactly that
command. Its sibling gate `_verify_mechanical_and_maybe_retry` performs the
identical read three functions later and gets it right — logs the error,
journals `{"outcome": "failed", "error": ...}`, returns `("failed", err)` —
so the shape this file asks for is already in the file, once.

AND THE TRIGGER REALLY IS WIDER THAN IT WAS. Measured by execution, same
`.dispatcher.yaml` both times: at `6d39031^` `repo_config.load` returns
`test='sh tests/run.sh', unknown_keys=('roles',)` and the seal gate runs; at
`6d39031` ("the loader stops swallowing a self-weakening roles:") the same
file raises `RepoConfigError` and the seal gate switches itself off. That
commit is right about `roles:` — a silently dropped protection is the failure
it exists to prevent — and it enlarged, as a side effect, the set of repos
for which the seal gate reports "no test command" about a repo that has one.

NO NEW OUTCOME LITERAL IS ASKED FOR. `test_seal_verify_failopen.py::
test_every_outcome_the_seal_gate_can_emit_is_classified_by_the_orchestrator`
pins the vocabulary at `{passed, failed, skipped, error}` against the
orchestrator's two membership tests, and that row may not be amended from
here. Every row below is satisfiable with `error`, which
`_OUTCOME_DISPOSITION` already classifies as "NOT judged — the block that
makes a non-judgement safe", which is exactly what a run that did not finish
is. A fifth literal (`timeout`, `not_run`) would redden that row; if a body
author wants one, it is a P4 item, not a workaround.

PRODUCIBILITY
-------------
No row asserts against a hand-made value; every one builds a real repository
and drives the production entry point, and each demonstrates its awkward
input BEFORE asking the gate anything, so a future environment in which the
input cannot be produced makes the row say so instead of passing.

  * The timeout is CAUSED BY THE INVERSION, not by a `sleep`. The branch's
    fix is what makes the suite terminate — `while ! grep -q fixed code.txt;
    do sleep 1; done` — so reverting it hangs the suite, which is the
    everyday shape of a fix for a deadlock, an infinite retry loop or a
    missing loop bound, sealed by a test that hangs without it. The generic
    route needs no such fix: the inverted tree is the pathological one and
    `verify_test_timeout_seconds` is a fixed budget, so any suite that
    normally runs near it times out here for reasons that have nothing to do
    with whether the new tests pin anything.
  * The launch failure is `E2BIG` on a 200 000-byte test command. `sh -c`
    takes the command as ONE argv entry, Linux caps a single argument at
    `MAX_ARG_STRLEN` = 32 pages = 131 072 bytes, and `exec` then fails with
    `[Errno 7] Argument list too long: '/bin/sh'` — measured exactly at the
    boundary: 131 071 bytes runs, 131 072 raises. That string is repo-supplied
    (`repo_config` validates `test:` as "a non-blank string" and nothing more)
    and `_verify_seal` hands it to `run_test_command` verbatim. The everyday
    route to the same `except OSError` is resource exhaustion — `fork`
    returning EAGAIN/ENOMEM on a dispatcher host running `max_parallel`
    worktrees' suites at once — which this row does not reproduce, because
    reproducing it means setting `RLIMIT_NPROC` on the test session.
  * The unreadable config is a `.dispatcher.yaml` carrying a valid `test:` and
    a `roles:` section with a negated glob (`immutable_paths:
    ['!**/tests/**']`) — the self-weakening policy `6d39031` added the refusal
    for. The row asserts the loader really refuses it and that the identical
    `test:` really loads on the twin.

NON-VACUITY. Every gate-driving row judges its awkward input AND an ordinary
twin in the same call, and the twin must reach a real verdict, so no row can
pass by the gate refusing everything. The one structural row (producer two's
stands-down invariant) has no twin and says in its own docstring why.

RUNTIME. The timeout row costs its own budget and nothing else: the bound is
`_TIMEOUT_BUDGET_SECONDS = 2`, deliberately the smallest value at which the
inversion's hang is unambiguous, and the whole file measures ~2.4s.

DISPUTES (for P4)
-----------------
  1. **A suite the kernel killed.** Measured: `kill -9` of the suite's shell
     gives `exit_code=-9`, and the OOM killer taking the runner under the
     shell gives `137`; both come back `("passed", "suite went red without
     the fix (exit=-9|137)")`. That is the third member of the same family —
     a run that did not reach a verdict, reported as red — but it is NOT
     sealed here, because the honest ruling is not obvious and ruling 2's
     logic cuts against blocking: a fix for a crash, inverted, legitimately
     kills the runner, and blocking there charges a hard stop to every
     crash fix. `137` is in any case indistinguishable from an ordinary
     non-zero exit, so no gate can separate it. Ruled on or not, this file
     does not touch it.
  2. **`_OUTCOME_DISPOSITION` says `error` means "the change could not be
     safely inverted/restored, or could not be partitioned at all"**
     (`SealVerifyResult`'s docstring). A suite that did not finish is none of
     those three; it is a fourth non-judgement. The rows below are satisfied
     by `error` and the docstring wants a sentence added by the body author.
     Named here so it is not mistaken for scope creep in the body change.
  3. **The panel filed this as `orchestrator._run_seal_gate` /
     `_run_mechanical_gate`.** No such names exist at `9ceb6d4`; the functions
     are `_verify_seal` and `_verify_mechanical_and_maybe_retry`, and
     `grep -rl _run_seal_gate tests/` returning nothing is therefore not
     evidence of anything. Under the real name the grep returned exactly one
     file before this one — the sibling — which reads `_verify_seal` as a
     STRING through the AST and never calls it. Nothing executed it.
"""

from __future__ import annotations

import ast
import subprocess
import time
from pathlib import Path

import pytest

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import orchestrator as orch_mod
from claude_dispatcher import plan as plan_mod
from claude_dispatcher import repo_config as repo_config_mod
from claude_dispatcher import seal_verify as sv
from claude_dispatcher import worktree as wt_mod

# The disposition table is the sibling file's, imported rather than copied: it
# is the one written-out statement of which outcomes the orchestrator blocks
# on, and a second copy here would be a second policy that drifts. Importable
# because `tests/` has no `__init__.py`, so pytest's default `prepend` import
# mode puts this directory on `sys.path`.
from test_seal_verify_failopen import _BLOCKING

#: The inversion's suite budget for the timeout row, in seconds. Production's
#: is `RunConfig.verify_test_timeout_seconds` (default 600, CLI-settable), and
#: the row is a statement about the bound being HIT, not about its size — so
#: this is the smallest value at which the hang is unambiguous rather than a
#: scheduling artefact. Every non-timeout row runs at 30s and finishes in
#: milliseconds.
_TIMEOUT_BUDGET_SECONDS = 2

#: A single argv entry longer than Linux's `MAX_ARG_STRLEN` (32 pages =
#: 131 072 bytes) cannot be exec'd. Measured at the boundary 2026-08-10:
#: 131 071 runs, 131 072 raises `OSError(7, 'Argument list too long')`. Well
#: past it, so a page-size difference cannot make the row vacuous.
_UNEXECUTABLE_PADDING = 200_000


# --------------------------------------------------------------------------- #
# Repository fixtures — real git, never a stub.
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True)
    assert proc.returncode == 0, f"git {args!r} failed: {proc.stderr}"
    return proc.stdout


def _seal_repo(root: Path, name: str, *, config: str | None = None) -> Path:
    """`main` holds `code.txt` = broken and a trivial green suite.

    The same base as the sibling file's, plus an optional `.dispatcher.yaml`
    for the rows that go through the orchestrator. Each row rewrites
    `tests/run.sh` on its branch to be the seal under test.
    """
    repo = root / name
    (repo / "tests").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "T")
    (repo / "code.txt").write_text("broken\n", encoding="utf-8")
    (repo / "tests" / "run.sh").write_text("exit 0\n", encoding="utf-8")
    if config is not None:
        (repo / repo_config_mod.CONFIG_FILENAME).write_text(
            config, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "fix/seal")
    return repo


def _commit_fix(repo: Path, *, seal: str) -> None:
    """The branch commit: `code.txt` becomes the fix, `run.sh` becomes a seal."""
    (repo / "code.txt").write_text("fixed\n", encoding="utf-8")
    (repo / "tests" / "run.sh").write_text(seal, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix + seal")


def _invert(
    repo: Path,
    *,
    command: str = "sh tests/run.sh",
    timeout_seconds: int = 30,
) -> tuple[sv.SealVerifyResult, list[str], float]:
    """Drive the production entry point; return result, log and elapsed time."""
    logs: list[str] = []
    started = time.monotonic()
    result = sv.run_seal_inversion(
        worktree=repo, base="main", test_command=command,
        timeout_seconds=timeout_seconds, log=logs.append,
    )
    return result, logs, time.monotonic() - started


def _red_verdict_claim(control: sv.SealVerifyResult) -> str:
    """The sentence the gate uses to claim a COMPLETED red run, taken from the
    control's own detail in the same test.

    Derived rather than hard-coded so these rows pin the CLAIM and not today's
    wording: if a body author rewrites the red verdict's sentence, the control
    supplies the new one and the assertion still means "do not say this about
    a run that never finished".
    """
    claim = control.detail.split("(")[0].strip()
    assert len(claim) > 10, (
        "the control's verdict detail is too short to be the claim this row "
        f"forbids ({control.detail!r}); without it the assertions below would "
        "pass vacuously"
    )
    return claim


# --------------------------------------------------------------------------- #
# 1. The live fail-open: a suite that did not finish.
# --------------------------------------------------------------------------- #


def test_a_suite_that_never_finished_is_not_a_suite_that_went_red(
    tmp_path: Path,
) -> None:
    """RED — a timed-out inversion run is certified as a real seal.

    `run_seal_inversion` reads the suite through
    `MechanicalVerifyResult.passed`, which is `exit_code == 0`. A killed
    command has `exit_code is None`, so it is not `passed`, so it falls
    through to `SealVerifyResult("passed", "suite went red without the fix")`
    — the gate's certificate that the new tests pin the change, issued on a
    run that never said whether they fail. MEASURED 2026-08-10 at `9ceb6d4`:
    `("passed", "suite went red without the fix (exit=None)")`, the run log
    carrying `mechanical-verify: command timed out after 2s` that the result,
    the journal and the orchestrator never see.

    This is the gate's whole subject turned inside out: it exists to catch the
    false-passing seal, and a suite that hangs makes every seal pass.

    PRODUCIBLE, and produced by the inversion itself rather than faked. The
    branch's fix is the thing that makes the suite terminate — the seal loops
    until `code.txt` says `fixed` — so reverting the fix hangs it. That is a
    fix for a hang, sealed by a test that hangs without it: an infinite retry,
    a missing loop bound, a deadlock. The row demonstrates BOTH halves before
    asking the gate anything: the suite exits 0 promptly with the fix in
    place, and the gate's own log records that the inverted run hit the bound.
    The generic route needs no hang at all — the budget is fixed and the
    inverted tree is the pathological one, so a suite that normally runs near
    `verify_test_timeout_seconds` times out here for reasons unrelated to the
    seal.

    BOUNDED DELIBERATELY: the budget is `_TIMEOUT_BUDGET_SECONDS` = 2, and the
    row costs that plus milliseconds. The control twin uses the same budget
    and finishes in ~10ms, which is also what proves the bound is not what
    reddens the awkward twin.

    Red now: `passed`.
    Green when: a result with no exit code is a non-judgement. `error` is the
    honest outcome and needs no new vocabulary — `_OUTCOME_DISPOSITION`
    already reads it as "NOT judged". SEPARATE body change.
    Falsify: the control — an identical branch whose seal really goes red in
    milliseconds — is judged in the same call, so a gate that blocked
    everything, or one that blocked every multi-second suite, reddens on it.
    Making the gate return `failed` for the timeout also reddens this row: see
    the second assertion.
    """
    hanging = _seal_repo(tmp_path, "hanging")
    _commit_fix(hanging, seal=(
        "# terminates only when the fix is in the tree\n"
        "while ! grep -q fixed code.txt; do sleep 1; done\n"
    ))

    control = _seal_repo(tmp_path, "control")
    _commit_fix(control, seal="grep -q fixed code.txt\n")

    # Producibility, half one: WITH the fix the suite is green and prompt, so
    # the hang below is the inversion's doing and not a slow suite.
    with_fix = subprocess.run(
        "sh tests/run.sh", shell=True, cwd=str(hanging), capture_output=True,
        text=True, timeout=_TIMEOUT_BUDGET_SECONDS)
    assert with_fix.returncode == 0, (
        "the fixture no longer reproduces the input under test: the branch's "
        f"own suite is not green with the fix in place (rc={with_fix.returncode}"
        f", output={with_fix.stdout!r}{with_fix.stderr!r})"
    )

    hung_result, hung_logs, hung_elapsed = _invert(
        hanging, timeout_seconds=_TIMEOUT_BUDGET_SECONDS)
    control_result, control_logs, control_elapsed = _invert(
        control, timeout_seconds=_TIMEOUT_BUDGET_SECONDS)

    # Producibility, half two: the gate's own log says the bound was hit.
    assert any("timed out" in line for line in hung_logs), (
        "the fixture no longer reproduces the input under test: the inverted "
        f"suite was not killed at the {_TIMEOUT_BUDGET_SECONDS}s bound "
        f"(elapsed {hung_elapsed:.2f}s, log {hung_logs!r})"
    )
    assert hung_elapsed >= _TIMEOUT_BUDGET_SECONDS > control_elapsed, (
        "the fixture no longer reproduces the input under test: the hanging "
        f"twin took {hung_elapsed:.2f}s and the control {control_elapsed:.2f}s "
        f"against a {_TIMEOUT_BUDGET_SECONDS}s bound"
    )

    assert hung_result.outcome in _BLOCKING, (
        "the suite was killed at the bound and never said whether the new "
        f"tests fail without the fix, and the gate returned "
        f"{hung_result.outcome!r} — {hung_result.detail!r} — which the "
        "orchestrator does not block on. That is the gate certifying a seal "
        "on the strength of a run that did not complete, which is the exact "
        "false-passing seal it exists to catch"
    )
    assert hung_result.outcome != "failed", (
        "`failed` is the accusation that the change's new tests are vacuous, "
        f"and this run produced no evidence for it: {hung_result.detail!r}. A "
        "suite that was killed did not stay green either — the honest answer "
        "is the one that says the judgement was never made"
    )
    claim = _red_verdict_claim(control_result)
    assert claim not in hung_result.detail, (
        f"the gate reported {claim!r} about a suite that was killed before it "
        f"finished: {hung_result.detail!r}. That sentence is what the journal "
        "keeps and what the panel's evidence lens reads, and it is the same "
        "sentence a genuinely red run gets"
    )
    assert _git(hanging, "status", "--porcelain").strip() == "", (
        "the worktree was left inverted after the suite was killed: the "
        "branch's fix is reverted on disk and every later gate reads this tree"
    )

    assert control_result.outcome == "passed" and control_logs, (
        "control: an identical branch whose seal really goes red in "
        "milliseconds must reach a real verdict "
        f"({control_result.outcome!r} / {control_result.detail!r}), or the "
        "assertions above would pass by the gate blocking everything"
    )


def test_a_suite_that_never_started_is_not_a_suite_that_went_red(
    tmp_path: Path,
) -> None:
    """RED — a test command that could not be executed is certified as a real
    seal.

    The second arm of the same defect and NOT covered by the first: the
    timeout and the launch failure are different branches of
    `run_test_command`, and a body author who keys the fix on the string
    `timed out` closes one and leaves the other. `mechanical_verify`'s own
    docstring pairs them — `exit_code` is None "when no exit code exists: the
    command timed out and was killed, or it never launched (an OSError from
    the subprocess machinery)" — and `run_seal_inversion` reads both as red.
    MEASURED 2026-08-10 at `9ceb6d4`: `("passed", "suite went red without the
    fix (exit=None)")`, byte-identical to the timed-out run's detail, with
    `mechanical-verify: command failed to launch: [Errno 7] Argument list too
    long: '/bin/sh'` in the run log and nowhere else. Nothing ran at all, and
    the gate certified the seal.

    PRODUCIBLE. The command is the repository's own, plus padding that makes
    it unexecutable: `sh -c` passes the command as ONE argv entry and Linux
    caps a single argument at `MAX_ARG_STRLEN` (32 pages = 131 072 bytes), so
    `exec` fails with `E2BIG` before any shell exists. Measured at the
    boundary the same day: 131 071 bytes runs, 131 072 raises. Production's
    channel for it is `repo_config`, which validates `test:` as a non-blank
    string and imposes no length bound, and `_verify_seal`, which passes the
    value verbatim. The everyday route to the identical `except OSError` is
    `fork` failing with EAGAIN/ENOMEM on a host running `max_parallel` suites
    at once; this row does not reproduce that one, because reproducing it
    means putting an `RLIMIT_NPROC` on the test session.

    The row demonstrates the exec failure on this exact string, by hand, in
    this exact worktree, before asking the gate anything — so a kernel that
    raised the cap makes the row say the input is no longer producible rather
    than pass.

    Red now: `passed`.
    Green when: a result with no exit code is a non-judgement (`error`).
    SEPARATE body change, and the same one the row above wants.
    Falsify: the control is the SAME repository judged with the SAME command
    minus the padding, in the same call — so a gate that blocked every
    long-running or oddly-shaped command reddens on it.
    """
    repo = _seal_repo(tmp_path, "unlaunchable")
    _commit_fix(repo, seal="grep -q fixed code.txt\n")
    twin = _seal_repo(tmp_path, "launchable")
    _commit_fix(twin, seal="grep -q fixed code.txt\n")

    runnable = "sh tests/run.sh"
    unrunnable = runnable + " # " + "x" * _UNEXECUTABLE_PADDING

    # Producibility: this command really cannot be exec'd, here, today.
    try:
        subprocess.run(unrunnable, shell=True, cwd=str(repo),
                       capture_output=True, text=True, timeout=30)
    except OSError as exc:
        launch_error = exc
    else:
        pytest.fail(
            "the fixture no longer reproduces the input under test: a "
            f"{len(unrunnable)}-byte command was executed rather than "
            "refused, so MAX_ARG_STRLEN is not what this row assumes"
        )
    assert "Argument list too long" in str(launch_error), (
        "the fixture no longer reproduces the input under test: the exec "
        f"failed for some other reason ({launch_error!r})"
    )

    unlaunched_result, unlaunched_logs, _ = _invert(repo, command=unrunnable)
    control_result, control_logs, _ = _invert(twin, command=runnable)

    assert any("failed to launch" in line for line in unlaunched_logs), (
        "the fixture no longer reproduces the input under test: the gate did "
        f"not report a launch failure (log {unlaunched_logs!r})"
    )

    assert unlaunched_result.outcome in _BLOCKING, (
        "no suite was ever started — the shell could not be exec'd — and the "
        f"gate returned {unlaunched_result.outcome!r}: "
        f"{unlaunched_result.detail!r}. A repo whose test command cannot be "
        "launched gets EVERY seal certified, silently, for as long as the "
        "command stays that way"
    )
    assert unlaunched_result.outcome != "failed", (
        "`failed` accuses the change's tests of being vacuous; a command that "
        f"never started is evidence for nothing: {unlaunched_result.detail!r}"
    )
    claim = _red_verdict_claim(control_result)
    assert claim not in unlaunched_result.detail, (
        f"the gate reported {claim!r} about a command that was never "
        f"executed: {unlaunched_result.detail!r}"
    )
    assert _git(repo, "status", "--porcelain").strip() == "", (
        "the worktree was left inverted after the suite failed to launch"
    )

    assert control_result.outcome == "passed" and control_logs, (
        "control: the same repository and the same command without the "
        f"padding must reach a real verdict ({control_result.outcome!r} / "
        f"{control_result.detail!r}), or the assertions above would pass by "
        "the gate refusing every command"
    )


# --------------------------------------------------------------------------- #
# 2. The second `skipped` producer: the gate's own caller.
# --------------------------------------------------------------------------- #


#: A `.dispatcher.yaml` that declares a test command AND a `roles:` section
#: the loader refuses. The negated glob is the self-weakening policy
#: `role_protocol.role_policy_from_mapping` rejects and `6d39031` wired into
#: `repo_config.load`; before that commit the section landed in `unknown_keys`
#: and this file loaded cleanly.
_CONFIG_WITH_UNREADABLE_SECTION = (
    "test: sh tests/run.sh\n"
    "roles:\n"
    "  bodies:\n"
    "    immutable_paths: ['!**/tests/**']\n"
)

_CONFIG_PLAIN = "test: sh tests/run.sh\n"


def _run_config(tmp_path: Path, journal: journal_mod.Journal) -> orch_mod.RunConfig:
    return orch_mod.RunConfig(
        tasks_path=tmp_path / "tasks.yaml",
        runs_dir=tmp_path / "runs",
        run_id="r", mode="unattended",
        max_parallel=1, max_iterations=1, reviewer_count=None,
        skip_design=False, skip_security_linter=False,
        financial_paths="", claude_bin="claude", worktree_base=None,
        label_filter=plan_mod.parse_label_filter(None), only_keys=None,
        verify_test_timeout_seconds=30,
        journal=journal,
    )


def _journal(tmp_path: Path, name: str) -> journal_mod.Journal:
    """A real run journal — the sink `_emit_event` writes through in production.

    Not a recording double: the reason a fix shipped unsealed is what the
    journal keeps, and the genesis event hashes its provenance inputs, so
    those have to exist.
    """
    tasks_yaml = tmp_path / "tasks.yaml"
    if not tasks_yaml.exists():
        tasks_yaml.write_text("tasks: []\n", encoding="utf-8")
    (tmp_path / "prompts").mkdir(exist_ok=True)
    return journal_mod.Journal.create(
        tmp_path / f"{name}.jsonl",
        tasks_yaml_path=tasks_yaml,
        reviewer_prompts_dir=tmp_path / "prompts",
    )


def _seal_events(journal: journal_mod.Journal) -> list[dict]:
    return [e.payload for e in journal_mod.read_events(journal.path)
            if e.event_type == journal_mod.EventType.verification_seal.value]


def test_a_config_the_gate_could_not_read_is_not_a_repo_with_no_test_command(
    tmp_path: Path,
) -> None:
    """RED — `_verify_seal` switches the gate off, and journals a reason that
    is false.

    Producer two of the gate's `skipped`. `_verify_seal` loads the repo config
    inside a `try`, sets `repo_cfg = None` on `RepoConfigError`, and then
    cannot tell that case apart from a repo that declares no `test:` — so a
    config it could not READ is journaled as `{"outcome": "skipped", "reason":
    "no test command"}` and returns `("skipped", None)`, which the
    orchestrator proceeds on. MEASURED 2026-08-10 at `9ceb6d4`, against a repo
    whose `.dispatcher.yaml` says `test: sh tests/run.sh`.

    That sentence is the same shape the sibling file's ruling 1 closed one
    level down: a positive claim about the repo, made when the loader refused
    to say anything about it, byte-identical to what a repo that really has no
    test command gets. It is worse than the `skipped` inside
    `run_seal_inversion`, because it switches off the seal gate for the whole
    repository rather than for one change, and because the answer is available
    — the file is right there and the command is in it.

    THE SIBLING GETS IT RIGHT. `_verify_mechanical_and_maybe_retry` performs
    the identical `repo_config_mod.load(wt.path)` and disposes of the failure
    itself: it logs the error, journals `{"outcome": "failed", "error": ...}`
    and returns `("failed", err)` with the comment "no retry, because a
    fix-the-tests prompt can't fix a config the dispatcher can't parse". The
    row asserts that too, in the same call: it is the proof that the shape
    asked for here is already agreed in this file, and it reddens if someone
    ever settles the divergence by weakening the mechanical gate instead.

    PRODUCIBLE, and the trigger was WIDENED four days ago. The config carries
    a `roles:` section with a negated glob. Measured by execution on the same
    file: at `6d39031^` `repo_config.load` returns `test='sh tests/run.sh',
    unknown_keys=('roles',)` and the seal gate runs; at `6d39031` it raises
    `RepoConfigError` and the gate stands down. The row proves both halves
    here: the loader really refuses this file, and the identical `test:` on
    the twin really loads.

    Red now: `("skipped", None)` with `reason: "no test command"`.
    Green when: the handler disposes of the failure itself. `error` or
    `failed` both satisfy this row — unlike the two suite-outcome rows above,
    `failed` is defensible here because the sibling gate already chose it for
    exactly this input. SEPARATE body change.
    Falsify: the twin repo, whose only difference is the absence of the
    `roles:` section, is judged in the same call and must reach a real
    verdict — so a `_verify_seal` that blocked every repo reddens on it.
    """
    unreadable = _seal_repo(tmp_path, "unreadable-config",
                            config=_CONFIG_WITH_UNREADABLE_SECTION)
    _commit_fix(unreadable, seal="grep -q fixed code.txt\n")
    twin = _seal_repo(tmp_path, "readable-config", config=_CONFIG_PLAIN)
    _commit_fix(twin, seal="grep -q fixed code.txt\n")

    # Producibility: the loader really refuses this file, and the command it
    # refuses to report is really there.
    with pytest.raises(repo_config_mod.RepoConfigError):
        repo_config_mod.load(unreadable)
    declared = repo_config_mod.load(twin).test
    assert declared == "sh tests/run.sh" and declared in (
        unreadable / repo_config_mod.CONFIG_FILENAME).read_text(
            encoding="utf-8"), (
        "the fixture no longer reproduces the input under test: the refused "
        "config does not declare the same test command its twin loads "
        f"({declared!r})"
    )

    snap = orch_mod.TaskSnapshot(
        key="FIX-1", summary="s", description="d", type="Task",
        labels=["type:fix"], batch_keys=["FIX-1"],
    )

    bad_journal = _journal(tmp_path, "bad")
    bad_outcome, bad_detail = orch_mod._verify_seal(
        _run_config(tmp_path, bad_journal), snap,
        wt_mod.Worktree(path=unreadable, branch="fix/seal"),
        "main", tmp_path / "bad.log",
    )
    good_journal = _journal(tmp_path, "good")
    good_outcome, _good_detail = orch_mod._verify_seal(
        _run_config(tmp_path, good_journal), snap,
        wt_mod.Worktree(path=twin, branch="fix/seal"),
        "main", tmp_path / "good.log",
    )

    [bad_event] = _seal_events(bad_journal)
    assert bad_event.get("reason") != "no test command", (
        "the seal gate journaled that this repo declares no test command, "
        "over a `.dispatcher.yaml` that declares "
        f"{declared!r}: {bad_event!r}. The reason a fix shipped unsealed is "
        "the one thing the journal keeps about this decision, and it is false"
    )
    assert bad_outcome in _BLOCKING, (
        f"the seal gate returned {bad_outcome!r} / {bad_detail!r} for a repo "
        "whose config it could not read, so the whole gate is off for that "
        "repository and nothing downstream can tell"
    )
    assert bad_event.get("outcome") == bad_outcome, (
        "the journal and the caller were told different things about the same "
        f"decision: {bad_event!r} vs {bad_outcome!r}"
    )

    mech_outcome, mech_detail = orch_mod._verify_mechanical_and_maybe_retry(
        _run_config(tmp_path, _journal(tmp_path, "mech")), snap,
        wt_mod.Worktree(path=unreadable, branch="fix/seal"),
        tmp_path / "summary.md", {}, tmp_path / "mech.log",
        cycle=orch_mod._VerificationCycle(),
    )
    assert mech_outcome in _BLOCKING and mech_detail, (
        "the mechanical gate performs the identical read on the identical "
        f"repo and now returns {mech_outcome!r} / {mech_detail!r}: the two "
        "gates have been settled in the wrong direction. An unreadable "
        "config is a refusal, not a repo that opted out"
    )

    assert good_outcome == "passed", (
        "control: the same repository with a readable config must be inverted "
        f"and judged (got {good_outcome!r}), or the assertions above would "
        "pass by `_verify_seal` blocking everything"
    )


# --------------------------------------------------------------------------- #
# 3. The stands-down invariant, extended to the producer it never covered.
# --------------------------------------------------------------------------- #


#: The only reasons `orchestrator._verify_seal` may stand the gate down on.
#: The counterpart of the sibling file's `_APPLICABILITY_SKIPS`, which covers
#: `run_seal_inversion` and only that. Written out rather than counted, so a
#: third reason must be read and agreed to by a human before it can exist.
_VERIFY_SEAL_APPLICABILITY_SKIPS: tuple[str, ...] = (
    "no test command",
)


def _verify_seal_ast() -> ast.FunctionDef:
    source = Path(orch_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename="orchestrator.py")
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_verify_seal")


def _journaled_skip_reasons_in_verify_seal() -> tuple[str, ...]:
    """Every `reason` `_verify_seal` journals beside `outcome: "skipped"`.

    Reads the literal payload dicts, in source order, and refuses a
    non-literal reason: an f-string there would mean the reasons the seal gate
    stands down are no longer readable from the source, which is the sibling
    row's rule applied to this producer.
    """
    reasons: list[str] = []
    for node in ast.walk(_verify_seal_ast()):
        if not isinstance(node, ast.Dict):
            continue
        payload = {
            k.value: v for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant)
        }
        outcome = payload.get("outcome")
        if not (isinstance(outcome, ast.Constant) and outcome.value == "skipped"):
            continue
        reason = payload.get("reason")
        assert isinstance(reason, ast.Constant) and isinstance(
            reason.value, str), (
            "a `skipped` is journaled with a non-literal reason at line "
            f"{node.lineno}; the reasons the seal gate stands down must stay "
            "readable from the source"
        )
        reasons.append(reason.value)
    return tuple(reasons)


def test_the_seal_gate_stands_down_only_on_applicability_in_both_producers(
) -> None:
    """RED — the gate's second producer stands down on a step that FAILED.

    STRUCTURAL, and it says so. `test_seal_verify_failopen.py::
    test_the_gate_stands_down_only_on_the_two_applicability_judgements` states
    the invariant this extends: `skipped` is the gate's only non-blocking
    outcome, so every construction of it is a place the gate can switch itself
    off, and all of them must be judgements ABOUT THE CHANGE rather than
    reports of a step that did not work. That row's sweep reads
    `seal_verify.run_seal_inversion` and nothing else, while the same file's
    `_outcomes_verify_seal_can_return` names `orchestrator._verify_seal` as
    the gate's second producer — so the enumeration and the invariant are
    already out of step by one function, and the uncovered one is the one that
    can turn the gate off for an entire repository.

    Two things are pinned, both about producer two:

      * the ENUMERATION, so the open set cannot grow silently. Today there is
        one journaled reason, `"no test command"`. A future `"worktree gone"`
        or `"base ref missing"` must be read and agreed to here first — the
        `FORBIDDEN_DISPUTED_GLOBS` lesson, which the sibling file applies to
        the other producer.
      * the ANTECEDENT, which is the part that is red. No `except` handler in
        `_verify_seal` may fall through into the function body: a handler that
        assigns and continues merges "the config could not be read" into "the
        config says there is nothing to run", and the merged branch then emits
        an applicability judgement about a step that failed. Today the one
        handler is `except RepoConfigError: repo_cfg = None`, which is exactly
        that fall-through. `_verify_mechanical_and_maybe_retry`'s handler,
        three functions later, ends in `return "failed", err` — the shape this
        asks for, already agreed in this file.

    Deleting the handler entirely also satisfies this row (an unhandled
    `RepoConfigError` reaches the worker's handler and blocks the task), which
    is why the assertion is about the handler's disposal and not about which
    outcome it picks.

    NO TWIN, deliberately: the input is `orchestrator`'s own source, the same
    seam the sibling file's two structural rows use. The behavioural row above
    is the twinned one and reaches the same defect through a real repository;
    this row is what keeps the NEXT reason from arriving unread, which no
    behavioural row can do.

    Producible because: it reads the module's own source and refuses a
    non-literal reason rather than skipping it.

    Red now: the `except repo_config_mod.RepoConfigError` handler ends in
    `repo_cfg = None`.
    Green when: that handler returns (or raises) instead of falling through.
    Falsify: give `_verify_seal` a second journaled `skipped` reason — the
    enumeration reddens; restore the fall-through — the antecedent assertion
    reddens.
    """
    reasons = _journaled_skip_reasons_in_verify_seal()
    assert reasons == _VERIFY_SEAL_APPLICABILITY_SKIPS, (
        "`_verify_seal` stands the seal gate down at sites this seal has not "
        f"agreed to — it journals {list(reasons)!r} against an agreed "
        f"{list(_VERIFY_SEAL_APPLICABILITY_SKIPS)!r}. Every occurrence is a "
        "separate place the gate can switch itself off, so a repeat of an "
        "already-agreed reason is a new site and counts: `skipped` is the "
        "gate's only non-blocking outcome and this is the producer that emits "
        "it for a whole repository at once"
    )

    fell_through = [
        (handler.lineno, ast.unparse(handler.body[-1]))
        for handler in ast.walk(_verify_seal_ast())
        if isinstance(handler, ast.ExceptHandler)
        and not isinstance(handler.body[-1], (ast.Return, ast.Raise))
    ]
    assert not fell_through, (
        "an exception handler in `_verify_seal` falls through into the "
        f"function body instead of disposing of the failure: {fell_through!r}. "
        "Downstream of it sits the gate's one non-blocking outcome, so a step "
        "that FAILED is merged into an applicability judgement about the "
        "change — `skipped`, reason `no test command`, over a repo that has "
        "one. Its sibling `_verify_mechanical_and_maybe_retry` performs the "
        "same read and its handler ends in `return`"
    )
