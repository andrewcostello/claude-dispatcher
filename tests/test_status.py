"""Tests for `dispatcher status` (DISP-10).

Snapshot test: build_status() over a mid-run fixture (Done / In Progress /
To Do / Blocked tasks + a run.log whose final line is truncated) must match
the expected JSON document. The clock is injected so the liveness age is
deterministic.

Plus edge-case coverage: missing run dir, missing/partial run.log, all-done
completeness, and the CLI --json round-trip.
"""

from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import pytest

from claude_dispatcher import status as status_mod
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "status"
# Fixed reference clock: 30s after the last parseable run.log event.
NOW = dt.datetime(2026, 6, 10, 18, 25, 40, tzinfo=dt.timezone.utc)


def _invoke(argv, capsys):
    parser = build_parser()
    args = parser.parse_args(argv)
    rc = args.func(args)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_build_status_matches_snapshot(tmp_path: Path) -> None:
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    (run_dir / "run.log").write_bytes((FIXTURE_DIR / "run.log").read_bytes())

    result = status_mod.build_status(
        run_dir=run_dir,
        run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml",
        now=NOW,
    )

    expected = json.loads((FIXTURE_DIR / "expected_status.json").read_text())
    # tasks_yaml is an absolute path that varies by checkout — assert it
    # points at the fixture, then drop it before the structural compare.
    assert result["tasks_yaml"].endswith("fixtures/status/tasks.yaml")
    result.pop("tasks_yaml")
    assert result == expected


def test_partial_last_line_is_tolerated(tmp_path: Path) -> None:
    """The fixture run.log ends with a truncated line (no separator); the
    last *parseable* line must win for liveness, not the garbage tail."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    (run_dir / "run.log").write_bytes((FIXTURE_DIR / "run.log").read_bytes())

    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    live = result["liveness"]
    assert live["last_event_at"] == "2026-06-10T18:25:10+00:00"
    assert live["last_event"] == "dispatch SMOKE-B submitted"
    assert live["last_event_age_seconds"] == 30.0


def test_parseable_but_truncated_final_line_is_accepted(tmp_path: Path) -> None:
    """If the final line has a valid timestamp + separator but a half-written
    message (the realistic mid-run flush-mid-write case), it is still the most
    recent event — we accept it rather than discarding it. Locks in intended
    behavior so a future parser change can't silently regress it."""
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "run.log").write_text(
        "2026-06-10T18:24:48+00:00  dispatch SMOKE-A submitted\n"
        "2026-06-10T18:25:30+00:00  dispa"  # parseable ts, truncated message
    )
    result = status_mod.build_status(
        run_dir=run_dir, run_id="r",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    live = result["liveness"]
    assert live["last_event_at"] == "2026-06-10T18:25:30+00:00"
    assert live["last_event"] == "dispa"
    assert live["last_event_age_seconds"] == 10.0


def test_missing_run_log_gives_null_liveness(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()
    result = status_mod.build_status(
        run_dir=run_dir, run_id="empty-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    assert result["liveness"] == {
        "run_log_present": False,
        "last_event_at": None,
        "last_event_age_seconds": None,
        "last_event": None,
    }


def test_run_complete_when_all_terminal(tmp_path: Path) -> None:
    """A YAML where every task is Done/Blocked → run_complete, no current wave."""
    yaml_text = (
        "project: T\nepic: E\ntasks:\n"
        "  - key: X\n    summary: s\n    description: d\n    type: Task\n"
        "    labels: [size:S]\n    status: Done\n"
        "  - key: Y\n    summary: s\n    description: d\n    type: Task\n"
        "    labels: [size:S]\n    status: Blocked\n    blocked_reason: nope\n"
    )
    yaml_path = tmp_path / "done.yaml"
    yaml_path.write_text(yaml_text)
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    result = status_mod.build_status(
        run_dir=run_dir, run_id="r", yaml_path=yaml_path, now=NOW,
    )
    assert result["run_complete"] is True
    assert result["current_wave"] is None
    assert result["totals"]["run_cost_usd"] is None
    assert result["totals"]["tasks_billed"] == 0


def test_cli_json_roundtrip(tmp_path: Path, capsys) -> None:
    """End-to-end through the CLI: --json emits parseable JSON; --tasks-yaml
    bypasses summary-based discovery (no summaries exist here)."""
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "fixture-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run.log").write_bytes((FIXTURE_DIR / "run.log").read_bytes())

    rc, out, err = _invoke(
        ["status", "fixture-run", "--runs-dir", str(runs_dir),
         "--tasks-yaml", str(FIXTURE_DIR / "tasks.yaml"), "--json"],
        capsys,
    )
    assert rc == 0, err
    doc = json.loads(out)
    assert doc["run_id"] == "fixture-run"
    assert doc["totals"]["task_count"] == 4
    assert {t["key"] for t in doc["tasks"]} == {
        "SMOKE-A", "SMOKE-B", "SMOKE-C", "SMOKE-D"
    }


def test_cli_table_output(tmp_path: Path, capsys) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "fixture-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run.log").write_bytes((FIXTURE_DIR / "run.log").read_bytes())

    rc, out, err = _invoke(
        ["status", "fixture-run", "--runs-dir", str(runs_dir),
         "--tasks-yaml", str(FIXTURE_DIR / "tasks.yaml")],
        capsys,
    )
    assert rc == 0, err
    assert "Dispatcher status — fixture-run" in out
    assert "SMOKE-A" in out
    assert "Current wave: 1 / 2" in out


def test_cli_missing_run_dir_errors(tmp_path: Path, capsys) -> None:
    rc, out, err = _invoke(
        ["status", "nope", "--runs-dir", str(tmp_path)],
        capsys,
    )
    assert rc == 2
    assert "run directory not found" in err


def test_cli_no_yaml_discoverable_errors(tmp_path: Path, capsys) -> None:
    """Fresh run, no summaries, no --tasks-yaml → clear error, exit 2."""
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "fresh"
    run_dir.mkdir(parents=True)
    rc, out, err = _invoke(
        ["status", "fresh", "--runs-dir", str(runs_dir)],
        capsys,
    )
    assert rc == 2
    assert "Pass --tasks-yaml" in err
