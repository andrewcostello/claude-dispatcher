"""Seal: `orchestrator.execute` really produces, prints and replays the D1
build-protocol correlation warning.

Why this file exists
--------------------
`role_protocol.py`'s docstring claims, under "Wired by P3", that
``orchestrator.execute`` calls :func:`role_protocol.agent_correlation_warnings`
"alongside the preflight warnings (printed at run start and replayed into
run.log once it exists)". Until this file, that claim was pinned by exactly one
mechanism: the AST call-site scan in ``test_role_protocol_wiring.py``
(``test_every_wired_by_p3_claim_has_its_call_site``). That scan proves a call
*expression* exists in the source. It proves nothing about the three things the
sentence actually promises:

  * that a warning is *produced* for a worklist that deserves one,
  * that it is *printed* at run start,
  * that it is *replayed* into ``run.log``.

A call whose result is dropped on the floor, a warning loop deleted, or a
``run.log`` replay that stops writing all leave the AST row green. That is a
claim verified by hand and disclosed as unsealed — the exact shape that rotted
twice in this repo already. So it gets a mechanism.

The shape, and why
------------------
``execute`` is stubbed at exactly one seam: ``orchestrator._run_loop``, the
final ``return`` of ``execute``. Everything before that seam is the real thing —
the real ``_build_config``, the real ``plan.load_tasks``, the real
``role_protocol.validate``, the real ``agent_correlation_warnings`` call, the
real ``_effective_implementer``, the real ``run_dir`` creation and the real
``_log`` replay. Nothing is spawned, no worktree is created, and git is touched
only by the fixture's ``git init``. ``--skip-preflight`` keeps the run from
probing for agent binaries it will never use.

The alternative was the hermetic end-to-end (``test_no_claude_e2e.py``), which
reaches the same code by spawning a fake agent through a real worktree. It buys
nothing this seal needs and costs seconds plus the flakiness of real subprocess
and git plumbing.

Non-vacuity is not assumed. Every row here has been mutation-verified against a
throwaway clone of the tree: deleting the ``agent_correlation_warnings`` call,
deleting the ``print`` loop, deleting the ``_log`` replay loop, flipping the
``--no-claude`` implementer default from grok to claude, hardcoding it to grok,
and replacing the family intersection with a union each redden a specific,
different row. The stub is deliberately thin enough that ``rc == 0`` plus
``_run_loop`` having been reached is itself asserted: a row that passes because
``execute`` bailed out early is not a passing row.

That exercise found something the hand-verification did not — see the note
above row 3 — namely that ``_effective_implementer``'s ``--no-claude`` ternary
is dead code on every argparse-driven path, because ``_build_config`` resolves
the default first. The live rule and the unreachable fallback are now pinned
separately.

Status on commit: GREEN. Unlike most of unit D1's seals, this one pins wiring
that already landed (P3). It is green-because-correct, not green-because-weak —
see the mutation log in the commit message.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from claude_dispatcher import orchestrator
from claude_dispatcher.cli import build_parser


# The warning `agent_correlation_warnings` emits reaches the operator twice,
# through two different mechanisms that fail independently: a stderr print
# before `run.log` exists, and a replay into `run.log` once it does. Both
# prefixes are pinned here because a rename of either is a change to the
# operator-visible contract the docstring describes, not an implementation
# detail.
STDERR_PREFIX = "warning: role protocol: "
LOG_PREFIX = "role protocol warning: "


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A one-commit git repo. `execute` needs a repo root and a base branch."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "seed")
    return root


def _row(key: str, role: str, *, agent: str | None = None,
         blocked_by: str | None = None) -> str:
    lines = [
        f"  - key: {key}",
        f"    summary: \"{role} for the correlation-warning seal\"",
        "    description: \"a row that exists to be validated, never run\"",
        "    type: Task",
        "    labels: [size:XS]",
        f"    role: {role}",
    ]
    if agent is not None:
        lines.append(f"    agent: {agent}")
    if blocked_by is not None:
        lines.append(f"    blockedBy: [{blocked_by}]")
    return "\n".join(lines) + "\n"


def _worklist(*, seals_agent: str | None, bodies_agent: str | None) -> str:
    """A single scaffold->seals->bodies unit, U-1, with the given pins.

    `None` means the row states no `agent:` at all — which is the case that
    matters, because that is the row whose family comes from the run-level
    implementer rather than from the file.
    """
    return (
        "project: T\n"
        "epic: U\n"
        "tasks:\n"
        + _row("U-1", "scaffold")
        + _row("U-2", "seals", agent=seals_agent, blocked_by="U-1")
        + _row("U-3", "bodies", agent=bodies_agent, blocked_by="U-2")
    )


@dataclass(frozen=True)
class Run:
    """What one stubbed `execute` produced."""

    rc: int
    stderr: str
    log: str
    reached_run_loop: bool

    def stderr_role_warnings(self) -> list[str]:
        return [line for line in self.stderr.splitlines()
                if line.startswith(STDERR_PREFIX)]

    def logged_role_warnings(self) -> list[str]:
        return [line for line in self.log.splitlines() if LOG_PREFIX in line]


def _execute(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    worklist: str,
    run_id: str,
    extra_args: tuple[str, ...] = (),
) -> Run:
    """Drive the REAL `execute` up to (and not into) the task loop.

    The only seam stubbed is `_run_loop`. Everything the warning depends on —
    config build, `plan.load_tasks`, `role_protocol.validate`,
    `agent_correlation_warnings`, `_effective_implementer`, run-dir creation,
    the `run.log` replay — is the production path.
    """
    tasks = repo / f"{run_id}.yaml"
    tasks.write_text(worklist, encoding="utf-8")

    reached: list[bool] = []

    def _stub_run_loop(cfg, run_dir, log_path, repo_root):  # noqa: ANN001
        reached.append(True)
        return 0

    monkeypatch.setattr(orchestrator, "_run_loop", _stub_run_loop)

    runs_dir = tmp_path / "_runs"
    args = build_parser().parse_args([
        "run", str(tasks),
        "--mode", "unattended",
        "--run-id", run_id,
        "--runs-dir", str(runs_dir),
        "--worktree-base", str(tmp_path / "wt"),
        "--skip-preflight",
        *extra_args,
    ])

    capsys.readouterr()  # discard anything emitted by fixture setup
    rc = orchestrator.execute(args)
    captured = capsys.readouterr()

    log_path = runs_dir / run_id / "run.log"
    return Run(
        rc=rc,
        stderr=captured.err,
        log=log_path.read_text(encoding="utf-8") if log_path.exists() else "",
        reached_run_loop=bool(reached),
    )


def _assert_ran_for_real(run: Run) -> None:
    """The stub must not be how a row passes.

    `execute` has several early `return 2` paths before the warning block
    (invalid YAML, endpoint-agent pins, a failed preflight). A row that never
    reached the warning block would satisfy "no warning was printed" for
    entirely the wrong reason, so every row asserts the run got all the way to
    the seam instead.
    """
    assert run.reached_run_loop, (
        "execute() returned before reaching _run_loop, so it never reached the "
        "correlation-warning block. Whatever this row asserted, it did not "
        f"assert it about the warning. rc={run.rc}\nstderr:\n{run.stderr}"
    )
    assert run.rc == 0, f"stubbed execute should return the stub's 0, got {run.rc}"
    assert run.log, "execute() created no run.log, so there is no replay to check"


# --------------------------------------------------------------------------- #
# 1. the warning is produced and printed
# --------------------------------------------------------------------------- #


def test_execute_prints_the_correlation_warning(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A unit whose seals and bodies share a family warns on stderr at run start.

    Pins the *production* of the warning, which the AST call-site row cannot:
    that row stays green if the call's result is assigned and never used.

    Falsify: delete the `for warning in role_warnings: print(...)` loop in
    `execute`, or delete the `agent_correlation_warnings(...)` call itself —
    either reddens this row.
    """
    run = _execute(
        repo, tmp_path, monkeypatch, capsys,
        worklist=_worklist(seals_agent=None, bodies_agent=None),
        run_id="shared-family-printed",
        extra_args=("--no-claude",),
    )
    _assert_ran_for_real(run)

    printed = run.stderr_role_warnings()
    assert len(printed) == 1, (
        "expected exactly one role-protocol warning on stderr for a one-unit "
        f"worklist whose seals and bodies share a family, got {printed!r}\n"
        f"full stderr:\n{run.stderr}"
    )
    assert "unit U-1: seals (U-2) and bodies (U-3) share model family 'grok'" \
        in printed[0], (
        "the warning must name the unit, both sides, and the shared family — "
        "that is what makes it actionable rather than decorative. Got:\n"
        f"  {printed[0]}"
    )


# --------------------------------------------------------------------------- #
# 2. it is replayed into run.log
# --------------------------------------------------------------------------- #


def test_execute_replays_the_correlation_warning_into_run_log(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The docstring promises a run.log replay, so run.log is read.

    The stderr print and the run.log replay are two separate loops over the
    same tuple, written at two different points in `execute` (before and after
    `run_dir` exists). They fail independently: the replay is the one an
    operator reads after the fact, and it is the one the "Wired by P3" sentence
    explicitly claims.

    Falsify: delete the `for warning in role_warnings: _log(...)` loop — row 1
    stays green and this one reddens, which is why it is a separate row.
    """
    run = _execute(
        repo, tmp_path, monkeypatch, capsys,
        worklist=_worklist(seals_agent=None, bodies_agent=None),
        run_id="shared-family-replayed",
        extra_args=("--no-claude",),
    )
    _assert_ran_for_real(run)

    replayed = run.logged_role_warnings()
    assert len(replayed) == 1, (
        "expected exactly one 'role protocol warning:' line in run.log, got "
        f"{replayed!r}\nfull run.log:\n{run.log}"
    )
    assert "unit U-1: seals (U-2) and bodies (U-3) share model family 'grok'" \
        in replayed[0], (
        "the replayed line must carry the same actionable text as the printed "
        f"one, not a summary. Got:\n  {replayed[0]}"
    )


# --------------------------------------------------------------------------- #
# 3. the --no-claude -> grok resolution, pinned through behaviour
# --------------------------------------------------------------------------- #
#
# This is the arm the wiring author flagged as most likely to rot silently. If
# `_effective_implementer` resolved the run-level default to claude under
# `--no-claude`, an unpinned row would be compared as claude while the
# dispatcher actually spawns grok — the families would stop matching, the
# warning would never fire, and a seal that only ever checked "shared family
# warns" would still be green because it happened to use two unpinned rows.
#
# So the resolution is pinned by a worklist that can only warn if the default
# is grok: seals are pinned `agent: grok` and bodies state no agent at all.
# Same-default -> intersection -> warn. Wrong default -> {grok} vs {claude} ->
# silence. The mirror case (row 4) pins the other direction.
#
# WHERE the resolution actually happens is not where the code reads like it
# happens, and mutation testing is how that surfaced. `_effective_implementer`
# ends in `return "grok" if cfg.no_claude else "claude"`, and its docstring
# presents that line as the --no-claude rule. It is not: `_build_config`
# already does `if no_claude and not implementer: implementer = "grok"`, so by
# the time `_effective_implementer` runs on any argparse-driven path (execute
# and resume_run both build their config there) `cfg.implementer` is populated
# and the function returns from its FIRST branch. Flipping the ternary to
# "claude" changes nothing observable — every row in this file stays green.
# Flipping `_build_config`'s default reddens rows 1-3.
#
# Both are therefore pinned, separately and by name: the live one through
# behaviour (rows 1-4), the unreachable one directly (row 3c). Sealing only the
# line the wiring note pointed at would have sealed dead code.


def test_no_claude_resolves_an_unpinned_row_to_grok(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unpinned bodies row correlates with an `agent: grok` seals row.

    The only way this warning fires is if the run-level default an unstated
    `agent:` resolves to is grok. It is a behavioural pin, not an assertion
    about a private helper: it fails for the reason that matters (the compared
    family diverges from the family that will really be spawned) rather than
    because a function was renamed.

    Falsify: change `_effective_implementer`'s `--no-claude` branch to return
    "claude" — this row reddens and row 4 reddens the opposite way.
    """
    run = _execute(
        repo, tmp_path, monkeypatch, capsys,
        worklist=_worklist(seals_agent="grok", bodies_agent=None),
        run_id="no-claude-default-grok",
        extra_args=("--no-claude",),
    )
    _assert_ran_for_real(run)

    printed = run.stderr_role_warnings()
    assert len(printed) == 1 and "share model family 'grok'" in printed[0], (
        "an unpinned row under --no-claude must be compared as grok, the "
        "family the dispatcher will really spawn. No warning here means the "
        "run-level default resolved to something else — every other row in "
        "this file would still pass, and the warning would be dead in "
        f"production. stderr:\n{run.stderr}"
    )
    assert run.logged_role_warnings(), "and it must reach run.log too"


def test_claude_default_does_not_make_an_unpinned_row_grok(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The mirror: without --no-claude, the same worklist is cross-family.

    Row 3 alone is satisfied by a default hardcoded to grok regardless of the
    flag. This row is the other half: the default must *follow* the flag, so a
    claude-default run sees `agent: grok` seals and an unpinned (claude) bodies
    row as two families and stays silent.

    Falsify: hardcode `_effective_implementer` to "grok" — row 3 stays green
    and this one reddens.
    """
    run = _execute(
        repo, tmp_path, monkeypatch, capsys,
        worklist=_worklist(seals_agent="grok", bodies_agent=None),
        run_id="claude-default-cross-family",
        extra_args=(),
    )
    _assert_ran_for_real(run)

    assert run.stderr_role_warnings() == [], (
        "a grok seals row and a claude-default bodies row are two families; "
        f"warning about them is a false positive. stderr:\n{run.stderr}"
    )
    assert run.logged_role_warnings() == [], (
        f"and nothing should be replayed either. run.log:\n{run.log}"
    )


def test_build_config_is_where_no_claude_becomes_grok(
    repo: Path, tmp_path: Path,
) -> None:
    """The live resolution, pinned at the place it actually happens.

    Rows 1-3 prove the warning compares an unpinned row as grok. This row names
    the mechanism, so a refactor that moves the default out of `_build_config`
    has to move it somewhere the behavioural rows still see — and if it moves
    it nowhere, the failure message says which function stopped doing it rather
    than leaving three rows failing for an unexplained reason.

    Falsify: change `_build_config`'s `implementer = "grok"` to "claude".
    """
    args = build_parser().parse_args([
        "run", str(repo / "unused.yaml"), "--mode", "unattended", "--no-claude",
        "--run-id", "cfgprobe", "--runs-dir", str(tmp_path / "_runs"),
    ])
    cfg = orchestrator._build_config(args)
    assert cfg.implementer == "grok", (
        "--no-claude must fill the run-level implementer with grok at config "
        "build time. `_effective_implementer` reads this field first, so a "
        f"wrong value here is the value the warning compares against. Got "
        f"{cfg.implementer!r}"
    )
    assert orchestrator._effective_implementer(cfg) == "grok"


def test_effective_implementer_fallback_is_grok_under_no_claude(
    repo: Path, tmp_path: Path,
) -> None:
    """`_effective_implementer`'s own --no-claude fallback, pinned as such.

    This branch is UNREACHABLE from the CLI: `_build_config` never leaves
    `implementer` blank when `no_claude` is set, so the ternary at the end of
    `_effective_implementer` only fires for a `RunConfig` built by hand. It is
    sealed anyway, and deliberately in its own row, because a defensive default
    nobody exercises is exactly the kind of thing that gets "simplified" to
    claude by someone who cannot see what depends on it — and the day a caller
    does construct a config directly, a silent flip here makes the correlation
    warning compare a family the dispatcher will never spawn.

    Blanking the field is not a mutation of the source: it is the input state
    the branch exists to handle.

    Falsify: change the ternary to `return "claude"`.
    """
    args = build_parser().parse_args([
        "run", str(repo / "unused.yaml"), "--mode", "unattended", "--no-claude",
        "--run-id", "cfgprobe2", "--runs-dir", str(tmp_path / "_runs"),
    ])
    cfg = orchestrator._build_config(args)

    cfg.implementer = None
    assert orchestrator._effective_implementer(cfg) == "grok", (
        "a --no-claude run with no run-level implementer must fall back to "
        "grok, the family it will really spawn — not claude, the family it "
        "was told not to use"
    )
    cfg.no_claude = False
    assert orchestrator._effective_implementer(cfg) == "claude", (
        "and without --no-claude the same blank field falls back to claude; "
        "a fallback that ignores the flag is the mirror-image bug"
    )
    cfg.implementer = "  GROK  "
    assert orchestrator._effective_implementer(cfg) == "grok", (
        "an explicit implementer wins over both fallbacks, case- and "
        "whitespace-insensitively, because the family name is compared "
        "verbatim against role_protocol's `_agent_family`"
    )


# --------------------------------------------------------------------------- #
# 4. the control: cross-family worklists produce no warning
# --------------------------------------------------------------------------- #


def test_cross_family_worklist_produces_no_warning(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both sides explicitly pinned, to different families: silence.

    Without this row, `role_warnings = ("...",)` — an unconditional warning —
    satisfies rows 1, 2 and 3. This is the row that makes the other three mean
    "warns *when it should*" instead of "warns".

    Both pins are explicit here, so unlike row 4's mirror this control holds
    whatever the run-level default resolves to: it isolates the correlation
    rule from the resolution rule.

    Falsify: make `agent_correlation_warnings` warn unconditionally, or drop
    the family intersection and warn on every unit — this reddens.
    """
    run = _execute(
        repo, tmp_path, monkeypatch, capsys,
        worklist=_worklist(seals_agent="claude", bodies_agent="grok"),
        run_id="cross-family-control",
        extra_args=("--no-claude",),
    )
    _assert_ran_for_real(run)

    assert run.stderr_role_warnings() == [], (
        "seals pinned to claude and bodies pinned to grok share no family; a "
        f"warning here is a false positive. stderr:\n{run.stderr}"
    )
    assert run.logged_role_warnings() == [], (
        "and no replay should reach run.log — a warning nobody can act on is "
        f"noise in the artifact operators read after the fact. run.log:\n{run.log}"
    )
