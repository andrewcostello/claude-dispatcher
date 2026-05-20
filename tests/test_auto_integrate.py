"""Tests for the auto_integrate module.

Each test sets up a small two-branch git repo in tmp_path so the merge
logic runs against a real git tree. No claude subprocess is spawned —
auto_integrate.integrate() is the unit under test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import auto_integrate as ai


def _git(args: list[str], cwd: Path, check: bool = True) -> str:
    """Run git with stable env so commits don't pick up the host's name/email."""
    env = {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        # Skip any hooks the host happens to install.
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "HOME": str(cwd),
        "PATH": "/usr/bin:/bin",
    }
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env,
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} → rc={proc.returncode}\n{proc.stderr}")
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An empty git repo at tmp_path/repo with a `main` branch + one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], cwd=repo)
    (repo / "README.md").write_text("# test\n")
    (repo / "bay-session-tasks.yaml").write_text("project: TEST\ntasks: []\n")
    _git(["add", "-A"], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)
    return repo


def _make_feat_branch(repo: Path, branch: str, files: dict[str, str], msg: str) -> str:
    """Create a branch off main with the given files. Returns the commit SHA."""
    _git(["checkout", "-b", branch, "main"], cwd=repo)
    for path, content in files.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(["add", "-A"], cwd=repo)
    _git(["commit", "-m", msg], cwd=repo)
    sha = _git(["rev-parse", "HEAD"], cwd=repo).strip()
    _git(["checkout", "main"], cwd=repo)
    return sha


def _logs() -> tuple[list[str], callable]:
    """Return (captured_log_lines, log_fn) for assertions."""
    captured: list[str] = []
    def log(m: str) -> None:
        captured.append(m)
    return captured, log


def test_disabled_is_noop(repo: Path):
    """enabled=False short-circuits before touching git."""
    captured, log = _logs()
    result = ai.integrate(
        repo_root=repo,
        yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main",
        feat_branch="feat/whatever",
        task_key="TEST-1",
        log=log,
        enabled=False,
    )
    assert result.status == "skipped-disabled"
    assert result.merge_sha is None
    # Should NOT have logged anything since we bail before the work message.
    assert captured == []


def test_no_commits_is_skipped(repo: Path):
    """Branch pointing at main's tip (no extra commits) is reported as
    already-on — feat's tip is an ancestor of main, so there's nothing to
    integrate. (skipped-no-commits is reserved for the unusual case where
    feat has divergent commits but the diff vs base is empty.)"""
    _git(["branch", "feat/empty", "main"], cwd=repo)
    captured, log = _logs()
    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/empty",
        task_key="TEST-2", log=log,
    )
    assert result.status == "skipped-already-on"


def test_clean_merge_advances_base(repo: Path):
    """A non-conflicting feat branch merges cleanly and base advances."""
    _make_feat_branch(repo, "feat/add-file", {"new.txt": "hello\n"}, "add file")
    head_before = _git(["rev-parse", "main"], cwd=repo).strip()
    captured, log = _logs()
    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/add-file",
        task_key="TEST-3", log=log,
    )
    assert result.status == "integrated", result.detail
    assert result.merge_sha is not None
    # main advanced.
    head_after = _git(["rev-parse", "main"], cwd=repo).strip()
    assert head_after != head_before
    # The new file is now reachable from main.
    assert "hello" in (repo / "new.txt").read_text()


def test_already_merged_is_skipped(repo: Path):
    """If the feat branch tip is already an ancestor of main, skip."""
    sha = _make_feat_branch(repo, "feat/already-in",
                             {"in.txt": "x\n"}, "add in")
    # Fast-forward main to include it.
    _git(["merge", "--ff-only", "feat/already-in"], cwd=repo)
    captured, log = _logs()
    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/already-in",
        task_key="TEST-4", log=log,
    )
    assert result.status == "skipped-already-on"


def test_content_conflict_is_caught_by_merge_tree(repo: Path):
    """Two branches editing the same file produce a conflict the
    auto-integrator catches BEFORE touching the working tree."""
    # main now has a file.
    (repo / "shared.txt").write_text("base\n")
    _git(["add", "-A"], cwd=repo)
    _git(["commit", "-m", "add shared"], cwd=repo)
    # feat-a modifies shared.txt.
    _make_feat_branch(repo, "feat/feat-a",
                       {"shared.txt": "feat-a\n"}, "modify shared")
    # main also moves forward and modifies shared.txt differently.
    _git(["checkout", "main"], cwd=repo)
    (repo / "shared.txt").write_text("main-moved\n")
    _git(["add", "-A"], cwd=repo)
    _git(["commit", "-m", "main moved"], cwd=repo)
    head_before = _git(["rev-parse", "main"], cwd=repo).strip()
    captured, log = _logs()
    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/feat-a",
        task_key="TEST-5", log=log,
    )
    assert result.status == "skipped-conflict"
    # main did NOT advance — the conflict was caught before the merge.
    head_after = _git(["rev-parse", "main"], cwd=repo).strip()
    assert head_after == head_before


def test_yaml_changes_on_feat_branch_are_reverted(repo: Path):
    """A Tasker that committed bay-session-tasks.yaml on its feat branch
    must NOT bring that change into base_branch — the YAML is dispatcher-
    owned. The integrator reverts YAML edits as part of the merge."""
    _make_feat_branch(repo, "feat/touches-yaml", {
        "code.go": "package main\n",
        "bay-session-tasks.yaml": "project: TAINTED\ntasks: []\n",
    }, "tasker edited the yaml")
    captured, log = _logs()
    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/touches-yaml",
        task_key="TEST-6", log=log,
    )
    assert result.status == "integrated", result.detail
    # YAML in main is still the original.
    main_yaml = _git(["show", "main:bay-session-tasks.yaml"], cwd=repo)
    assert "TAINTED" not in main_yaml
    assert "TEST" in main_yaml
    # The code change DID land.
    assert (repo / "code.go").read_text() == "package main\n"


def test_integrate_result_records_merge_sha(repo: Path):
    """The IntegrateResult.merge_sha should match HEAD after success."""
    _make_feat_branch(repo, "feat/short-sha", {"x.txt": "x\n"}, "x")
    _, log = _logs()
    result = ai.integrate(
        repo_root=repo, yaml_path=repo / "bay-session-tasks.yaml",
        base_branch="main", feat_branch="feat/short-sha",
        task_key="TEST-7", log=log,
    )
    assert result.status == "integrated"
    head = _git(["rev-parse", "HEAD"], cwd=repo).strip()
    assert head.startswith(result.merge_sha)
