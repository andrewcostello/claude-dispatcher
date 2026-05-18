"""Verify that round-trip YAML I/O preserves comments and ordering.

The bay-session-tasks.yaml in evenplay-mono has 50+ lines of design-pivot
history in its header, plus section dividers (# ====) between groups. Losing
those on write would silently destroy load-bearing documentation.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from claude_dispatcher import yaml_io
from claude_dispatcher.yaml_io import FileLock, LockTimeout


def test_round_trip_preserves_header_comments(tmp_path: Path) -> None:
    src = tmp_path / "in.yaml"
    src.write_text(
        "# load-bearing header comment\n"
        "# second line, equally load-bearing\n"
        "tasks:\n"
        "  - key: A\n"
        "    summary: foo\n"
        "    description: |\n"
        "      multi-line\n"
        "      description\n"
        "    type: Task\n"
        "    labels: [size:S]\n",
        encoding="utf-8",
    )
    doc = yaml_io.load(src)
    yaml_io.dump(doc, src)
    text = src.read_text(encoding="utf-8")
    assert "# load-bearing header comment" in text
    assert "# second line, equally load-bearing" in text


def test_round_trip_preserves_section_dividers(tmp_path: Path) -> None:
    """Verify that # === divider comments inside the tasks list survive."""
    src = tmp_path / "in.yaml"
    src.write_text(
        "tasks:\n"
        "  # ============================================================\n"
        "  # GROUP 0: foundation\n"
        "  # ============================================================\n"
        "  - key: A\n"
        "    summary: foo\n"
        "    description: bar\n"
        "    type: Task\n"
        "    labels: [size:S]\n"
        "\n"
        "  # ============================================================\n"
        "  # GROUP 1: dependent\n"
        "  # ============================================================\n"
        "  - key: B\n"
        "    summary: baz\n"
        "    description: qux\n"
        "    type: Task\n"
        "    labels: [size:M]\n"
        "    blockedBy: [A]\n",
        encoding="utf-8",
    )
    doc = yaml_io.load(src)
    yaml_io.dump(doc, src)
    text = src.read_text(encoding="utf-8")
    assert "# GROUP 0: foundation" in text
    assert "# GROUP 1: dependent" in text
    # And the dividers themselves (regex would be overkill — substring is enough)
    assert text.count("# ====") >= 4


def test_atomic_write_creates_no_partial_file(tmp_path: Path) -> None:
    """The tmp-then-rename pattern means a reader never sees a half-written file."""
    src = tmp_path / "in.yaml"
    src.write_text("tasks:\n  - key: A\n    summary: foo\n    description: bar\n"
                   "    type: Task\n    labels: [size:S]\n", encoding="utf-8")
    doc = yaml_io.load(src)
    yaml_io.dump(doc, src)
    # No .tmp left behind
    assert not (tmp_path / "in.yaml.tmp").exists()


def test_file_lock_releases_on_exit(tmp_path: Path) -> None:
    target = tmp_path / "x.yaml"
    lock_path = target.with_suffix(target.suffix + ".lock")
    with FileLock(target, timeout_seconds=1.0):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_file_lock_excludes_concurrent_holder(tmp_path: Path) -> None:
    target = tmp_path / "x.yaml"
    with FileLock(target, timeout_seconds=1.0):
        with pytest.raises(LockTimeout):
            with FileLock(target, timeout_seconds=0.5):
                pytest.fail("should not have acquired lock while another holder is in scope")
