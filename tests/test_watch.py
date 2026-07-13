"""Seals for `dispatcher watch` exit codes and journal-tail robustness."""

from __future__ import annotations

import json
from pathlib import Path

from claude_dispatcher.watch import watch_run


def _write_journal(runs_dir: Path, run_id: str, events: list[dict],
                   tail_bytes: bytes = b"") -> Path:
    jdir = runs_dir / run_id
    jdir.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        (json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8")
        for e in events
    ) + tail_bytes
    (jdir / "journal.jsonl").write_bytes(payload)
    return jdir / "journal.jsonl"


def _ev(event_type: str, task_key: str = "T-1", **payload) -> dict:
    return {"event_type": event_type, "task_key": task_key,
            "payload": payload}


def test_missing_journal_exits_2(tmp_path: Path):
    assert watch_run("nope", runs_dir=tmp_path, follow=False) == 2


def test_clean_complete_run_exits_0(tmp_path: Path, capsys):
    _write_journal(tmp_path, "r1", [
        _ev("run_started"),
        _ev("task_started"),
        _ev("task_done"),
        _ev("run_complete"),
    ])
    assert watch_run("r1", runs_dir=tmp_path, follow=False) == 0
    out = capsys.readouterr().out
    assert "task_done" in out and "run_complete" in out


def test_blocked_task_exits_1(tmp_path: Path, capsys):
    _write_journal(tmp_path, "r2", [
        _ev("run_started"),
        _ev("task_blocked", reason="mechanical_verification_failed"),
        _ev("run_complete"),
    ])
    assert watch_run("r2", runs_dir=tmp_path, follow=False) == 1
    assert "mechanical_verification_failed" in capsys.readouterr().out


def test_non_ascii_payload_does_not_break_event_accounting(tmp_path: Path):
    """Multi-byte payloads must not corrupt the byte-offset accounting —
    a dropped task_blocked line flips the exit code operators script on."""
    _write_journal(tmp_path, "r3", [
        _ev("run_started"),
        _ev("task_blocked", reason="épuisé — vérification incomplète ✗"),
        _ev("run_complete"),
    ])
    assert watch_run("r3", runs_dir=tmp_path, follow=False) == 1


def test_torn_tail_line_is_dropped_not_parsed(tmp_path: Path, capsys):
    """A half-written last line (writer mid-flush) is ignored in --no-follow
    mode rather than fed to the JSON parser or miscounted."""
    _write_journal(
        tmp_path, "r4",
        [_ev("run_started"), _ev("task_done")],
        tail_bytes=b'{"event_type": "task_blo',  # torn mid-record
    )
    rc = watch_run("r4", runs_dir=tmp_path, follow=False)
    assert rc == 0  # torn record never counted as a block
    assert "task_blo" not in capsys.readouterr().out
