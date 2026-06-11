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
PR_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "status_pr"
# Fixed reference clock: 30s after the last parseable run.log event.
NOW = dt.datetime(2026, 6, 10, 18, 25, 40, tzinfo=dt.timezone.utc)
# pr-mode fixture clock: 30s after the last journal event.
PR_NOW = dt.datetime(2026, 6, 10, 18, 26, 10, tzinfo=dt.timezone.utc)


def _make_pr_journal(run_dir: Path, tmp_path: Path):
    """A pr-mode journal for the PRF-5 fixture: genesis run_config records
    integration=pr, then the merge-engine events for PR-A (merged) and PR-B
    (external-approved, conflict → needs_rebase)."""
    reviewer_dir = tmp_path / "reviewer_prompts"
    reviewer_dir.mkdir(exist_ok=True)
    (reviewer_dir / "r.md").write_text("review prompt\n")
    it = iter([
        "2026-06-10T18:24:47+00:00",  # genesis
        "2026-06-10T18:25:25+00:00",  # pr_approved PR-A
        "2026-06-10T18:25:30+00:00",  # pr_merged PR-A
        "2026-06-10T18:25:35+00:00",  # pr_approved PR-B
        "2026-06-10T18:25:40+00:00",  # pr_merge_failed PR-B
    ])
    j = journal_mod.Journal.create(
        run_dir / journal_mod.JOURNAL_FILENAME,
        tasks_yaml_path=PR_FIXTURE_DIR / "tasks.yaml",
        reviewer_prompts_dir=reviewer_dir,
        run_id="fixture-run", run_nonce="0" * 32,
        clock=lambda: next(it),
        run_config={"integration": "pr", "feature_branch": "feature/prflow"},
    )
    j.append(journal_mod.EventType.pr_approved,
             {"number": 201, "approver": "dispatcher-agent",
              "risk_level": "low", "reasons": []}, task_key="PR-A")
    j.append(journal_mod.EventType.pr_merged,
             {"number": 201, "merger": "dispatcher-agent",
              "approver": "dispatcher-agent", "target": "feature/prflow",
              "feature_branch_sha": "abc"}, task_key="PR-A")
    j.append(journal_mod.EventType.pr_approved,
             {"number": 202, "approver": "external:alice",
              "risk_level": "elevated", "reasons": ["touches finance"]},
             task_key="PR-B")
    j.append(journal_mod.EventType.pr_merge_failed,
             {"number": 202, "kind": "conflict", "needs_rebase": True,
              "detail": "merge conflict"}, task_key="PR-B")
    return j


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


# --- pr mode (PRF-5) ---------------------------------------------------------


def test_pr_mode_build_status_matches_snapshot(tmp_path: Path) -> None:
    """A pr-mode run (genesis run_config integration=pr) surfaces the full
    pr-flow: by_status gains Awaiting Review / Merged, each row gets a `pr`
    block (number / risk / approver / needs_rebase), merges_pending is set, and
    run_complete is False while PRs are unmerged. Snapshot-pinned."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    _make_pr_journal(run_dir, tmp_path)

    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=PR_FIXTURE_DIR / "tasks.yaml", now=PR_NOW,
    )
    expected = json.loads((PR_FIXTURE_DIR / "expected_status.json").read_text())
    assert result["tasks_yaml"].endswith("fixtures/status_pr/tasks.yaml")
    result.pop("tasks_yaml")
    assert result == expected


def test_pr_mode_distinguishes_tasks_done_merges_pending(tmp_path: Path) -> None:
    """No To Do/In Progress tasks remain (current_wave None) yet two PRs are
    Awaiting Review → run NOT complete, merges_pending == 2, and the table says
    'tasks done — N PR(s) awaiting merge'."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    _make_pr_journal(run_dir, tmp_path)

    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=PR_FIXTURE_DIR / "tasks.yaml", now=PR_NOW,
    )
    assert result["run_complete"] is False
    assert result["current_wave"] is None
    assert result["merges_pending"] == 2

    table = status_mod.render_table(result)
    assert "tasks done — 2 PR(s) awaiting merge" in table
    # The new lifecycle statuses appear in the counts line.
    assert "Awaiting Review: 2" in table
    assert "Merged: 1" in table
    # Compact pr notes render per row.
    assert "PR#201 low self" in table
    assert "PR#202 elevated ext ⚠rebase" in table


def test_branch_mode_status_has_no_pr_surface(tmp_path: Path) -> None:
    """Acceptance: branch-mode output is unchanged — no `pr` block on rows, no
    merges_pending key, no Awaiting Review/Merged in by_status. Uses a journal
    whose genesis omits integration (defaults to branch)."""
    run_dir = tmp_path / "fixture-run"
    run_dir.mkdir()
    # A journal with NO run_config → integration_mode defaults to branch.
    _make_journal(run_dir, tmp_path, [
        "2026-06-10T18:24:47+00:00",
        "2026-06-10T18:25:30+00:00",
    ]).append(
        journal_mod.EventType.task_started,
        {"summary": "s", "type": "Task", "labels": [], "model": None},
        task_key="SMOKE-A",
    )
    result = status_mod.build_status(
        run_dir=run_dir, run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml", now=NOW,
    )
    assert "merges_pending" not in result
    assert set(result["totals"]["by_status"]) == {
        "To Do", "In Progress", "Done", "Blocked", "Escalated"}
    assert all("pr" not in t for t in result["tasks"])


def test_branch_mode_stray_status_dropped_from_counts_line(tmp_path: Path) -> None:
    """A hand-authored non-standard status in a branch-mode YAML must NOT leak
    into the rendered counts line — the table iterates a fixed status order, so
    strays stay dropped exactly as before PRF-5 (branch output unchanged)."""
    yaml_text = (
        "project: T\nepic: E\ntasks:\n"
        "  - key: X\n    summary: s\n    description: d\n    type: Task\n"
        "    labels: [size:S]\n    status: Done\n"
        "  - key: Y\n    summary: s\n    description: d\n    type: Task\n"
        "    labels: [size:S]\n    status: Frobnicated\n"
    )
    yaml_path = tmp_path / "stray.yaml"
    yaml_path.write_text(yaml_text)
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    result = status_mod.build_status(
        run_dir=run_dir, run_id="r", yaml_path=yaml_path, now=NOW,
    )
    # The stray status is still counted in the JSON by_status (as in main)...
    assert result["totals"]["by_status"]["Frobnicated"] == 1
    # ...but never rendered into the human counts line.
    counts_line = next(
        ln for ln in status_mod.render_table(result).splitlines()
        if ln.startswith("Tasks (")
    )
    assert "Frobnicated" not in counts_line


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
