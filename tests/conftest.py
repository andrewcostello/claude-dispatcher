"""Pytest fixtures shared across the dispatcher test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _default_verifier_verified():
    """Default the VG-4 LLM verification gate to an instant VERIFIED stub.

    The gate is ON by default in production (it spawns a real `claude`
    verifier over the diff). The vast majority of the suite's live-loop tests
    only care about OTHER lifecycle stages, so without this they'd each spawn a
    real verifier subprocess and stall/fail. This autouse fixture installs a
    no-subprocess VERIFIED stub so those tests behave exactly as they did
    pre-VG-4 (plus the two verification_* journal events the gate now emits).
    Tests that exercise the gate itself call ``orchestrator.set_verifier(...)``
    to override this, and the override is reset here after every test.
    """
    from claude_dispatcher import orchestrator, verifier as v

    def _verified(**_kwargs):
        return v.VerifierResult(
            verdict=v.VerifierVerdict(verdict=v.VerdictKind.VERIFIED),
        )

    orchestrator.set_verifier(_verified)
    yield
    orchestrator.set_verifier(None)


@pytest.fixture
def three_task_yaml(tmp_path: Path) -> Path:
    """Copy the three-task fixture into a tmp_path so tests can mutate it."""
    src = FIXTURE_DIR / "three_task.yaml"
    dst = tmp_path / "three_task.yaml"
    shutil.copy2(src, dst)
    return dst
