"""Tests for the `dispatcher report` per-run rollup.

The rollup is journal-sourced when `journal.jsonl` exists (real spend = sum of
cost/tokens across ALL of a task's spawns), and falls back to a clearly
labeled YAML-only rollup for pre-journal runs. Journal fixtures are REAL
hash-chained journals built via journal.Journal.create with an injected
clock, mirroring the test_status.py pattern, so the parser is exercised
against the exact on-disk format the orchestrator writes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import report as report_mod
from claude_dispatcher.cli import build_parser


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "report"

YAML_FALLBACK_LABEL = (
    "yaml (pre-journal run — per-task usage reflects last spawn only)"
)
JOURNAL_UNREADABLE_LABEL = (
    "yaml (journal unreadable — per-task usage reflects last spawn only)"
)

SUMMARY_REP_A = """\
# REP-A: Done task with two spawns

**Status:** Done
**Started:** 2026-06-10T18:00:05+00:00
**Completed:** 2026-06-10T18:20:00+00:00
**Iterations:** 1
**Linter cycles:** 0
**Human gate fired:** no
**Final quality score:** 23/25

## What landed
Stuff.

## Key decisions
None.

## Deferred findings
- minor: rename helper

## Review consensus
| Reviewer | Score | Verdict |
|----------|-------|---------|
| A | 23/25 | APPROVE |

## Files changed
- src/x.py

## PR
https://example.test/pr/7
"""


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


def _setup_run(tmp_path: Path) -> Path:
    """Run dir with REP-A's summary.md (used for YAML discovery + reviews)."""
    run_dir = tmp_path / "runs" / "fixture-run"
    task_dir = run_dir / "REP-A"
    task_dir.mkdir(parents=True)
    (task_dir / "summary.md").write_text(SUMMARY_REP_A)
    return run_dir


def _full_journal(run_dir: Path, tmp_path: Path, *, with_run_complete=True):
    """The reference journal: REP-A re-spawned once (panel iterate) with an
    error-form verdict noise event, REP-B's spawn unmeasured, REP-C mid-flight,
    GHOST not in the YAML at all."""
    timestamps = [
        "2026-06-10T18:00:00+00:00",  # genesis run_started
        "2026-06-10T18:01:00+00:00",  # task_started REP-A
        "2026-06-10T18:10:00+00:00",  # spawn 1 REP-A
        "2026-06-10T18:10:30+00:00",  # summary_parsed REP-A
        "2026-06-10T18:11:00+00:00",  # panel block REP-A
        "2026-06-10T18:15:00+00:00",  # spawn 2 REP-A (iterate)
        "2026-06-10T18:16:00+00:00",  # panel approve REP-A
        "2026-06-10T18:16:30+00:00",  # panel error-form REP-A (must be ignored)
        "2026-06-10T18:20:00+00:00",  # task_done REP-A
        "2026-06-10T18:21:00+00:00",  # task_started REP-B
        "2026-06-10T18:25:00+00:00",  # spawn REP-B (all-null usage)
        "2026-06-10T18:25:30+00:00",  # task_blocked REP-B (pre-agent-meta form)
        "2026-06-10T18:26:00+00:00",  # task_started REP-C
        "2026-06-10T18:27:00+00:00",  # spawn GHOST (task missing from YAML)
        "2026-06-10T18:30:00+00:00",  # run_complete
    ]
    if not with_run_complete:
        timestamps = timestamps[:-1]
    j = _make_journal(run_dir, tmp_path, timestamps)
    j.append(journal_mod.EventType.task_started,
             {"summary": "s", "type": "Task", "labels": [], "model": None},
             task_key="REP-A")
    j.append(journal_mod.EventType.task_spawn_finished, {
        "exit_code": 0, "cost_usd": 0.05,
        "input_tokens": 1000, "output_tokens": 500,
        "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50,
        "duration_ms": 30000, "num_turns": 5, "model": "claude-opus-4-8",
    }, task_key="REP-A")
    j.append(journal_mod.EventType.summary_parsed, {
        "status": "Done", "malformed": False, "problems": [],
        "iterations": 0, "linter_cycles": 0, "final_quality_score": 22,
        "awaiting_human_approval": False,
    }, task_key="REP-A")
    j.append(journal_mod.EventType.panel_verdict, {
        "consensus": "block", "summary": "x", "blocking_findings": 2,
        "verdicts": {"claude": "block"}, "blocking_locations": [],
    }, task_key="REP-A")
    j.append(journal_mod.EventType.task_spawn_finished, {
        "exit_code": 0, "cost_usd": 0.03,
        "input_tokens": 600, "output_tokens": 300,
        "cache_read_input_tokens": 40, "cache_creation_input_tokens": 20,
        "duration_ms": 20000, "num_turns": 4, "model": "claude-opus-4-8",
    }, task_key="REP-A")
    j.append(journal_mod.EventType.panel_verdict, {
        "consensus": "approve", "summary": "ok", "blocking_findings": 0,
        "verdicts": {"claude": "approve"}, "blocking_locations": [],
    }, task_key="REP-A")
    # A later panel run raised — error-form payload carries no consensus and
    # must not erase the approve above.
    j.append(journal_mod.EventType.panel_verdict,
             {"error": "panel crashed"}, task_key="REP-A")
    j.append(journal_mod.EventType.task_done, {
        "pr_url": "https://example.test/pr/7", "iterations": 1,
        "final_quality_score": 23, "panel_consensus": "approve",
        "auto_integrate_status": None, "needs_push": False,
        "agent": "claude", "dispatcher_version": "0.1.0",
        "agent_version": "2.0.0",
    }, task_key="REP-A")
    j.append(journal_mod.EventType.task_started,
             {"summary": "s", "type": "Task", "labels": [], "model": None},
             task_key="REP-B")
    j.append(journal_mod.EventType.task_spawn_finished, {
        "exit_code": 1, "cost_usd": None,
        "input_tokens": None, "output_tokens": None,
        "cache_read_input_tokens": None, "cache_creation_input_tokens": None,
        "duration_ms": None, "num_turns": None, "model": None,
    }, task_key="REP-B")
    # Pre-agent-metadata terminal payload: no agent / needs_push keys.
    j.append(journal_mod.EventType.task_blocked,
             {"reason": "panel block: 2 blocking findings"}, task_key="REP-B")
    j.append(journal_mod.EventType.task_started,
             {"summary": "s", "type": "Task", "labels": [], "model": None},
             task_key="REP-C")
    j.append(journal_mod.EventType.task_spawn_finished, {
        "exit_code": 0, "cost_usd": 0.01,
        "input_tokens": 10, "output_tokens": 5,
        "cache_read_input_tokens": 1, "cache_creation_input_tokens": 2,
        "duration_ms": 1000, "num_turns": 1, "model": "claude-haiku-4-5",
    }, task_key="GHOST-1")
    if with_run_complete:
        j.append(journal_mod.EventType.run_complete, {
            "done": 1, "blocked": 1, "escalated": 0,
            "blocked_rollup": [
                {"key": "REP-B", "reason": "panel block: 2 blocking findings"},
            ],
        })
    return j


def _build(run_dir: Path):
    return report_mod.build_report(
        run_dir=run_dir,
        run_id="fixture-run",
        yaml_path=FIXTURE_DIR / "tasks.yaml",
    )


def _invoke(argv, capsys):
    parser = build_parser()
    args = parser.parse_args(argv)
    rc = args.func(args)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _task_row(data: dict, key: str) -> dict:
    return {t["key"]: t for t in data["rollup"]["tasks"]}[key]


# --- journal-mode rollup ------------------------------------------------------


def test_journal_snapshot(tmp_path: Path) -> None:
    """Full journal-mode document matches the expected JSON fixture."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    data = _build(run_dir)

    expected = json.loads((FIXTURE_DIR / "expected_report.json").read_text())
    # Absolute paths vary by checkout — assert their tails, then drop them.
    assert data["tasks_yaml"].endswith("fixtures/report/tasks.yaml")
    assert data["run_dir"].endswith("runs/fixture-run")
    data.pop("tasks_yaml")
    data.pop("run_dir")
    assert data == expected


def test_multi_spawn_task_sums_cost_and_tokens_model_is_last(tmp_path: Path) -> None:
    """Two spawns (panel iterate) → cost/tokens are SUMS across both spawns —
    legitimately exceeding the YAML row, which records only the last spawn —
    and spawn_count reflects the retry."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    row = _task_row(_build(run_dir), "REP-A")
    assert row["cost_usd"] == pytest.approx(0.08)
    assert row["input_tokens"] == 1600
    assert row["output_tokens"] == 800
    assert row["cache_read_input_tokens"] == 140
    assert row["cache_creation_input_tokens"] == 70
    assert row["spawn_count"] == 2
    assert row["model"] == "claude-opus-4-8"
    assert row["unmeasured_spawns"] == 0


def test_run_totals_sum_all_spawns_and_count_unmeasured(tmp_path: Path) -> None:
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    totals = _build(run_dir)["rollup"]["totals"]
    assert totals["cost_usd"] == pytest.approx(0.09)  # 0.05 + 0.03 + 0.01
    assert totals["input_tokens"] == 1610
    assert totals["output_tokens"] == 805
    assert totals["cache_read_input_tokens"] == 141
    assert totals["cache_creation_input_tokens"] == 72
    assert totals["spawn_count"] == 4
    assert totals["unmeasured_spawns"] == 1  # REP-B's null-usage spawn
    assert totals["tasks_by_status"] == {
        "Done": 1, "Blocked": 1, "In Progress": 2,
    }


def test_null_usage_spawn_excluded_from_sums_and_rendered_unmeasured(
    tmp_path: Path,
) -> None:
    """Null usage fields are never treated as 0: they stay null on the row,
    the spawn is counted unmeasured, and the table renders em-dashes."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    data = _build(run_dir)
    row = _task_row(data, "REP-B")
    assert row["cost_usd"] is None
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None
    assert row["spawn_count"] == 1
    assert row["unmeasured_spawns"] == 1

    rendered = report_mod.render_report(data)
    rep_b_line = next(
        line for line in rendered.splitlines()
        if line.strip().startswith("REP-B") and "Blocked" in line
        and "—" in line
    )
    assert "$" not in rep_b_line  # no fabricated zero-cost


def test_wall_clock_from_run_started_to_run_complete(tmp_path: Path) -> None:
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    wc = _build(run_dir)["rollup"]["wall_clock"]
    assert wc == {
        "started_at": "2026-06-10T18:00:00+00:00",
        "ended_at": "2026-06-10T18:30:00+00:00",
        "seconds": 1800.0,
        "in_flight": False,
    }


def test_in_flight_run_wall_clock_to_last_event_and_labeled(tmp_path: Path) -> None:
    """No run_complete → wall clock measures to the last event, flagged
    in_flight, and the table says so."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path, with_run_complete=False)

    data = _build(run_dir)
    wc = data["rollup"]["wall_clock"]
    assert wc["in_flight"] is True
    assert wc["ended_at"] == "2026-06-10T18:27:00+00:00"  # last event (GHOST spawn)
    assert wc["seconds"] == 1620.0
    assert "in flight" in report_mod.render_report(data)


def test_pre_agent_metadata_terminal_payload_yields_nulls(tmp_path: Path) -> None:
    """REP-B's task_blocked payload predates the agent/needs_push keys —
    the row renders nulls, never a KeyError."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    row = _task_row(_build(run_dir), "REP-B")
    assert row["agent"] is None
    assert row["needs_push"] is None
    # And the OPS-4-era payload on REP-A populates both.
    row_a = _task_row(_build(run_dir), "REP-A")
    assert row_a["agent"] == "claude"
    assert row_a["needs_push"] is False


def test_panel_error_form_ignored_in_favor_of_real_verdict(tmp_path: Path) -> None:
    """The error-form panel_verdict appended after REP-A's approve must not
    erase it: the rollup shows the last REAL consensus."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    assert _task_row(_build(run_dir), "REP-A")["panel_verdict"] == "approve"


def test_journal_task_missing_from_yaml_still_rendered(tmp_path: Path) -> None:
    """GHOST-1 has spawn usage in the journal but no YAML row — it must still
    appear in the rollup (flagged not-in-YAML) and feed the totals."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    data = _build(run_dir)
    row = _task_row(data, "GHOST-1")
    assert row["in_yaml"] is False
    assert row["cost_usd"] == pytest.approx(0.01)
    assert row["model"] == "claude-haiku-4-5"
    assert "GHOST-1" in report_mod.render_report(data)


def test_per_model_aggregate(tmp_path: Path) -> None:
    """Spawns grouped by model; the null-model spawn groups under unknown."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    by_model = {m["model"]: m for m in _build(run_dir)["rollup"]["by_model"]}
    assert set(by_model) == {"claude-opus-4-8", "claude-haiku-4-5", "unknown"}
    opus = by_model["claude-opus-4-8"]
    assert opus["spawns"] == 2
    assert opus["tasks"] == 1
    assert opus["cost_usd"] == pytest.approx(0.08)
    assert opus["input_tokens"] == 1600
    unknown = by_model["unknown"]
    assert unknown["spawns"] == 1
    assert unknown["cost_usd"] is None
    assert unknown["unmeasured_spawns"] == 1


def test_torn_final_journal_line_tolerated(tmp_path: Path) -> None:
    """A flush-mid-write fragment as the journal's final line is skipped; the
    rollup is computed from the intact events (via the shared lenient reader)."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)
    with (run_dir / journal_mod.JOURNAL_FILENAME).open("a", encoding="utf-8") as fh:
        fh.write('\n{"seq":99,"event_type":"task_done","timesta')

    data = _build(run_dir)
    assert data["source"] == "journal"
    assert data["rollup"]["totals"]["spawn_count"] == 4
    assert data["rollup"]["wall_clock"]["ended_at"] == "2026-06-10T18:30:00+00:00"


# --- YAML fallback mode -------------------------------------------------------


def test_yaml_fallback_labeled_in_table_and_json(tmp_path: Path) -> None:
    """No journal.jsonl → YAML-only rollup, clearly labeled in BOTH outputs."""
    run_dir = _setup_run(tmp_path)

    data = _build(run_dir)
    assert data["source"] == "yaml"
    assert data["source_label"] == YAML_FALLBACK_LABEL
    assert YAML_FALLBACK_LABEL in report_mod.render_report(data)


def test_yaml_fallback_rollup_from_rows(tmp_path: Path) -> None:
    """YAML mode: totals/rows come from rows stamped with this run's id;
    journal-only fields are null; other-run rows are excluded."""
    run_dir = _setup_run(tmp_path)

    data = _build(run_dir)
    rollup = data["rollup"]
    assert rollup["wall_clock"] is None
    totals = rollup["totals"]
    assert totals["cost_usd"] == pytest.approx(0.03)  # REP-A only; REP-Z excluded
    assert totals["input_tokens"] == 600
    assert totals["spawn_count"] is None
    assert totals["unmeasured_spawns"] is None
    assert totals["tasks_by_status"] == {
        "Done": 1, "Blocked": 1, "In Progress": 1,
    }

    row_a = _task_row(data, "REP-A")
    assert row_a["cost_usd"] == pytest.approx(0.03)  # last spawn only
    assert row_a["model"] == "claude-opus-4-8"
    assert row_a["agent"] == "claude"
    assert row_a["panel_verdict"] == "approve"
    assert row_a["spawn_count"] is None
    assert row_a["iterations"] == 1

    row_b = _task_row(data, "REP-B")
    assert row_b["cost_usd"] is None
    assert row_b["needs_push"] is None
    assert "REP-Z" not in {t["key"] for t in rollup["tasks"]}

    by_model = {m["model"]: m for m in rollup["by_model"]}
    assert by_model["claude-opus-4-8"]["tasks"] == 1
    assert by_model["claude-opus-4-8"]["spawns"] is None
    assert by_model["unknown"]["tasks"] == 2  # REP-B, REP-C have no model


def test_unreadable_journal_falls_back_with_distinct_note(tmp_path: Path) -> None:
    """journal.jsonl present but yielding no parseable events → YAML mode with
    a journal-unreadable label, never a traceback."""
    run_dir = _setup_run(tmp_path)
    (run_dir / journal_mod.JOURNAL_FILENAME).write_text("garbage\nnot json\n")

    data = _build(run_dir)
    assert data["source"] == "yaml"
    assert data["source_label"] == JOURNAL_UNREADABLE_LABEL
    assert JOURNAL_UNREADABLE_LABEL in report_mod.render_report(data)


# --- existing report content preserved ----------------------------------------


def test_existing_sections_preserved_in_render(tmp_path: Path) -> None:
    """Quality table, concerning tasks, reviewer breakdown, PRs and blocked
    lists keep rendering alongside the new rollup."""
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    out = report_mod.render_report(_build(run_dir))
    assert "Status counts:" in out
    assert "Tasks in this run" in out
    assert "Concerning tasks to spot-check" in out
    assert "Per-reviewer breakdown" in out
    assert "PRs raised" in out
    assert "Blocked for other reasons" in out
    assert "https://example.test/pr/7" in out


def test_quality_data_in_json(tmp_path: Path) -> None:
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    q = _build(run_dir)["quality"]
    by_key = {t["key"]: t for t in q["tasks"]}
    assert by_key["REP-A"]["final_quality_score"] == 23
    assert by_key["REP-A"]["iteration_count"] == 1
    assert any(c["key"] == "REP-A" for c in q["concerning"])
    reviews = {r["key"]: r for r in q["reviews"]}
    assert reviews["REP-A"]["consensus"] == [
        {"reviewer": "A", "score": "23/25", "verdict": "APPROVE"}
    ]
    assert q["prs"] == [{
        "key": "REP-A", "jira_key": None,
        "pr_url": "https://example.test/pr/7",
    }]
    assert q["blocked"] == [{
        "key": "REP-B", "reason": "panel block: 2 blocking findings",
    }]


# --- CLI ------------------------------------------------------------------------


def test_cli_json_roundtrip(tmp_path: Path, capsys) -> None:
    """End-to-end through the CLI: report --json emits ONE parseable JSON
    document (no trailing prose), with the source label embedded."""
    import shutil
    shutil.copy2(FIXTURE_DIR / "tasks.yaml", tmp_path / "tasks.yaml")
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    rc, out, err = _invoke(
        ["report", "fixture-run", "--runs-dir", str(tmp_path / "runs"), "--json"],
        capsys,
    )
    assert rc == 0, err
    doc = json.loads(out)  # would raise on trailing prose
    assert doc["run_id"] == "fixture-run"
    assert doc["source"] == "journal"
    assert doc["source_label"] == "journal"
    assert doc["rollup"]["totals"]["spawn_count"] == 4


def test_cli_json_yaml_fallback_labeled(tmp_path: Path, capsys) -> None:
    import shutil
    shutil.copy2(FIXTURE_DIR / "tasks.yaml", tmp_path / "tasks.yaml")
    _setup_run(tmp_path)

    rc, out, err = _invoke(
        ["report", "fixture-run", "--runs-dir", str(tmp_path / "runs"), "--json"],
        capsys,
    )
    assert rc == 0, err
    doc = json.loads(out)
    assert doc["source"] == "yaml"
    assert doc["source_label"] == YAML_FALLBACK_LABEL


def test_cli_table_output(tmp_path: Path, capsys) -> None:
    import shutil
    shutil.copy2(FIXTURE_DIR / "tasks.yaml", tmp_path / "tasks.yaml")
    run_dir = _setup_run(tmp_path)
    _full_journal(run_dir, tmp_path)

    rc, out, err = _invoke(
        ["report", "fixture-run", "--runs-dir", str(tmp_path / "runs")],
        capsys,
    )
    assert rc == 0, err
    assert "Dispatcher report — fixture-run" in out
    assert "Run rollup" in out
    assert "Per-model usage" in out


def test_cli_missing_run_dir_exit_code_unchanged(tmp_path: Path, capsys) -> None:
    rc, out, err = _invoke(
        ["report", "nope", "--runs-dir", str(tmp_path)],
        capsys,
    )
    assert rc == 2
    assert "error" in err
