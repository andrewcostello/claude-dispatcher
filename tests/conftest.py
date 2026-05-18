"""Pytest fixtures shared across the dispatcher test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def three_task_yaml(tmp_path: Path) -> Path:
    """Copy the three-task fixture into a tmp_path so tests can mutate it."""
    src = FIXTURE_DIR / "three_task.yaml"
    dst = tmp_path / "three_task.yaml"
    shutil.copy2(src, dst)
    return dst
