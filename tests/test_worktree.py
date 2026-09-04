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
    caller gets a typed WorktreeError (not a CalledProcessError traceback).

    AMENDED 2026-08-17. This test used to construct the race as "the branch
    exists and the target path is absent" — but that state is INDISTINGUISHABLE
    from a legitimate re-dispatch, because a branch survives `git worktree
    remove` while the directory does not. Asserting an error there made every
    Blocked task undispatchable once its preserved worktree was tidied; measured
    the same day on all three wave-2 scaffolds.

    The genuine race is the branch being CHECKED OUT by another worker, which
    git refuses on its own, so the typed error still surfaces and this test
    still guards what it was written to guard. Bare-branch-exists is now a
    reuse, sealed in tests/test_worktree_existing_branch.py.
    """
    base = tmp_path / "wtbase"
    # The real collision: another worker already holds this branch.
    subprocess.run(["git", "branch", "feat/DISP-2-x", "main"],
                   cwd=repo, check=True, capture_output=True)
    held = tmp_path / "held-by-another-worker"
    subprocess.run(["git", "worktree", "add", str(held), "feat/DISP-2-x"],
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


def test_worktree_error_str_includes_git_stderr() -> None:
    """`blocked_reason` and the run log both render the error with `str(e)`.
    Dropping stderr there leaves every failure looking identical."""
    e = wt.WorktreeError("git worktree add failed for T-1 at /x",
                         stderr="fatal: invalid reference: main")
    assert "fatal: invalid reference: main" in str(e)
    assert "git worktree add failed for T-1 at /x" in str(e)


def test_worktree_error_str_without_stderr_is_unchanged() -> None:
    assert str(wt.WorktreeError("plain message")) == "plain message"


# ── explaining a dependency-merge conflict ──────────────────────────────────
# `create` REUSES an existing branch rather than resetting it to the base —
# that is deliberate and has recovered real work four times. The cost is that a
# task re-dispatched long after its first attempt merges its dependencies into
# a tree that predates them. Measured on W2-1-3 (2026-08-29): 152 commits
# behind main, and the conflict named five files its dependency never opened.


def _repo_with_stale_branch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo,
                   check=True, capture_output=True)

    def commit(name: str) -> None:
        (repo / name).write_text(name, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", name], cwd=repo,
                       check=True, capture_output=True)

    commit("base")
    subprocess.run(["git", "branch", "stale"], cwd=repo, check=True,
                   capture_output=True)
    for i in range(3):
        commit(f"later-{i}")
    return repo


def test_commits_behind_counts_what_the_branch_is_missing(tmp_path) -> None:
    repo = _repo_with_stale_branch(tmp_path)
    assert wt.commits_behind(repo, "stale", "main") == 3


def test_a_current_branch_is_zero_behind(tmp_path) -> None:
    """Zero is falsy and the caller uses that to stay silent, so a fresh branch
    must report 0 and not None."""
    repo = _repo_with_stale_branch(tmp_path)
    assert wt.commits_behind(repo, "main", "main") == 0


def test_an_unresolvable_ref_reports_none_rather_than_zero(tmp_path) -> None:
    """None and 0 must not be conflated: 0 means "current", None means "could
    not tell", and reporting the second as the first would silently drop the
    explanation on exactly the repos where git is unhappy."""
    repo = _repo_with_stale_branch(tmp_path)
    assert wt.commits_behind(repo, "no-such-branch", "main") is None


# ── two repos sharing a parent collide on worktree paths ───────────────────
# A worktree path is `<repo_root.parent>/worktree-<KEY>` on a host, so every
# repository under ~/Project produces the SAME path for the same task key.
# Measured 2026-08-30: a killed run against claude-dispatcher left
# `worktree-GO-4-1` behind and the next run, against claude-workflow, reused
# it. The task looked for its branch in a checkout of the wrong repository and
# escalated. The reuse path exists to preserve THIS repo's work; a directory
# owned by another repo holds none of it.


def _linked_worktree(tmp_path, owner_name: str, wt_name: str):
    """A directory shaped like git's linked worktree, owned by `owner_name`."""
    owner = tmp_path / owner_name
    (owner / ".git" / "worktrees" / wt_name).mkdir(parents=True)
    linked = tmp_path / wt_name
    linked.mkdir()
    (linked / ".git").write_text(
        f"gitdir: {owner}/.git/worktrees/{wt_name}\n", encoding="utf-8")
    return owner, linked


def test_owning_repo_reads_the_worktree_gitdir_pointer(tmp_path) -> None:
    owner, linked = _linked_worktree(tmp_path, "repo-a", "worktree-T-1")
    assert wt.owning_repo(linked) == owner


def test_owning_repo_is_none_for_an_ordinary_directory(tmp_path) -> None:
    """A normal checkout has `.git` as a DIRECTORY, not a pointer file. None
    means "not a linked worktree", and must not be confused with "owned by
    somebody else" — the caller only refuses on a positive mismatch."""
    plain = tmp_path / "plain"
    (plain / ".git").mkdir(parents=True)
    assert wt.owning_repo(plain) is None


def test_create_refuses_a_worktree_owned_by_another_repo(tmp_path) -> None:
    _owner, _wt = _linked_worktree(tmp_path, "repo-a", "worktree-T-1")
    mine = tmp_path / "repo-b"
    mine.mkdir()

    with pytest.raises(wt.WorktreeError) as ei:
        wt.create(mine, "T-1", "feat/t-1", base_path=tmp_path)
    assert "DIFFERENT repository" in str(ei.value)
    assert "repo-a" in str(ei.value)


def test_create_still_reuses_a_worktree_this_repo_owns(tmp_path) -> None:
    """The refusal must not cost the reuse property, which is what preserves
    commits an unblocked task already made."""
    owner, _wt = _linked_worktree(tmp_path, "repo-a", "worktree-T-1")
    # Same repo: no refusal. It fails later for unrelated reasons (this is not
    # a real git repo), but NOT with the cross-repo message.
    try:
        wt.create(owner, "T-1", "feat/t-1", base_path=tmp_path)
    except wt.WorktreeError as e:
        assert "DIFFERENT repository" not in str(e)
    except Exception:
        pass


# --- naming the Jira ticket, for repos whose CI requires it ----------------
#
# evenplay-mono's "Jira Keys" check requires a key in the BRANCH, the PR TITLE
# and EVERY commit in the range, spelled exactly `SMG-1234`. The dispatcher
# names rows by its own key (`WAL-LEDGER-3`), so every dispatched PR failed it
# -- 26 of 26 on the wallet v2 run. Rows already carry `jira_key`; these thread
# it through the three places CI reads.
#
# The bracketed dispatcher key STAYS. `dispatcher audit`'s landed-by-message
# route greps for `[KEY]` with --fixed-strings, so replacing it would break
# landed-vs-missing detection.


def test_branch_name_leads_with_the_jira_key_when_present() -> None:
    b = wt.branch_name("Task", "WAL-LEDGER-3", "bodies ledger write path",
                       jira_key="SMG-4257")
    assert b.startswith("feat/SMG-4257-"), b
    assert "WAL-LEDGER-3" in b, "the dispatcher key must survive for audit"


def test_branch_name_unchanged_without_a_jira_key() -> None:
    """Byte-identical for every repo that does not use jira_key -- including
    repos whose task key IS the Jira key, the shape the docstring describes."""
    assert wt.branch_name("Task", "SMG-9", "do a thing") == \
        wt.branch_name("Task", "SMG-9", "do a thing", jira_key=None)


def test_branch_name_does_not_double_the_key() -> None:
    """A row whose task key already IS its Jira key must not become
    feat/SMG-9-SMG-9-...."""
    b = wt.branch_name("Task", "SMG-9", "do a thing", jira_key="SMG-9")
    assert b.count("SMG-9") == 1, b


def test_the_prompt_requires_a_jira_trailer_on_every_commit() -> None:
    """The CI gate reads subject+body of EVERY commit in the range, so the
    brief must ask for a trailer, not just a subject tag."""
    from claude_dispatcher import spawn
    prompt = spawn.build_prompt(
        task_key="WAL-LEDGER-3", jira_key="SMG-4257",
        summary_path=Path("/tmp/s.md"), run_id="r", max_iterations=1,
        financial_paths="**", task_summary="s", task_type="Task",
        task_labels=["size:S"], agent="claude",
        task_description="d", branch="feat/x", skip_design=True,
        skip_security_linter=True, reviewer_count=1,
    )
    assert "Jira: SMG-4257" in prompt, prompt[-500:]
    assert "[WAL-LEDGER-3]" in prompt


def test_the_prompt_is_unchanged_without_a_jira_key() -> None:
    from claude_dispatcher import spawn
    kw = dict(task_key="T-1", summary_path=Path("/tmp/s.md"), run_id="r",
              max_iterations=1, financial_paths="**", task_summary="s",
              task_type="Task", task_labels=["size:S"], agent="claude",
              task_description="d", branch="feat/x", skip_design=True,
              skip_security_linter=True, reviewer_count=1)
    assert "Jira:" not in spawn.build_prompt(**kw)


def test_the_dispatchers_own_fallback_commit_names_the_ticket() -> None:
    """When the agent cannot commit, the dispatcher commits for it. That
    message faces the same gate — one auto-committed task would otherwise
    redden the check for the whole PR."""
    from claude_dispatcher import spawn
    msg = spawn._autocommit_message("WAL-LEDGER-3", "codex", "SMG-4257")
    assert "Jira: SMG-4257" in msg and "[WAL-LEDGER-3]" in msg
    assert "Jira:" not in spawn._autocommit_message("T-1", "codex", None)


def test_the_snapshot_carries_jira_key_into_the_pr_title() -> None:
    """End-to-end through the title generator: a row's jira_key must reach the
    PR title, and the bracketed dispatcher key must survive for audit."""
    from claude_dispatcher import orchestrator as orch
    snap = orch.TaskSnapshot(
        key="WAL-LEDGER-3", summary="bodies ledger", description="d",
        type="Task", labels=["size:S"], jira_key="SMG-4257")
    title = orch._generated_pr_title(snap)
    assert "SMG-4257" in title and "[WAL-LEDGER-3]" in title, title
    bare = orch.TaskSnapshot(
        key="T-1", summary="s", description="d", type="Task", labels=[])
    assert orch._generated_pr_title(bare) == "feat: [T-1] s"


def test_a_bodies_brief_states_that_parameter_names_are_part_of_the_signature() -> None:
    """The gate blocks a bodies task that renames a scaffolded parameter, and
    the brief never said so.

    Measured 2026-09-03, WAL-LEDGER-3's fifth block: it moved ServiceCredit
    and CreditCorrection into post.go and renamed `c` -> `credit` on the way.
    `SignatureChange` is explicit that "a renamed parameter IS a change", so
    the gate is behaving as designed -- but the implementer brief says nothing
    about signatures at all, so the agent was blocked by a rule it was never
    given. Enforcing an unstated rule is the defect, not the rename.
    """
    from claude_dispatcher import spawn
    kw = dict(task_key="T-1", summary_path=Path("/tmp/s.md"), run_id="r",
              max_iterations=1, financial_paths="**", task_summary="s",
              task_type="Task", task_labels=["size:S"], agent="claude",
              task_description="d", branch="feat/x", skip_design=True,
              skip_security_linter=True, reviewer_count=1)
    body = spawn.build_prompt(role="bodies", **kw).lower()
    assert "parameter name" in body, "must say parameter names count"
    assert "deviation" in body, "a needed signature change is a Deviation"
    # A scaffold task writes the signatures, so the constraint must not appear.
    assert "parameter name" not in spawn.build_prompt(role="scaffold", **kw).lower()


def test_the_orchestrator_passes_the_role_to_the_brief() -> None:
    """END TO END wiring, not the helper. A `role=` parameter the orchestrator
    never fills is inert — which is exactly how PR #93 shipped a fix that did
    nothing. Every build_prompt call site must carry the role."""
    import inspect, re
    from claude_dispatcher import orchestrator as orch
    src = inspect.getsource(orch)
    calls = re.findall(r"spawn_mod\.build_prompt\(\n(.*?)\n\s*\)", src, re.DOTALL)
    assert calls, "no build_prompt call sites found"
    missing = [i for i, c in enumerate(calls) if "role=" not in c]
    assert not missing, (
        f"{len(missing)} of {len(calls)} build_prompt call sites do not pass "
        "the role, so the bodies constraint never reaches the agent"
    )
