"""Unit tests for the append-only JSONL run journal."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from claude_dispatcher import journal as journal_mod


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    j = journal_mod.Journal(tmp_path / "journal.jsonl")
    j.append(journal_mod.RUN_STARTED, run_id="R1", config={"a": 1})
    j.append(journal_mod.TASK_DISPATCHED, key="T-1")
    j.append(journal_mod.TASK_FINISHED, key="T-1", status="Done")

    events = j.read()
    assert [e["event"] for e in events] == [
        journal_mod.RUN_STARTED,
        journal_mod.TASK_DISPATCHED,
        journal_mod.TASK_FINISHED,
    ]
    assert events[0]["config"] == {"a": 1}
    assert events[2]["status"] == "Done"
    # Every event is timestamped.
    assert all(e.get("ts") for e in events)


def test_genesis_returns_first_run_started(tmp_path: Path) -> None:
    j = journal_mod.Journal(tmp_path / "journal.jsonl")
    assert j.genesis() is None  # nothing written yet
    j.append(journal_mod.RUN_STARTED, run_id="R1", config={"tasks_yaml": "/x"})
    j.append(journal_mod.RESUME_STARTED, genesis_run_id="R1")
    g = j.genesis()
    assert g is not None
    assert g["run_id"] == "R1"
    assert g["config"]["tasks_yaml"] == "/x"


def test_read_tolerates_torn_final_line(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    j = journal_mod.Journal(path)
    j.append(journal_mod.RUN_STARTED, run_id="R1")
    # Simulate a crash mid-write: append a partial, unparseable line.
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"ts": "2026-01-01T00:00:00+00:00", "event": "heartb')
    events = j.read()
    assert len(events) == 1
    assert events[0]["event"] == journal_mod.RUN_STARTED


def test_seconds_since_last_event(tmp_path: Path) -> None:
    j = journal_mod.Journal(tmp_path / "journal.jsonl")
    assert j.seconds_since_last_event() is None  # empty journal

    old = dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
    j.append(journal_mod.HEARTBEAT, ts=old.isoformat())
    now = old + dt.timedelta(seconds=120)
    age = j.seconds_since_last_event(now=now)
    assert age == 120.0


def test_exists(tmp_path: Path) -> None:
    j = journal_mod.Journal(tmp_path / "journal.jsonl")
    assert not j.exists()
    j.append(journal_mod.RUN_STARTED)
    assert j.exists()
