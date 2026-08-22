"""Seals for the advisory prose:code measurement journaled per task (B3).

Advisory by design: there is no defensible ratio threshold, because a
contract-heavy scaffold legitimately runs high. What these rows protect is that
it (a) reports, and (b) can NEVER fail a task — a measurement that could block
would be a gate, and this is deliberately not one.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import orchestrator, worktree as wt_mod


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(a, cwd=repo, capture_output=True, check=True)
    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")
    (repo / "seed.txt").write_text("x\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "seed")
    return repo


def _cfg(tmp_path):
    tasks = tmp_path / "t.yaml"
    tasks.write_text(json.dumps({"tasks": []}))
    return orchestrator.RunConfig(
        tasks_path=tasks, runs_dir=tmp_path / "runs", run_id="R",
        mode="unattended", max_parallel=1, max_iterations=1, reviewer_count=None,
        skip_design=False, skip_security_linter=False, financial_paths="",
        claude_bin="claude", worktree_base=None, label_filter=[], only_keys=None,
        base_branch="main",
    )


def _snap(key="T-1"):
    return orchestrator.TaskSnapshot(
        key=key, summary="s", description="d", type="Task", labels=["size:M"],
    )


def _commit_py(repo: Path, name: str, body: str) -> str:
    (repo / name).write_text(body)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", f"add {name}"], cwd=repo, check=True,
                   capture_output=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def test_it_journals_the_ratio_for_changed_python_files(tmp_path, monkeypatch):
    """Measured under: drop the `_emit_event` call and this reddens — the number
    would be computed and thrown away, which is the invisibility this fixes.
    """
    repo = _repo(tmp_path)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    _commit_py(repo, "prose_heavy.py", '''"""Doc.

Line two.
Line three.
Line four.
"""


def f():
    return 1
''')
    events = []
    monkeypatch.setattr(orchestrator, "_emit_event",
                        lambda cfg, et, payload, **kw: events.append(payload))
    monkeypatch.setattr(orchestrator, "_log", lambda *a, **k: None)

    wt = wt_mod.Worktree(path=repo, branch="main")
    orchestrator._measure_diff_shape(_cfg(tmp_path), _snap(), wt, base,
                                     tmp_path / "log")
    assert len(events) == 1
    p = events[0]
    assert p["check"] == "diff_shape" and p["decision"] == "advisory"
    assert p["prose_ratio"] > 1.0
    assert [f["path"] for f in p["files"]] == ["prose_heavy.py"]


def test_non_python_and_deleted_files_are_not_measured(tmp_path, monkeypatch):
    """A .md or a deletion has no prose:code ratio; including either would make
    the number meaningless.

    Measured under: drop the `.py` filter and this reddens.
    """
    repo = _repo(tmp_path)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    (repo / "notes.md").write_text("# just prose\n")
    (repo / "seed.txt").unlink()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "md only"], cwd=repo, check=True,
                   capture_output=True)

    events = []
    monkeypatch.setattr(orchestrator, "_emit_event",
                        lambda cfg, et, payload, **kw: events.append(payload))
    monkeypatch.setattr(orchestrator, "_log", lambda *a, **k: None)
    wt = wt_mod.Worktree(path=repo, branch="main")
    orchestrator._measure_diff_shape(_cfg(tmp_path), _snap(), wt, base,
                                     tmp_path / "log")
    assert events == []


def test_it_never_raises_and_never_fails_a_task(tmp_path, monkeypatch):
    """The property that keeps it advisory. A bad base ref, a missing worktree, an
    unparseable file — none may propagate, because the caller has no branch for
    "the measurement broke" and a task must not block on a statistic.

    Measured under: remove the except clause and each case below raises.
    """
    logged = []
    monkeypatch.setattr(orchestrator, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "_log", lambda p, m: logged.append(m))
    cfg = _cfg(tmp_path)

    # 1. worktree that does not exist
    gone = wt_mod.Worktree(path=tmp_path / "nope", branch="main")
    orchestrator._measure_diff_shape(cfg, _snap(), gone, "HEAD", tmp_path / "log")

    # 2. a base ref git does not know
    repo = _repo(tmp_path)
    wt = wt_mod.Worktree(path=repo, branch="main")
    orchestrator._measure_diff_shape(cfg, _snap(), wt, "deadbeef", tmp_path / "log")

    # 3. a .py file that does not parse
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    _commit_py(repo, "broken.py", "def (:\n")
    orchestrator._measure_diff_shape(cfg, _snap(), wt, base, tmp_path / "log")
    # Reached here without an exception; that IS the assertion.
    assert True


def test_it_runs_before_the_mechanical_gate(tmp_path):
    """Cheap and it frames the expensive step, so it belongs before the suite.

    Measured under: move the call after `_verify_mechanical_and_maybe_retry` and
    this reddens.
    """
    src = Path(orchestrator.__file__).read_text()
    shape_at = src.index("_measure_diff_shape(cfg, snap, wt, gate_base_used")
    mech_at = src.index("mech_outcome, mech_detail = _verify_mechanical_and_maybe_retry(")
    assert shape_at < mech_at
