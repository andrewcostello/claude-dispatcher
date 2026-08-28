"""W2-1-2b seals: each journal-less entry point, by executing it.

One row per member of ``prompt_provenance.UNANCHORED_ENTRY_POINTS``. Each row
RUNS the function that owns the listed ``cfr.run_panel`` call — with the
reviewer CLIs, the implementer spawn and the repositories replaced by
stand-ins, and NOTHING between the entry point and
``cross_family_reviewer._load_prompt`` replaced — then reads the state the run
left behind: the declaration the process holds and the load records the gate
reported. No source is read; a declaration that did not execute leaves no
declaration, and the gate's default refusal is what the row then observes.

Green means the entry point's OWN RUN declared itself journal-less, under the
register row for its file, before the prompt loaded — every load record is
``LOAD_UNANCHORED_DECLARED`` quoting that declaration's reason — and the panel
completed. State is cleared after the tool module is imported and before it is
driven, so a declaration made at import time reads as absent: an import is
made by whoever imports the module, not by the entry point.

Until W2-1-3 lands ``check_prompt_tree`` and wires it, every entry point loads
silently: a completed panel, no declaration, no record. EXACTLY that shape is
recorded xfail while the gate is still the W2-1-1 stub; any other outcome
under the stub — a declaration with no record, a record, a refusal, an error —
is a failure, and a row completing under the stub is a strict XPASS failure.
"""

from __future__ import annotations

import contextlib
import functools
import importlib.util
import io
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

import pytest

from claude_dispatcher import cross_family_reviewer as cfr
from claude_dispatcher import plan as plan_mod
from claude_dispatcher import prompt_provenance as pp
from claude_dispatcher import spawn as spawn_mod

ROOT = Path(__file__).resolve().parent.parent

#: The register rows this file seals, by the file each names. A row's ``who``
#: must be the register entry, so the line number lives in ONE place — the
#: register — and this file does not go stale when W2-1-3 shifts the call.
_ENTRY_FILES = (
    "src/claude_dispatcher/bakeoff.py",
    "tools/cross_family_panel.py",
    "tools/retroactive_sweep.py",
)


def _register_row(entry_file: str) -> str:
    rows = [r for r in pp.UNANCHORED_ENTRY_POINTS if r.startswith(entry_file + ":")]
    assert len(rows) == 1, f"{entry_file} has {len(rows)} register rows: {rows}"
    return rows[0]


# --------------------------------------------------------------------------- #
# Is the gate still the W2-1-1 stub? Probed on first use, not at collection.
# --------------------------------------------------------------------------- #


_STUB_SIGNATURE = "this scaffold fixes the contract (W2-1-1)"


@functools.cache
def _gate_is_stub() -> bool:
    """True only while ``check_prompt_tree`` ends in its own P1 stub raise:
    exactly ``NotImplementedError``, innermost frame that seam in
    ``prompt_provenance.py``, the scaffold's message. Anything else — a
    decision, a refusal, a ``NotImplementedError`` from elsewhere — means a
    body landed and the rows run plainly."""
    probe = pp.TreeSnapshot(
        tree_dir="<probe>", what="probe tree", members=(("a.md", b"probe\n"),)
    )
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            pp.check_prompt_tree(probe)
    except NotImplementedError as e:
        if _STUB_SIGNATURE not in str(e) or e.__traceback__ is None:
            return False
        tb = e.__traceback__
        while tb.tb_next is not None:
            tb = tb.tb_next
        code = tb.tb_frame.f_code
        return (
            code.co_name == "check_prompt_tree"
            and Path(code.co_filename).resolve() == Path(pp.__file__).resolve()
        )
    except Exception:  # noqa: BLE001 — any other outcome is a landed body
        return False
    finally:
        pp.clear_anchors()
    return False


# --------------------------------------------------------------------------- #
# Stand-ins for what the entry points reach that is not the prompt load
# --------------------------------------------------------------------------- #


_APPROVE_OUTPUT = textwrap.dedent("""\
    ## Verdict
    APPROVE

    ## Dimension scores
    - Correctness: 5
    - Security: 4
    - Compliance: 4
    - Resilience: 4
    - Idempotency: 4
    - Observability: 4
    - Performance: 4
    - Maintainability: 4

    ## Findings
""")


class _ApprovingReviewer:
    """A seat that answers APPROVE to whatever prompt it is handed. The prompt
    it is handed is still built by ``build_review_prompt`` → ``_load_prompt``,
    which is the path under seal."""

    def __init__(self, family: str) -> None:
        self.family = family

    def review(self, prompt: str) -> cfr.ReviewerVerdict:
        assert prompt.strip(), "the panel handed a reviewer an empty prompt"
        return cfr.parse_review_output(self.family, _APPROVE_OUTPUT)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=seal", "-c", "user.email=seal@example.invalid",
         *args],
        cwd=str(cwd), check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def two_commit_repo(tmp_path: Path) -> Path:
    """A repo on ``main`` whose HEAD has one parent and a non-empty diff to it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")
    return repo


@pytest.fixture
def approving_panel(monkeypatch: pytest.MonkeyPatch) -> list[_ApprovingReviewer]:
    """``bakeoff`` and ``retroactive_sweep`` seat ``cfr.default_reviewers``;
    those seats are the CLIs. Replace them at the seam both read."""
    seats = [_ApprovingReviewer("codex"), _ApprovingReviewer("grok")]
    monkeypatch.setattr(cfr, "default_reviewers", lambda *_a, **_k: list(seats))
    return seats


def _load_tool(name: str) -> ModuleType:
    """Import ``tools/<name>.py`` as a module, the way ``python tools/x.py``
    would execute it minus ``__main__``."""
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_w2_1_2b_{name}", path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


# --------------------------------------------------------------------------- #
# Driving an entry point, and what it leaves behind
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Outcome:
    """What the entry point itself reported."""

    #: The panel reached a consensus and the entry point returned normally.
    panel_ran: bool
    #: The consensus, or the error the entry point surfaced.
    detail: str


@dataclass(frozen=True)
class Observation:
    outcome: Outcome
    records: tuple[pp.PromptLoadRecord, ...]
    declaration: pp.UnanchoredDeclaration | None
    anchors: tuple[pp.Anchor, ...]


Hook = Callable[[], None]


def _drive_bakeoff(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                   after_import: Hook) -> Outcome:
    from claude_dispatcher import bakeoff

    after_import()
    def spawn_that_commits(*, cwd: Path, **_kw) -> spawn_mod.SpawnResult:
        (cwd / "work.txt").write_text("done\n", encoding="utf-8")
        _git(cwd, "add", "-A")
        _git(cwd, "commit", "-q", "-m", "cell")
        return spawn_mod.SpawnResult(
            exit_code=0, summary_path=cwd / ".bakeoff-summary.md", stdout="", stderr=""
        )

    monkeypatch.setattr(spawn_mod, "spawn_agent", spawn_that_commits)
    task = plan_mod.Task(
        key="SEAL-1", summary="a cell", description="a cell", type="Task",
        labels=[], blocked_by=[], status="To Do", raw={},
    )
    cell = bakeoff.run_cell(
        task=task, agent="claude", base_ref="main", repo_root=repo,
        worktree_base=tmp_path / "cells", test_command=None, run_id="seal-run",
        financial_paths="**", claude_extra_args=[], claude_bin="claude",
        task_timeout=5, gate_timeout=5, panel_timeout=5, log=lambda _m: None,
    )
    if cell.error or cell.panel_consensus is None:
        return Outcome(False, cell.error or "panel did not run")
    return Outcome(True, cell.panel_consensus)


def _drive_cross_family_panel(repo: Path, tmp_path: Path, _mp: pytest.MonkeyPatch,
                              after_import: Hook) -> Outcome:
    tool = _load_tool("cross_family_panel")
    after_import()
    stub = tmp_path / "stub.md"
    stub.write_text(_APPROVE_OUTPUT, encoding="utf-8")
    summary = tmp_path / "summary.md"
    summary.write_text("# SEAL-1\n**Status:** Done\n", encoding="utf-8")
    base = _git(repo, "rev-parse", "HEAD^1")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc = tool.main([
            "--repo", str(repo), "--base", base, "--branch", "main",
            "--ticket", "SEAL-1", "--summary-md", str(summary),
            "--dry-run-with-stub-output", str(stub), "--output", "json",
        ])
    return Outcome(rc == 0, f"exit {rc}")


def _drive_retroactive_sweep(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                             after_import: Hook) -> Outcome:
    tool = _load_tool("retroactive_sweep")
    after_import()
    run_dir = tmp_path / "runs"
    (run_dir / "SEAL-1").mkdir(parents=True)
    (run_dir / "SEAL-1" / "summary.md").write_text(
        "# SEAL-1\n**Status:** Done\n", encoding="utf-8"
    )
    monkeypatch.setattr(tool, "EVENPLAY", repo)
    monkeypatch.setattr(tool, "RUN_DIR", run_dir)
    ticket = {
        "key": "SEAL-1", "merge_sha": _git(repo, "rev-parse", "HEAD"),
        "labels": [], "auto_integrate_status": "integrated",
    }
    result = tool.run_one(ticket, tmp_path / "results", 5, lambda _m: None)
    if result.get("skipped") or "consensus" not in result:
        return Outcome(False, str(result))
    return Outcome(True, result["consensus"])


_DRIVERS = {
    "src/claude_dispatcher/bakeoff.py": _drive_bakeoff,
    "tools/cross_family_panel.py": _drive_cross_family_panel,
    "tools/retroactive_sweep.py": _drive_retroactive_sweep,
}


def _observe(entry_file: str, repo: Path, tmp_path: Path,
             monkeypatch: pytest.MonkeyPatch, *,
             after_import: Hook = pp.clear_anchors) -> Observation:
    """Run the entry point and collect what it left. The entry point's own
    exception is an outcome, not a test error: the gate's refusal and the
    declaration's raise both arrive this way.

    ``after_import`` sets the process state the run starts from, and runs
    after the entry point's module is imported: a declaration the import made
    is dropped, so only one the RUN makes can be observed."""
    records: list[pp.PromptLoadRecord] = []
    pp.set_load_reporter(records.append)
    try:
        outcome = _DRIVERS[entry_file](repo, tmp_path, monkeypatch, after_import)
    except Exception as e:  # noqa: BLE001 — surfaced, then asserted on
        outcome = Outcome(False, f"{type(e).__name__}: {e}")
    return Observation(
        outcome=outcome, records=tuple(records),
        declaration=pp.live_declaration(), anchors=pp.live_anchors(),
    )


_RED = "check_prompt_tree is still the W2-1-1 stub; W2-1-3 wires it and declares this entry point"


def _silent_under_stub(obs: Observation, entry_file: str) -> None:
    """Under the stub the only honest outcome is the silent load: the panel
    completed, nothing was declared, nothing was reported. Record that as
    the expected red. Anything else is a real finding and fails."""
    if obs.outcome.panel_ran and not obs.records and obs.declaration is None:
        pytest.xfail(_RED)
    pytest.fail(
        f"{entry_file}: the gate is still the stub, but the run did not load "
        f"silently — outcome={obs.outcome}, records={obs.records}, "
        f"declaration={obs.declaration}"
    )


# --------------------------------------------------------------------------- #
# The register itself: three files, one row each, all present
# --------------------------------------------------------------------------- #


def test_the_register_names_exactly_these_three_files_once_each():
    assert len(pp.UNANCHORED_ENTRY_POINTS) == len(_ENTRY_FILES)
    for entry_file in _ENTRY_FILES:
        assert (ROOT / entry_file).is_file(), entry_file
        _register_row(entry_file)


# --------------------------------------------------------------------------- #
# The rows: one per entry point, executed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entry_file", _ENTRY_FILES)
def test_the_entry_point_declares_itself_before_it_loads(
    entry_file: str, two_commit_repo: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, approving_panel,
):
    """Journal-less process: the run must leave the register row's declaration
    and a declared load that quotes it, and the panel must complete."""
    who = _register_row(entry_file)
    obs = _observe(entry_file, two_commit_repo, tmp_path, monkeypatch)
    if _gate_is_stub():
        _silent_under_stub(obs, entry_file)

    assert obs.declaration is not None, (
        f"{who} never declared itself journal-less; the run reported "
        f"{obs.outcome.detail!r} and the gate recorded "
        f"{[r.decision.value for r in obs.records]}"
    )
    assert obs.declaration.who == who, (
        f"declared as {obs.declaration.who!r}, but the register row is {who!r}"
    )
    assert obs.records, (
        f"{who} declared itself and the panel ran, but no load reached "
        "check_prompt_tree: _load_prompt is not wired through the gate"
    )
    for record in obs.records:
        assert record.decision is pp.PromptLoad.LOAD_UNANCHORED_DECLARED, (
            f"{who}: a load was {record.decision.value}, not declared — the "
            "declaration ran after the load, or not on its path"
        )
        assert record.anchor_detail == obs.declaration.reason
        assert Path(record.tree_dir).resolve() == cfr._PROMPTS_DIR.resolve()
    assert obs.outcome.panel_ran, obs.outcome.detail
    assert obs.anchors == ()


@pytest.mark.parametrize("entry_file", _ENTRY_FILES)
def test_the_entry_point_cannot_excuse_itself_from_a_live_anchor(
    entry_file: str, two_commit_repo: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, approving_panel,
):
    """Anchored process: the same run must NOT produce a declared load, must
    not drop the anchor to make room for one, and must not complete a panel
    against a tree the anchor does not attest. The other half of the
    invariant W2-1-2a sealed at the module, observed at the entry point."""
    pin = pp.PromptPin(
        digest="0" * 64, run_nonce="seal-genesis", source=pp.PinSource.RUN_START,
        detail="a genesis this process holds",
    )

    def anchored() -> None:
        pp.clear_anchors()
        pp.record_anchor(pin)

    obs = _observe(entry_file, two_commit_repo, tmp_path, monkeypatch, after_import=anchored)

    assert obs.anchors == (pin,), "the run touched an anchor it does not own"
    if _gate_is_stub():
        _silent_under_stub(obs, entry_file)

    declared = [r for r in obs.records if r.decision is pp.PromptLoad.LOAD_UNANCHORED_DECLARED]
    assert not declared, f"{entry_file} loaded declared while an anchor was live"
    assert obs.declaration is None, (
        f"{entry_file} left a declaration beside a live anchor: {obs.declaration}"
    )
    assert not obs.outcome.panel_ran, (
        f"{entry_file} completed a panel in an anchored process whose anchor "
        f"does not attest the loaded tree: {obs.outcome.detail}"
    )
