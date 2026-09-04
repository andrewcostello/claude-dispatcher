"""The dry-run preview uses the integration mode the run would use.

The mode decides DISPATCH ORDERING: in pr mode a bodies row whose seals row is
Merged is runnable, in branch mode it is not. `_dry_run` called
`runnable_now(all_tasks)` with no mode, so it always previewed BRANCH ordering.

Measured 2026-09-04 on the 77-row wallet worklist, whose `.dispatcher.yaml`
sets `integration: pr`: the preview said 2 runnable and 48 "waiting on
dependency" while the run would dispatch 10. A preview used to decide whether
to spend money must not be wrong in the direction of "there is nothing to do".
"""

from __future__ import annotations

import argparse
from pathlib import Path

from claude_dispatcher import run as run_mod


def _args(**kw) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.integration = kw.get("integration")
    return ns


def _repo(tmp_path: Path, integration: str | None) -> Path:
    import subprocess
    repo = tmp_path / "repo"
    (repo / "dispatcher").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True,
                   capture_output=True)
    if integration is not None:
        (repo / ".dispatcher.yaml").write_text(f"integration: {integration}\n")
    tasks = repo / "dispatcher" / "tasks.yaml"
    tasks.write_text("tasks: []\n")
    return tasks


def test_the_repo_config_supplies_the_mode(tmp_path) -> None:
    tasks = _repo(tmp_path, "pr")
    assert run_mod._dry_run_integration(_args(), tasks) == "pr"


def test_the_cli_flag_beats_the_repo_config(tmp_path) -> None:
    """Same precedence as orchestrator.execute: flag > repo > branch."""
    tasks = _repo(tmp_path, "pr")
    assert run_mod._dry_run_integration(_args(integration="branch"), tasks) \
        == "branch"


def test_no_config_means_branch(tmp_path) -> None:
    tasks = _repo(tmp_path, None)
    assert run_mod._dry_run_integration(_args(), tasks) == "branch"


def test_a_malformed_config_does_not_break_the_preview(tmp_path) -> None:
    """A preview spends nothing; it must never fail on config."""
    tasks = _repo(tmp_path, None)
    (tasks.parent.parent / ".dispatcher.yaml").write_text("integration: [oops\n")
    assert run_mod._dry_run_integration(_args(), tasks) in ("branch", "pr")


def test_the_config_is_read_from_the_worklist_s_repo_not_the_cwd(
    tmp_path, monkeypatch,
) -> None:
    """A worklist is routinely dispatched from elsewhere. Reading the process
    cwd's config is how a preview silently disagrees with the run."""
    tasks = _repo(tmp_path, "pr")
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / ".dispatcher.yaml").write_text("integration: branch\n")
    monkeypatch.chdir(other)
    assert run_mod._dry_run_integration(_args(), tasks) == "pr"


def test_the_preview_passes_the_mode_to_runnable_now() -> None:
    """WIRING. Resolving the mode and not using it is the #84/#86/#93 shape."""
    import inspect
    import re
    src = inspect.getsource(run_mod._dry_run)
    calls = re.findall(r"runnable_now\(\n(.*?)\n    \)", src, re.DOTALL)
    assert len(calls) == 1, f"expected one runnable_now call, found {len(calls)}"
    assert "integration=" in calls[0], calls[0]
