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

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import status as status_mod
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "status"
# Fixed reference clock: 30s after the last parseable run.log event.
NOW = dt.datetime(2026, 6, 10, 18, 25, 40, tzinfo=dt.timezone.utc)


def _make_journal(run_dir: Path, tmp_path: Path, timestamps: list[str]):
    """Build a real hash-chained journal under run_dir with a deterministic
    clock (one timestamp consumed per appended event, genesis first)."""
    reviewer_dir = tmp_path / "reviewer_prompts"
    reviewer_dir.mkdir(exist_ok=True)
    (reviewer_dir / "r.md").write_text("review prompt\n")
    it = iter(timestamps)
    j = journal_mod.Journal.create(
        run_dir / journal_mod.JOURNAL_FILENAME,
        tasks_yaml_path=FIXTURE_DIR / "tasks.yaml",
        reviewer_prompts_dir=reviewer_dir,
        run_id="fixture-run",
        run_nonce="0" * 32,
        clock=lambda: next(it),
    )
    return j


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
        "source": None,
        "journal_present": False,
        "run_log_present": False,
        "last_event_at": None,
        "last_event_age_seconds": None,
        "last_event": None,
        "last_event_type": None,
        "last_event_seq": None,
    }


def test_pre_journal_run_labels_run_log_fallback(tmp_path: Path) -> None:
    """A run dir with run.log but no journal.jsonl sources liveness from
    run.log and labels it as the fallback (acceptance: pre-journal runs)."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    (run_dir / "run.log").write_bytes((FIXTURE_DIR / "run.log").read_bytes())
    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    live = result["liveness"]
    assert live["source"] == "run.log"
    assert live["journal_present"] is False
    assert live["last_event"] == "dispatch SMOKE-B submitted"
    # Every per-task row carries journal:null when there is no journal.
    assert all(t["journal"] is None for t in result["tasks"])


def test_liveness_prefers_journal_over_run_log(tmp_path: Path) -> None:
    """When both artifacts exist the journal wins, even though run.log here has
    a NEWER last line — the journal is the authoritative liveness source."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    j = _make_journal(run_dir, tmp_path, [
        "2026-06-10T18:24:47+00:00",  # genesis run_started
        "2026-06-10T18:25:30+00:00",  # task_started
    ])
    j.append(journal_mod.EventType.task_started,
             {"summary": "s", "type": "Task", "labels": [], "model": None},
             task_key="SMOKE-A")
    # run.log present but its last event is OLDER than the journal's.
    (run_dir / "run.log").write_text(
        "2026-06-10T18:24:48+00:00  dispatch SMOKE-A submitted\n"
    )

    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    live = result["liveness"]
    assert live["source"] == "journal"
    assert live["journal_present"] is True
    assert live["run_log_present"] is True
    assert live["last_event_at"] == "2026-06-10T18:25:30+00:00"
    assert live["last_event_age_seconds"] == 10.0
    assert live["last_event_type"] == "task_started"
    assert live["last_event_seq"] == 1
    assert live["last_event"] == "task_started (SMOKE-A)"


def test_per_task_journal_enrichment(tmp_path: Path) -> None:
    """Spawn usage and the panel verdict for a task surface in its journal
    block; tasks with no events stay journal:null."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    j = _make_journal(run_dir, tmp_path, [
        "2026-06-10T18:24:47+00:00",  # genesis
        "2026-06-10T18:25:00+00:00",  # spawn finished
        "2026-06-10T18:25:20+00:00",  # panel verdict
    ])
    j.append(journal_mod.EventType.task_spawn_finished, {
        "exit_code": 0, "cost_usd": 0.05,
        "input_tokens": 1200, "output_tokens": 800,
        "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50,
        "duration_ms": 42000, "num_turns": 7, "model": "claude-opus-4-8",
    }, task_key="SMOKE-A")
    j.append(journal_mod.EventType.panel_verdict, {
        "consensus": "approve", "summary": "lgtm", "blocking_findings": 0,
        "verdicts": {"claude": "approve", "codex": "approve"},
        "blocking_locations": [],
    }, task_key="SMOKE-A")

    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    by_key = {t["key"]: t for t in result["tasks"]}
    assert by_key["SMOKE-A"]["journal"] == {
        "spawn": {
            "input_tokens": 1200, "output_tokens": 800,
            "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50,
            "duration_ms": 42000, "num_turns": 7,
        },
        "panel": {
            "consensus": "approve", "blocking_findings": 0,
            "verdicts": {"claude": "approve", "codex": "approve"},
        },
    }
    # A task with no journal events keeps journal:null.
    assert by_key["SMOKE-C"]["journal"] is None


def test_journal_enrichment_uses_last_spawn_and_skips_error_verdict(tmp_path: Path) -> None:
    """A re-spawned task shows its LATEST spawn usage, and a panel exception
    (error-form payload) does not erase the prior real verdict."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    j = _make_journal(run_dir, tmp_path, [
        "2026-06-10T18:24:47+00:00",
        "2026-06-10T18:25:00+00:00",
        "2026-06-10T18:25:05+00:00",
        "2026-06-10T18:25:10+00:00",
        "2026-06-10T18:25:15+00:00",
    ])
    j.append(journal_mod.EventType.task_spawn_finished,
             {"exit_code": 0, "output_tokens": 100}, task_key="SMOKE-A")
    j.append(journal_mod.EventType.panel_verdict,
             {"consensus": "block", "summary": "x", "blocking_findings": 2,
              "verdicts": {"claude": "block"}, "blocking_locations": []},
             task_key="SMOKE-A")
    # Re-spawn after iterate: newer usage must win.
    j.append(journal_mod.EventType.task_spawn_finished,
             {"exit_code": 0, "output_tokens": 250}, task_key="SMOKE-A")
    # A later panel run raised — error-form payload carries no consensus.
    j.append(journal_mod.EventType.panel_verdict,
             {"error": "panel crashed"}, task_key="SMOKE-A")

    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    journal = {t["key"]: t for t in result["tasks"]}["SMOKE-A"]["journal"]
    assert journal["spawn"]["output_tokens"] == 250          # latest spawn
    assert journal["panel"]["consensus"] == "block"          # error verdict skipped
    assert journal["panel"]["blocking_findings"] == 2


def test_journal_torn_final_line_tolerated(tmp_path: Path) -> None:
    """A flush-mid-write fragment as the journal's final line is skipped; the
    last fully-written event still drives liveness (acceptance: mid-run)."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    j = _make_journal(run_dir, tmp_path, [
        "2026-06-10T18:24:47+00:00",
        "2026-06-10T18:25:20+00:00",
    ])
    j.append(journal_mod.EventType.task_started,
             {"summary": "s", "type": "Task", "labels": [], "model": None},
             task_key="SMOKE-A")
    # Append a torn (newline-less, half-written JSON) trailing record.
    with (run_dir / journal_mod.JOURNAL_FILENAME).open("a", encoding="utf-8") as fh:
        fh.write('{"seq":2,"event_type":"task_done","timesta')

    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    live = result["liveness"]
    assert live["source"] == "journal"
    assert live["last_event_type"] == "task_started"
    assert live["last_event_at"] == "2026-06-10T18:25:20+00:00"
    assert live["last_event_age_seconds"] == 20.0


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
