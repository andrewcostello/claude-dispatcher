"""Pytest fixtures shared across the dispatcher test suite."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures"

# A stand-in for `cmd/classify`: reads the diff off stdin (recording it so tests
# can assert what was actually piped to the binary), then either prints a fixed
# JSON payload or exits non-zero to simulate a classification failure.
_CLASSIFY_STUB = '''\
#!/usr/bin/env python3
import sys
open({stdin_path!r}, "w", encoding="utf-8").write(sys.stdin.read())
if {exit_code}:
    sys.stderr.write("classify: simulated failure\\n")
    sys.exit({exit_code})
sys.stdout.write(open({payload_path!r}, encoding="utf-8").read())
'''


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


@pytest.fixture(autouse=True)
def _no_classify_binary(monkeypatch):
    """Default path classification to "unavailable" for the whole suite.

    ``risk.classify`` shells out to ``cmd/classify`` when the binary is on PATH
    (or at the developer's ~/Project/claude-workflow checkout), and that binary
    is fail-closed: a tmp_path repo whose files match no rule table classifies
    ``high``, which would flip every low-risk fixture to elevated on a developer
    machine and stay low in CI. Pointing CLASSIFY_BIN at a nonexistent file makes
    ``classify_binary()`` return None everywhere, so tests see the rules alone.
    Tests that exercise the integration set CLASSIFY_BIN to their own stub.
    """
    monkeypatch.setenv("CLASSIFY_BIN", str(Path("/nonexistent/classify")))


@pytest.fixture
def classify_stub(tmp_path: Path, monkeypatch):
    """Install a fake ``cmd/classify`` on ``CLASSIFY_BIN`` and return a handle.

    ``install(payload, exit_code=0)`` writes the stub and points the binary
    lookup at it. The returned object exposes ``stdin_path`` so a test can assert
    the real unified diff reached the binary — the whole point of GO-1 is that
    the shell-out works, not just that the parsing does.
    """

    class _Stub:
        stdin_path = tmp_path / "classify_stub.stdin"
        payload_path = tmp_path / "classify_stub.json"
        script = tmp_path / "classify_stub.py"

        #: The policy-bearing fields cmd/classify emits UNCONDITIONALLY. Tests
        #: name only what they care about (usually just "risk"); the stub fills
        #: the rest so it behaves like the real producer. Without this every
        #: test payload is malformed under the strict parser and every verdict
        #: comes back elevated — which is correct behaviour but tells you
        #: nothing about the case under test.
        PRODUCER_DEFAULTS = {
            "financial_paths_touched": False,
            "client_only": False,
            "server_surface": True,
            "migration": False,
            "human_pr_gate": False,
            "panel": {"reduced": False, "seats": 5},
        }

        def install(
            self,
            payload: dict | None = None,
            *,
            exit_code: int = 0,
            raw: bool = False,
        ) -> Path:
            """Install the stub. `raw=True` writes the payload verbatim, for
            tests that deliberately exercise a malformed producer contract."""
            body = payload or {}
            if not raw:
                body = {**self.PRODUCER_DEFAULTS, **body}
            self.payload_path.write_text(json.dumps(body), encoding="utf-8")
            self.script.write_text(
                _CLASSIFY_STUB.format(
                    stdin_path=str(self.stdin_path),
                    payload_path=str(self.payload_path),
                    exit_code=exit_code,
                ),
                encoding="utf-8",
            )
            self.script.chmod(0o755)
            monkeypatch.setenv("CLASSIFY_BIN", str(self.script))
            return self.script

        def stdin(self) -> str:
            return self.stdin_path.read_text(encoding="utf-8")

    return _Stub()


@pytest.fixture
def three_task_yaml(tmp_path: Path) -> Path:
    """Copy the three-task fixture into a tmp_path so tests can mutate it."""
    src = FIXTURE_DIR / "three_task.yaml"
    dst = tmp_path / "three_task.yaml"
    shutil.copy2(src, dst)
    return dst
