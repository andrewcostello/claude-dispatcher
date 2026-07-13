"""Unit tests for the independent verifier module.

No real CLI is invoked — `subprocess.run` is monkeypatched on the module
under test so the tests are hermetic, mirroring test_cross_family_reviewer.
"""

from __future__ import annotations

import json
import subprocess
import textwrap

import pytest

from claude_dispatcher import verifier as vf


TASK = {
    "key": "VG-99",
    "summary": "Build the frobnicator",
    "type": "Task",
    "labels": ["risk:medium", "verifier"],
    "description": "Acceptance:\n- frobnicate the spline\n- add tests",
}

DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n-old\n+new frob logic\n"

SUMMARY = "## Status\nDone — frobnicator implemented and tested."


# --- prompt building ---------------------------------------------------------


def test_build_verifier_prompt_includes_all_inputs():
    p = vf.build_verifier_prompt(TASK, DIFF, SUMMARY)
    assert "VG-99" in p
    assert "Build the frobnicator" in p
    assert "Task" in p
    assert "risk:medium, verifier" in p
    assert "frobnicate the spline" in p
    assert "## Status\nDone — frobnicator implemented and tested." in p
    assert "+new frob logic" in p
    # Comes from the packaged verifier.md template.
    assert "independent verifier" in p
    assert "Verdict: VERIFIED" in p


def test_build_verifier_prompt_missing_fields_fall_back():
    p = vf.build_verifier_prompt({}, "d", "s")
    assert "unknown" in p  # key and type degrade to "unknown"


def test_build_verifier_prompt_truncates_oversized_diff():
    big_diff = "\n".join(f"+line {i}" for i in range(100))
    p = vf.build_verifier_prompt(TASK, big_diff, SUMMARY, max_diff_lines=10)
    assert "... [diff truncated at 10 lines of 100 total] ..." in p
    assert "+line 9" in p
    assert "+line 99" not in p


def test_build_verifier_prompt_small_diff_not_truncated():
    small_diff = "\n".join(f"+line {i}" for i in range(5))
    p = vf.build_verifier_prompt(TASK, small_diff, SUMMARY, max_diff_lines=10)
    assert "diff truncated" not in p
    assert "+line 4" in p


# --- parse_verdict: VERIFIED paths -------------------------------------------


def test_parse_clean_fenced_verified():
    raw = textwrap.dedent("""\
        ```
        Verdict: VERIFIED
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.VERIFIED
    assert v.reason is None
    assert v.gaps == []


def test_parse_verified_with_surrounding_prose():
    raw = textwrap.dedent("""\
        I walked the acceptance list against the diff. All three deliverables
        are present, the tests exist, and nothing is stubbed or deferred.

        ```
        Verdict: VERIFIED
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.VERIFIED
    assert v.reason is None
    assert v.gaps == []


# --- parse_verdict: INCOMPLETE with gaps --------------------------------------


def test_parse_incomplete_with_gaps_header_and_locations():
    raw = textwrap.dedent("""\
        The summary claims tests were added, but the diff contains none.

        ```
        Verdict: INCOMPLETE
        Gaps:
        1. src/pkg/frob.py:42 — frobnicate() raises NotImplementedError
        2. tests/test_frob.py:? — summary claims tests; none in the diff
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 2
    assert v.gaps[0].index == 1
    assert v.gaps[0].location == "src/pkg/frob.py:42"
    assert v.gaps[0].description == "frobnicate() raises NotImplementedError"
    assert v.gaps[1].index == 2
    assert v.gaps[1].location == "tests/test_frob.py:?"
    assert "none in the diff" in v.gaps[1].description


def test_parse_incomplete_gap_without_location():
    raw = textwrap.dedent("""\
        ```
        Verdict: INCOMPLETE
        Gaps:
        1. a.py:3 — stubbed handler
        2. The summary claims coverage that the diff cannot demonstrate
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 2
    assert v.gaps[1].location is None
    assert (
        v.gaps[1].description
        == "The summary claims coverage that the diff cannot demonstrate"
    )


def test_parse_instruction_echo_never_matches():
    # The prompt's own contract line uses `|` between the two tokens — the
    # EOL-anchored regex must not read it as a verdict.
    raw = textwrap.dedent("""\
        The contract requires me to end with `Verdict: VERIFIED | INCOMPLETE`
        as a fenced block. My analysis found a stub, so:

        ```
        Verdict: INCOMPLETE
        Gaps:
        1. x.py:1 — stub where real logic was required
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    # The echo must not register as a VERIFIED line → not CONFLICTING.
    assert v.reason is None
    assert len(v.gaps) == 1


def test_parse_instruction_echo_alone_is_malformed():
    # Only the echo, no real verdict line — nothing must match.
    v = vf.parse_verdict("Verdict: VERIFIED | INCOMPLETE")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_MALFORMED


# --- parse_verdict: malformed / truncated / conflicting -----------------------


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   \n\t  \n",
        "lorem ipsum dolor sit amet, no verdict anywhere",
    ],
    ids=["empty", "whitespace", "garbage"],
)
def test_parse_malformed_output(raw):
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_MALFORMED
    assert v.gaps == []


def test_parse_truncated_mid_token_is_malformed():
    raw = "Analysis complete, my verdict follows:\n```\nVerdict: VERIF"
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_MALFORMED


def test_parse_truncated_gap_list_keeps_parsed_gaps():
    # Stream cut off mid-second-item: item 2 has its number but no text.
    raw = "```\nVerdict: INCOMPLETE\nGaps:\n1. a.py:7 — first gap parsed fully\n2."
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].location == "a.py:7"
    assert v.gaps[0].description == "first gap parsed fully"


def test_parse_multiple_fenced_blocks_last_one_wins():
    # Contract: the verdict lives in the LAST fenced block that contains
    # one. A model that changes its mind and re-emits the fence gets its
    # final answer honored cleanly — not flagged as conflicting.
    raw = textwrap.dedent("""\
        ```
        Verdict: VERIFIED
        ```

        Wait — on reflection, the tests are missing:

        ```
        Verdict: INCOMPLETE
        Gaps:
        1. tests/test_frob.py:? — claimed tests absent from diff
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].location == "tests/test_frob.py:?"


def test_parse_incomplete_fence_then_verified_fence_stays_incomplete():
    # The conservative asymmetry: INCOMPLETE evidence anywhere can only
    # make the verdict MORE conservative. A later VERIFIED fence never
    # overrides earlier INCOMPLETE evidence — that is a conflict.
    raw = textwrap.dedent("""\
        ```
        Verdict: INCOMPLETE
        Gaps:
        1. a.py:1 — stub where real logic was required
        ```

        Actually, never mind:

        ```
        Verdict: VERIFIED
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_CONFLICTING
    # Gaps from the INCOMPLETE evidence are still surfaced for the human.
    assert len(v.gaps) == 1
    assert v.gaps[0].location == "a.py:1"


def test_parse_conflicting_lines_within_one_fence():
    raw = textwrap.dedent("""\
        ```
        Verdict: VERIFIED
        Verdict: INCOMPLETE
        Gaps:
        1. a.py:1 — stub where real logic was required
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_CONFLICTING
    assert len(v.gaps) == 1


def test_parse_incomplete_without_parseable_gaps():
    raw = textwrap.dedent("""\
        ```
        Verdict: INCOMPLETE
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_GAPS_UNPARSED
    assert v.gaps == []


def test_parse_tolerates_ansi_escapes():
    raw = "\x1b[32m```\x1b[0m\n\x1b[1mVerdict: VERIFIED\x1b[0m\n```\n"
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.VERIFIED
    assert v.reason is None


def test_parse_tolerates_bold_and_bullet_verdict_line():
    v = vf.parse_verdict("- **Verdict: INCOMPLETE**\nGaps:\n1. x.py:1 — gap")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1


# --- parse_verdict: false-VERIFY regressions (asymmetric detection + fenced
# --- block scoping) ------------------------------------------------------------


def test_parse_checklist_verified_echoes_with_suffixed_incomplete():
    # Reviewer repro 1: a per-item checklist emits `- Verdict: VERIFIED`
    # bullets for passing items, then the REAL verdict arrives with a
    # natural-language suffix. The old strict-only parser saw only the
    # VERIFIED bullets and auto-verified. Must be INCOMPLETE — and since
    # bulleted VERIFIED lines are no longer strict verdicts at all, the
    # checklist echoes register no conflict: this is a CLEAN incomplete.
    raw = textwrap.dedent("""\
        Acceptance walk, item by item:
        - frobnicate the spline: present in the diff.
        - Verdict: VERIFIED
        - add tests: summary claims tests, the diff contains none.
        - Verdict: VERIFIED

        Verdict: INCOMPLETE — claimed tests absent from the diff
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    # The verdict-line suffix is surfaced as a single location-less gap.
    assert len(v.gaps) == 1
    assert v.gaps[0].location is None
    assert v.gaps[0].description == "claimed tests absent from the diff"


def test_parse_contract_echo_verified_with_prose_incomplete():
    # Reviewer repro 2: a standalone contract-echo `Verdict: VERIFIED`
    # line in prose, with the INCOMPLETE intent expressed only in
    # suffixed form. Must be INCOMPLETE, never VERIFIED.
    raw = textwrap.dedent("""\
        On success the contract would have me answer:
        Verdict: VERIFIED
        However the diff does not contain the claimed tests, so my answer is
        Verdict: INCOMPLETE — claimed tests absent from the diff
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_CONFLICTING
    assert len(v.gaps) == 1
    assert v.gaps[0].description == "claimed tests absent from the diff"


def test_parse_prose_verdict_loses_to_fenced_block():
    # Fenced-block scoping: prose mentions VERIFIED on its own line, but
    # the fenced block disagrees — the fenced block wins, cleanly.
    raw = textwrap.dedent("""\
        If every item were present my answer would be
        Verdict: VERIFIED
        but the tests are missing, so:

        ```
        Verdict: INCOMPLETE
        Gaps:
        1. tests/test_frob.py:? — claimed tests absent from diff
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].location == "tests/test_frob.py:?"


def test_parse_suffixed_incomplete_alone_yields_suffix_gap():
    # `Verdict: INCOMPLETE — reason` with no numbered gaps: the suffix
    # becomes the single gap and REASON_GAPS_UNPARSED does NOT apply.
    v = vf.parse_verdict("Verdict: INCOMPLETE — claimed tests absent from the diff")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].index == 1
    assert v.gaps[0].location is None
    assert v.gaps[0].description == "claimed tests absent from the diff"


def test_parse_suffixed_incomplete_with_numbered_gaps_prefers_numbered():
    raw = "```\nVerdict: INCOMPLETE — see gaps\nGaps:\n1. a.py:1 — stub\n```\n"
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].location == "a.py:1"
    assert v.gaps[0].description == "stub"


def test_parse_bold_suffixed_incomplete_strips_formatting_from_suffix():
    v = vf.parse_verdict("**Verdict: INCOMPLETE** — claimed tests absent")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].description == "claimed tests absent"


def test_parse_suffixed_verified_never_verifies():
    # The asymmetry only runs in the conservative direction: a suffixed
    # VERIFIED is NOT a strict verdict line and must not verify.
    v = vf.parse_verdict("```\nVerdict: VERIFIED — everything matches\n```")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_MALFORMED


def test_parse_pipe_echo_incomplete_first_matches_neither():
    # Pipe-adjacent echo in the other order must also match neither.
    v = vf.parse_verdict("Verdict: INCOMPLETE | VERIFIED")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_MALFORMED


def test_parse_fenced_block_without_verdict_falls_back_to_prose():
    # Tolerance preserved: a fenced block that merely quotes code does not
    # capture the scope; the prose verdict is still honored.
    raw = textwrap.dedent("""\
        The diff adds this function:

        ```
        def frob():
            return spline
        ```

        Verdict: VERIFIED
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.VERIFIED
    assert v.reason is None


# --- parse_verdict: round-2 false-VERIFY regressions (prefix/case tolerance) ---

# Per-item checklist echoes that precede every probe below. Bulleted
# `- Verdict: VERIFIED` lines are instruction echoes, never real verdicts —
# they must neither verify nor register a conflict against the probe.
_CHECKLIST_ECHOES = textwrap.dedent("""\
    Acceptance walk, item by item:
    - frobnicate the spline: present in the diff.
    - Verdict: VERIFIED
    - add tests: summary claims tests, the diff contains none.
    - Verdict: VERIFIED

""")


def test_parse_probe_qualifier_word_before_verdict():
    # Probe 1: qualifier word before "Verdict".
    v = vf.parse_verdict(
        _CHECKLIST_ECHOES + "Final Verdict: INCOMPLETE — claimed tests absent"
    )
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    # Bulleted VERIFIED echoes are not strict verdicts → clean INCOMPLETE.
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].location is None
    assert v.gaps[0].description == "claimed tests absent"


def test_parse_probe_heading_prefix_with_numbered_gaps():
    # Probe 2: markdown heading marker prefix + contract-shaped gap list.
    raw = _CHECKLIST_ECHOES + textwrap.dedent("""\
        ## Verdict: INCOMPLETE
        Gaps:
        1. tests/test_frob.py:? — claimed tests absent from diff
        2. The summary claims coverage the diff cannot demonstrate
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 2
    assert v.gaps[0].location == "tests/test_frob.py:?"
    assert v.gaps[1].location is None


def test_parse_probe_pipe_separator_with_real_reason():
    # Probe 3: pipe used as a separator before a NON-verdict-token reason.
    # Only the two-token instruction echo is excluded; this must match.
    v = vf.parse_verdict(_CHECKLIST_ECHOES + "Verdict: INCOMPLETE | tests missing")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].location is None
    assert v.gaps[0].description == "tests missing"


def test_parse_probe_lowercase_verdict():
    # Probe 4: all-lowercase verdict line.
    v = vf.parse_verdict(
        _CHECKLIST_ECHOES + "verdict: incomplete — claimed tests absent from the diff"
    )
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].description == "claimed tests absent from the diff"


def test_parse_probe_numbered_list_prefix():
    # Probe 5: numbered-list prefix before the verdict.
    v = vf.parse_verdict(
        _CHECKLIST_ECHOES + "1. Verdict: INCOMPLETE — claimed tests absent"
    )
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].description == "claimed tests absent"


def test_parse_probe_space_before_colon():
    # Probe 6: whitespace before the colon, bare verdict (no suffix, no
    # numbered gaps) → INCOMPLETE with gaps unparsed, never VERIFIED.
    v = vf.parse_verdict(_CHECKLIST_ECHOES + "Verdict : INCOMPLETE")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_GAPS_UNPARSED
    assert v.gaps == []


@pytest.mark.parametrize(
    "raw",
    [
        "Verdict: VERIFIED | INCOMPLETE",
        "Verdict: INCOMPLETE | VERIFIED",
        "- Verdict: VERIFIED | INCOMPLETE",
        "- Verdict: INCOMPLETE | VERIFIED",
        "- Emit exactly ONE verdict line. Never emit both verdicts.",
        "the allowed verdicts are VERIFIED | INCOMPLETE",
    ],
    ids=[
        "echo-verified-first",
        "echo-incomplete-first",
        "bulleted-echo-verified-first",
        "bulleted-echo-incomplete-first",
        "contract-rule-prose",
        "allowed-verdicts-prose",
    ],
)
def test_parse_contract_echoes_alone_are_malformed(raw):
    # The widened INCOMPLETE tolerance must NOT pick up the prompt's own
    # instruction echo (either token order, bulleted or not) or contract
    # prose — alone, these carry no verdict at all.
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_MALFORMED
    assert v.gaps == []


def test_parse_bulleted_verified_alone_is_malformed():
    # Strict VERIFIED no longer tolerates a bullet prefix: a checklist echo
    # with no real verdict anywhere is malformed output, not VERIFIED.
    v = vf.parse_verdict("- Verdict: VERIFIED")
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason == vf.REASON_MALFORMED


def test_parse_lowercase_heading_incomplete_in_fence_selects_scope():
    # The widened evidence regex must still drive fence scoping: a fenced
    # lowercase/heading INCOMPLETE selects that fence as the scope, so the
    # strict VERIFIED line in the prose outside registers no conflict.
    raw = textwrap.dedent("""\
        If every item were present my answer would be
        Verdict: VERIFIED
        but it is not:

        ```
        ## verdict: incomplete
        Gaps:
        1. tests/test_frob.py:? — claimed tests absent from diff
        ```
    """)
    v = vf.parse_verdict(raw)
    assert v.verdict == vf.VerdictKind.INCOMPLETE
    assert v.reason is None
    assert len(v.gaps) == 1
    assert v.gaps[0].location == "tests/test_frob.py:?"


# --- run_verifier: CLI adapter -------------------------------------------------


_VERIFIED_MESSAGE = "All acceptance items present.\n\n```\nVerdict: VERIFIED\n```\n"


def _claude_envelope(message: str) -> str:
    """A realistic `claude --print --output-format json` envelope."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "result": message,
            "total_cost_usd": 0.42,
            "duration_ms": 61234,
            "duration_api_ms": 59000,
            "num_turns": 3,
            "session_id": "sess-1",
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 80,
                "cache_read_input_tokens": 500,
                "cache_creation_input_tokens": 100,
            },
            "modelUsage": {"claude-opus-4-6": {"inputTokens": 1200}},
        }
    )


def test_run_verifier_invokes_cli_and_parses_envelope(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["input"] = kwargs.get("input")
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=_claude_envelope(_VERIFIED_MESSAGE),
            stderr="",
        )

    monkeypatch.setattr(vf.subprocess, "run", fake_run)
    res = vf.run_verifier(task=TASK, diff=DIFF, summary_text=SUMMARY)

    # Exact flag set, same as the Tasker spawn / ClaudeReviewer.
    assert captured["cmd"] == [
        "claude", "--print",
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--allow-dangerously-skip-permissions",
    ]
    # Prompt arrives on stdin, not argv.
    assert "VG-99" in captured["input"]
    assert "+new frob logic" in captured["input"]
    assert not any("VG-99" in a for a in captured["cmd"])
    assert captured["timeout"] == vf.DEFAULT_VERIFIER_TIMEOUT_SECONDS

    # JSON envelope unwrapped → verdict parsed from the embedded message.
    assert res.verdict.verdict == vf.VerdictKind.VERIFIED
    assert res.verdict.reason is None
    assert res.error is None
    assert res.duration_seconds is not None and res.duration_seconds >= 0
    # Usage fields land on result.usage.
    assert res.usage.cost_usd == 0.42
    assert res.usage.input_tokens == 1200
    assert res.usage.output_tokens == 80
    assert res.usage.cache_read_input_tokens == 500
    assert res.usage.cache_creation_input_tokens == 100
    assert res.usage.duration_ms == 61234
    assert res.usage.num_turns == 3
    assert res.usage.model == "claude-opus-4-6"


def test_run_verifier_non_json_stdout_falls_back_to_raw(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=_VERIFIED_MESSAGE, stderr="",
        )

    monkeypatch.setattr(vf.subprocess, "run", fake_run)
    res = vf.run_verifier(task=TASK, diff=DIFF, summary_text=SUMMARY)
    assert res.verdict.verdict == vf.VerdictKind.VERIFIED
    assert res.error is None
    # No envelope → usage all-None.
    assert res.usage.cost_usd is None
    assert res.usage.input_tokens is None
    assert res.usage.output_tokens is None
    assert res.usage.model is None


def test_run_verifier_cli_missing_is_spawn_failed(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("no such binary: claude")

    monkeypatch.setattr(vf.subprocess, "run", fake_run)
    res = vf.run_verifier(task=TASK, diff=DIFF, summary_text=SUMMARY)
    assert res.verdict.verdict == vf.VerdictKind.INCOMPLETE
    assert res.verdict.reason == vf.REASON_SPAWN_FAILED
    assert "not found" in (res.error or "")
    assert res.duration_seconds is not None and res.duration_seconds >= 0


def test_run_verifier_timeout_is_spawn_failed(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)

    monkeypatch.setattr(vf.subprocess, "run", fake_run)
    res = vf.run_verifier(
        task=TASK, diff=DIFF, summary_text=SUMMARY, timeout_seconds=5,
    )
    assert res.verdict.verdict == vf.VerdictKind.INCOMPLETE
    assert res.verdict.reason == vf.REASON_SPAWN_FAILED
    assert "timed out after 5s" in (res.error or "")


def test_run_verifier_nonzero_exit_is_spawn_failed(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="", stderr="boom: quota exceeded",
        )

    monkeypatch.setattr(vf.subprocess, "run", fake_run)
    res = vf.run_verifier(task=TASK, diff=DIFF, summary_text=SUMMARY)
    assert res.verdict.verdict == vf.VerdictKind.INCOMPLETE
    assert res.verdict.reason == vf.REASON_SPAWN_FAILED
    assert "exit=1" in (res.error or "")
    assert "quota exceeded" in (res.error or "")


def test_run_verifier_unexpected_exception_is_spawn_failed(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise RuntimeError("kernel weirdness")

    monkeypatch.setattr(vf.subprocess, "run", fake_run)
    res = vf.run_verifier(task=TASK, diff=DIFF, summary_text=SUMMARY)
    assert res.verdict.verdict == vf.VerdictKind.INCOMPLETE
    assert res.verdict.reason == vf.REASON_SPAWN_FAILED
    assert "kernel weirdness" in (res.error or "")


def test_run_verifier_respects_claude_bin_override(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=_VERIFIED_MESSAGE, stderr="",
        )

    monkeypatch.setattr(vf.subprocess, "run", fake_run)
    vf.run_verifier(
        task=TASK, diff=DIFF, summary_text=SUMMARY, claude_bin="/opt/claude",
    )
    assert captured["cmd"][0] == "/opt/claude"


# --- serialization -------------------------------------------------------------


def test_gap_to_dict_roundtrip():
    g = vf.Gap(index=2, location="x.py:9", description="d")
    assert g.to_dict() == {"index": 2, "location": "x.py:9", "description": "d"}
    # Location-less gap keeps None on the wire.
    assert vf.Gap(index=1, location=None, description="d").to_dict() == {
        "index": 1, "location": None, "description": "d",
    }


def test_verifier_verdict_to_dict_roundtrip():
    v = vf.VerifierVerdict(
        verdict=vf.VerdictKind.INCOMPLETE,
        gaps=[vf.Gap(index=1, location="a.py:1", description="d")],
        reason=None,
        raw_output="huge blob that must stay off the wire",
    )
    d = v.to_dict()
    assert d == {
        "verdict": "INCOMPLETE",
        "gaps": [{"index": 1, "location": "a.py:1", "description": "d"}],
        "reason": None,
    }


def test_verifier_result_to_dict_roundtrip():
    res = vf.VerifierResult(
        verdict=vf.VerifierVerdict(
            verdict=vf.VerdictKind.INCOMPLETE, reason=vf.REASON_SPAWN_FAILED,
        ),
        duration_seconds=1.5,
        error="cli not found: claude",
    )
    d = res.to_dict()
    assert d["verdict"]["verdict"] == "INCOMPLETE"
    assert d["verdict"]["reason"] == vf.REASON_SPAWN_FAILED
    assert d["duration_seconds"] == 1.5
    assert d["error"] == "cli not found: claude"
    # Default usage serializes as all-None fields.
    assert d["usage"]["cost_usd"] is None
    assert d["usage"]["input_tokens"] is None


def test_run_verifier_routes_model_when_given(monkeypatch):
    """model= appends --model <id>; omitting it keeps the legacy argv.

    Regression: without an explicit --model the spawn inherits the
    operator's CLI session default — observed as a Medium/sonnet task
    verified on fable (partner-hub PH-1, 2026-07-10). The orchestrator
    passes snap.model (explicit row model or tier routing) so the
    verifier rides the same routing policy as the Tasker spawn.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=_claude_envelope(_VERIFIED_MESSAGE),
            stderr="",
        )

    monkeypatch.setattr(vf.subprocess, "run", fake_run)

    vf.run_verifier(task=TASK, diff=DIFF, summary_text=SUMMARY,
                    model="claude-sonnet-5")
    assert captured["cmd"][-2:] == ["--model", "claude-sonnet-5"]
    # Routing flag appends; the base flag set is unchanged.
    assert captured["cmd"][:1] == ["claude"]
    assert "--allow-dangerously-skip-permissions" in captured["cmd"]

    vf.run_verifier(task=TASK, diff=DIFF, summary_text=SUMMARY, model=None)
    assert "--model" not in captured["cmd"]
