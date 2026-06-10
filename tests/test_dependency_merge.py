"""Dispatch-time dependency rule (INT-4).

When a dependent task's worktree is created, each blockedBy dependency whose
commits are NOT yet reachable from base is merged into the new task branch
(in blockedBy order) BEFORE the Tasker is spawned. On a merge failure the
task is Blocked and no Tasker is dispatched into the tree: a genuine content
conflict (unmerged paths present) is labelled ``dependency_merge_conflict``,
any other merge failure (e.g. committer identity unknown) is labelled
``dependency_merge_failure``. The merged dependency SHAs ride along in the
``task_started`` journal payload.

These tests cover:
  - the worktree-level merge mechanics (merge / no-op / unresolved / conflict
    / non-conflict failure),
  - the orchestrator wiring end to end via the fake-claude harness:
      * acceptance 1: A done-on-branch, B blockedBy A → B's worktree contains
        A's commits before spawn; merged SHAs in the task_started payload;
      * acceptance 2: conflicting dependency branches → Blocked(
        dependency_merge_conflict), no spawn, journal event present;
      * acceptance 3: no-op when dependencies are already on base.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import (
    journal as journal_mod,
    orchestrator,
    spawn as spawn_mod,
    worktree as wt_mod,
    yaml_io,
)
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures"
FAKE_CLAUDE = FIXTURE_DIR / "fake_claude.py"


# --- low-level git helpers for building fixtures ----------------------------


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _commit_file(repo: Path, name: str, content: str, message: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one commit on `main`, isolated under tmp_path."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)],
                   check=True, capture_output=True)
    _git(repo_dir, "config", "user.email", "test@test")
    _git(repo_dir, "config", "user.name", "Test")
    (repo_dir / "README.md").write_text("init\n", encoding="utf-8")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    return repo_dir


# --- worktree-level merge mechanics -----------------------------------------


def _make_dep_branch(repo: Path, branch: str, fname: str, content: str) -> str:
    """Create `branch` off main with one commit touching `fname`, return tip SHA.

    Leaves main checked out afterward so the next branch forks from main too.
    """
    _git(repo, "checkout", "-q", "-b", branch, "main")
    sha = _commit_file(repo, fname, content, f"work on {branch}")
    _git(repo, "checkout", "-q", "main")
    return sha


def test_merge_brings_unintegrated_dependency_into_worktree(repo: Path,
                                                            tmp_path: Path) -> None:
    """A dependency branch whose commits are NOT on base is merged into the
    dependent's worktree, and recorded in `merged` with its tip SHA."""
    dep_sha = _make_dep_branch(repo, "feat/DEP-A", "a.txt", "from A\n")
    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)

    result = wt_mod.merge_dependencies(
        repo, wt, "main", [("DEP-A", "feat/DEP-A")],
    )

    assert result.conflict is None
    assert [m.key for m in result.merged] == ["DEP-A"]
    assert result.merged[0].branch == "feat/DEP-A"
    assert result.merged[0].sha == dep_sha
    assert result.already_on_base == []
    # The dependency's file is now present in the dependent's worktree.
    assert (wt.path / "a.txt").read_text(encoding="utf-8") == "from A\n"


def test_merge_noop_when_dependency_already_on_base(repo: Path,
                                                    tmp_path: Path) -> None:
    """When a dependency's commits are already reachable from base, the merge
    is a no-op recorded under `already_on_base` (acceptance 3)."""
    _make_dep_branch(repo, "feat/DEP-A", "a.txt", "from A\n")
    # Land DEP-A on base (fast-forward) — now its commits are on main.
    _git(repo, "merge", "--ff-only", "feat/DEP-A")
    _git(repo, "checkout", "-q", "main")

    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)
    result = wt_mod.merge_dependencies(
        repo, wt, "main", [("DEP-A", "feat/DEP-A")],
    )

    assert result.merged == []
    assert result.already_on_base == ["DEP-A"]
    assert result.conflict is None
    # The file is present because the worktree forked from base, not via merge.
    assert (wt.path / "a.txt").exists()


def test_merge_unresolved_branch_is_skipped(repo: Path, tmp_path: Path) -> None:
    """A dependency whose branch ref can't be resolved is recorded under
    `unresolved` and skipped — not a conflict, not a merge."""
    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)
    result = wt_mod.merge_dependencies(
        repo, wt, "main", [("DEP-GONE", "feat/does-not-exist")],
    )
    assert result.unresolved == ["DEP-GONE"]
    assert result.merged == []
    assert result.conflict is None


def test_merge_multiple_dependencies_in_order(repo: Path, tmp_path: Path) -> None:
    """Two non-conflicting dependencies are both merged, in blockedBy order."""
    sha_a = _make_dep_branch(repo, "feat/DEP-A", "a.txt", "from A\n")
    sha_b = _make_dep_branch(repo, "feat/DEP-B", "b.txt", "from B\n")
    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)

    result = wt_mod.merge_dependencies(
        repo, wt, "main",
        [("DEP-A", "feat/DEP-A"), ("DEP-B", "feat/DEP-B")],
    )

    assert [m.key for m in result.merged] == ["DEP-A", "DEP-B"]
    assert [m.sha for m in result.merged] == [sha_a, sha_b]
    assert (wt.path / "a.txt").exists()
    assert (wt.path / "b.txt").exists()


def test_merge_conflict_aborts_and_reports(repo: Path, tmp_path: Path) -> None:
    """Conflicting dependency branches → conflict reported, merge aborted so
    the worktree is left without an in-progress merge."""
    # A shared file on base that both dependencies edit on the same line.
    _commit_file(repo, "shared.txt", "base\n", "add shared")
    _make_dep_branch(repo, "feat/DEP-A", "shared.txt", "from A\n")
    _make_dep_branch(repo, "feat/DEP-B", "shared.txt", "from B\n")

    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)
    result = wt_mod.merge_dependencies(
        repo, wt, "main",
        [("DEP-A", "feat/DEP-A"), ("DEP-B", "feat/DEP-B")],
    )

    assert result.conflict is not None
    assert result.conflict.key == "DEP-B"
    assert result.conflict.branch == "feat/DEP-B"
    assert result.conflict.reason == "dependency_merge_conflict"
    assert "shared.txt" in result.conflict.detail
    # DEP-A merged cleanly before the DEP-B conflict.
    assert [m.key for m in result.merged] == ["DEP-A"]
    # No in-progress merge left behind (the failed merge was aborted).
    merge_head = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        cwd=str(wt.path), capture_output=True, text=True,
    )
    assert merge_head.returncode != 0, "MERGE_HEAD must be gone after abort"


def _break_committer_identity(repo: Path, monkeypatch) -> None:
    """Make merge-commit creation fail in `repo` (and its worktrees), exit 128.

    `user.useConfigOnly` plus an unset `user.email` makes git refuse to invent
    a committer identity; pointing the global/system config files at /dev/null
    defeats the developer's real identity on the host. Worktrees share the
    parent repo's `.git/config`, so the breakage reaches the task worktree.
    A content-clean merge then fails only at commit creation — a non-conflict
    failure (no unmerged paths, no MERGE_HEAD).
    """
    _git(repo, "config", "user.useConfigOnly", "true")
    _git(repo, "config", "--unset", "user.email")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    for var in ("GIT_COMMITTER_EMAIL", "GIT_AUTHOR_EMAIL", "EMAIL"):
        monkeypatch.delenv(var, raising=False)


def _make_orphan_branch(repo: Path, branch: str, fname: str, content: str) -> None:
    """Create `branch` with NO common history with main (one orphan commit).

    Merging such a branch fails without any content conflict — git refuses to
    merge unrelated histories (exit 128) before producing unmerged paths.
    """
    _git(repo, "checkout", "-q", "--orphan", branch)
    _git(repo, "rm", "-r", "-f", "-q", ".")
    _commit_file(repo, fname, content, f"orphan work on {branch}")
    _git(repo, "checkout", "-q", "main")


def test_merge_failure_without_conflict_reports_failure_reason(
    repo: Path, tmp_path: Path, monkeypatch,
) -> None:
    """A merge that fails for a non-conflict reason (committer identity
    unknown) is classified ``dependency_merge_failure`` — not a conflict —
    with git's own diagnosis in the detail, and the worktree is left without
    an in-progress merge."""
    # The dependency touches a DIFFERENT file from base: the merge itself is
    # content-clean and fails only when git tries to create the merge commit.
    _make_dep_branch(repo, "feat/DEP-A", "a.txt", "from A\n")
    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)
    _break_committer_identity(repo, monkeypatch)

    result = wt_mod.merge_dependencies(
        repo, wt, "main", [("DEP-A", "feat/DEP-A")],
    )

    assert result.conflict is not None
    assert result.conflict.key == "DEP-A"
    assert result.conflict.branch == "feat/DEP-A"
    assert result.conflict.reason == "dependency_merge_failure"
    # Detail carries git's identity complaint, not a conflicting-file list.
    detail = result.conflict.detail.lower()
    assert "email" in detail or "identity" in detail
    assert "conflicting files" not in detail
    assert result.merged == []
    # No in-progress merge left behind (mirrors the conflict test).
    merge_head = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        cwd=str(wt.path), capture_output=True, text=True,
    )
    assert merge_head.returncode != 0, "MERGE_HEAD must be gone after a failure"


def test_merge_stops_at_non_conflict_failure_after_clean_merge(
    repo: Path, tmp_path: Path,
) -> None:
    """Multi-dependency: the first dep merges clean, the second hits a
    non-conflict failure (unrelated history) → `merged` retains the first dep,
    merging stops, and the failure carries reason ``dependency_merge_failure``."""
    sha_a = _make_dep_branch(repo, "feat/DEP-A", "a.txt", "from A\n")
    _make_orphan_branch(repo, "feat/DEP-B", "b.txt", "from B\n")

    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)
    result = wt_mod.merge_dependencies(
        repo, wt, "main",
        [("DEP-A", "feat/DEP-A"), ("DEP-B", "feat/DEP-B")],
    )

    # DEP-A merged cleanly before the DEP-B failure stopped the loop.
    assert [m.key for m in result.merged] == ["DEP-A"]
    assert result.merged[0].sha == sha_a
    assert result.conflict is not None
    assert result.conflict.key == "DEP-B"
    assert result.conflict.reason == "dependency_merge_failure"
    assert "unrelated histories" in result.conflict.detail
    # No in-progress merge left behind.
    merge_head = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        cwd=str(wt.path), capture_output=True, text=True,
    )
    assert merge_head.returncode != 0, "MERGE_HEAD must be gone after a failure"


# --- orchestrator wiring (fake-claude harness) ------------------------------


def _seed_repo_with_yaml(repo: Path, yaml_text: str) -> None:
    roles = repo / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True, exist_ok=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    (repo / "tasks.yaml").write_text(yaml_text, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "seed tasks")


def _args(repo: Path, **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--run-id", "dep-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
    ]
    for k, v in overrides.items():
        if v is None:
            continue
        flag = f"--{k.replace('_', '-')}"
        if v is True:
            argv += [flag]
        else:
            argv += [flag, str(v)]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch) -> None:
    def fake(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        proc = subprocess.run(
            [sys.executable, str(FAKE_CLAUDE)],
            input=prompt, capture_output=True, text=True,
            cwd=str(cwd), env=env, timeout=timeout_seconds,
        )
        return spawn_mod.SpawnResult(
            exit_code=proc.returncode,
            summary_path=Path(env["SUMMARY_PATH"]),
            stdout=proc.stdout, stderr=proc.stderr,
        )
    monkeypatch.setattr(spawn_mod, "spawn_claude", fake)


def _events(repo: Path) -> list[journal_mod.JournalEvent]:
    jpath = repo / "_runs" / "dep-test" / journal_mod.JOURNAL_FILENAME
    return list(journal_mod.read_events(jpath))


# Two-task chain: A (no deps) then B blockedBy A.
_CHAIN_YAML = """\
project: TEST
epic: INT

tasks:
  - key: INT-A
    summary: "dependency producer"
    description: Produces a commit on its own branch.
    type: Task
    estimate: 5m
    labels: [size:XS, area:test]

  - key: INT-B
    summary: "dependent on A"
    description: Depends on INT-A; its worktree should contain A's commits.
    type: Task
    estimate: 5m
    labels: [size:XS, area:test]
    blockedBy: [INT-A]
"""


def test_dependent_worktree_contains_dependency_commits_and_journals_shas(
    repo: Path, monkeypatch,
) -> None:
    """Acceptance 1: A done-on-branch, B blockedBy A → B's worktree contains
    A's commits before spawn; merged SHAs in the task_started payload.

    auto-integrate is OFF, so A's work lands only on its feat branch — the
    dependency merge is what carries it into B's worktree.
    """
    _seed_repo_with_yaml(repo, _CHAIN_YAML)
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo))
    assert rc == 0

    doc = yaml_io.load(repo / "tasks.yaml")
    rows = {t["key"]: t for t in doc["tasks"]}
    assert rows["INT-A"]["status"] == "Done"
    assert rows["INT-B"]["status"] == "Done"

    # B's worktree contains A's committed marker file (carried by the merge).
    b_wt = repo.parent / "wt" / "worktree-INT-B"
    assert (b_wt / "smoke-marker-INT-A.txt").exists(), (
        "B's worktree must contain A's commits via the dependency merge"
    )

    # task_started for INT-B carries A's merged branch + tip SHA.
    started = next(
        e for e in _events(repo)
        if e.event_type == "task_started" and e.task_key == "INT-B"
    )
    merged = started.payload.get("merged_dependencies")
    assert merged and len(merged) == 1
    assert merged[0]["key"] == "INT-A"
    a_branch = rows["INT-A"]["branch"]
    assert merged[0]["branch"] == a_branch
    expected_sha = _git(repo, "rev-parse", a_branch)
    assert merged[0]["sha"] == expected_sha


def test_noop_when_dependency_already_on_base(repo: Path, monkeypatch) -> None:
    """Acceptance 3: with --auto-integrate, A lands on base before B is
    dispatched, so the dependency merge is a no-op (already_on_base)."""
    _seed_repo_with_yaml(repo, _CHAIN_YAML)
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo, auto_integrate=True))
    assert rc == 0

    started = next(
        e for e in _events(repo)
        if e.event_type == "task_started" and e.task_key == "INT-B"
    )
    assert started.payload.get("merged_dependencies") == []
    assert started.payload.get("dependencies_already_on_base") == ["INT-A"]


# Conflict fixture: two done dependencies on conflicting branches, one
# dependent blockedBy both.
_CONFLICT_YAML = """\
project: TEST
epic: INT

tasks:
  - key: INT-A
    summary: "dep A"
    description: Edits shared.txt.
    type: Task
    estimate: 5m
    labels: [size:XS, area:test]
    status: Done
    branch: feat/INT-A

  - key: INT-B
    summary: "dep B"
    description: Edits shared.txt differently.
    type: Task
    estimate: 5m
    labels: [size:XS, area:test]
    status: Done
    branch: feat/INT-B

  - key: INT-C
    summary: "dependent on A and B"
    description: blockedBy both conflicting deps.
    type: Task
    estimate: 5m
    labels: [size:XS, area:test]
    blockedBy: [INT-A, INT-B]
"""


def test_conflicting_dependencies_block_without_spawn(repo: Path, monkeypatch) -> None:
    """Acceptance 2: conflicting dependency branches → Blocked(
    dependency_merge_conflict), no spawn, journal event present."""
    # Build the two conflicting dependency branches on a shared base file.
    _commit_file(repo, "shared.txt", "base\n", "add shared")
    _make_dep_branch(repo, "feat/INT-A", "shared.txt", "from A\n")
    _make_dep_branch(repo, "feat/INT-B", "shared.txt", "from B\n")
    _seed_repo_with_yaml(repo, _CONFLICT_YAML)

    # Record spawn calls; assert the Tasker is never dispatched.
    spawn_calls: list[str] = []

    def no_spawn(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        spawn_calls.append(env.get("TASK_KEY", "?"))
        raise AssertionError("spawn_claude must not run on a conflicted tree")

    monkeypatch.setattr(spawn_mod, "spawn_claude", no_spawn)

    rc = orchestrator.execute(_args(repo, only="INT-C"))
    assert rc == 1, "the dependent task must be Blocked"
    assert spawn_calls == [], "no Tasker may be spawned into a conflicted tree"

    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "INT-C")
    assert row["status"] == "Blocked"
    assert "dependency_merge_conflict" in row.get("blocked_reason", "")

    # Journal: task_started carries the conflict detail; task_blocked records it.
    events = _events(repo)
    started = next(
        e for e in events
        if e.event_type == "task_started" and e.task_key == "INT-C"
    )
    conflict = started.payload.get("dependency_merge_conflict")
    assert conflict and conflict["key"] == "INT-B"
    blocked = next(
        e for e in events
        if e.event_type == "task_blocked" and e.task_key == "INT-C"
    )
    assert "dependency_merge_conflict" in blocked.payload["reason"]


# Dependent on an already-Done dependency branch, used to prove the commit
# check measures the Tasker's OWN work against the post-merge baseline.
_DEPENDENT_ONLY_YAML = """\
project: TEST
epic: INT

tasks:
  - key: INT-A
    summary: "dep A"
    description: Already done on its own branch.
    type: Task
    estimate: 5m
    labels: [size:XS, area:test]
    status: Done
    branch: feat/INT-A

  - key: INT-B
    summary: "dependent on A"
    description: blockedBy INT-A.
    type: Task
    estimate: 5m
    labels: [size:XS, area:test]
    blockedBy: [INT-A]
"""


def test_uncommitted_own_work_blocks_despite_merged_dependency(
    repo: Path, monkeypatch,
) -> None:
    """The dependent's commit check must measure the Tasker's own work against
    the post-merge tip, not base. A Tasker that merges dependencies in but
    commits nothing of its own is still caught by the commit-retry net —
    the merged dependency commits must NOT mask a forgot-to-commit failure.
    """
    # A real dependency branch with a commit not on base, marked Done.
    _make_dep_branch(repo, "feat/INT-A", "a.txt", "from A\n")
    _seed_repo_with_yaml(repo, _DEPENDENT_ONLY_YAML)

    # The Tasker reports Done but never commits its own work.
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-no-commit")
    _patch_spawn(monkeypatch)

    rc = orchestrator.execute(_args(repo, only="INT-B"))
    assert rc == 1

    # The dependency WAS merged in (so base..HEAD > 0 from A's commit alone) —
    # yet INT-B is Blocked because the Tasker committed nothing of its own.
    b_wt = repo.parent / "wt" / "worktree-INT-B"
    assert (b_wt / "a.txt").exists(), "dependency merge should have happened"

    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "INT-B")
    assert row["status"] == "Blocked"
    assert "no commits produced after commit-retry" in row.get("blocked_reason", "")


def test_dependency_merge_failure_blocks_without_spawn(repo: Path, monkeypatch) -> None:
    """A dependency merge that fails for a non-conflict reason (committer
    identity unknown) Blocks the dependent under ``dependency_merge_failure``
    — NOT ``dependency_merge_conflict`` — with no Tasker spawned: the YAML
    blocked_reason starts with the label, the task_started payload is keyed
    by it, and task_blocked carries it."""
    # A real dependency branch touching a file absent from base, so the merge
    # is content-clean and fails only at merge-commit creation.
    _make_dep_branch(repo, "feat/INT-A", "a.txt", "from A\n")
    _seed_repo_with_yaml(repo, _DEPENDENT_ONLY_YAML)
    # Break identity only AFTER seeding (the seed itself commits).
    _break_committer_identity(repo, monkeypatch)

    # Record spawn calls; assert the Tasker is never dispatched.
    spawn_calls: list[str] = []

    def no_spawn(claude_bin, cwd, env, prompt, extra_args=None, timeout_seconds=3600):
        spawn_calls.append(env.get("TASK_KEY", "?"))
        raise AssertionError("spawn_claude must not run after a failed dependency merge")

    monkeypatch.setattr(spawn_mod, "spawn_claude", no_spawn)

    rc = orchestrator.execute(_args(repo, only="INT-B"))
    assert rc == 1, "the dependent task must be Blocked"
    assert spawn_calls == [], "no Tasker may be spawned after a failed merge"

    doc = yaml_io.load(repo / "tasks.yaml")
    row = next(t for t in doc["tasks"] if t["key"] == "INT-B")
    assert row["status"] == "Blocked"
    assert row.get("blocked_reason", "").startswith("dependency_merge_failure")

    # Journal: task_started keyed by the failure label (and NOT the conflict
    # label — existing dependency_merge_conflict readers stay unaffected);
    # task_blocked records the label in its reason.
    events = _events(repo)
    started = next(
        e for e in events
        if e.event_type == "task_started" and e.task_key == "INT-B"
    )
    failure = started.payload.get("dependency_merge_failure")
    assert failure and failure["key"] == "INT-A"
    assert failure["branch"] == "feat/INT-A"
    assert "dependency_merge_conflict" not in started.payload
    blocked = next(
        e for e in events
        if e.event_type == "task_blocked" and e.task_key == "INT-B"
    )
    assert "dependency_merge_failure" in blocked.payload["reason"]


# --- direct-to-base (Mode 2) commit check vs. merged dependencies -----------


def test_commit_check_mode2_excludes_merged_dependency_commits(
    repo: Path, tmp_path: Path,
) -> None:
    """Mode 2 (direct-to-base) must not count merged dependency commits as the
    Tasker's own work. A dependent that fast-forwards its dep-containing branch
    into base WITHOUT committing its own work is correctly seen as no-commits
    when feat_baseline_sha is supplied — but masquerades as work without it
    (the pre-INT-4 behavior, asserted here as the discriminator)."""
    init_sha = _git(repo, "rev-parse", "main")
    _make_dep_branch(repo, "feat/DEP", "a.txt", "from A\n")
    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)
    res = wt_mod.merge_dependencies(repo, wt, "main", [("DEP", "feat/DEP")])
    assert res.merged
    feat_baseline = _git(wt.path, "rev-parse", "HEAD")

    # Simulate the Tasker FF'ing its dep-containing branch into base with NO
    # own commit: advance base to the post-merge tip (update-ref, since main
    # is checked out in the repo root worktree).
    _git(repo, "update-ref", "refs/heads/main", feat_baseline)
    log_path = tmp_path / "run.log"

    # With the post-merge baseline: base advanced only by merged deps → no work.
    assert orchestrator._has_commits_on_branch(
        wt, "main", repo, init_sha, log_path, "DEP-C",
        feat_baseline_sha=feat_baseline,
    ) is False
    # Without it: the merged dependency commits are miscounted as work.
    assert orchestrator._has_commits_on_branch(
        wt, "main", repo, init_sha, log_path, "DEP-C",
        feat_baseline_sha=None,
    ) is True


def test_commit_check_mode2_counts_own_work_on_base(
    repo: Path, tmp_path: Path,
) -> None:
    """The feat_baseline exclusion must not over-exclude: genuine own work that
    lands on base (beyond the merged deps) is still detected as commits."""
    init_sha = _git(repo, "rev-parse", "main")
    _make_dep_branch(repo, "feat/DEP", "a.txt", "from A\n")
    base = tmp_path / "wtbase"
    wt = wt_mod.create(repo, "DEP-C", "feat/DEP-C", base_path=base)
    res = wt_mod.merge_dependencies(repo, wt, "main", [("DEP", "feat/DEP")])
    assert res.merged
    feat_baseline = _git(wt.path, "rev-parse", "HEAD")

    # The Tasker commits its own work directly on base (a commit NOT reachable
    # from the post-merge feat tip), while the worktree HEAD stays at baseline.
    _commit_file(repo, "own.txt", "own work\n", "feat: own work on base")
    log_path = tmp_path / "run.log"

    assert orchestrator._has_commits_on_branch(
        wt, "main", repo, init_sha, log_path, "DEP-C",
        feat_baseline_sha=feat_baseline,
    ) is True
