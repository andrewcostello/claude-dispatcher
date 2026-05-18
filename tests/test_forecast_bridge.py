"""Tests for the forecast bridge — smart detection, arg building, create/sync flows."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import pytest

from claude_dispatcher import forecast_bridge, yaml_io


# --- helpers ----------------------------------------------------------------

@dataclass
class FakeProc:
    """subprocess.CompletedProcess stand-in for the injection seam."""
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _make_runner(per_call_outputs):
    """Return a `runner` callable that returns FakeProc objects from a list.

    Each call consumes one entry. If the entry is callable, it's invoked with
    the argv and the result is returned — used for context-sensitive responses.
    """
    iter_ = iter(per_call_outputs)

    def runner(argv, **kwargs):
        out = next(iter_)
        if callable(out):
            return out(argv)
        return out

    return runner


def _write_tasks_yaml(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


# --- detection -------------------------------------------------------------

def test_detect_skips_when_forecast_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    _write_tasks_yaml(tmp_path / "tasks.yaml", "tasks: []\n")
    ctx = forecast_bridge.detect(tmp_path / "tasks.yaml")
    assert ctx.usable is False
    assert "not on PATH" in ctx.skip_reason


def test_detect_skips_when_config_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/fake/forecast")
    _write_tasks_yaml(tmp_path / "tasks.yaml", "tasks: []\n")
    ctx = forecast_bridge.detect(tmp_path / "tasks.yaml")
    assert ctx.usable is False
    assert ".forecast/config.yaml" in ctx.skip_reason


def test_detect_finds_config_walking_up(tmp_path: Path, monkeypatch) -> None:
    """A .forecast/config.yaml two dirs above the YAML is still discovered."""
    monkeypatch.setattr(shutil, "which", lambda name: "/fake/forecast")
    (tmp_path / ".forecast").mkdir()
    (tmp_path / ".forecast" / "config.yaml").write_text("jira: {}\n")
    nested = tmp_path / "deeply" / "nested"
    nested.mkdir(parents=True)
    _write_tasks_yaml(nested / "tasks.yaml", "tasks: []\n")
    ctx = forecast_bridge.detect(nested / "tasks.yaml")
    assert ctx.usable is True
    assert ctx.config_path == (tmp_path / ".forecast" / "config.yaml")


def test_detect_picks_up_yaml_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/fake/forecast")
    (tmp_path / ".forecast").mkdir()
    (tmp_path / ".forecast" / "config.yaml").write_text("jira: {}\n")
    _write_tasks_yaml(tmp_path / "tasks.yaml", dedent("""
        forecast:
          placeholder_prefix: "STUB-"
          status_mapping:
            Done: "Resolved"
            Blocked: {to: "Is Blocked", resolution: "Won't Do"}
        tasks: []
    """).lstrip())
    ctx = forecast_bridge.detect(tmp_path / "tasks.yaml")
    assert ctx.placeholder_prefix == "STUB-"
    assert ctx.status_mapping["Done"] == ("Resolved", None)
    assert ctx.status_mapping["Blocked"] == ("Is Blocked", "Won't Do")


# --- key classification ----------------------------------------------------

@pytest.mark.parametrize("key,prefix,expected", [
    ("", "TBD-", True),
    ("TBD-1", "TBD-", True),
    ("TBD-77", "TBD-", True),
    ("STUB-1", "STUB-", True),
    ("SMG-123", "TBD-", False),
    ("FSG-9", "TBD-", False),
    ("FOO_BAR-99", "TBD-", True),  # underscore not in regex class — treat as placeholder
    ("random-string", "TBD-", True),
])
def test_is_placeholder_key(key, prefix, expected) -> None:
    assert forecast_bridge.is_placeholder_key(key, prefix) is expected


# --- argv building ---------------------------------------------------------

def test_build_create_argv_minimal() -> None:
    argv = forecast_bridge.build_create_argv("forecast", {
        "summary": "Add login button",
        "type": "Task",
    }, default_epic=None)
    assert argv == ["forecast", "jira", "create", "--summary", "Add login button", "--type", "Task"]


def test_build_create_argv_full() -> None:
    argv = forecast_bridge.build_create_argv("forecast", {
        "summary": "Big feature",
        "type": "Story",
        "description": "Multi-line\nbody",
        "labels": ["size:L", "type:component"],
        "priority": "High",
        "epic": "SMG-100",
        "story_points": 8,
        "due_date": "2026-06-30",
        "assignee": "a@b.com",
        "fix_versions": ["v1.4.2"],
        "components": ["Backend", "API"],
    }, default_epic="SMG-OTHER")
    # row-level epic overrides default
    assert "--epic" in argv and argv[argv.index("--epic") + 1] == "SMG-100"
    assert "--summary" in argv and argv[argv.index("--summary") + 1] == "Big feature"
    assert "--type" in argv and argv[argv.index("--type") + 1] == "Story"
    assert "--labels" in argv and argv[argv.index("--labels") + 1] == "size:L,type:component"
    assert "--story-points" in argv and argv[argv.index("--story-points") + 1] == "8"
    assert "--fix-versions" in argv and argv[argv.index("--fix-versions") + 1] == "v1.4.2"
    assert "--components" in argv and argv[argv.index("--components") + 1] == "Backend,API"


def test_build_create_argv_uses_default_epic_when_row_omits_it() -> None:
    argv = forecast_bridge.build_create_argv("forecast", {
        "summary": "x", "type": "Task",
    }, default_epic="SMG-BSA")
    assert argv[argv.index("--epic") + 1] == "SMG-BSA"


# --- parsing ----------------------------------------------------------------

def test_parse_create_output_extracts_key() -> None:
    out = "Created: SMG-5678\nURL: https://smgames.atlassian.net/browse/SMG-5678\n"
    assert forecast_bridge.parse_create_output(out) == "SMG-5678"


def test_parse_create_output_returns_none_on_unexpected() -> None:
    assert forecast_bridge.parse_create_output("nothing useful here\n") is None


# --- create flow -----------------------------------------------------------

@pytest.fixture
def forecast_project(tmp_path: Path, monkeypatch) -> Path:
    """A tmp directory with a .forecast/config.yaml so detect() returns usable=True."""
    monkeypatch.setattr(shutil, "which", lambda name: "/fake/forecast")
    (tmp_path / ".forecast").mkdir()
    (tmp_path / ".forecast" / "config.yaml").write_text("jira: {}\n")
    return tmp_path


def test_create_skips_all_when_forecast_not_detected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    yaml_path = tmp_path / "tasks.yaml"
    _write_tasks_yaml(yaml_path, dedent("""
        tasks:
          - key: TBD-1
            summary: x
            description: y
            type: Task
            labels: [size:S]
    """).lstrip())
    result = forecast_bridge.create_missing_tickets(yaml_path)
    assert result["skipped_all"] is True
    assert "not on PATH" in result["reason"]
    # YAML untouched
    doc = yaml_io.load(yaml_path)
    assert doc["tasks"][0]["key"] == "TBD-1"


def test_create_creates_missing_keys_and_writes_back(forecast_project: Path) -> None:
    yaml_path = forecast_project / "tasks.yaml"
    _write_tasks_yaml(yaml_path, dedent("""
        epic: BSA
        tasks:
          - key: TBD-1
            summary: First task
            description: Do the first thing
            type: Task
            labels: [size:S]
          - key: SMG-9999
            summary: Already exists in Jira
            description: Skip me
            type: Task
            labels: [size:M]
          - key: TBD-2
            summary: Second task
            description: Do the second thing
            type: Task
            labels: [size:M]
    """).lstrip())

    runner = _make_runner([
        FakeProc(0, "Created: SMG-1001\nURL: https://x/browse/SMG-1001\n"),
        FakeProc(0, "Created: SMG-1002\nURL: https://x/browse/SMG-1002\n"),
    ])
    result = forecast_bridge.create_missing_tickets(yaml_path, runner=runner)
    assert result["skipped_all"] is False
    assert result["created"] == [("TBD-1", "SMG-1001"), ("TBD-2", "SMG-1002")]
    assert result["skipped"] == ["SMG-9999"]
    assert result["errors"] == []

    doc = yaml_io.load(yaml_path)
    keys = [t["key"] for t in doc["tasks"]]
    assert keys == ["SMG-1001", "SMG-9999", "SMG-1002"]


def test_create_records_errors_without_corrupting_yaml(forecast_project: Path) -> None:
    yaml_path = forecast_project / "tasks.yaml"
    _write_tasks_yaml(yaml_path, dedent("""
        tasks:
          - key: TBD-1
            summary: This one will fail
            description: x
            type: Task
            labels: [size:S]
    """).lstrip())
    runner = _make_runner([FakeProc(1, "", "API auth failed")])
    result = forecast_bridge.create_missing_tickets(yaml_path, runner=runner)
    assert result["created"] == []
    assert len(result["errors"]) == 1
    assert "API auth failed" in result["errors"][0][1]
    # YAML untouched on error
    doc = yaml_io.load(yaml_path)
    assert doc["tasks"][0]["key"] == "TBD-1"


def test_create_dry_run_doesnt_invoke_runner(forecast_project: Path) -> None:
    yaml_path = forecast_project / "tasks.yaml"
    _write_tasks_yaml(yaml_path, dedent("""
        tasks:
          - key: TBD-1
            summary: x
            description: y
            type: Task
            labels: [size:S]
    """).lstrip())

    def panic_runner(argv, **kwargs):
        raise AssertionError(f"runner should not be called in dry-run; got {argv}")

    result = forecast_bridge.create_missing_tickets(yaml_path, dry_run=True, runner=panic_runner)
    assert result["created"] == [("TBD-1", "(dry-run, not created)")]
    # YAML still untouched
    assert yaml_io.load(yaml_path)["tasks"][0]["key"] == "TBD-1"


# --- sync flow -------------------------------------------------------------

def test_sync_skips_all_when_forecast_not_detected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    yaml_path = tmp_path / "tasks.yaml"
    _write_tasks_yaml(yaml_path, dedent("""
        tasks:
          - key: SMG-1
            summary: x
            description: y
            type: Task
            labels: [size:S]
            status: Done
    """).lstrip())
    result = forecast_bridge.sync_terminal_statuses(yaml_path)
    assert result["skipped_all"] is True


def test_sync_transitions_terminal_statuses(forecast_project: Path) -> None:
    yaml_path = forecast_project / "tasks.yaml"
    _write_tasks_yaml(yaml_path, dedent("""
        tasks:
          - key: SMG-1
            summary: Done one
            description: x
            type: Task
            labels: [size:S]
            status: Done
            pr_url: https://github.com/test/repo/pull/1
            iteration_count: 1
          - key: SMG-2
            summary: Blocked one
            description: x
            type: Task
            labels: [size:S]
            status: Blocked
            blocked_reason: awaiting human PR approval
          - key: SMG-3
            summary: In progress (should skip)
            description: x
            type: Task
            labels: [size:S]
            status: In Progress
          - key: TBD-4
            summary: Not a real Jira key
            description: x
            type: Task
            labels: [size:S]
            status: Done
    """).lstrip())

    captured_calls: list[list[str]] = []

    def runner(argv, **kwargs):
        captured_calls.append(list(argv))
        return FakeProc(0, "OK", "")

    result = forecast_bridge.sync_terminal_statuses(yaml_path, runner=runner)

    assert result["transitioned"] == [("SMG-1", "Done"), ("SMG-2", "Is Blocked")]
    assert len(result["skipped"]) == 2  # In Progress + TBD-4

    # SMG-1 call: --to Done, --resolution Done, comment includes PR URL
    smg1_call = captured_calls[0]
    assert smg1_call[3] == "SMG-1"
    assert "Done" in smg1_call
    assert "--resolution" in smg1_call
    # Comment is the next arg after --comment
    comment_idx = smg1_call.index("--comment")
    assert "https://github.com/test/repo/pull/1" in smg1_call[comment_idx + 1]

    # SMG-2 call: --to "Is Blocked", no --resolution, comment with blocked_reason
    smg2_call = captured_calls[1]
    assert smg2_call[3] == "SMG-2"
    assert "Is Blocked" in smg2_call
    assert "--resolution" not in smg2_call
    comment_idx = smg2_call.index("--comment")
    assert "awaiting human PR approval" in smg2_call[comment_idx + 1]


def test_sync_dry_run(forecast_project: Path) -> None:
    yaml_path = forecast_project / "tasks.yaml"
    _write_tasks_yaml(yaml_path, dedent("""
        tasks:
          - key: SMG-1
            summary: x
            description: y
            type: Task
            labels: [size:S]
            status: Done
    """).lstrip())

    def panic_runner(argv, **kwargs):
        raise AssertionError("runner must not be called in dry-run")

    result = forecast_bridge.sync_terminal_statuses(yaml_path, dry_run=True, runner=panic_runner)
    assert result["transitioned"] == [("SMG-1", "Done (dry-run)")]
