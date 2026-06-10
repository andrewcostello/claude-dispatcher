"""Run-start preflight checks (OPS-3).

Two layers, mirroring test_push_verify.py:
  * Unit tests drive ``preflight.run_preflight`` against throwaway git repos,
    pinning every check's pass/warn/fail branch — including each accepted
    permission-bypass mechanism and the two rejected look-alikes.
  * End-to-end tests drive ``orchestrator.execute`` (and ``run.execute`` for
    the dry-run path) through the fake-claude harness, asserting the
    fail-fast contract: a failed preflight exits 2 BEFORE any run_dir,
    journal, or worktree exists, while a clean run journals a ``preflight``
    event at seq 1 and a ``--skip-preflight`` run journals the skip.

Hermeticity: nothing here depends on this machine's real `claude` binary or
pipx state. The binary probe uses ``sys.executable`` (or a deliberately
nonexistent name); the staleness check uses fixture repos with a synthetic
pyproject.toml plus a monkeypatched installed-version lookup.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import (
    journal as journal_mod,
    orchestrator,
    preflight,
    run as run_mod,
    spawn as spawn_mod,
)
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures"
FAKE_CLAUDE = FIXTURE_DIR / "fake_claude.py"

# The pair form is the canonical accepted mechanism; tests that just need a
# preflight-clean arg list use this.
BYPASS_ARGS = ["--permission-mode", "bypassPermissions"]


# --- fixture repos -----------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
    )


def _init_repo(repo_dir: Path) -> Path:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)],
                   check=True, capture_output=True)
    _git(repo_dir, "config", "user.email", "t@t")
    _git(repo_dir, "config", "user.name", "t")
    return repo_dir


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Git repo with a TRACKED regular tasker.md + the three-task YAML.

    Nested under tmp_path/"repo" so repo.parent (the worktree base and the
    preflight probe's parent) is unique per test.
    """
    repo_dir = _init_repo(tmp_path / "repo")
    roles = repo_dir / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("stub", encoding="utf-8")
    (repo_dir / "tasks.yaml").write_text(
        (FIXTURE_DIR / "three_task.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    return repo_dir


@pytest.fixture
def bare_repo(tmp_path: Path) -> Path:
    """Git repo with one commit and NO role file anywhere (tracked or not)."""
    repo_dir = _init_repo(tmp_path / "repo")
    (repo_dir / "README.md").write_text("init\n", encoding="utf-8")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    return repo_dir


@pytest.fixture
def symlink_repo(tmp_path: Path) -> Path:
    """Mirror this repo's dogfood layout: `.claude/workflow` is a COMMITTED
    relative symlink to ../../claude-workflow (a directory OUTSIDE the repo,
    sibling of it), so `git ls-files` on the role file fails even though the
    path resolves in any worktree created next to the repo."""
    workflow = tmp_path / "claude-workflow" / "roles"
    workflow.mkdir(parents=True)
    (workflow / "tasker.md").write_text("real role file", encoding="utf-8")

    repo_dir = _init_repo(tmp_path / "repo")
    dot_claude = repo_dir / ".claude"
    dot_claude.mkdir()
    # Relative target: from repo/.claude, ../../claude-workflow == tmp_path/claude-workflow.
    (dot_claude / "workflow").symlink_to(Path("..") / ".." / "claude-workflow")
    (repo_dir / "README.md").write_text("init\n", encoding="utf-8")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    # Sanity: the symlink itself is tracked (mode 120000), the role file is not.
    assert (repo_dir / ".claude" / "workflow" / "roles" / "tasker.md").exists()
    return repo_dir


def _seed_pyproject(repo: Path, *, name: str, version: str) -> None:
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\n', encoding="utf-8",
    )
    _git(repo, "add", "pyproject.toml")
    _git(repo, "commit", "-q", "-m", "pyproject")


def _pf(repo: Path, **overrides) -> preflight.PreflightResult:
    kwargs = dict(
        claude_bin=sys.executable,
        claude_extra_args=list(BYPASS_ARGS),
        mode="unattended",
        repo_root=repo,
        base_branch="main",
    )
    kwargs.update(overrides)
    return preflight.run_preflight(**kwargs)


# --- end-to-end harness (mirrors test_orchestrator_journal.py) ---------------


def _args(repo: Path, *extra_argv: str, run_id: str = "pf-test", **overrides):
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended", "--max-parallel", "1",
        "--max-iterations", "2",
        "--run-id", run_id,
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt"),
        "--claude-bin", sys.executable,
        *extra_argv,
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


def _journal_events(repo: Path, run_id: str = "pf-test"):
    return list(journal_mod.read_events(
        repo / "_runs" / run_id / journal_mod.JOURNAL_FILENAME))


# --- permission flags (unit) -------------------------------------------------


def test_missing_permission_flags_unattended_fails(repo: Path) -> None:
    res = _pf(repo, claude_extra_args=[])
    assert not res.ok
    assert any("--claude-extra-args" in f for f in res.failures)
    assert any("permission-bypass" in f for f in res.failures)
    assert res.checks["permission_flags"]["ok"] is False


def test_missing_permission_flags_supervised_fails(repo: Path) -> None:
    res = _pf(repo, claude_extra_args=[], mode="supervised")
    assert not res.ok
    assert any("permission-bypass" in f for f in res.failures)


@pytest.mark.parametrize("args", [
    ["--permission-mode", "bypassPermissions"],
    ["--permission-mode=bypassPermissions"],
    ["--dangerously-skip-permissions"],
    # Stacked with other args, mechanism still found.
    ["--model", "opus", "--permission-mode", "bypassPermissions",
     "--allow-dangerously-skip-permissions"],
])
def test_accepted_permission_mechanisms_pass(repo: Path, args: list[str]) -> None:
    res = _pf(repo, claude_extra_args=args)
    assert res.ok, res.failures
    assert res.checks["permission_flags"]["ok"] is True
    assert res.checks["permission_flags"]["mechanism"]


@pytest.mark.parametrize("args", [
    ["--permission-mode", "plan"],
    ["--permission-mode=plan"],
    ["--allow-dangerously-skip-permissions"],
    # Pair must be adjacent: a value-consuming flag in between breaks it.
    ["--permission-mode", "plan", "bypassPermissions"],
])
def test_rejected_permission_lookalikes_fail(repo: Path, args: list[str]) -> None:
    res = _pf(repo, claude_extra_args=args)
    assert not res.ok
    assert res.checks["permission_flags"]["ok"] is False


# --- claude binary (unit) ----------------------------------------------------


def test_missing_claude_binary_fails(repo: Path) -> None:
    res = _pf(repo, claude_bin="definitely-not-a-real-binary-xyz")
    assert not res.ok
    assert any("not found on PATH" in f for f in res.failures)
    assert any("--claude-bin" in f for f in res.failures)
    assert res.checks["claude_binary"]["ok"] is False


def test_present_binary_with_unreadable_version_warns_only(
    repo: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(preflight.doctor, "probe_binary", lambda name, **kw: {
        "present": True, "path": "/usr/bin/x", "version": None,
        "version_raw": None, "version_error": "--version exited 1",
    })
    res = _pf(repo)
    assert res.ok
    assert any("version" in w for w in res.warnings)
    assert res.checks["claude_binary"]["ok"] is True


# --- dispatcher staleness (unit + end-to-end) ---------------------------------


def test_staleness_warns_when_repo_version_differs(repo: Path, monkeypatch) -> None:
    _seed_pyproject(repo, name="claude-dispatcher", version="9.9.9")
    monkeypatch.setattr(preflight, "_installed_version", lambda: "0.1.0")
    res = _pf(repo)
    assert res.ok, "staleness is a warning, never a failure"
    assert any("9.9.9" in w and "0.1.0" in w for w in res.warnings)
    assert any("pipx install --force" in w for w in res.warnings)
    chk = res.checks["dispatcher_staleness"]
    assert chk["applicable"] is True
    assert chk["stale"] is True


def test_staleness_silent_when_versions_match(repo: Path, monkeypatch) -> None:
    _seed_pyproject(repo, name="claude-dispatcher", version="0.1.0")
    monkeypatch.setattr(preflight, "_installed_version", lambda: "0.1.0")
    res = _pf(repo)
    assert res.ok
    assert not res.warnings
    assert res.checks["dispatcher_staleness"]["stale"] is False


def test_staleness_not_applicable_for_other_repo(repo: Path, monkeypatch) -> None:
    _seed_pyproject(repo, name="some-other-project", version="3.0.0")
    monkeypatch.setattr(preflight, "_installed_version", lambda: "0.1.0")
    res = _pf(repo)
    assert res.ok
    assert not res.warnings
    assert res.checks["dispatcher_staleness"]["applicable"] is False


def test_staleness_not_applicable_without_pyproject(repo: Path) -> None:
    res = _pf(repo)
    assert res.ok
    assert res.checks["dispatcher_staleness"]["applicable"] is False


def test_staleness_skipped_when_installed_version_unknown(
    repo: Path, monkeypatch,
) -> None:
    _seed_pyproject(repo, name="claude-dispatcher", version="9.9.9")
    monkeypatch.setattr(preflight, "_installed_version", lambda: None)
    res = _pf(repo)
    assert res.ok
    assert not res.warnings
    assert res.checks["dispatcher_staleness"]["applicable"] is False


def test_staleness_falls_back_to_working_tree_when_not_committed(
    repo: Path, monkeypatch,
) -> None:
    """No pyproject.toml at HEAD → the working-tree file is consulted."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "claude-dispatcher"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )  # deliberately NOT committed
    monkeypatch.setattr(preflight, "_installed_version", lambda: "0.1.0")
    res = _pf(repo)
    assert any("9.9.9" in w for w in res.warnings)


def test_parse_name_version_regex_fallback_on_broken_toml() -> None:
    """A pyproject that tomllib rejects still yields name/version via the
    tolerant line regex (the check only ever warns, so it must not crash)."""
    text = (
        'name = "claude-dispatcher"\n'
        'version = "1.2.3"\n'
        "this is [not(valid toml ===\n"
    )
    assert preflight._parse_name_version(text) == ("claude-dispatcher", "1.2.3")
    # Nothing parseable at all → (None, None), never an exception.
    assert preflight._parse_name_version("\x00garbage") == (None, None)


def test_staleness_uses_head_not_working_tree(repo: Path, monkeypatch) -> None:
    """The check reads pyproject.toml from HEAD; an uncommitted edit to the
    working-tree file must not change the verdict."""
    _seed_pyproject(repo, name="claude-dispatcher", version="9.9.9")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "claude-dispatcher"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )  # uncommitted: HEAD still says 9.9.9
    monkeypatch.setattr(preflight, "_installed_version", lambda: "0.1.0")
    res = _pf(repo)
    assert any("9.9.9" in w for w in res.warnings)


def test_staleness_warning_run_proceeds_end_to_end(
    repo: Path, monkeypatch, capsys,
) -> None:
    _seed_pyproject(repo, name="claude-dispatcher", version="9.9.9")
    monkeypatch.setattr(preflight, "_installed_version", lambda: "0.1.0")
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(
        repo, "--claude-extra-args=--permission-mode bypassPermissions",
        only="SMOKE-A",
    ))
    assert rc == 0, "a stale-dispatcher warning must not block the run"
    err = capsys.readouterr().err
    assert "warning: preflight:" in err
    assert "9.9.9" in err
    # The warning also landed in run.log.
    log = (repo / "_runs" / "pf-test" / "run.log").read_text(encoding="utf-8")
    assert "preflight warning" in log


# --- tasker role file (unit) ---------------------------------------------------


def test_tracked_regular_role_file_passes_without_probe(
    repo: Path, monkeypatch,
) -> None:
    def boom(*a, **k):
        raise AssertionError("probe worktree must not be created for a tracked file")
    monkeypatch.setattr(preflight, "_probe_worktree_check", boom)
    res = _pf(repo)
    assert res.ok
    assert res.checks["tasker_role_file"]["method"] == "tracked-regular-file"


def test_untracked_unresolvable_role_file_fails_with_symlink_hint(
    bare_repo: Path,
) -> None:
    res = _pf(bare_repo)
    assert not res.ok
    msg = "\n".join(res.failures)
    assert "won't resolve in fresh worktrees" in msg
    assert "git add .claude/workflow" in msg
    assert "6923d0a" in msg
    assert res.checks["tasker_role_file"]["ok"] is False


def test_tracked_symlink_resolvable_passes_via_probe(symlink_repo: Path) -> None:
    res = _pf(symlink_repo)
    assert res.ok, res.failures
    assert res.checks["tasker_role_file"]["method"] == "probe-worktree"


def test_probe_falls_back_to_head_when_base_branch_missing(
    symlink_repo: Path,
) -> None:
    res = _pf(symlink_repo, base_branch="no-such-branch")
    assert res.ok, res.failures
    assert res.checks["tasker_role_file"]["probe_ref"] == "HEAD"


def test_probe_infrastructure_failure_is_warning_not_failure(
    symlink_repo: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        preflight, "_probe_worktree_check",
        lambda *a, **k: (None, "fatal: simulated worktree add failure"),
    )
    res = _pf(symlink_repo)
    assert res.ok
    assert any("simulated worktree add failure" in w for w in res.warnings)
    assert res.checks["tasker_role_file"]["method"] == "probe-failed"


@pytest.mark.parametrize("fixture_name", ["bare_repo", "symlink_repo"])
def test_probe_worktree_cleaned_up(fixture_name: str, request) -> None:
    """After a probe-based check (fail for bare_repo, pass for symlink_repo),
    no probe worktree remains on disk and git has no stale worktree entry."""
    repo = request.getfixturevalue(fixture_name)
    _pf(repo)
    leftovers = [p for p in repo.parent.iterdir() if "preflight-probe" in p.name]
    assert leftovers == [], f"probe worktree leaked: {leftovers}"
    out = _git(repo, "worktree", "list", "--porcelain").stdout
    assert "preflight-probe" not in out


# --- end-to-end: fail-fast contract ------------------------------------------


def test_failed_preflight_exits_2_before_anything_exists(
    repo: Path, monkeypatch, capsys,
) -> None:
    """Missing permission flags: exit 2, no run_dir, no journal, no worktree,
    and stderr carries the exact actionable suggestion."""
    spawned = []
    monkeypatch.setattr(
        spawn_mod, "spawn_claude",
        lambda *a, **k: spawned.append(1) or (_ for _ in ()).throw(AssertionError),
    )
    rc = orchestrator.execute(_args(repo))  # no --claude-extra-args at all
    assert rc == 2

    err = capsys.readouterr().err
    assert "error: preflight:" in err
    assert ("--claude-extra-args '--permission-mode bypassPermissions "
            "--allow-dangerously-skip-permissions'") in err

    assert not (repo / "_runs").exists(), "no run_dir may exist after a failed preflight"
    assert not (repo.parent / "wt").exists(), "no worktree may exist after a failed preflight"
    assert spawned == []


def test_dry_run_unaffected_by_missing_flags(repo: Path, monkeypatch, capsys) -> None:
    """The same flag-less args with --mode dry-run print the plan and exit 0:
    dry-run returns before orchestrator.execute, so preflight never runs."""
    def boom(*a, **k):
        raise AssertionError("preflight must not run for dry-run")
    monkeypatch.setattr(orchestrator.preflight_mod, "run_preflight", boom)

    parser = build_parser()
    args = parser.parse_args([
        "run", str(repo / "tasks.yaml"), "--mode", "dry-run",
        "--runs-dir", str(repo / "_runs"),
    ])
    rc = run_mod.execute(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Dispatcher plan" in out
    assert not (repo / "_runs").exists()


def test_clean_run_journals_preflight_event_at_seq_1(repo: Path, monkeypatch) -> None:
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(
        repo, "--claude-extra-args=--permission-mode bypassPermissions",
        only="SMOKE-A",
    ))
    assert rc == 0

    jpath = repo / "_runs" / "pf-test" / journal_mod.JOURNAL_FILENAME
    assert journal_mod.verify(jpath).ok
    events = _journal_events(repo)
    ev = events[1]
    assert ev.seq == 1
    assert ev.event_type == "preflight"
    assert ev.task_key is None
    assert ev.payload["skipped"] is False
    assert ev.payload["failures"] == []
    assert ev.payload["checks"], "checks payload must be non-empty on a real preflight"
    for name in ("claude_binary", "dispatcher_staleness",
                 "permission_flags", "tasker_role_file"):
        assert name in ev.payload["checks"]


def test_skip_preflight_runs_and_journals_the_skip(repo: Path, monkeypatch) -> None:
    """--skip-preflight with MISSING permission flags still runs (the fake
    spawn doesn't care), and the skip is recorded in the journal + genesis."""
    _patch_spawn(monkeypatch)
    rc = orchestrator.execute(_args(repo, only="SMOKE-A", skip_preflight=True))
    assert rc == 0

    events = _journal_events(repo)
    assert events[0].payload["run_config"]["skip_preflight"] is True
    ev = events[1]
    assert ev.event_type == "preflight"
    assert ev.payload == {"skipped": True, "checks": {}, "warnings": [], "failures": []}


def test_resume_does_not_rerun_preflight(repo: Path, monkeypatch) -> None:
    """resume_run() deliberately skips preflight: a resumed run with args
    that would FAIL preflight still proceeds."""
    _patch_spawn(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("resume_run must not re-run preflight")
    monkeypatch.setattr(orchestrator.preflight_mod, "run_preflight", boom)

    args = _args(repo, only="SMOKE-A")  # flag-less: would fail preflight
    run_dir = repo / "_runs" / "pf-test"
    run_dir.mkdir(parents=True)
    journal = journal_mod.Journal.create(
        run_dir / journal_mod.JOURNAL_FILENAME,
        tasks_yaml_path=repo / "tasks.yaml",
        reviewer_prompts_dir=Path(journal_mod.__file__).parent / "reviewer_prompts",
        run_id="pf-test",
    )
    rc = orchestrator.resume_run(args, journal)
    assert rc == 0
