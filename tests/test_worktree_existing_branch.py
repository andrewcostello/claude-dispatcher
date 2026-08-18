"""A re-dispatched task whose worktree was tidied must still get a worktree.

`git worktree add -b <branch>` CREATES the branch and fails if it exists. The
branch survives `git worktree remove`, and the reuse path only fires when the
DIRECTORY is still present — so tidying preserved worktrees made every Blocked
task undispatchable. Measured 2026-08-17: all three wave-2 scaffolds failed with
"git worktree add failed", and the branch holding their work was the cause.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from claude_dispatcher import worktree as wt_mod


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


def test_a_worktree_is_created_when_the_branch_does_not_exist(tmp_path) -> None:
    repo = _repo(tmp_path)
    wt = wt_mod.create(
        repo_root=repo, task_key="T-1", branch="feat/T-1", base_branch="main",
        base_path=tmp_path / "wts",
    )
    assert wt.path.exists() and wt.branch == "feat/T-1"


def test_a_worktree_is_created_when_the_branch_ALREADY_exists(tmp_path) -> None:
    """The regression. Measured under: restore the unconditional `-b` and this
    reddens with "git worktree add failed" — which is exactly what three Blocked
    tasks hit.
    """
    repo = _repo(tmp_path)
    subprocess.run(["git", "branch", "feat/T-2", "main"], cwd=repo, check=True,
                   capture_output=True)
    wt = wt_mod.create(
        repo_root=repo, task_key="T-2", branch="feat/T-2", base_branch="main",
        base_path=tmp_path / "wts",
    )
    assert wt.path.exists() and wt.branch == "feat/T-2"


def test_checking_out_an_existing_branch_keeps_its_commits(tmp_path) -> None:
    """The property that must NOT be traded for convenience: a re-dispatch may
    not silently discard commits an unblocked task already made. Preserved work
    has been recovered from exactly this state four times (D-54, D-59, D-63,
    D-66).

    Measured under: add `--force`/reset the branch to base_branch on the reuse
    path and this reddens — the task's own commit disappears.
    """
    repo = _repo(tmp_path)
    subprocess.run(["git", "branch", "feat/T-3", "main"], cwd=repo, check=True,
                   capture_output=True)
    # a commit that exists only on the task branch, as an unblocked task's would
    scratch = tmp_path / "scratch"
    subprocess.run(["git", "worktree", "add", str(scratch), "feat/T-3"], cwd=repo,
                   check=True, capture_output=True)
    (scratch / "task_work.txt").write_text("the agent's work\n")
    subprocess.run(["git", "add", "-A"], cwd=scratch, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "task work"], cwd=scratch, check=True,
                   capture_output=True)
    tip = subprocess.run(["git", "rev-parse", "HEAD"], cwd=scratch, check=True,
                         capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "worktree", "remove", str(scratch)], cwd=repo, check=True,
                   capture_output=True)

    wt = wt_mod.create(
        repo_root=repo, task_key="T-3", branch="feat/T-3", base_branch="main",
        base_path=tmp_path / "wts",
    )
    got = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt.path, check=True,
                         capture_output=True, text=True).stdout.strip()
    assert got == tip, "the re-dispatch discarded the task's own commit"
    assert (wt.path / "task_work.txt").exists()
