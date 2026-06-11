"""Mechanical merge engine + `dispatcher merge-prs` command (PRF-4).

These exercise the merge pass directly against a real git repo, a tasks YAML
with Awaiting Review rows, and a stubbed `gh` (review state + merge), so the
ladder, the topological ordering, and the conflict path are tested without
spawning a Tasker. The four acceptance criteria map to:

  * low-risk chain A<-B merges in order, B never before A   → test_low_risk_chain_*
  * elevated without approval stays + notifies once; with    → test_elevated_*
    a stubbed approval, merges
  * conflict → needs_rebase journaled+notified, engine        → test_conflict_*
    continues with the other eligible PRs
  * merge-prs works against a finished run's YAML/journal      → test_merge_prs_command_*
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import merge_engine as me
from claude_dispatcher import notify as notify_mod
from claude_dispatcher import pr as pr_mod
from claude_dispatcher import yaml_io
from claude_dispatcher import merge_prs as merge_prs_cmd


# A `gh` stub covering the three calls the engine makes. `pr create` is unused
# here (rows arrive pre-raised). Behavior is env-driven so each test scripts
# approvals/conflicts per PR number:
#   FAKE_GH_APPROVED — comma list of PR numbers whose `pr view` reports APPROVED
#   FAKE_GH_CONFLICT — comma list of PR numbers whose `pr merge` fails as a conflict
#   FAKE_GH_ERROR    — comma list of PR numbers whose `pr merge` fails (non-conflict)
# Every invocation is appended to $FAKE_GH_LOG so tests assert merge ORDER.
_FAKE_GH = '''\
#!/usr/bin/env python3
import os, sys, json
args = sys.argv[1:]
log = os.environ.get("FAKE_GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(" ".join(args) + "\\n")

def _num():
    for a in args:
        if a.isdigit():
            return a
    return ""

def _csv(name):
    return [x for x in os.environ.get(name, "").split(",") if x]

if "view" in args:
    num = _num()
    if num in _csv("FAKE_GH_APPROVED"):
        reviews = [{"author": {"login": "reviewer-bot"}, "state": "APPROVED"}]
    else:
        reviews = []
    print(json.dumps({"reviews": reviews}))
    sys.exit(0)
if "merge" in args:
    num = _num()
    if num in _csv("FAKE_GH_CONFLICT"):
        sys.stderr.write("failed to merge: not mergeable: merge conflict\\n")
        sys.exit(1)
    if num in _csv("FAKE_GH_ERROR"):
        sys.stderr.write("HTTP 403: insufficient permissions\\n")
        sys.exit(1)
    sys.exit(0)
sys.exit(0)
'''


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _write_gh(repo: Path) -> Path:
    gh = repo / "fake_gh.py"
    gh.write_text(_FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    return gh


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with main + a `feature/x` branch forked from it."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path,
                   check=True, capture_output=True)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path,
                   check=True, capture_output=True)
    subprocess.run(["git", "branch", "feature/x", "main"], cwd=tmp_path,
                   check=True, capture_output=True)
    _write_gh(tmp_path)
    return tmp_path


def _make_branch(repo: Path, branch: str, filename: str, body: str = "x = 1\n") -> None:
    """Create `branch` off feature/x with one small commit adding `filename`.

    Done via a temp worktree so the repo's own checkout (main) is untouched and
    the branch becomes a real ref the engine can diff against.
    """
    wt = repo.parent / f"wt-{branch.replace('/', '-')}"
    subprocess.run(["git", "worktree", "add", "-b", branch, str(wt), "feature/x"],
                   cwd=repo, check=True, capture_output=True)
    (wt / filename).write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=wt, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", f"work on {branch}"],
                   cwd=wt, check=True, capture_output=True)
    subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                   cwd=repo, check=True, capture_output=True)


def _row(key, *, pr_number, branch, labels, blocked_by=None, status="Awaiting Review"):
    r = {
        "key": key,
        "summary": f"summary {key}",
        "description": f"desc {key}",
        "type": "Task",
        "labels": labels,
        "status": status,
        "branch": branch,
        "pr_number": pr_number,
        "pr_url": f"https://github.com/test/repo/pull/{pr_number}",
        "verified": True,
        "verification_iterations": 0,
    }
    if blocked_by:
        r["blockedBy"] = blocked_by
    return r


def _write_tasks(repo: Path, rows: list[dict]) -> Path:
    path = repo / "tasks.yaml"
    yaml_io.dump({"project": "T", "epic": "X", "tasks": rows}, path)
    return path


def _cfg(repo: Path, tasks_path: Path) -> me.MergeEngineConfig:
    return me.MergeEngineConfig(
        tasks_path=tasks_path,
        repo_root=repo,
        feature_branch="feature/x",
        gh_bin=str(repo / "fake_gh.py"),
        run_id="run-1",
    )


def _status(repo: Path, key: str) -> str:
    doc = yaml_io.load(repo / "tasks.yaml")
    return next(t for t in doc["tasks"] if t["key"] == key)["status"]


def _rowof(repo: Path, key: str) -> dict:
    doc = yaml_io.load(repo / "tasks.yaml")
    return next(t for t in doc["tasks"] if t["key"] == key)


def _merge_order(gh_log: Path) -> list[str]:
    """PR numbers in the order `pr merge <n>` was invoked."""
    out = []
    for line in gh_log.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if "merge" in parts:
            out += [p for p in parts if p.isdigit()]
    return out


# --------------------------------------------------------------------------- #
# Low-risk chain ordering
# --------------------------------------------------------------------------- #

def test_low_risk_chain_merges_in_order(repo: Path, monkeypatch) -> None:
    """A<-B, both low-risk: both merge, and A merges before B even though B is
    just as approved — the topological gate forces the order."""
    _make_branch(repo, "feat-a", "a.py")
    _make_branch(repo, "feat-b", "b.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "area:x"]),
        _row("B", pr_number=2, branch="feat-b", labels=["size:S", "area:x"],
             blocked_by=["A"]),
    ])
    gh_log = repo / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))

    result = me.merge_pass(_cfg(repo, tasks), notifier=notify_mod.NullNotifier())

    assert _status(repo, "A") == "Merged"
    assert _status(repo, "B") == "Merged"
    assert result.merged == ["A", "B"]
    # A's PR (#1) merged before B's (#2): ordering enforced, not eyeballed.
    assert _merge_order(gh_log) == ["1", "2"]
    # Self-approved low-risk records the dispatcher as approver + merger.
    assert _rowof(repo, "A")["pr_approved_by"] == me.DISPATCHER_APPROVER
    assert _rowof(repo, "A")["merged_by"] == me.DISPATCHER_APPROVER


def test_dependent_never_merges_before_unmerged_dependency(repo: Path, monkeypatch) -> None:
    """B (low-risk, fully approved) must NOT merge while its dependency A is
    held unmerged (A elevated, no external approval). The approval-first
    dependent is still gated on the dependency landing first."""
    _make_branch(repo, "feat-a", "a.py")
    _make_branch(repo, "feat-b", "b.py")
    tasks = _write_tasks(repo, [
        # A elevated via a forbidden label → needs external approval (absent).
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "financial"]),
        _row("B", pr_number=2, branch="feat-b", labels=["size:S", "area:x"],
             blocked_by=["A"]),
    ])
    gh_log = repo / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))

    result = me.merge_pass(_cfg(repo, tasks), notifier=notify_mod.NullNotifier())

    assert _status(repo, "A") == "Awaiting Review"
    assert _status(repo, "B") == "Awaiting Review"  # gated on A merging first
    assert result.awaiting_approval == ["A"]
    assert result.merged == []
    # B was never even merge-attempted — it never entered the mergeable set.
    assert "2" not in _merge_order(gh_log)


def test_dependent_merges_after_dependency_gets_approval(repo: Path, monkeypatch) -> None:
    """Once A's external approval lands, A merges and B cascades in the same
    pass — in order."""
    _make_branch(repo, "feat-a", "a.py")
    _make_branch(repo, "feat-b", "b.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "financial"]),
        _row("B", pr_number=2, branch="feat-b", labels=["size:S", "area:x"],
             blocked_by=["A"]),
    ])
    gh_log = repo / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))
    monkeypatch.setenv("FAKE_GH_APPROVED", "1")  # A approved externally

    result = me.merge_pass(_cfg(repo, tasks), notifier=notify_mod.NullNotifier())

    assert _status(repo, "A") == "Merged"
    assert _status(repo, "B") == "Merged"
    assert _merge_order(gh_log) == ["1", "2"]
    assert _rowof(repo, "A")["pr_approved_by"] == "external:reviewer-bot"


# --------------------------------------------------------------------------- #
# Elevated approval ladder + once-per-task notification
# --------------------------------------------------------------------------- #

def test_elevated_without_approval_stays_and_notifies_once(repo: Path, monkeypatch) -> None:
    """An elevated PR with no external approval stays Awaiting Review and
    notifies exactly once across repeated passes (shared state)."""
    _make_branch(repo, "feat-a", "a.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "financial"]),
    ])
    gh_log = repo / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))
    notifier = notify_mod.NullNotifier()
    state = me.MergePassState()
    cfg = _cfg(repo, tasks)

    me.merge_pass(cfg, notifier=notifier, state=state)
    me.merge_pass(cfg, notifier=notifier, state=state)  # second pass, same run

    assert _status(repo, "A") == "Awaiting Review"
    assert "1" not in _merge_order(gh_log)  # never merged
    approvals = [n for n in notifier.sent if "awaiting approval to merge" in n.title]
    assert len(approvals) == 1  # once per task, not per pass


def test_elevated_with_external_approval_merges(repo: Path, monkeypatch) -> None:
    """An elevated PR with a stubbed GitHub approval merges, recording the
    external approver and emitting pr_approved + pr_merged."""
    _make_branch(repo, "feat-a", "a.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=7, branch="feat-a", labels=["size:S", "security"]),
    ])
    monkeypatch.setenv("FAKE_GH_APPROVED", "7")
    jpath = repo / "journal.jsonl"
    journal = journal_mod.Journal.create(
        jpath, tasks_yaml_path=tasks, reviewer_prompts_dir=repo, run_id="run-1")

    me.merge_pass(_cfg(repo, tasks), journal=journal,
                  notifier=notify_mod.NullNotifier())

    row = _rowof(repo, "A")
    assert row["status"] == "Merged"
    assert row["pr_approved_by"] == "external:reviewer-bot"
    assert row["merged_by"] == me.DISPATCHER_APPROVER

    approved = [e for e in journal_mod.read_events(jpath)
                if e.event_type == "pr_approved"]
    merged = [e for e in journal_mod.read_events(jpath)
              if e.event_type == "pr_merged"]
    assert len(approved) == 1 and approved[0].payload["risk_level"] == "elevated"
    assert approved[0].payload["approver"] == "external:reviewer-bot"
    assert len(merged) == 1
    assert merged[0].payload["merger"] == me.DISPATCHER_APPROVER
    assert merged[0].payload["target"] == "feature/x"
    assert merged[0].payload["feature_branch_sha"]
    assert journal_mod.verify(jpath).ok


# --------------------------------------------------------------------------- #
# Conflict path
# --------------------------------------------------------------------------- #

def test_conflict_sets_needs_rebase_notifies_and_continues(repo: Path, monkeypatch) -> None:
    """A's merge conflicts → needs_rebase + journal + one notify, and the engine
    CONTINUES to merge the independent B."""
    _make_branch(repo, "feat-a", "a.py")
    _make_branch(repo, "feat-b", "b.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "area:x"]),
        _row("B", pr_number=2, branch="feat-b", labels=["size:S", "area:x"]),
    ])
    monkeypatch.setenv("FAKE_GH_CONFLICT", "1")  # A conflicts
    jpath = repo / "journal.jsonl"
    journal = journal_mod.Journal.create(
        jpath, tasks_yaml_path=tasks, reviewer_prompts_dir=repo, run_id="run-1")
    notifier = notify_mod.NullNotifier()

    result = me.merge_pass(_cfg(repo, tasks), journal=journal, notifier=notifier)

    # A held, flagged; B merged — the engine did not stop at the conflict.
    assert _status(repo, "A") == "Awaiting Review"
    assert _rowof(repo, "A")["needs_rebase"] is True
    assert _status(repo, "B") == "Merged"
    assert result.needs_rebase == ["A"]
    assert result.merged == ["B"]

    failed = [e for e in journal_mod.read_events(jpath)
              if e.event_type == "pr_merge_failed"]
    assert len(failed) == 1
    assert failed[0].payload["kind"] == "conflict"
    assert failed[0].payload["needs_rebase"] is True

    rebase_notes = [n for n in notifier.sent if "needs rebase" in n.title]
    assert len(rebase_notes) == 1
    assert journal_mod.verify(jpath).ok


def test_conflict_not_retried_within_run_but_retried_with_fresh_state(
    repo: Path, monkeypatch,
) -> None:
    """A conflicting PR is attempted once per RUN (shared state), not once per
    pass — re-attempting mid-run can't help without an out-of-band rebase. A
    fresh state (the standalone catch-up) DOES retry, which is when a rebase may
    have landed."""
    _make_branch(repo, "feat-a", "a.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "area:x"]),
    ])
    gh_log = repo / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))
    monkeypatch.setenv("FAKE_GH_CONFLICT", "1")
    cfg = _cfg(repo, tasks)
    state = me.MergePassState()

    me.merge_pass(cfg, notifier=notify_mod.NullNotifier(), state=state)
    me.merge_pass(cfg, notifier=notify_mod.NullNotifier(), state=state)
    # Same run (shared state): merge attempted exactly once across both passes.
    assert _merge_order(gh_log) == ["1"]

    # Fresh state == the standalone catch-up: it retries the conflicting PR.
    me.merge_pass(cfg, notifier=notify_mod.NullNotifier(),
                  state=me.MergePassState())
    assert _merge_order(gh_log) == ["1", "1"]


def test_non_conflict_merge_error_does_not_flag_needs_rebase(repo: Path, monkeypatch) -> None:
    """A non-conflict gh failure surfaces (merge_error) but never sets
    needs_rebase — a rebase wouldn't fix an auth/usage error."""
    _make_branch(repo, "feat-a", "a.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "area:x"]),
    ])
    monkeypatch.setenv("FAKE_GH_ERROR", "1")

    result = me.merge_pass(_cfg(repo, tasks), notifier=notify_mod.NullNotifier())

    row = _rowof(repo, "A")
    assert row["status"] == "Awaiting Review"
    assert "needs_rebase" not in row
    assert row["merge_error"]
    assert result.needs_rebase == ["A"]  # surfaced in the same bucket for the caller


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

def test_no_awaiting_review_rows_is_a_noop(repo: Path) -> None:
    """Nothing Awaiting Review → empty pass, no crash."""
    _make_branch(repo, "feat-a", "a.py")
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S"], status="Merged"),
    ])
    result = me.merge_pass(_cfg(repo, tasks), notifier=notify_mod.NullNotifier())
    assert result.merged == [] and result.awaiting_approval == []


def test_awaiting_row_without_pr_number_is_unactionable(repo: Path) -> None:
    """An Awaiting Review row with no pr_number can't be merged — surfaced, not
    crashed, not merged."""
    _make_branch(repo, "feat-a", "a.py")
    row = _row("A", pr_number=1, branch="feat-a", labels=["size:S"])
    del row["pr_number"]
    tasks = _write_tasks(repo, [row])
    result = me.merge_pass(_cfg(repo, tasks), notifier=notify_mod.NullNotifier())
    assert result.unactionable == ["A"]
    assert _status(repo, "A") == "Awaiting Review"


def test_non_integer_pr_number_is_unactionable_not_a_crash(repo: Path) -> None:
    """A hand-edited, non-numeric pr_number (realistic for the standalone
    command on human YAML) is unactionable, not a ValueError that aborts the
    whole pass."""
    _make_branch(repo, "feat-a", "a.py")
    _make_branch(repo, "feat-b", "b.py")
    bad = _row("A", pr_number=1, branch="feat-a", labels=["size:S"])
    bad["pr_number"] = "not-a-number"
    tasks = _write_tasks(repo, [
        bad,
        _row("B", pr_number=2, branch="feat-b", labels=["size:S", "area:x"]),
    ])
    result = me.merge_pass(_cfg(repo, tasks), notifier=notify_mod.NullNotifier())
    assert result.unactionable == ["A"]
    # The good independent PR still merged — one bad row didn't abort the pass.
    assert _status(repo, "B") == "Merged"


# --------------------------------------------------------------------------- #
# `dispatcher merge-prs` command
# --------------------------------------------------------------------------- #

class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _finished_run(repo: Path, runs_dir: Path, rows: list[dict]) -> Path:
    """Stand up a finished pr-mode run: tasks YAML + a journal whose genesis
    run_config locates everything, capped with a run_complete event."""
    tasks = _write_tasks(repo, rows)
    run_dir = runs_dir / "run-9"
    run_dir.mkdir(parents=True)
    jpath = run_dir / journal_mod.JOURNAL_FILENAME
    run_config = {
        "tasks_yaml": str(tasks),
        "integration": "pr",
        "feature_branch": "feature/x",
        "base_branch": "feature/x",
        "gh_bin": str(repo / "fake_gh.py"),
        "run_id": "run-9",
        "lock_timeout_seconds": 30.0,
    }
    journal = journal_mod.Journal.create(
        jpath, tasks_yaml_path=tasks, reviewer_prompts_dir=repo,
        run_id="run-9", run_config=run_config)
    journal.append(journal_mod.EventType.run_complete,
                   {"done": 0, "blocked": 0, "escalated": 0, "blocked_rollup": []})
    return jpath


def test_merge_prs_command_merges_finished_run(repo: Path, tmp_path: Path, capsys) -> None:
    """merge-prs reconstructs the run from its journal, merges the eligible
    low-risk PRs, and appends pr_merged to the SAME (still-verifiable) chain."""
    _make_branch(repo, "feat-a", "a.py")
    _make_branch(repo, "feat-b", "b.py")
    runs_dir = tmp_path / "runs"
    jpath = _finished_run(repo, runs_dir, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "area:x"]),
        _row("B", pr_number=2, branch="feat-b", labels=["size:S", "area:x"],
             blocked_by=["A"]),
    ])

    rc = merge_prs_cmd.execute(_Args(run_id="run-9", runs_dir=str(runs_dir),
                                     force=True))
    assert rc == 0
    assert _status(repo, "A") == "Merged"
    assert _status(repo, "B") == "Merged"
    merged = [e for e in journal_mod.read_events(jpath)
              if e.event_type == "pr_merged"]
    assert len(merged) == 2
    # The merge events extend the existing chain past run_complete; still valid.
    assert journal_mod.verify(jpath).ok


def test_merge_prs_command_refuses_recent_run_without_force(repo: Path, tmp_path: Path) -> None:
    """The liveness guard: a fresh journal (recent last event) is refused with
    exit 4 unless --force, to avoid double-merging a still-active run."""
    _make_branch(repo, "feat-a", "a.py")
    runs_dir = tmp_path / "runs"
    _finished_run(repo, runs_dir, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S", "area:x"]),
    ])
    rc = merge_prs_cmd.execute(_Args(run_id="run-9", runs_dir=str(runs_dir),
                                     force=False))
    assert rc == 4
    assert _status(repo, "A") == "Awaiting Review"  # untouched


def test_merge_prs_command_noop_for_branch_mode(repo: Path, tmp_path: Path, capsys) -> None:
    """A branch-mode run has no PRs to merge — clean exit 0, no-op."""
    tasks = _write_tasks(repo, [
        _row("A", pr_number=1, branch="feat-a", labels=["size:S"], status="Done"),
    ])
    run_dir = tmp_path / "runs" / "run-b"
    run_dir.mkdir(parents=True)
    jpath = run_dir / journal_mod.JOURNAL_FILENAME
    journal_mod.Journal.create(
        jpath, tasks_yaml_path=tasks, reviewer_prompts_dir=repo, run_id="run-b",
        run_config={"tasks_yaml": str(tasks), "integration": "branch",
                    "run_id": "run-b"})
    rc = merge_prs_cmd.execute(_Args(run_id="run-b", runs_dir=str(tmp_path / "runs"),
                                     force=True))
    assert rc == 0
    assert "not a pr-mode run" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# pr.py adapters (gh review state + merge) parsing
# --------------------------------------------------------------------------- #

def test_pr_review_state_latest_per_author(repo: Path) -> None:
    """An author's CHANGES_REQUESTED followed by APPROVED reads as approved;
    a trailing CHANGES_REQUESTED blocks even if an earlier APPROVED exists."""
    gh = repo / "gh_reviews.py"
    gh.write_text(
        "#!/usr/bin/env python3\nimport json,sys\n"
        "print(json.dumps({'reviews':["
        "{'author':{'login':'x'},'state':'CHANGES_REQUESTED'},"
        "{'author':{'login':'x'},'state':'APPROVED'}]}))\n",
        encoding="utf-8")
    gh.chmod(0o755)
    st = pr_mod.pr_review_state(cwd=repo, number=1, gh_bin=str(gh))
    assert st.approved is True
    assert st.approver == "x"
    assert st.error is None


def test_pr_review_state_fails_closed_on_error(repo: Path) -> None:
    """A missing gh binary → approved False with an error (caller fails closed)."""
    st = pr_mod.pr_review_state(cwd=repo, number=1, gh_bin="/nonexistent/gh")
    assert st.approved is False and st.error


def test_merge_pr_detects_conflict_vs_error(repo: Path) -> None:
    conflict_gh = repo / "gh_conflict.py"
    conflict_gh.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "sys.stderr.write('Pull request is not mergeable\\n'); sys.exit(1)\n",
        encoding="utf-8")
    conflict_gh.chmod(0o755)
    res = pr_mod.merge_pr(cwd=repo, number=1, gh_bin=str(conflict_gh))
    assert res.merged is False and res.conflict is True

    err_gh = repo / "gh_err.py"
    err_gh.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "sys.stderr.write('HTTP 403 forbidden\\n'); sys.exit(1)\n",
        encoding="utf-8")
    err_gh.chmod(0o755)
    res2 = pr_mod.merge_pr(cwd=repo, number=1, gh_bin=str(err_gh))
    assert res2.merged is False and res2.conflict is False
