"""`dispatcher blocked` / `dispatcher unblock` — the review-and-clear loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_dispatcher import unblock, yaml_io
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
    # Paths in the suggested command may contain the key of a Done task.
    project = tmp_path / "ProjectC"
    project.mkdir()
    p = _write_tasks(project)
    rc = _run(["blocked", str(p)])
    out = capsys.readouterr().out
    assert rc == 3  # alertable: something is blocked
    assert "A  [mechanical_verification_failed]" in out
    assert "helper.go" in out
    assert "B  [seal_verification_failed]" in out
    assert "GREEN with the fix reverted" in out
    assert str(p) in out
    listed_keys = [
        line.split("  [", 1)[0] for line in out.splitlines()
        if "  [" in line and not line.startswith(" ")
    ]
    assert listed_keys == ["A", "B"]  # Done rows not listed
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


# ── requeue ─────────────────────────────────────────────────────────────────
# The difference from unblock is the branch: unblock KEEPS it, requeue DESTROYS
# it. That difference is the fix for a failure that recurred three times —
# EPA-1..4 and GO-1 each re-dispatched onto a branch weeks old, dragging in an
# old base, an old .gitignore and dependencies that no longer merged.


def _fake_git(existing=("feat/x",), fail=()):
    calls = []

    def run(cmd):
        calls.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return (0, "abc\n", "") if cmd[-1] in existing else (1, "", "")
        if cmd[:2] == ["git", "tag"]:
            return (1, "", "tag refused") if "tag" in fail else (0, "", "")
        if cmd[:2] == ["git", "branch"]:
            return (1, "", "delete refused") if "delete" in fail else (0, "", "")
        if cmd[:2] == ["git", "worktree"]:
            return (0, "", "")
        return (0, "", "")

    return run, calls


def test_requeue_tags_before_it_deletes():
    """The tag must come first. That branch may be the only record of a
    completed attempt, and deleting it to fix a process problem must never be
    the thing that loses it."""
    run, calls = _fake_git()
    ok, detail = unblock.archive_and_delete_branch(
        "feat/x", "EPA-1", cwd=Path("."), date="2026-08-25", run=run
    )
    assert ok, detail
    verbs = [c[1] for c in calls if c[0] == "git"]
    assert verbs.index("tag") < verbs.index("branch"), "tag must precede delete"
    assert any(c[:2] == ["git", "tag"] and "archive/EPA-1-2026-08-25" in c
               for c in calls)


def test_requeue_aborts_when_the_archive_fails():
    """A branch that cannot be archived must not be deleted."""
    run, calls = _fake_git(fail={"tag"})
    ok, detail = unblock.archive_and_delete_branch(
        "feat/x", "EPA-1", cwd=Path("."), date="2026-08-25", run=run
    )
    assert not ok
    assert "could not tag" in detail
    assert not any(c[:2] == ["git", "branch"] for c in calls), (
        "no delete may be attempted once the archive has failed"
    )


def test_requeue_on_a_missing_branch_is_a_no_op_not_an_error():
    run, _ = _fake_git(existing=())
    ok, detail = unblock.archive_and_delete_branch(
        "feat/gone", "EPA-9", cwd=Path("."), date="2026-08-25", run=run
    )
    assert ok
    assert "nothing to archive" in detail


def test_run_state_fields_cover_what_a_dispatch_writes():
    """The list must include `branch` — clearing every other field and leaving
    that one is precisely the mistake that made three re-dispatches reuse a
    stale branch."""
    for essential in ("branch", "status" if False else "gate_base_sha",
                      "blocked_reason", "dispatcher_run_id"):
        assert essential in unblock.RUN_STATE_FIELDS


def test_requeue_cli_entrypoint_runs(tmp_path: Path) -> None:
    """Every other requeue test calls `archive_and_delete_branch` directly, so
    the command itself was never imported and run — and it shipped with a
    missing `Path` import that made every real invocation crash."""
    tasks = _write_tasks(tmp_path)
    args = build_parser().parse_args(
        ["requeue", str(tasks), "A", "--repo", str(tmp_path)]
    )
    assert args.func(args) == 0

    row = next(t for t in yaml_io.load(tasks)["tasks"] if t["key"] == "A")
    assert row["status"] == "To Do"
    assert "blocked_reason" not in row
