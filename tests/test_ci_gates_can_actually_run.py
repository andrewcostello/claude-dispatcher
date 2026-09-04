"""Every CI job that runs the gate vendors the TypeScript parser first.

`ts_signature_fingerprint/typescript.js` is gitignored, so it is absent on
every fresh checkout — including each CI runner. Without it, collection of
tests/test_ts_state_machine.py raises ComparatorUnavailable and the whole run
exits 2 before a single test executes.

Measured 2026-09-04: CI had been red on main for FIVE consecutive merges
(#101-#105) on this and one other collection error, and nobody looked, because
a gate that fails identically every time reports nothing. This seal exists so
the next person who adds a job cannot reintroduce it silently.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
VENDOR = "claude_dispatcher.ts_parser_vendor"
#: Commands that collect the pytest suite, and so need the parser present.
GATE_COMMANDS = ("scripts/test.sh", "make verify", "-m pytest")


def _jobs(text: str) -> dict[str, str]:
    """Crude split on top-level job keys — enough to attribute steps to jobs
    without taking a YAML dependency this repo's tests do not otherwise need."""
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            if name:
                out[name] = "\n".join(buf)
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf)
    return out


def test_every_gate_job_vendors_the_parser() -> None:
    checked = 0
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text()
        for job, body in _jobs(text).items():
            if not any(cmd in body for cmd in GATE_COMMANDS):
                continue
            checked += 1
            assert VENDOR in body, (
                f"{wf.name}:{job} runs the gate but never vendors the "
                f"TypeScript parser; collection will fail on a fresh runner")
    assert checked >= 2, (
        f"expected to find at least the two gate jobs, found {checked} — the "
        f"job parser has probably stopped matching this workflow's shape")


def test_the_vendor_step_runs_before_the_gate() -> None:
    """Vendoring after the gate is the same as not vendoring."""
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text()
        for job, body in _jobs(text).items():
            if VENDOR not in body:
                continue
            at = body.index(VENDOR)
            for cmd in GATE_COMMANDS:
                if cmd in body:
                    assert body.index(cmd) > at, (
                        f"{wf.name}:{job} vendors the parser after {cmd!r}")


def test_the_no_anchors_constant_is_not_a_bare_dataclass_default() -> None:
    """Narrow, and honest about being narrow.

    `RunContext.anchors = MappingProxyType({})` made the whole package
    unimportable on Python 3.11 — the version `requires-python` declares and CI
    runs — while 3.12+ accepts it, so it went unnoticed locally.

    I tried to seal the general rule ("no dataclass default whose class is
    unhashable") and it could not fail: `mappingproxy.__hash__` is a slot
    wrapper, not None, so that is not the predicate 3.11 applies. A seal that
    cannot fail is worse than no seal, so this one only asserts the concrete
    regression, and the general case is verified by CI actually running 3.11 —
    which is the point of the vendor fix above making CI legible again.
    """
    src = (Path(__file__).resolve().parents[1] / "src" / "claude_dispatcher"
           / "boundary" / "generated" / "__init__.py").read_text()
    assert "= _NO_ANCHORS\n" not in src, (
        "_NO_ANCHORS is a bare dataclass default again; Python 3.11 refuses it "
        "at class creation and the package becomes unimportable there")
    assert "default_factory=lambda: _NO_ANCHORS" in src
