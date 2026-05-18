"""Integration test for the dry-run path.

Builds the parser, runs `dispatcher run --mode dry-run` against the
fabricated three-task fixture, asserts the plan output identifies the
right waves and parallelism.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from claude_dispatcher.cli import build_parser
from claude_dispatcher import run as run_mod


def _invoke(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    parser = build_parser()
    args = parser.parse_args(argv)
    rc = args.func(args)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_dry_run_exits_clean_on_three_task_fixture(
    three_task_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _invoke(
        ["run", str(three_task_yaml), "--mode", "dry-run"],
        capsys,
    )
    assert rc == 0, err
    assert "Dispatcher plan — dry-run mode" in out
    assert "Total tasks in file: 3" in out
    # Wave 1 contains the two no-dependency tasks
    assert "Wave 1" in out
    assert "SMOKE-A" in out
    assert "SMOKE-B" in out
    # Wave 2 contains SMOKE-C
    assert "Wave 2" in out
    assert "SMOKE-C" in out
    # Parallelism estimate
    assert "max parallelism: 2" in out
    # Dry-run footer
    assert "no worktrees created" in out


def test_dry_run_with_filter_restricts_selection(
    three_task_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _invoke(
        ["run", str(three_task_yaml), "--mode", "dry-run", "--filter", "size:XS,area:smoke"],
        capsys,
    )
    assert rc == 0, err
    # All three tasks have these labels, so filter is a no-op
    assert "Selected by filter/only: 3" in out


def test_dry_run_with_only_restricts_to_specific_keys(
    three_task_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, err = _invoke(
        ["run", str(three_task_yaml), "--mode", "dry-run", "--only", "SMOKE-B"],
        capsys,
    )
    assert rc == 0, err
    assert "Selected by filter/only: 1" in out


def test_dry_run_reports_default_financial_paths(
    three_task_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The dispatcher exposes the financial-paths list it would hand to Tasker."""
    rc, out, _ = _invoke(
        ["run", str(three_task_yaml), "--mode", "dry-run"],
        capsys,
    )
    assert rc == 0
    assert "apps/finance-domain/wallet/**" in out
    assert "apps/finance-domain/settlement/**" in out


def test_dry_run_reports_default_iteration_cap(
    three_task_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default max-iterations is 2 per build spec."""
    rc, out, _ = _invoke(
        ["run", str(three_task_yaml), "--mode", "dry-run"],
        capsys,
    )
    assert rc == 0
    assert "Max iterations: 2" in out


def test_dry_run_with_skip_design_surfaces_in_env_handoff(
    three_task_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _invoke(
        ["run", str(three_task_yaml), "--mode", "dry-run", "--skip-design"],
        capsys,
    )
    assert rc == 0
    assert "SKIP_DESIGN=1" in out


def test_dry_run_with_reviewer_count_override_shows_in_plan(
    three_task_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, out, _ = _invoke(
        ["run", str(three_task_yaml), "--mode", "dry-run", "--reviewer-count", "1"],
        capsys,
    )
    assert rc == 0
    assert "REVIEWER_COUNT=1" in out


# test_supervised_mode_not_yet_implemented removed — supervised mode is wired
# as of step 6. The full supervised flow is covered in tests/test_supervised.py.
