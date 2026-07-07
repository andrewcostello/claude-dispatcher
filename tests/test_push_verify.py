"""Tests for post-Done push/PR verification (INT-3).

Two layers:
  * Unit tests drive ``push_verify.verify`` with an injected ``run`` callable,
    pinning every branch of the decision (no-remote, pushed, absent, stale,
    no-PR, gh-unavailable, expect_pr=False, ls-remote error).
  * Integration tests drive the live dispatch loop against a REAL bare-repo
    ``origin`` through the fake_claude binary, asserting the retry fires and
    ``needs_push`` surfaces in the YAML row and the journal when the push
    never lands — and does NOT surface when the branch is pushed.

Mirrors the commit-retry safety net (test_commit_retry.py): a Done task that
forgot to push is recoverable with one corrective spawn, not an immediate
failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import (
    journal as journal_mod,
    orchestrator,
    push_verify as pv,
    spawn as spawn_mod,
    yaml_io,
)
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


# --------------------------------------------------------------------------
# Unit tests: push_verify.verify with an injected `run`.
# --------------------------------------------------------------------------


def _scripted_run(script):
    """Build a `run` callable that maps a command-key to a (rc, out, err).

    The key is a short discriminator on the command so each test declares only
    the calls it cares about; an unscripted call raises (so tests can't pass by
    accident on a path they didn't model).
    """
    def run(cmd, *, cwd):
        if cmd[:2] == ["git", "remote"]:
            key = "remote"
        elif cmd[:2] == ["git", "rev-parse"]:
            key = "rev-parse"
        elif cmd[:2] == ["git", "ls-remote"]:
            key = "ls-remote"
        elif cmd[1:3] == ["pr", "list"]:
            key = "pr-list"
        else:
            raise AssertionError(f"unscripted command: {cmd}")
        if key not in script:
            raise AssertionError(f"unscripted command-key {key!r}: {cmd}")
        return script[key]
    return run


def test_skips_when_no_remote() -> None:
    run = _scripted_run({"remote": (0, "", "")})
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "skipped-no-remote"
    assert not res.needs_attention


def test_skips_when_remote_named_differently() -> None:
    # An `upstream`-only repo has no `origin` → the default remote is absent.
    run = _scripted_run({"remote": (0, "upstream\n", "")})
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "skipped-no-remote"


def test_pushed_with_open_pr_is_ok() -> None:
    sha = "a" * 40
    run = _scripted_run({
        "remote": (0, "origin\n", ""),
        "rev-parse": (0, sha + "\n", ""),
        "ls-remote": (0, f"{sha}\trefs/heads/feat/x\n", ""),
        "pr-list": (0, '[{"url": "https://example/pr/1"}]', ""),
    })
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "ok"
    assert res.pr_checked is True
    assert not res.needs_attention


def test_pushed_but_branch_absent_on_remote() -> None:
    sha = "a" * 40
    run = _scripted_run({
        "remote": (0, "origin\n", ""),
        "rev-parse": (0, sha + "\n", ""),
        "ls-remote": (0, "", ""),  # branch not on remote
    })
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "not-pushed"
    assert res.needs_attention


def test_stale_remote_tip_is_not_pushed() -> None:
    local, remote = "a" * 40, "b" * 40
    run = _scripted_run({
        "remote": (0, "origin\n", ""),
        "rev-parse": (0, local + "\n", ""),
        "ls-remote": (0, f"{remote}\trefs/heads/feat/x\n", ""),
    })
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "not-pushed"
    assert "behind local" in res.detail


def test_pushed_but_no_open_pr() -> None:
    sha = "a" * 40
    run = _scripted_run({
        "remote": (0, "origin\n", ""),
        "rev-parse": (0, sha + "\n", ""),
        "ls-remote": (0, f"{sha}\trefs/heads/feat/x\n", ""),
        "pr-list": (0, "[]", ""),  # gh conclusive: no open PR
    })
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "no-pr"
    assert res.pr_checked is True
    assert res.needs_attention


def test_gh_unavailable_does_not_flag_pr() -> None:
    sha = "a" * 40
    run = _scripted_run({
        "remote": (0, "origin\n", ""),
        "rev-parse": (0, sha + "\n", ""),
        "ls-remote": (0, f"{sha}\trefs/heads/feat/x\n", ""),
        "pr-list": (127, "", "gh: not found"),  # tool absent / errored
    })
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "ok"
    assert res.pr_checked is False
    assert not res.needs_attention


def test_no_pr_check_when_pr_not_expected() -> None:
    sha = "a" * 40
    # Note: no "pr-list" scripted — verify must not consult gh at all.
    run = _scripted_run({
        "remote": (0, "origin\n", ""),
        "rev-parse": (0, sha + "\n", ""),
        "ls-remote": (0, f"{sha}\trefs/heads/feat/x\n", ""),
    })
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=False, run=run)
    assert res.status == "ok"
    assert res.pr_checked is False


def test_ls_remote_error_is_inconclusive_not_unpushed() -> None:
    sha = "a" * 40
    run = _scripted_run({
        "remote": (0, "origin\n", ""),
        "rev-parse": (0, sha + "\n", ""),
        "ls-remote": (128, "", "fatal: could not read from remote"),
    })
    res = pv.verify(repo_root=Path("/x"), branch="feat/x", expect_pr=True, run=run)
    assert res.status == "error"
    assert not res.needs_attention, "an unreachable remote must not flag needs_push"


# --------------------------------------------------------------------------
# Integration tests: live dispatch loop against a real bare-repo origin.
# --------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with a real bare `origin` remote, mirroring test_commit_retry
    but adding the remote so the push path is exercised end-to-end."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
    roles = repo_dir / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    # The dispatcher writes its run artifacts under `_runs/` inside the repo.
    # With --auto-integrate, auto_integrate.integrate() pristines the working
    # tree (`git clean -fd`) before merging; that removes any untracked,
    # non-ignored path — which would wipe `_runs/` mid-run and make the next
    # `_log` fail with FileNotFoundError. Production keeps the runs dir
    # gitignored (see the auto_integrate `git clean -fd` comment, which lists
    # `docs/runs` among the preserved ignored paths), so mirror that here.
    (repo_dir / ".gitignore").write_text("_runs/\n", encoding="utf-8")
    src = Path(__file__).parent / "fixtures" / "three_task.yaml"
    (repo_dir / "tasks.yaml").write_text(src.read_text(), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir, check=True, capture_output=True)

    # Bare remote, registered as origin. main is pushed so the remote shares
    # history (a feat branch is then "ahead" only by the task's commit).
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repo_dir, check=True, capture_output=True)
    return repo_dir


def _args(repo: Path, **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--run-id", "push-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        "--only", "SMOKE-A",
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in overrides.items():
        flag = f"--{k.replace('_', '-')}"
        if v is True:  # store_true flag (e.g. --auto-integrate)
            argv.append(flag)
        else:
            argv += [flag, str(v)]
    return parser.parse_args(argv)


def _patch_spawn(monkeypatch):
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


def _row(repo: Path):
    doc = yaml_io.load(repo / "tasks.yaml")
    return next(t for t in doc["tasks"] if t["key"] == "SMOKE-A")


def _journal_events(repo: Path):
    jpath = repo / "_runs" / "push-test" / journal_mod.JOURNAL_FILENAME
    return list(journal_mod.read_events(jpath))


def _push_verify_events(repo: Path):
    return [e for e in _journal_events(repo) if e.event_type == "push_verify"]


def test_pushed_branch_lands_done_without_flag(repo: Path, monkeypatch) -> None:
    """A task that commits AND pushes lands Done with no needs_push flag and a
    single push_verify(pushed) event — no retry. (Acceptance: no behavior
    change for tasks that pushed.)"""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-pushed")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert "needs_push" not in row
    evs = _push_verify_events(repo)
    assert len(evs) == 1
    assert evs[0].payload["outcome"] == "pushed"
    assert evs[0].payload["retry_attempted"] is False


def test_unpushed_done_retries_then_flags_needs_push(repo: Path, monkeypatch) -> None:
    """The DISP-9 failure mode: Done with commits but never pushed. The retry
    path fires, and because the push still never lands, needs_push surfaces in
    the YAML row AND the journal. (Acceptance 1.)"""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-no-push")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    # needs_push is advisory — the task is still Done, run still "clean".
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert row.get("needs_push") is True

    evs = _push_verify_events(repo)
    assert len(evs) == 1
    p = evs[0].payload
    assert p["outcome"] == "needs_push"
    assert p["retry_attempted"] is True
    assert p["pre_retry_status"] == "not-pushed"
    assert p["post_retry_status"] == "not-pushed"

    # The terminal task_done event also records the flag.
    done = next(e for e in _journal_events(repo) if e.event_type == "task_done")
    assert done.payload["needs_push"] is True

    # The branch genuinely never reached the remote.
    bare = repo.parent / "origin.git"
    heads = subprocess.run(
        ["git", "ls-remote", "--heads", str(bare)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "SMOKE-A" not in heads


def test_push_retry_recovers(repo: Path, monkeypatch) -> None:
    """When the first run forgets to push but the push-retry invocation pushes,
    the task lands Done with NO needs_push flag and a recovered event."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-push-retry")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert "needs_push" not in row

    evs = _push_verify_events(repo)
    assert len(evs) == 1
    assert evs[0].payload["outcome"] == "recovered"
    assert evs[0].payload["retry_attempted"] is True

    # The branch reached the remote.
    bare = repo.parent / "origin.git"
    heads = subprocess.run(
        ["git", "ls-remote", "--heads", str(bare)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "SMOKE-A" in heads


def test_no_remote_skips_with_journaled_reason(repo: Path, monkeypatch) -> None:
    """With origin removed, push-verify skips and journals the reason — no
    needs_push, status unchanged. (Acceptance 3.)"""
    subprocess.run(["git", "remote", "remove", "origin"], cwd=repo, check=True, capture_output=True)
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-no-push")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert "needs_push" not in row
    evs = _push_verify_events(repo)
    assert len(evs) == 1
    assert evs[0].payload["outcome"] == "skipped-no-remote"
    assert evs[0].payload["retry_attempted"] is False


def test_pushed_no_pr_retries_then_flags(repo: Path, monkeypatch) -> None:
    """Pushed branch but no open PR (and PR expected): the no-pr path fires the
    retry end-to-end and, with the PR still absent, flags needs_push. Simulates
    a present-but-conclusive `gh` (the local bare-repo origin can't host real
    PRs) by forcing _pr_open to report 'no open PR'."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-pushed")
    monkeypatch.setattr(pv, "_pr_open", lambda *a, **k: False)
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert row.get("needs_push") is True
    evs = _push_verify_events(repo)
    assert len(evs) == 1
    p = evs[0].payload
    assert p["outcome"] == "needs_push"
    assert p["pre_retry_status"] == "no-pr"
    assert p["post_retry_status"] == "no-pr"


def test_explicit_not_raised_pr_is_not_flagged(repo: Path, monkeypatch) -> None:
    """A Done that pushed its branch but honestly declared 'Not raised: ...'
    must NOT be flagged for a missing PR, even when `gh` conclusively reports no
    open PR. The push half still passes (branch is pushed), so outcome=pushed
    and no needs_push. Regression guard for the deliberately-PR-less Done."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-pushed-not-raised")
    # _pr_open returns False (conclusive no-PR); expect_pr must suppress it.
    monkeypatch.setattr(pv, "_pr_open", lambda *a, **k: False)
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert "needs_push" not in row
    assert row.get("pr_not_raised_reason")  # the honest declaration was recorded
    evs = _push_verify_events(repo)
    assert len(evs) == 1
    assert evs[0].payload["outcome"] == "pushed"
    assert evs[0].payload["expect_pr"] is False
    assert evs[0].payload["retry_attempted"] is False


def test_auto_integrate_skips_push_verify(repo: Path, monkeypatch) -> None:
    """Auto-integrate merges direct-to-base and never pushes, so push-verify is
    skipped entirely — no push_verify event, no needs_push flag."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "done-no-push")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, auto_integrate=True))
    assert rc == 0
    row = _row(repo)
    assert row["status"] == "Done"
    assert "needs_push" not in row
    assert _push_verify_events(repo) == []
