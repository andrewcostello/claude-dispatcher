"""Seals for the state-machine gate.

The checker existed across three languages and nothing called it. This is the
call, and its scope is the load-bearing decision: it refuses a declaration that
is PRESENT AND WRONG, and says nothing about a unit that has no state machine.
Demanding a declaration everywhere would be ceremony, and ceremony is what makes
a gate get switched off.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from claude_dispatcher import (
    orchestrator as orch,
    ts_state_machine,
    worktree as wt_mod,
)

GOOD = '''
from enum import Enum


class S(Enum):
    A = "a"
    DONE = "done"


class E(Enum):
    GO = "go"


STATE_MACHINE = {
    "name": "m", "state_enum": "S", "event_enum": "E",
    "initial": "A", "terminal": ["DONE"],
    "transitions": [{"from": "A", "event": "GO", "to": "DONE"}],
}
'''

# Present and WRONG: adding an event leaves (A x STOP) neither declared nor
# covered by a default_rejection, so the machine stops being total.
BAD = GOOD.replace('class E(Enum):\n    GO = "go"',
                   'class E(Enum):\n    GO = "go"\n    STOP = "stop"')
assert BAD != GOOD, "the BAD fixture must actually differ from GOOD"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True)
    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")
    (repo / "seed.txt").write_text("x\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "seed")
    return repo


def _commit(repo: Path, name: str, body: str) -> str:
    (repo / name).write_text(body)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", name], cwd=repo, check=True,
                   capture_output=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def _check(tmp_path, files: dict[str, str], monkeypatch):
    monkeypatch.setattr(orch, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_log", lambda *a, **k: None)
    repo = _repo(tmp_path)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    for name, body in files.items():
        _commit(repo, name, body)
    wt = wt_mod.Worktree(path=repo, branch="main")
    snap = SimpleNamespace(key="T-1")
    return orch._check_state_machines(SimpleNamespace(), snap, wt, base, tmp_path / "log")


def test_a_valid_declaration_passes(tmp_path, monkeypatch) -> None:
    assert _check(tmp_path, {"m.py": GOOD}, monkeypatch) is None


def test_a_declaration_that_is_present_and_WRONG_blocks(tmp_path, monkeypatch) -> None:
    """Adding an event leaves (A x STOP) neither declared nor defaulted, so the
    machine stops being total.

    Measured under: return None instead of the reason and this reddens — the
    checker would run, journal, and decide nothing.
    """
    reason = _check(tmp_path, {"m.py": BAD}, monkeypatch)
    assert reason is not None
    assert reason.startswith("state_machine_invalid:")
    assert "m.py" in reason


def test_a_branch_with_NO_declaration_is_silent(tmp_path, monkeypatch) -> None:
    """The scope decision. Most units have no state machine, and demanding one
    everywhere is ceremony — which is what gets a gate switched off.

    Measured under: block when `checked == 0` and every ordinary task fails.
    """
    assert _check(tmp_path, {"plain.py": "def f():\n    return 1\n"},
                  monkeypatch) is None


def test_a_file_the_branch_did_not_touch_is_not_judged(tmp_path, monkeypatch) -> None:
    """Scoped to the branch's own diff. A pre-existing invalid declaration
    elsewhere is not this task's to answer for — the same reason
    `branch_reachability` judges a DELTA rather than a tree, where a whole-tree
    gate was red on an untouched checkout from its first commit.
    """
    monkeypatch.setattr(orch, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_log", lambda *a, **k: None)
    repo = _repo(tmp_path)
    _commit(repo, "old_bad.py", BAD)                     # already on the branch
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    _commit(repo, "new_ok.py", GOOD)                     # what this task changed
    wt = wt_mod.Worktree(path=repo, branch="main")
    assert orch._check_state_machines(
        SimpleNamespace(), SimpleNamespace(key="T-1"), wt, base, tmp_path / "log"
    ) is None


def test_it_never_raises_on_a_broken_repo_or_toolchain(tmp_path, monkeypatch) -> None:
    """A reader that cannot run is a MACHINE fault, already named by
    GoHelperUnavailable / TsHelperUnavailable. Blocking a task on a missing Go
    toolchain would punish the branch for the operator's environment.
    """
    monkeypatch.setattr(orch, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_log", lambda *a, **k: None)
    gone = wt_mod.Worktree(path=tmp_path / "nope", branch="main")
    assert orch._check_state_machines(
        SimpleNamespace(), SimpleNamespace(key="T-1"), gone, "HEAD", tmp_path / "log"
    ) is None


def test_a_readers_own_failure_does_not_become_a_verdict(tmp_path, monkeypatch) -> None:
    """The INNER guard, which the broken-repo row above never reaches: git
    succeeds, the file is found, and the READER raises — no Go toolchain, an
    unreadable vendored parser, a helper that will not build.

    That is a machine fault with its own name (GoHelperUnavailable /
    TsHelperUnavailable) and it must not fail the branch. Blocking here would
    punish a task for the operator's environment.

    Measured under: narrow the inner `except Exception` and this reddens.
    """
    from claude_dispatcher import state_machine as sm_mod

    def _boom(*a, **k):
        raise RuntimeError("toolchain unavailable")

    monkeypatch.setattr(sm_mod, "check", _boom)
    assert _check(tmp_path, {"m.py": BAD}, monkeypatch) is None


def test_a_whole_tree_scan_would_judge_untouched_files(tmp_path, monkeypatch) -> None:
    """Companion to the delta row, and the one that actually catches a whole-tree
    scan: an invalid declaration that predates the branch is present in the
    worktree, so a checker reading the TREE would block on it while a checker
    reading the DIFF stays silent.

    Measured under: swap the diff range for `git ls-files` and this reddens.
    """
    monkeypatch.setattr(orch, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_log", lambda *a, **k: None)
    repo = _repo(tmp_path)
    _commit(repo, "old_bad.py", BAD)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    _commit(repo, "unrelated.txt", "no python here\n")
    assert (repo / "old_bad.py").exists(), "the invalid declaration is in the tree"
    wt = wt_mod.Worktree(path=repo, branch="main")
    assert orch._check_state_machines(
        SimpleNamespace(), SimpleNamespace(key="T-1"), wt, base, tmp_path / "log"
    ) is None


def test_it_runs_before_the_suite() -> None:
    """Cheap, and it frames the expensive step: a branch whose declared machine is
    not total has not produced something worth spending 160s of suite on.
    """
    src = Path(orch.__file__).read_text()
    sm_at = src.index("sm_reason = _check_state_machines(")
    mech_at = src.index("mech_outcome, mech_detail = _verify_mechanical_and_maybe_retry(")
    assert sm_at < mech_at


def test_it_applies_to_every_role_not_only_scaffold() -> None:
    """A declared machine must stay valid whoever edits it, and the phase that
    breaks one is not necessarily the phase that wrote it.

    Measured under: guard the call on `role is SCAFFOLD` and this reddens.
    """
    src = Path(orch.__file__).read_text()
    at = src.index("sm_reason = _check_state_machines(")
    preceding = src[max(0, at - 400):at]
    assert "HOLE_CHECKED_ROLES" not in preceding
    assert "Role.SCAFFOLD" not in preceding


# --------------------------------------------------------------------------
# The other two languages. Go is the target repo (bay-session); Python was the
# proof of the format. Nothing sealed that the gate reaches either, and it did
# not: the prefilter used Python's spelling for every language, so every Go
# file was skipped in silence. Found by the mutation "only .py is checked"
# firing no row at all.
# --------------------------------------------------------------------------

GO_BAD = '''package baysession

type BetState string

const (
\tBetStateAccepted BetState = "accepted"
\tBetStateSettled  BetState = "settled"
)

type BetEvent int

const (
\tBetEventGo BetEvent = iota
\tBetEventStop
)

const StateMachine = `{
  "name": "m", "state_enum": "BetState", "event_enum": "BetEvent",
  "initial": "BetStateAccepted", "terminal": ["BetStateSettled"],
  "transitions": [
    {"from": "BetStateAccepted", "event": "BetEventGo", "to": "BetStateSettled"}
  ]
}`
'''

TS_BAD = '''export enum BetState {
  Accepted = "accepted",
  Settled = "settled",
}

export type BetEvent = "go" | "stop";

export const STATE_MACHINE = {
  name: "m",
  state_enum: "BetState",
  event_enum: "BetEvent",
  initial: "Accepted",
  terminal: ["Settled"],
  transitions: [
    { from: "Accepted", event: "go", to: "Settled" },
  ],
} as const;
'''


def test_the_go_spelling_matches_the_go_helper() -> None:
    """`go_state_machine.DECLARATION_NAME` must equal `declName` in main.go.

    These are two files in two languages that have to agree. If they drift, the
    prefilter looks for a name the helper never reads (or the reverse) and Go
    files are skipped in silence — no fault, no log, a green gate.
    """
    from claude_dispatcher import go_state_machine as gsm

    src = (Path(gsm.__file__).parent / "go_state_machine" / "main.go").read_text()
    assert f'const declName = "{gsm.DECLARATION_NAME}"' in src


@pytest.mark.skipif(shutil.which("go") is None, reason="no Go toolchain")
def test_a_go_declaration_is_checked_too(tmp_path: Path, monkeypatch) -> None:
    """End to end, with the real Go toolchain: an invalid machine in a .go file
    blocks the branch.

    Measured under: restrict the extension filter to `.py`, or prefilter Go on
    Python's `STATE_MACHINE` spelling, and this reddens. The second mutation is
    the bug this row was written to catch — it was live.
    """
    reason = _check(tmp_path, {"bay.go": GO_BAD}, monkeypatch)
    assert reason is not None, "an invalid Go machine must block"
    assert "bay.go" in reason


@pytest.mark.skipif(
    shutil.which("node") is None
    or not (Path(ts_state_machine.__file__).parent
            / "ts_signature_fingerprint" / "typescript.js").exists(),
    reason="no node, or the vendored TS parser is not provisioned",
)
def test_a_typescript_declaration_is_checked_too(tmp_path: Path, monkeypatch) -> None:
    """The third language, end to end. Measured under: restrict the extension
    filter to `.py` and this reddens.
    """
    reason = _check(tmp_path, {"bay.ts": TS_BAD}, monkeypatch)
    assert reason is not None, "an invalid TS machine must block"
    assert "bay.ts" in reason


# A VALID declaration in each language must be SILENT. These are the rows that
# actually seal ROUTING: an invalid file blocks even when misrouted, because the
# wrong reader also fails on it. Only a valid machine tells the two apart — the
# wrong reader turns it into a false block, and a gate with false positives is a
# gate that gets switched off.

GO_GOOD = GO_BAD.replace(
    '"terminal": ["BetStateSettled"],',
    '"terminal": ["BetStateSettled"], "default_rejection": "IllegalTransition",')

TS_GOOD = TS_BAD.replace(
    '  terminal: ["Settled"],',
    '  terminal: ["Settled"],\n  default_rejection: "IllegalTransition",')


@pytest.mark.skipif(shutil.which("go") is None, reason="no Go toolchain")
def test_a_valid_go_declaration_is_silent(tmp_path: Path, monkeypatch) -> None:
    """Measured under: route .go to the Python reader and this reddens — Python
    cannot read Go, reports a fault, and a correct machine gets blocked.
    """
    assert GO_GOOD != GO_BAD
    assert _check(tmp_path, {"bay.go": GO_GOOD}, monkeypatch) is None


@pytest.mark.skipif(
    shutil.which("node") is None
    or not (Path(ts_state_machine.__file__).parent
            / "ts_signature_fingerprint" / "typescript.js").exists(),
    reason="no node, or the vendored TS parser is not provisioned",
)
def test_a_valid_typescript_declaration_is_silent(tmp_path: Path, monkeypatch) -> None:
    """Measured under: route .ts to the Python reader and this reddens."""
    assert TS_GOOD != TS_BAD
    assert _check(tmp_path, {"bay.ts": TS_GOOD}, monkeypatch) is None


def test_a_file_that_only_MENTIONS_the_name_is_silent(tmp_path, monkeypatch) -> None:
    """The prefilter is a substring search, so it also catches files that talk
    ABOUT state machines without declaring one — this gate's own module does,
    and so will any doc, test helper or comment in a judged repo.

    Those parse to `Fault.NO_DECLARATION`, which is "nothing to check", not "the
    declaration is wrong". Treating it as a fault would block every branch that
    edited a file merely naming the constant.

    Measured under: drop the NO_DECLARATION filter and this reddens.
    """
    mentions = (
        "# The gate looks for a module-level STATE_MACHINE literal.\n"
        "STATES = ['a', 'b']\n"
        "def describe() -> str:\n"
        "    return 'this module has no STATE_MACHINE of its own'\n"
    )
    assert "STATE_MACHINE" in mentions
    assert _check(tmp_path, {"talks_about_it.py": mentions}, monkeypatch) is None


@pytest.mark.skipif(shutil.which("go") is None, reason="no Go toolchain")
def test_a_go_file_that_only_MENTIONS_the_name_is_silent(
    tmp_path, monkeypatch
) -> None:
    """Same rule in Go, where the spelling differs and the mention is likelier —
    `StateMachine` is an ordinary identifier a Go repo may use for a type or a
    field without ever declaring the gate's literal.
    """
    mentions = (
        "package baysession\n\n"
        "// StateMachine drives the session; its declaration lives elsewhere.\n"
        "type StateMachineRunner struct{ name string }\n"
    )
    assert _check(tmp_path, {"runner.go": mentions}, monkeypatch) is None
