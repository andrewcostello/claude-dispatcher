"""A requeued task is not a task that forgot to commit.

`_has_commits_on_branch` asks "did THIS SPAWN commit?" — right for a first
attempt, wrong for a re-run. On a requeue the worktree still holds the task's
earlier commits, so the baseline captured at dispatch already includes them,
and an attempt that correctly finds nothing left to change is indistinguishable
from one that did nothing.

Measured 2026-09-05: WAL-FX-4 and WAL-STMT-4, both requeued after a quota
failure. FX-4 had THREE commits from 09-04 and said so — "it found nothing left
to change, so it added no commit. Working tree is clean" — and was blocked for
producing none. Its adjudication work was complete.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from claude_dispatcher import orchestrator as orch


def _repo(tmp_path: Path):
    repo = tmp_path / "wt"
    repo.mkdir()
    for a in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
              ["config", "user.name", "t"]):
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True,
                   capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feat/x"], cwd=repo,
                   check=True, capture_output=True)
    return repo


def _commit(repo: Path, subject: str, fname: str) -> None:
    (repo / fname).write_text(fname)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", subject], cwd=repo, check=True,
                   capture_output=True)


def _probe(repo: Path, key: str, tmp_path: Path) -> bool:
    return orch._task_already_has_own_commits(
        SimpleNamespace(path=repo), "main", key, tmp_path / "log")


def test_the_tasks_own_earlier_commits_are_found(tmp_path) -> None:
    """The FX-4 case: work landed on a previous attempt."""
    repo = _repo(tmp_path)
    _commit(repo, "fix(wallet): adjudicate the FX panel findings [WAL-FX-4]", "a.txt")
    assert _probe(repo, "WAL-FX-4", tmp_path) is True


def test_a_merged_dependencys_commits_are_not_mistaken_for_this_tasks(
    tmp_path,
) -> None:
    """FX-4's branch carries FX-3's commits from the dependency merge. Reading
    those as its own would excuse a task that really did forget to commit."""
    repo = _repo(tmp_path)
    _commit(repo, "[WAL-FX-3] codex implementation", "dep.txt")
    assert _probe(repo, "WAL-FX-4", tmp_path) is False
    assert _probe(repo, "WAL-FX-3", tmp_path) is True


def test_a_first_attempt_with_no_commits_is_still_caught(tmp_path) -> None:
    """The behaviour this check exists for must survive: a Tasker that reported
    Done and committed nothing is still blocked."""
    repo = _repo(tmp_path)
    assert _probe(repo, "WAL-FX-4", tmp_path) is False


def test_a_bare_key_mention_does_not_count(tmp_path) -> None:
    """The BRACKETED form is the signal. CLAUDE.md measured the difference:
    `W2-1-1` appears in 16 commit messages on main and `[W2-1-1]` in 3, so a
    bare mention would let a task inherit credit for someone else's commit."""
    repo = _repo(tmp_path)
    _commit(repo, "chore: prepare for WAL-FX-4 next sprint", "n.txt")
    assert _probe(repo, "WAL-FX-4", tmp_path) is False


def test_a_commit_already_on_BASE_is_not_this_branchs_work(tmp_path) -> None:
    """The scoping seal. A task that landed once and was merged to base, then
    requeued for more work, still has its old commit reachable from HEAD — but
    it is not work on THIS branch, and reading it as such would skip the
    commit-retry for a task that really did forget to commit.

    Added because a mutation removing the `base_branch..HEAD` range SURVIVED:
    the original fixture had no key-bearing commit on base, so scoped and
    unscoped gave the same answer and the test proved nothing.
    """
    repo = _repo(tmp_path)
    # Put the task's own earlier commit on BASE, not on the feat branch.
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True,
                   capture_output=True)
    _commit(repo, "fix(wallet): earlier landed work [WAL-FX-4]", "old.txt")
    subprocess.run(["git", "checkout", "-q", "-B", "feat/x", "main"], cwd=repo,
                   check=True, capture_output=True)
    # HEAD can reach it, but base_branch..HEAD is empty.
    assert _probe(repo, "WAL-FX-4", tmp_path) is False


def test_a_git_failure_fails_closed(tmp_path) -> None:
    """Any probe failure must preserve the old commit-retry behaviour rather
    than silently accepting a task that did forget to commit."""
    missing = tmp_path / "not-a-repo"
    missing.mkdir()
    assert orch._task_already_has_own_commits(
        SimpleNamespace(path=missing), "main", "WAL-FX-4", tmp_path / "log") is False


def test_the_commit_retry_consults_the_requeue_check() -> None:
    """WIRING. Adding the probe and not consulting it is the #84/#86/#93 shape,
    and this run has produced four of those."""
    import inspect
    import re
    src = inspect.getsource(orch)
    m = re.search(r'if \(s\.status == "Done"\n(.*?)\):', src, re.DOTALL)
    assert m, "commit-retry condition not found"
    assert "_task_already_has_own_commits" in m.group(1), m.group(1)
