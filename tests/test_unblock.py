"""`dispatcher blocked` / `dispatcher unblock` — the review-and-clear loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_dispatcher import yaml_io
from claude_dispatcher.cli import build_parser


def _write_tasks(tmp_path: Path) -> Path:
    p = tmp_path / "tasks.yaml"
    yaml_io.dump({
        "tasks": [
            {
                "key": "A", "summary": "dirty tree task", "description": "do A",
                "type": "Task", "labels": [], "status": "Blocked",
                "blocked_reason": "mechanical_verification_failed",
                "mechanical_verification": "failed",
                "mechanical_verification_detail":
                    "uncommitted changes in worktree at verification time — "
                    "test evidence is not keyed to the committed tree: "
                    "helper.go, debug.log",
            },
            {
                "key": "B", "summary": "false seal task", "description": "do B",
                "type": "Task", "labels": ["type:fix"], "status": "Blocked",
                "blocked_reason": "seal_verification_failed",
                "seal_verification": "failed",
                "seal_verification_detail":
                    "suite stayed GREEN with the fix reverted",
            },
            {
                "key": "C", "summary": "fine task", "description": "do C",
                "type": "Task", "labels": [], "status": "Done",
            },
        ],
    }, p)
    return p


def _run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


def _row(p: Path, key: str) -> dict:
    return next(t for t in yaml_io.load(p)["tasks"] if t["key"] == key)


def test_blocked_lists_reasons_and_details(tmp_path: Path, capsys) -> None:
    p = _write_tasks(tmp_path)
    rc = _run(["blocked", str(p)])
    out = capsys.readouterr().out
    assert rc == 3  # alertable: something is blocked
    assert "A  [mechanical_verification_failed]" in out
    assert "helper.go" in out
    assert "B  [seal_verification_failed]" in out
    assert "GREEN with the fix reverted" in out
    assert "C" not in out.replace("cleared", "")  # Done rows not listed
    assert "2 blocked task(s)" in out


def test_blocked_clean_exits_zero(tmp_path: Path, capsys) -> None:
    p = tmp_path / "tasks.yaml"
    yaml_io.dump({"tasks": [{"key": "A", "summary": "s", "description": "d",
                             "type": "Task", "labels": [],
                             "status": "Done"}]}, p)
    assert _run(["blocked", str(p)]) == 0
    assert "no blocked tasks" in capsys.readouterr().out


def test_unblock_clears_status_stamps_and_notes(tmp_path: Path) -> None:
    p = _write_tasks(tmp_path)
    rc = _run(["unblock", str(p), "A",
               "--note", "commit helper.go, delete debug.log"])
    assert rc == 0
    row = _row(p, "A")
    assert row["status"] == "To Do"
    assert "blocked_reason" not in row
    assert "mechanical_verification" not in row
    assert "mechanical_verification_detail" not in row
    assert "unblocked_at" in row
    assert "## Unblock note (human)" in row["description"]
    assert "commit helper.go" in row["description"]
    assert "mechanical_verification_failed" in row["description"]  # prior reason kept
    # B untouched.
    assert _row(p, "B")["status"] == "Blocked"


def test_unblock_all(tmp_path: Path) -> None:
    p = _write_tasks(tmp_path)
    assert _run(["unblock", str(p), "--all"]) == 0
    assert _row(p, "A")["status"] == "To Do"
    assert _row(p, "B")["status"] == "To Do"
    assert _row(p, "C")["status"] == "Done"


def test_unblock_refuses_non_blocked_and_unknown(tmp_path: Path, capsys) -> None:
    p = _write_tasks(tmp_path)
    rc = _run(["unblock", str(p), "C", "NOPE", "A"])
    err = capsys.readouterr().err
    assert rc == 1                       # some keys failed
    assert "C: status is 'Done'" in err
    assert "NOPE: no such task" in err
    assert _row(p, "A")["status"] == "To Do"   # the valid one still cleared
    assert _row(p, "C")["status"] == "Done"


def test_unblock_requires_keys_or_all(tmp_path: Path, capsys) -> None:
    p = _write_tasks(tmp_path)
    assert _run(["unblock", str(p)]) == 2
    assert "at least one task key" in capsys.readouterr().err
