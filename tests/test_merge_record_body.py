"""DF-1-3 body regressions — the totality legs the DF-1-2 seals could not pin.

Written by the BODIES task under the cross-family panel order that blocked
DF-1-3's first attempt (a bodies-role test edit is a recorded Deviation in
that task's summary; DF-1-4 holds ``tests/**`` in its ``disputed_paths``).
Two legs live here and not in ``tests/test_merge_record.py`` — that file is
DF-1-2's and stays untouched by this task:

  * **Malformed bytes** — the panel's HIGH: ``subprocess.run(text=True)``
    can raise ``UnicodeDecodeError`` while decoding gh's output, an
    exception no enumerated handler covered, escaping a function that
    promises totality AFTER the irreversible merge. The body now captures
    bytes and decodes with ``errors="replace"``; these rows pin that a gh
    emitting invalid UTF-8 (on stdout with exit 0, and on stderr with exit
    1) still RETURNS a named absence.
  * **Timeout** — the seals recorded this leg Predicted (unmeasured) and
    assigned its demonstration to DF-1-3, refusing to buy it with suite
    wall-clock. The bound is the module constant
    ``merge_record.GH_TIMEOUT_SECONDS``; monkeypatching it small against a
    hanging gh measures the leg in well under a second.

No assertion here is a truthiness check over a recorded SHA: absences are
judged as key-absence and states by equality, matching the seal file's own
anti-twin rule.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import merge_record as mr
from claude_dispatcher.merge_record import WitnessState, witness_merged_sha


def _script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.mark.parametrize(
    ("case", "script"),
    [
        pytest.param(
            "stdout-invalid-utf8-exit-0",
            "#!/usr/bin/env python3\nimport sys\n"
            "sys.stdout.buffer.write(b'\\xff\\xfe{not json either')\n",
            id="stdout-invalid-utf8-exit-0",
        ),
        pytest.param(
            "stderr-invalid-utf8-exit-1",
            "#!/usr/bin/env python3\nimport sys\n"
            "sys.stderr.buffer.write(b'HTTP 502 \\xff\\xfe upstream')\n"
            "sys.exit(1)\n",
            id="stderr-invalid-utf8-exit-1",
        ),
    ],
)
def test_gh_output_that_is_not_valid_utf8_is_a_named_absence_not_a_raise(
    tmp_path: Path, case: str, script: str,
) -> None:
    """Panel HIGH regression: malformed subprocess output must degrade to an
    UNAVAILABLE witness, never escape as ``UnicodeDecodeError`` after the
    merge has already landed on origin.

    Control, judged first in the same call: the fake gh's raw output really
    is undecodable as strict UTF-8 — so a pass below is the decode policy's
    doing, not an accidentally-clean byte stream.
    """
    gh = _script(tmp_path / f"gh-{case}.py", script)
    probe = subprocess.run(
        [str(gh), "pr", "view", "7", "--json", "mergeCommit"],
        capture_output=True, timeout=30,
    )
    raw = probe.stdout if case.startswith("stdout") else probe.stderr
    with pytest.raises(UnicodeDecodeError):  # control: really undecodable
        raw.decode("utf-8")

    w = witness_merged_sha(
        cwd=tmp_path, pr_number=7, target="feature/x", gh_bin=str(gh))
    assert w.state is WitnessState.UNAVAILABLE
    assert w.sha is None and w.source is None
    assert w.detail
    assert "merged_sha" not in w.stamp_fields()


def test_a_hanging_gh_is_a_named_absence_within_the_stated_bound(
    tmp_path: Path, monkeypatch,
) -> None:
    """The timeout leg, measured: a gh that outlives the bound returns an
    UNAVAILABLE witness naming the timeout. The bound is monkeypatched small
    so the measurement costs ~0.5s, not the production 60s — the seal
    author's stated reason for leaving this leg to DF-1-3.
    """
    gh = _script(
        tmp_path / "gh-hang.py",
        "#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n",
    )
    monkeypatch.setattr(mr, "GH_TIMEOUT_SECONDS", 0.5)

    w = witness_merged_sha(
        cwd=tmp_path, pr_number=7, target="feature/x", gh_bin=str(gh))
    assert w.state is WitnessState.UNAVAILABLE
    assert w.sha is None and w.source is None
    assert "timed out" in w.detail
    assert w.stamp_fields() == {
        "merged_sha_state": "unavailable",
        "merged_sha_detail": w.detail,
    }
