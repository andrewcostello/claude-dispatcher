"""PR-flow run mode (PRF-1): run-level feature branch + config plumbing.

Exercises the integration-mode switch end-to-end with the fake `claude`
binary:

  * pr mode CREATES the feature branch from base when absent, and task
    worktrees fork FROM it (asserted via the worktree branch's merge-base);
  * pr mode REUSES an existing feature branch untouched, and the worktree
    descends from the feature branch's own tip (not main) — the decisive
    "forked from the feature branch, not the base" check;
  * the genesis run_config records integration / feature_branch /
    feature_branch_sha (+ status);
  * branch mode is unchanged: no feature branch created, base stays main;
  * precedence — the --integration CLI flag wins over .dispatcher.yaml.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import orchestrator
from claude_dispatcher import resume as resume_mod
from claude_dispatcher import yaml_io
from claude_dispatcher.cli import build_parser


FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with the three-task fixture (epic: SMOKE) and a tracked
    Tasker role file, so the run-start preflight passes."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=tmp_path, check=True, capture_output=True)
    roles = tmp_path / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("# Tasker stub", encoding="utf-8")
    fixture = Path(__file__).parent / "fixtures" / "three_task.yaml"
    (tmp_path / "tasks.yaml").write_text(
        fixture.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"],
                   cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _build_args(repo: Path, **overrides) -> Any:
    parser = build_parser()
    argv = [
        "run", str(repo / "tasks.yaml"),
        "--mode", "unattended",
        "--max-parallel", "1",
        "--run-id", "pr-flow-run",
        "--runs-dir", str(repo / "_runs"),
        # Unique per test: `tmp_path`'s PARENT (the session basetemp) is shared
        # across tests, so a fixed base would reuse stale sibling worktrees from
        # earlier tests. repo.name is the unique per-test dir name.
        "--worktree-base", str(repo.parent / f"wt-{repo.name}"),
        "--claude-bin", sys.executable,
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in overrides.items():
        if v is None:
            continue
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return parser.parse_args(argv)


def _patched_spawn(monkeypatch) -> None:
    from claude_dispatcher import spawn as spawn_mod

    def fake(claude_bin: str, cwd: Path, env: dict, prompt: str,
             extra_args=None, timeout_seconds: int = 3600):
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


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _is_ancestor(repo: Path, commitish: str, ref: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commitish, ref],
        cwd=repo, capture_output=True,
    ).returncode == 0


def _genesis_run_config(repo: Path) -> dict:
    journal_path = repo / "_runs" / "pr-flow-run" / journal_mod.JOURNAL_FILENAME
    events = list(journal_mod.read_events(journal_path))
    return events[0].payload["run_config"]


def _branch_of(repo: Path, key: str) -> str:
    doc = yaml_io.load(repo / "tasks.yaml")
    return next(t["branch"] for t in doc["tasks"] if t["key"] == key)


# --- pr mode: create + fork-from-feature ------------------------------------

def test_pr_mode_creates_feature_branch_and_records_genesis(
    repo: Path, monkeypatch,
) -> None:
    """pr mode with no pre-existing feature branch creates feature/smoke from
    main, worktrees fork from it, and the genesis records mode + branch + SHA."""
    _patched_spawn(monkeypatch)
    main_sha = _git(repo, "rev-parse", "main")

    rc = orchestrator.execute(_build_args(repo, integration="pr"))
    assert rc == 0

    # Feature branch exists, forked from main (epic SMOKE → feature/smoke).
    assert subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "feature/smoke"],
        cwd=repo, capture_output=True,
    ).returncode == 0
    assert _git(repo, "rev-parse", "feature/smoke") == main_sha

    cfg = _genesis_run_config(repo)
    assert cfg["integration"] == "pr"
    assert cfg["feature_branch"] == "feature/smoke"
    assert cfg["feature_branch_sha"] == main_sha
    assert cfg["feature_branch_status"] == "created"
    # base_branch is repointed to the effective base (the feature branch) so a
    # resume forks from it.
    assert cfg["base_branch"] == "feature/smoke"

    # Each task worktree branch descends from the feature branch tip.
    feat_tip = _git(repo, "rev-parse", "feature/smoke")
    for key in ("SMOKE-A", "SMOKE-B"):
        wt_branch = _branch_of(repo, key)
        assert _is_ancestor(repo, feat_tip, wt_branch), (
            f"{key} worktree {wt_branch} did not fork from feature/smoke")


def test_pr_mode_reuses_existing_feature_branch_worktrees_fork_from_it(
    repo: Path, monkeypatch,
) -> None:
    """A pre-existing, DIVERGED feature branch is reused untouched, and task
    worktrees fork from ITS tip — the decisive 'feature branch, not base' check.

    A feature-only commit (absent from main) must be reachable from each task
    worktree branch; if worktrees had forked from main it would not be.
    """
    _patched_spawn(monkeypatch)
    main_sha = _git(repo, "rev-parse", "main")

    # Build feature/smoke with a commit main does NOT have.
    subprocess.run(["git", "branch", "feature/smoke", "main"],
                   cwd=repo, check=True, capture_output=True)
    fwt = repo.parent / "feature-wt"
    subprocess.run(["git", "worktree", "add", str(fwt), "feature/smoke"],
                   cwd=repo, check=True, capture_output=True)
    (fwt / "feature-only.txt").write_text("feature work\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=fwt, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "feature-only commit"],
                   cwd=fwt, check=True, capture_output=True)
    feat_tip = _git(repo, "rev-parse", "feature/smoke")
    assert feat_tip != main_sha

    rc = orchestrator.execute(_build_args(repo, integration="pr"))
    assert rc == 0

    # Reused, not reset: tip unchanged, status 'existing', genesis sha matches.
    assert _git(repo, "rev-parse", "feature/smoke") == feat_tip
    cfg = _genesis_run_config(repo)
    assert cfg["feature_branch_status"] == "existing"
    assert cfg["feature_branch_sha"] == feat_tip

    # The feature-only commit is in every worktree branch's history → forked
    # from the feature branch. (It is NOT reachable from main.)
    assert not _is_ancestor(repo, feat_tip, "main")
    for key in ("SMOKE-A", "SMOKE-B"):
        wt_branch = _branch_of(repo, key)
        assert _is_ancestor(repo, feat_tip, wt_branch), (
            f"{key} forked from base, not from the diverged feature branch")


def test_pr_mode_custom_feature_branch_name(repo: Path, monkeypatch) -> None:
    """--feature-branch overrides the epic-derived default."""
    _patched_spawn(monkeypatch)
    rc = orchestrator.execute(
        _build_args(repo, integration="pr", feature_branch="feature/custom-x"),
    )
    assert rc == 0
    assert subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "feature/custom-x"],
        cwd=repo, capture_output=True,
    ).returncode == 0
    assert _genesis_run_config(repo)["feature_branch"] == "feature/custom-x"


# --- branch mode: unchanged --------------------------------------------------

def test_branch_mode_default_creates_no_feature_branch(
    repo: Path, monkeypatch,
) -> None:
    """Without --integration, behavior is today's: base stays main, no feature/*."""
    _patched_spawn(monkeypatch)
    rc = orchestrator.execute(_build_args(repo))
    assert rc == 0

    branches = _git(repo, "branch", "--list", "feature/*")
    assert branches == "", "branch mode must not create any feature/* branch"

    cfg = _genesis_run_config(repo)
    assert cfg["integration"] == "branch"
    assert cfg["feature_branch"] is None
    assert cfg["feature_branch_sha"] is None
    assert cfg["base_branch"] == "main"


# --- precedence: CLI > .dispatcher.yaml --------------------------------------

def test_dispatcher_yaml_integration_default_applies(
    repo: Path, monkeypatch,
) -> None:
    """.dispatcher.yaml `integration: pr` activates pr mode with no CLI flag."""
    (repo / ".dispatcher.yaml").write_text("integration: pr\n", encoding="utf-8")
    _patched_spawn(monkeypatch)
    rc = orchestrator.execute(_build_args(repo))
    assert rc == 0
    assert _genesis_run_config(repo)["integration"] == "pr"
    assert subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "feature/smoke"],
        cwd=repo, capture_output=True,
    ).returncode == 0


def test_cli_integration_flag_wins_over_dispatcher_yaml(
    repo: Path, monkeypatch,
) -> None:
    """--integration branch overrides .dispatcher.yaml `integration: pr`."""
    (repo / ".dispatcher.yaml").write_text("integration: pr\n", encoding="utf-8")
    _patched_spawn(monkeypatch)
    rc = orchestrator.execute(_build_args(repo, integration="branch"))
    assert rc == 0
    assert _genesis_run_config(repo)["integration"] == "branch"
    assert _git(repo, "branch", "--list", "feature/*") == ""


# --- config error ------------------------------------------------------------

def test_pr_mode_resume_reconstructs_feature_branch_as_effective_base(
    repo: Path, monkeypatch,
) -> None:
    """A resumed pr-mode run forks from the feature branch with no
    re-resolution: the genesis already carries the feature branch as the
    effective base, so the rebuilt config points base_branch at it.

    Also confirms resume itself doesn't choke on the new genesis keys: a
    completed run resumes as a clean no-op.
    """
    _patched_spawn(monkeypatch)
    assert orchestrator.execute(_build_args(repo, integration="pr")) == 0

    # Rebuild the run config from the genesis exactly as `dispatcher resume`
    # does, and confirm the effective base + mode survived the round-trip.
    cfg_dict = _genesis_run_config(repo)
    resumed_args = resume_mod._namespace_from_config(cfg_dict)
    rebuilt = orchestrator._build_config(resumed_args)
    assert rebuilt.integration == "pr"
    assert rebuilt.feature_branch == "feature/smoke"
    assert rebuilt.base_branch == "feature/smoke"  # forks from the feature branch

    # And resuming the (completed) run is a clean no-op — the new genesis keys
    # don't break reconstruction. --force: the journal is fresh (would
    # otherwise trip the liveness guard).
    parser = build_parser()
    resume_argv = parser.parse_args(
        ["resume", "pr-flow-run", "--runs-dir", str(repo / "_runs"), "--force"])
    assert resume_mod.execute(resume_argv) == 0


def test_malformed_dispatcher_yaml_downgrades_to_branch_with_warning(
    repo: Path, monkeypatch, capsys,
) -> None:
    """A malformed .dispatcher.yaml at run start is not fatal: mode resolution
    falls back to branch and warns to stderr (the per-worktree mechanical gate
    surfaces the malformation itself later)."""
    # `integration:` present but invalid → RepoConfigError on load.
    (repo / ".dispatcher.yaml").write_text("integration: gitflow\n", encoding="utf-8")
    _patched_spawn(monkeypatch)
    rc = orchestrator.execute(_build_args(repo))
    assert rc == 0
    assert _genesis_run_config(repo)["integration"] == "branch"
    assert _git(repo, "branch", "--list", "feature/*") == ""
    assert "could not read .dispatcher.yaml" in capsys.readouterr().err


def test_pr_mode_no_epic_no_flag_errors(repo: Path, monkeypatch) -> None:
    """pr mode with neither a derivable epic nor --feature-branch → exit 2."""
    _patched_spawn(monkeypatch)
    # Strip the top-level `epic:` from the YAML.
    doc = yaml_io.load(repo / "tasks.yaml")
    del doc["epic"]
    yaml_io.dump(doc, repo / "tasks.yaml")

    rc = orchestrator.execute(_build_args(repo, integration="pr"))
    assert rc == 2
    assert _git(repo, "branch", "--list", "feature/*") == ""
