"""Tests for git worktree creation: path layout + graceful failures (DISP-2).

Covers the Path-based layout decision (no string-prefix checks) and the typed
WorktreeError wrapping around `git worktree add`, including the concurrent
same-key race.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import worktree as wt


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one commit on `main`, isolated under tmp_path."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=repo_dir, check=True, capture_output=True)
    (repo_dir / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=repo_dir, check=True, capture_output=True)
    return repo_dir


# --- Layout classification (no string-prefix checks) ------------------------

def test_layout_container_when_base_named_worktrees() -> None:
    assert wt.layout_for(Path("/worktrees")) is wt.WorktreeLayout.CONTAINER
    assert wt.layout_for(Path("/var/run/worktrees")) is wt.WorktreeLayout.CONTAINER


def test_layout_sibling_for_dev_host_parent() -> None:
    assert wt.layout_for(Path("/home/dev/Project")) is wt.WorktreeLayout.SIBLING


def test_layout_prefix_lookalikes_are_sibling() -> None:
    # The old `str(base).startswith("/worktrees")` misclassified these as
    # container. Path-based name comparison must treat them as SIBLING.
    assert wt.layout_for(Path("/worktrees-scratch")) is wt.WorktreeLayout.SIBLING
    assert wt.layout_for(Path("/worktrees_old")) is wt.WorktreeLayout.SIBLING


def test_worktree_path_per_layout() -> None:
    assert wt.worktree_path(Path("/worktrees"), "DISP-2") == Path("/worktrees/DISP-2")
    assert wt.worktree_path(Path("/home/dev/Project"), "DISP-2") == \
        Path("/home/dev/Project/worktree-DISP-2")
    # prefix-lookalike resolves to the namespaced sibling form, not flat
    assert wt.worktree_path(Path("/worktrees-scratch"), "DISP-2") == \
        Path("/worktrees-scratch/worktree-DISP-2")


def test_source_has_no_string_prefix_check() -> None:
    """Acceptance: no string-prefix path checks remain in worktree.py."""
    src = Path(wt.__file__).read_text(encoding="utf-8")
    assert 'startswith("/worktrees")' not in src
    assert ".startswith(" not in src


# --- Normal creation (unchanged behavior) -----------------------------------

def test_create_normal_path_sibling_layout(repo: Path, tmp_path: Path) -> None:
    base = tmp_path / "wtbase"
    handle = wt.create(repo, "DISP-2", "feat/DISP-2-x", base_path=base)
    assert handle.path == base / "worktree-DISP-2"
    assert handle.branch == "feat/DISP-2-x"
    assert (handle.path / ".git").exists()
    # the branch exists and is checked out in the worktree
    branches = subprocess.run(["git", "branch", "--list", "feat/DISP-2-x"],
                              cwd=repo, capture_output=True, text=True).stdout
    assert "feat/DISP-2-x" in branches


def test_create_container_layout_flat_path(repo: Path, tmp_path: Path) -> None:
    base = tmp_path / "worktrees"  # base.name == "worktrees" -> CONTAINER
    handle = wt.create(repo, "DISP-2", "feat/DISP-2-x", base_path=base)
    assert handle.path == base / "DISP-2"
    assert (handle.path / ".git").exists()


def test_create_idempotent_reuse_skips_worktree_add(repo: Path, tmp_path: Path,
                                                     monkeypatch) -> None:
    base = tmp_path / "wtbase"
    first = wt.create(repo, "DISP-2", "feat/DISP-2-x", base_path=base)
    # Second call with an existing worktree must NOT re-create it. A cheap
    # read-only query (rev-parse) to learn the branch is fine; `worktree add`
    # is not.
    real_run = wt.subprocess.run

    def guarded(args, *a, **k):
        if isinstance(args, (list, tuple)) and "worktree" in args and "add" in args:
            raise AssertionError("git worktree add must not run on idempotent reuse")
        return real_run(args, *a, **k)
    monkeypatch.setattr(wt.subprocess, "run", guarded)
    second = wt.create(repo, "DISP-2", "feat/DISP-2-x", base_path=base)
    assert second.path == first.path
    assert second.branch == "feat/DISP-2-x"


# --- Graceful failures -------------------------------------------------------

def test_create_failure_raises_worktree_error_with_stderr(repo: Path,
                                                          tmp_path: Path) -> None:
    base = tmp_path / "wtbase"
    with pytest.raises(wt.WorktreeError) as ei:
        wt.create(repo, "DISP-2", "feat/DISP-2-x",
                  base_branch="nonexistent-branch", base_path=base)
    # git stderr is attached, not swallowed
    assert ei.value.stderr
    assert "DISP-2" in str(ei.value)


def test_concurrent_same_key_second_caller_no_traceback(repo: Path,
                                                        tmp_path: Path,
                                                        monkeypatch) -> None:
    """Simulate the same-key race: the path/branch is taken between the
    existence check and `git worktree add`. The second caller must either
    reuse idempotently or get a typed WorktreeError — never a raw traceback.
    """
    base = tmp_path / "wtbase"
    # First caller wins the path normally.
    first = wt.create(repo, "DISP-2", "feat/DISP-2-x", base_path=base)

    # Second caller targets the SAME key but a different branch, and we force
    # the existence check to miss (as if it ran before the first completed),
    # so it actually attempts `git worktree add` against an occupied path.
    orig_exists = Path.exists
    calls = {"n": 0}

    def first_check_misses(self: Path) -> bool:
        # Only the very first .exists() call (the idempotency guard) reports
        # False; everything afterwards (including the post-failure recheck)
        # behaves normally.
        if self == first.path and calls["n"] == 0:
            calls["n"] += 1
            return False
        return orig_exists(self)

    monkeypatch.setattr(Path, "exists", first_check_misses)
    result = wt.create(repo, "DISP-2", "feat/DISP-2-other", base_path=base)
    monkeypatch.undo()
    # Post-failure recheck saw the valid worktree -> idempotent reuse.
    assert result.path == first.path
    assert (result.path / ".git").exists()
    # The handle reports the branch actually checked out (the winner's), not
    # the losing caller's requested branch, which never got created.
    assert result.branch == "feat/DISP-2-x"


def test_create_failure_on_occupied_plain_dir_raises(repo: Path,
                                                     tmp_path: Path) -> None:
    """A non-empty plain dir at the target (no .git) must surface a
    WorktreeError, never be wrongly reused as a worktree."""
    base = tmp_path / "wtbase"
    wt_path = wt.worktree_path(base, "DISP-2")
    wt_path.mkdir(parents=True)
    (wt_path / "stray.txt").write_text("not a worktree\n", encoding="utf-8")
    with pytest.raises(wt.WorktreeError) as ei:
        wt.create(repo, "DISP-2", "feat/DISP-2-x", base_path=base)
    assert ei.value.stderr


def test_concurrent_same_key_branch_collision_raises(repo: Path,
                                                     tmp_path: Path) -> None:
    """If `git worktree add` fails and the path is NOT a valid worktree, the
    caller gets a typed WorktreeError (not a CalledProcessError traceback)."""
    base = tmp_path / "wtbase"
    # Pre-create the branch so `-b` collides, but leave the target path absent.
    subprocess.run(["git", "branch", "feat/DISP-2-x", "main"],
                   cwd=repo, check=True, capture_output=True)
    with pytest.raises(wt.WorktreeError) as ei:
        wt.create(repo, "DISP-2", "feat/DISP-2-x", base_path=base)
    assert ei.value.stderr


# --- PR-flow feature branch (PRF-1) -----------------------------------------

def test_sanitize_branch_segment_basic() -> None:
    assert wt.sanitize_branch_segment("PHASE-3-PRF") == "phase-3-prf"
    assert wt.sanitize_branch_segment("My Epic Name") == "my-epic-name"
    assert wt.sanitize_branch_segment("SMOKE") == "smoke"
    # Leading/trailing separators and slashes are stripped; punctuation runs
    # collapse to a single dash.
    assert wt.sanitize_branch_segment("  //weird__name!! ") == "weird__name"
    assert wt.sanitize_branch_segment("***") == ""


def test_default_feature_branch() -> None:
    assert wt.default_feature_branch("PHASE-3-PRF") == "feature/phase-3-prf"
    assert wt.default_feature_branch("SMOKE") == "feature/smoke"
    # No epic, or an epic that sanitizes to nothing → None (caller must then
    # require an explicit --feature-branch).
    assert wt.default_feature_branch(None) is None
    assert wt.default_feature_branch("") is None
    assert wt.default_feature_branch("***") is None


def test_ensure_feature_branch_creates_from_base(repo: Path) -> None:
    """Absent feature branch → forked from base, status 'created', tip == base tip."""
    base_sha = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    result = wt.ensure_feature_branch(repo, "feature/smoke", "main")
    assert result.status == "created"
    assert result.branch == "feature/smoke"
    assert result.sha == base_sha
    # The ref now exists in the repo.
    assert subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "feature/smoke"],
        cwd=repo, capture_output=True,
    ).returncode == 0


def test_ensure_feature_branch_reuses_existing(repo: Path) -> None:
    """Existing feature branch → reused untouched, status 'existing', its own tip."""
    # Put a distinct commit on feature/smoke so its tip diverges from main.
    subprocess.run(["git", "branch", "feature/smoke", "main"],
                   cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "worktree", "add", str(repo.parent / "fwt"),
                    "feature/smoke"], cwd=repo, check=True, capture_output=True)
    (repo.parent / "fwt" / "extra.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo.parent / "fwt",
                   check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "feature work"],
                   cwd=repo.parent / "fwt", check=True, capture_output=True)
    feat_sha = subprocess.run(
        ["git", "rev-parse", "feature/smoke"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()

    result = wt.ensure_feature_branch(repo, "feature/smoke", "main")
    assert result.status == "existing"
    assert result.sha == feat_sha  # reused, not reset to main


def test_ensure_feature_branch_bad_base_raises(repo: Path) -> None:
    """A base branch that doesn't resolve → WorktreeError (can't fork)."""
    with pytest.raises(wt.WorktreeError):
        wt.ensure_feature_branch(repo, "feature/smoke", "no-such-branch")
