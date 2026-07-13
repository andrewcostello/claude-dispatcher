"""Unit tests for the cross-family reviewer module.

No real CLI is invoked — `_invoke_cli` is overridden on subclasses so the
tests are hermetic. Real-CLI integration is exercised via
tools/cross_family_panel.py, not the test suite (the brief asked us not to
spend tokens on real LLM calls during pytest runs).
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import cross_family_reviewer as cfr


# --- panel_required gating --------------------------------------------------


@pytest.mark.parametrize(
    "labels,task_type,expected",
    [
        # Bare tokens
        (["critical"], None, True),
        (["high"], None, True),
        (["security"], None, True),
        (["financial"], None, True),
        # Prefixed forms
        (["risk:critical"], None, True),
        (["risk:high"], None, True),
        (["tier:financial"], None, True),
        (["severity:security"], None, True),
        (["priority:critical"], None, True),
        # Case-insensitive
        (["CRITICAL"], None, True),
        (["Risk:High"], None, True),
        # Non-matching
        (["medium"], None, False),
        (["low"], None, False),
        (["size:M"], None, False),
        (["area:smoke"], None, False),
        ([], None, False),
        (None, None, False),
        # Mixed — any matching tier wins
        (["size:M", "risk:high"], None, True),
        # docs / test type skips even with high-risk label
        (["critical"], "docs", False),
        (["high"], "test", False),
        # Unknown task_type doesn't short-circuit
        (["critical"], "Task", True),
    ],
)
def test_panel_required(labels, task_type, expected):
    assert cfr.panel_required(labels, task_type=task_type) is expected


# --- parser robustness ------------------------------------------------------


def test_parse_canonical_approve():
    raw = textwrap.dedent("""\
        ## Verdict
        APPROVE

        ## Dimension scores
        - Correctness: 5
        - Security: 4
        - Compliance: 4
        - Resilience: 4
        - Idempotency: 4
        - Observability: 4
        - Performance: 4
        - Maintainability: 4

        ## Findings
    """)
    rv = cfr.parse_review_output("claude", raw)
    assert rv.verdict == cfr.Verdict.APPROVE
    assert rv.dimensions == {
        "Correctness": 5, "Security": 4, "Compliance": 4, "Resilience": 4,
        "Idempotency": 4, "Observability": 4, "Performance": 4, "Maintainability": 4,
    }
    assert rv.findings == []
    assert not rv.is_blocker()


def test_parse_changes_requested_with_findings():
    raw = textwrap.dedent("""\
        ## Verdict
        CHANGES_REQUESTED

        ## Dimension scores
        - Correctness: 3
        - Security: 4
        - Compliance: 4
        - Resilience: 4
        - Idempotency: 4
        - Observability: 3
        - Performance: 4
        - Maintainability: 3

        ## Findings

        ### HIGH: apps/wallet/service.go:42
        Description: The transfer path does not validate the source balance
        before debiting. A concurrent debit could push the balance negative.
        Fix: Wrap the debit in `SELECT ... FOR UPDATE` and check `balance >= amount`
        before issuing the UPDATE.

        ### MEDIUM: apps/wallet/service.go:99
        Description: Missing structured log on the success path.
        Fix: Add a structured `transfer_committed` log line with from/to/amount.
    """)
    rv = cfr.parse_review_output("gemini", raw)
    assert rv.verdict == cfr.Verdict.CHANGES_REQUESTED
    assert len(rv.findings) == 2
    assert rv.findings[0].severity == cfr.Severity.HIGH
    assert rv.findings[0].location == "apps/wallet/service.go:42"
    assert "concurrent debit" in rv.findings[0].description
    assert "FOR UPDATE" in rv.findings[0].fix
    assert rv.findings[1].severity == cfr.Severity.MEDIUM
    assert rv.is_blocker()
    assert len(rv.blocking_findings()) == 1


def test_parse_tolerates_preamble_narrative():
    raw = textwrap.dedent("""\
        I reviewed the change and ran tests. Here is my verdict:

        ## Verdict
        REJECT

        ## Dimension scores
        - Correctness: 1
        - Security: 2
        - Compliance: 2
        - Resilience: 2
        - Idempotency: 2
        - Observability: 2
        - Performance: 2
        - Maintainability: 2

        ## Findings

        ### CRITICAL: apps/wallet/service.go:42
        Description: SQL injection via concatenated string.
        Fix: Use parameterized query.

        ## Notes
        I would recommend a full rewrite of this module.
    """)
    rv = cfr.parse_review_output("codex", raw)
    assert rv.verdict == cfr.Verdict.REJECT
    assert len(rv.findings) == 1
    assert rv.findings[0].severity == cfr.Severity.CRITICAL
    assert "rewrite" in rv.notes


def test_parse_tolerates_score_with_max():
    raw = textwrap.dedent("""\
        ## Verdict
        APPROVE

        ## Dimension scores
        - Correctness: 5/5
        - Security: 4/5
        - Compliance: 4 / 5
        - Resilience: **4**
        - Idempotency: 4
        - Observability: 4
        - Performance: 4
        - Maintainability: 4

        ## Findings
    """)
    rv = cfr.parse_review_output("claude", raw)
    assert rv.verdict == cfr.Verdict.APPROVE
    assert rv.dimensions["Correctness"] == 5
    assert rv.dimensions["Security"] == 4
    assert rv.dimensions["Resilience"] == 4


def test_parse_tolerates_ansi_escape():
    # Some CLIs (gemini in particular) can emit ANSI even with TTY off.
    raw = "\x1b[32m## Verdict\x1b[0m\nAPPROVE\n\n## Dimension scores\n- Correctness: 5\n\n## Findings\n"
    rv = cfr.parse_review_output("gemini", raw)
    assert rv.verdict == cfr.Verdict.APPROVE


def test_parse_fallback_when_no_verdict_section():
    # Reviewer dropped the template but mentioned the verdict word.
    raw = "I'm done reviewing. My final answer is REJECT — the implementation is broken."
    rv = cfr.parse_review_output("codex", raw)
    assert rv.verdict == cfr.Verdict.REJECT


def test_parse_returns_parse_failed_on_garbage():
    rv = cfr.parse_review_output("codex", "lorem ipsum")
    assert rv.verdict == cfr.Verdict.PARSE_FAILED
    assert rv.error is not None


def test_parse_returns_parse_failed_on_empty():
    rv = cfr.parse_review_output("codex", "")
    assert rv.verdict == cfr.Verdict.PARSE_FAILED


def test_parse_clamps_scores():
    raw = textwrap.dedent("""\
        ## Verdict
        APPROVE
        ## Dimension scores
        - Correctness: 99
        - Security: -2
        ## Findings
    """)
    rv = cfr.parse_review_output("claude", raw)
    assert rv.dimensions["Correctness"] == 5
    assert rv.dimensions["Security"] == 0


def test_parse_unavailable_self_report():
    raw = textwrap.dedent("""\
        ## Verdict
        UNAVAILABLE
        ## Dimension scores
        - Correctness: 0
        ## Findings
        ## Notes
        No diff was provided to review.
    """)
    rv = cfr.parse_review_output("gemini", raw)
    assert rv.verdict == cfr.Verdict.UNAVAILABLE
    assert "No diff" in rv.notes


# --- aggregation rules ------------------------------------------------------


def _approve_verdict(family: str) -> cfr.ReviewerVerdict:
    return cfr.ReviewerVerdict(
        family=family, verdict=cfr.Verdict.APPROVE,
        dimensions={d: 4 for d in cfr.DIMENSION_NAMES},
        findings=[],
    )


def _changes_verdict(family: str, sev: cfr.Severity = cfr.Severity.HIGH) -> cfr.ReviewerVerdict:
    return cfr.ReviewerVerdict(
        family=family, verdict=cfr.Verdict.CHANGES_REQUESTED,
        dimensions={d: 4 for d in cfr.DIMENSION_NAMES} | {"Correctness": 3},
        findings=[cfr.Finding(severity=sev, location="x.go:1", description="d", fix="f")],
    )


def _unavailable_verdict(family: str) -> cfr.ReviewerVerdict:
    return cfr.ReviewerVerdict(
        family=family, verdict=cfr.Verdict.UNAVAILABLE,
        dimensions={}, findings=[], error="cli not found",
    )


def test_aggregate_all_approve():
    panel = cfr.aggregate([_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")])
    assert panel.consensus == "approve"
    assert panel.is_approve
    assert panel.blocking_findings == []


def test_aggregate_lone_high_does_not_block_but_corroborated_high_does():
    """Corroboration gate: a LONE HIGH dissenter is uncorroborated and does NOT
    block (the finding is still recorded for the backlog); a HIGH raised by >=2
    available families IS corroborated and blocks.
    """
    lone = cfr.aggregate([
        _approve_verdict("claude"), _approve_verdict("gemini"),
        _changes_verdict("codex"),
    ])
    assert lone.consensus == "approve"
    assert lone.is_approve
    # The finding is still harvested even though it did not block.
    assert len(lone.blocking_findings) == 1

    corroborated = cfr.aggregate([
        _approve_verdict("claude"),
        _changes_verdict("gemini"), _changes_verdict("codex"),
    ])
    assert corroborated.consensus == "block"
    assert not corroborated.is_approve
    assert len(corroborated.blocking_findings) == 2


def test_aggregate_partial_unavailable_approves_all_unavailable_incomplete():
    """Corroboration gate: a single UNAVAILABLE seat is tolerated — the panel
    still reaches a verdict from the reviewers that DID run. Consensus is only
    "incomplete" when the whole available set is UNAVAILABLE.
    """
    partial = cfr.aggregate([
        _approve_verdict("claude"), _approve_verdict("gemini"),
        _unavailable_verdict("codex"),
    ])
    assert partial.consensus == "approve"

    all_gone = cfr.aggregate([
        _unavailable_verdict("claude"), _unavailable_verdict("gemini"),
        _unavailable_verdict("codex"),
    ])
    assert all_gone.consensus == "incomplete"
    assert not all_gone.is_approve


def test_aggregate_two_seat_panel_one_unavailable_approves():
    """Reduced panel (two invited seats): one
    UNAVAILABLE + one APPROVE must still approve, not incomplete-block.
    """
    panel = cfr.aggregate([
        _unavailable_verdict("gemini"),
        _approve_verdict("codex"),
    ])
    assert panel.consensus == "approve"
    assert panel.is_approve


def test_aggregate_critical_finding_alone_blocks_even_if_verdict_is_approve():
    # A reviewer that returns APPROVE but lists a CRITICAL finding is
    # self-contradicting — the finding wins, panel blocks.
    rv = _approve_verdict("claude")
    rv.findings = [cfr.Finding(severity=cfr.Severity.CRITICAL, location="x:1",
                                description="d", fix="f")]
    panel = cfr.aggregate([rv, _approve_verdict("gemini"), _approve_verdict("codex")])
    assert panel.consensus == "block"
    assert len(panel.blocking_findings) == 1


def test_aggregate_lone_parse_failed_is_tolerated():
    """Corroboration gate: a single PARSE_FAILED seat yields no parseable
    findings, so it cannot corroborate a block. With the other reviewers
    approving, the flaky seat cannot solo-block and the panel ships.

    (NB: aggregate() no longer consults ReviewerVerdict.is_blocker() — it counts
    blocking FINDINGS. A PARSE_FAILED still reports is_blocker()==True in
    isolation, but contributes nothing to the panel's finding-based gate.)
    """
    rv = cfr.ReviewerVerdict(family="codex", verdict=cfr.Verdict.PARSE_FAILED)
    assert rv.is_blocker()  # would block in isolation...
    panel = cfr.aggregate([_approve_verdict("claude"), _approve_verdict("gemini"), rv])
    assert panel.consensus == "approve"  # ...but one flaky seat can't solo-block


def test_aggregate_one_parse_failed_among_valid_seats_still_ships():
    """Single-flaky-seat tolerance preserved: ONE PARSE_FAILED beside two valid
    APPROVE seats still meets the >=2 valid-review floor, so the panel ships.
    (Scenario (c) — unchanged behaviour, asserted explicitly.)
    """
    panel = cfr.aggregate([
        _approve_verdict("gemini"), _approve_verdict("codex"),
        cfr.ReviewerVerdict(family="grok", verdict=cfr.Verdict.PARSE_FAILED),
    ])
    assert panel.consensus == "approve"
    assert panel.is_approve


def test_aggregate_all_parse_failed_is_incomplete():
    """Money-adjacent gating gap: a panel where EVERY seat failed to parse is
    NOT a valid review. It must degrade to "incomplete" (which blocks
    auto-integrate), never silently "approve" on zero real reviews.
    (Scenario (a).)
    """
    panel = cfr.aggregate([
        cfr.ReviewerVerdict(family="gemini", verdict=cfr.Verdict.PARSE_FAILED),
        cfr.ReviewerVerdict(family="codex", verdict=cfr.Verdict.PARSE_FAILED),
        cfr.ReviewerVerdict(family="grok", verdict=cfr.Verdict.PARSE_FAILED),
    ])
    assert panel.consensus == "incomplete"
    assert not panel.is_approve


def test_aggregate_majority_parse_failed_with_one_approve_is_not_approve():
    """A lone APPROVE beside a MAJORITY of PARSE_FAILED seats is uncorroborated:
    two seats never produced a real review, so the one that parsed cannot clear
    the auto-integrate gate on its own. Must be "incomplete", not a clean
    "approve". (Scenario (b).)
    """
    panel = cfr.aggregate([
        _approve_verdict("gemini"),
        cfr.ReviewerVerdict(family="codex", verdict=cfr.Verdict.PARSE_FAILED),
        cfr.ReviewerVerdict(family="grok", verdict=cfr.Verdict.PARSE_FAILED),
    ])
    assert panel.consensus == "incomplete"
    assert not panel.is_approve


def test_aggregate_mixed_unavailable_and_parse_failed_is_incomplete():
    """The "no valid seat" floor covers ANY mix of degraded seats — one
    UNAVAILABLE plus two PARSE_FAILED leaves zero valid reviews → "incomplete".
    """
    panel = cfr.aggregate([
        _unavailable_verdict("gemini"),
        cfr.ReviewerVerdict(family="codex", verdict=cfr.Verdict.PARSE_FAILED),
        cfr.ReviewerVerdict(family="grok", verdict=cfr.Verdict.PARSE_FAILED),
    ])
    assert panel.consensus == "incomplete"
    assert not panel.is_approve


def test_aggregate_empty_reviews_is_incomplete():
    panel = cfr.aggregate([])
    assert panel.consensus == "incomplete"


# --- panel runner with stub reviewers ---------------------------------------


class _StubReviewer(cfr.Reviewer):
    """Test double that returns a canned output without shelling out."""

    family = "stub"

    def __init__(self, family: str, output: str, *, raise_exc: Exception | None = None):
        super().__init__()
        self.family = family
        self._output = output
        self._raise = raise_exc
        self.call_count = 0

    def _invoke_cli(self, prompt: str) -> str:
        self.call_count += 1
        if self._raise is not None:
            raise self._raise
        return self._output


def test_run_panel_three_stubs_all_approve():
    out = textwrap.dedent("""\
        ## Verdict
        APPROVE
        ## Dimension scores
        - Correctness: 5
        - Security: 5
        - Compliance: 5
        - Resilience: 4
        - Idempotency: 4
        - Observability: 4
        - Performance: 4
        - Maintainability: 4
        ## Findings
    """)
    revs = [_StubReviewer(f, out) for f in ("claude", "gemini", "codex")]
    panel = cfr.run_panel(
        ticket_key="T1", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t1", base_branch="main", reviewers=revs,
    )
    assert panel.consensus == "approve"
    assert len(panel.reviewers) == 3
    assert all(r.call_count == 1 for r in revs)


def test_run_panel_corroborated_dissent_blocks():
    approve = textwrap.dedent("""\
        ## Verdict
        APPROVE
        ## Dimension scores
        - Correctness: 5
        - Security: 5
        - Compliance: 5
        - Resilience: 4
        - Idempotency: 4
        - Observability: 4
        - Performance: 4
        - Maintainability: 4
        ## Findings
    """)
    block = textwrap.dedent("""\
        ## Verdict
        CHANGES_REQUESTED
        ## Dimension scores
        - Correctness: 3
        - Security: 4
        - Compliance: 4
        - Resilience: 4
        - Idempotency: 4
        - Observability: 4
        - Performance: 4
        - Maintainability: 4
        ## Findings
        ### HIGH: x.go:1
        Description: race on shared state.
        Fix: lock it.
    """)
    # Corroboration gate: a HIGH blocks only when >=2 available families raise
    # a blocking finding, so both gemini and codex must dissent.
    revs = [
        _StubReviewer("claude", approve),
        _StubReviewer("gemini", block),
        _StubReviewer("codex", block),
    ]
    panel = cfr.run_panel(
        ticket_key="T2", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t2", base_branch="main", reviewers=revs,
    )
    assert panel.consensus == "block"
    assert len(panel.blocking_findings) == 2
    assert all(f.severity == cfr.Severity.HIGH for f in panel.blocking_findings)


def test_run_panel_all_unavailable_yields_incomplete():
    """Corroboration gate: "incomplete" requires the WHOLE available set to be
    UNAVAILABLE (a single missing seat is tolerated), so all three CLIs must be
    missing for the panel to report it cannot reach a verdict.
    """
    revs = [
        _StubReviewer("claude", "", raise_exc=FileNotFoundError("claude")),
        _StubReviewer("gemini", "", raise_exc=FileNotFoundError("gemini")),
        _StubReviewer("codex", "", raise_exc=FileNotFoundError("codex")),
    ]
    panel = cfr.run_panel(
        ticket_key="T3", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t3", base_branch="main", reviewers=revs,
    )
    assert panel.consensus == "incomplete"
    codex_rv = next(r for r in panel.reviewers if r.family == "codex")
    assert codex_rv.verdict == cfr.Verdict.UNAVAILABLE
    assert "not found" in (codex_rv.error or "")


def test_run_panel_parse_failure_triggers_one_retry():
    """A reviewer whose first output is unparseable should be retried once
    with a strict-template reminder. If the retry succeeds, that verdict wins.
    """
    good = textwrap.dedent("""\
        ## Verdict
        APPROVE
        ## Dimension scores
        - Correctness: 5
        - Security: 5
        - Compliance: 5
        - Resilience: 4
        - Idempotency: 4
        - Observability: 4
        - Performance: 4
        - Maintainability: 4
        ## Findings
    """)

    class _FlakyReviewer(cfr.Reviewer):
        family = "claude"
        def __init__(self):
            super().__init__()
            self.call_count = 0
        def _invoke_cli(self, prompt: str) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return "lorem ipsum totally not a verdict"
            return good

    flaky = _FlakyReviewer()
    panel = cfr.run_panel(
        ticket_key="T4", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t4", base_branch="main",
        reviewers=[flaky, _StubReviewer("gemini", good), _StubReviewer("codex", good)],
    )
    assert flaky.call_count == 2  # retry occurred
    assert panel.consensus == "approve"


def test_run_panel_parse_failure_twice_is_tolerated_uncorroborated():
    """Reviewer that fails to produce a parseable verdict on BOTH attempts ends
    up PARSE_FAILED. In isolation that verdict is a blocker, but the
    corroboration gate no longer lets a single flaky seat solo-block: with the
    other two families approving, the panel ships. The retry + PARSE_FAILED
    mechanics are still asserted so the parse path itself stays covered.
    """
    revs = [
        _StubReviewer("claude", "still not a verdict either way"),
        _StubReviewer("gemini", textwrap.dedent("""\
            ## Verdict
            APPROVE
            ## Dimension scores
            - Correctness: 5
            ## Findings
        """)),
        _StubReviewer("codex", textwrap.dedent("""\
            ## Verdict
            APPROVE
            ## Dimension scores
            - Correctness: 5
            ## Findings
        """)),
    ]
    panel = cfr.run_panel(
        ticket_key="T5", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t5", base_branch="main", reviewers=revs,
    )
    assert panel.consensus == "approve"  # one flaky seat cannot solo-block
    claude_rv = next(r for r in panel.reviewers if r.family == "claude")
    assert claude_rv.verdict == cfr.Verdict.PARSE_FAILED
    assert revs[0].call_count == 2  # the flaky reviewer was retried


def test_run_panel_all_parse_failed_yields_incomplete():
    """End-to-end money-adjacent gate: if EVERY seat's output is unparseable on
    both attempts, the panel has zero valid reviews and must be "incomplete" —
    never "approve" on an effectively-unreviewed diff.
    """
    revs = [
        _StubReviewer("gemini", "not a verdict"),
        _StubReviewer("codex", "still garbage"),
        _StubReviewer("grok", "nope, no template here"),
    ]
    panel = cfr.run_panel(
        ticket_key="T6", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t6", base_branch="main", reviewers=revs,
    )
    assert panel.consensus == "incomplete"
    assert not panel.is_approve
    assert all(r.verdict == cfr.Verdict.PARSE_FAILED for r in panel.reviewers)


# --- render output ----------------------------------------------------------


def test_render_findings_markdown_approve():
    panel = cfr.aggregate([
        _approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex"),
    ])
    md = cfr.render_findings_markdown(panel)
    assert "Verdict: APPROVE" in md
    assert "consensus=approve" in md


def test_render_findings_markdown_block_lists_findings():
    panel = cfr.aggregate([
        _approve_verdict("claude"), _approve_verdict("gemini"),
        _changes_verdict("codex", cfr.Severity.CRITICAL),
    ])
    md = cfr.render_findings_markdown(panel)
    assert "block" in md.lower()
    assert "CRITICAL" in md
    assert "x.go:1" in md


# --- prompt rendering -------------------------------------------------------


def test_build_review_prompt_includes_all_inputs():
    p = cfr.build_review_prompt(
        family="claude",
        ticket_key="TICK-1",
        ticket_summary="add escrow state",
        summary_md="## Status\nDone",
        diff="--- a/x.go\n+++ b/x.go\n@@ -1,3 +1,3 @@\n-old\n+new\n",
        branch="feat/x",
        base_branch="main",
    )
    assert "TICK-1" in p
    assert "add escrow state" in p
    assert "## Status\nDone" in p
    assert "+new" in p
    assert "main" in p and "feat/x" in p
    # Family-specific preamble must be present
    assert "Claude reviewer" in p


def test_build_review_prompt_unknown_family_raises():
    with pytest.raises(FileNotFoundError):
        cfr.build_review_prompt(
            family="bogus", ticket_key="T", ticket_summary="",
            summary_md="", diff="", branch="b", base_branch="m",
        )


# --- collect_diff -----------------------------------------------------------


def test_collect_diff_uses_three_dot_form(tmp_path: Path):
    import subprocess
    # Build a tiny repo with two branches and a divergent commit.
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "f.txt").write_text("base\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feat"], cwd=repo, check=True, capture_output=True)
    (repo / "f.txt").write_text("base\nfeature line\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat"], cwd=repo, check=True, capture_output=True)

    diff = cfr.collect_diff(repo_root=repo, base_branch="main", branch="feat")
    assert "feature line" in diff


# --- per-family adapter wiring ---------------------------------------------


def test_claude_message_extraction_strips_json_envelope():
    raw = '{"type":"result","result":"## Verdict\\nAPPROVE\\n","cost_usd":0.01}'
    msg = cfr._extract_claude_message(raw)
    assert msg == "## Verdict\nAPPROVE\n"


def test_claude_message_extraction_falls_back_for_non_json():
    # If stdout isn't a JSON envelope, _extract_claude_message returns
    # None and the adapter falls back to raw stdout.
    assert cfr._extract_claude_message("not json") is None
    assert cfr._extract_claude_message("") is None
    # Array root is also non-conforming.
    assert cfr._extract_claude_message("[1,2,3]") is None


def test_claude_reviewer_uses_correct_cli_flags(monkeypatch, tmp_path: Path):
    """ClaudeReviewer must invoke `claude --print --output-format json` with the
    bypass-permissions flags so the reviewer can run without stdin prompts.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        # Simulate a JSON envelope on stdout.
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout='{"result":"## Verdict\\nAPPROVE\\n## Dimension scores\\n- Correctness: 5\\n## Findings\\n"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = cfr.ClaudeReviewer()
    out = r._invoke_cli("hello prompt")
    assert "## Verdict" in out
    cmd = captured["cmd"]
    assert "claude" in cmd[0]
    assert "--print" in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--permission-mode" in cmd
    assert "bypassPermissions" in cmd
    assert "--allow-dangerously-skip-permissions" in cmd
    # Prompt must go via stdin, not argv.
    assert captured["input"] == "hello prompt"
    assert "hello prompt" not in cmd


def test_gemini_reviewer_invokes_agy_with_stdin(monkeypatch):
    """Gemini family CLI is `agy` (Antigravity, post-2026-05 rebrand). The
    family identifier stays "gemini" for column compatibility, but the
    binary and flags moved. Prompt must arrive via stdin.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout="## Verdict\nAPPROVE\n## Dimension scores\n- Correctness: 5\n## Findings\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = cfr.GeminiReviewer()
    out = r._invoke_cli("hello gemini" + "x" * 200000)  # big prompt
    assert "## Verdict" in out
    cmd = captured["cmd"]
    assert cmd[0] == "agy"
    assert "--print" in cmd
    assert "--print-timeout" in cmd
    # Family identifier stays "gemini" for record compatibility.
    assert r.family == "gemini"
    # Prompt MUST be on stdin, NOT in argv — argv limit is ~128KB.
    assert captured["input"].startswith("hello gemini")
    assert not any(len(a) > 1024 for a in cmd), "no argv element should carry the prompt"


@pytest.mark.parametrize("empty_stdout", ["", "   \n\t  \n"])
def test_gemini_reviewer_empty_stdout_exit0_is_unavailable(monkeypatch, empty_stdout):
    """antigravity-cli#76: agy can exit 0 with empty (or whitespace-only)
    stdout when stdout is a non-TTY pipe — exactly how the panel consumes
    it. The adapter must treat this as UNAVAILABLE with the suspected-bug
    reason, NOT let an empty string reach the parser (where it becomes
    PARSE_FAILED, a blocker, plus a wasted retry invocation).
    """
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=empty_stdout, stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    rv = cfr.GeminiReviewer().review("review this")

    assert rv.verdict == cfr.Verdict.UNAVAILABLE
    assert rv.error == "empty stdout (suspected antigravity-cli#76)"
    # Must NOT have been parsed into PARSE_FAILED, and must NOT have retried.
    assert calls["n"] == 1, "empty stdout must not trigger the parse-failure retry"
    assert not rv.findings
    assert rv.duration_seconds is not None and rv.duration_seconds >= 0


def test_codex_reviewer_uses_output_last_message(monkeypatch, tmp_path: Path):
    """Codex's stdout interleaves agent progress with the final answer.
    The adapter must use --output-last-message so we get a clean response,
    and the prompt MUST go on stdin (with `-` as the positional arg) so
    large diffs don't blow ARG_MAX.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["input"] = kwargs.get("input")
        captured["stdin"] = kwargs.get("stdin")
        # Find the --output-last-message tmpfile arg and write a synthetic
        # response there.
        for i, a in enumerate(cmd):
            if a == "--output-last-message":
                Path(cmd[i + 1]).write_text(
                    "## Verdict\nAPPROVE\n## Dimension scores\n- Correctness: 5\n## Findings\n",
                    encoding="utf-8",
                )
                break
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout="agent: noisy progress output unrelated to the verdict",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = cfr.CodexReviewer()
    out = r._invoke_cli("hello codex" + "x" * 200000)  # big prompt
    cmd = captured["cmd"]
    assert "codex" in cmd[0]
    assert "exec" in cmd
    # `--full-auto` is deprecated; the adapter must use the explicit sandbox
    # mode instead. `workspace-write` must immediately follow `--sandbox`.
    assert "--full-auto" not in cmd
    assert "--sandbox" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
    assert "--color" in cmd and "never" in cmd
    assert "--skip-git-repo-check" in cmd
    assert "--output-last-message" in cmd
    # `-` MUST be the positional prompt — tells codex to read from stdin.
    assert cmd[-1] == "-", f"expected '-' as the last argv (stdin marker), got {cmd[-1]!r}"
    # Prompt MUST be on stdin, NOT in argv.
    assert captured["input"].startswith("hello codex")
    assert not any(len(a) > 1024 for a in cmd), "no argv element should carry the prompt"
    # stdin MUST be a managed/closed handle, never the parent's (inherited)
    # stdin. Passing `input=` makes subprocess allocate a PIPE and close it
    # after the write, sending EOF — without that, `codex exec` blocks
    # forever on a non-TTY stdin (openai/codex#20919). Assert we never let
    # subprocess inherit stdin (stdin=None with no input=).
    assert captured["input"] is not None
    assert captured.get("stdin") is None, (
        "must not set an explicit stdin handle alongside input= "
        "(subprocess raises if both are given); the prompt+EOF via input= "
        "is what closes the handle"
    )
    # The output should be the clean response from the tmpfile, NOT the noisy stdout.
    assert "## Verdict" in out
    assert "APPROVE" in out
    assert "noisy progress" not in out


def test_codex_reviewer_falls_back_to_stdout_when_tmpfile_missing(monkeypatch):
    """If codex doesn't populate the last-message file (older build,
    config mismatch), the adapter should fall back to stdout instead of
    silently returning empty.
    """
    def fake_run(cmd, **kwargs):
        # Do NOT populate the tmpfile.
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout="## Verdict\nAPPROVE\n## Dimension scores\n- Correctness: 5\n## Findings\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = cfr.CodexReviewer()
    out = r._invoke_cli("p")
    assert "APPROVE" in out


def test_parse_codex_usage_with_reasoning_tokens():
    """Codex 0.122–0.139 includes reasoning_output_tokens in the usage event."""
    line = (
        '{"type":"token_count","usage":{"input_tokens":1200,'
        '"cached_input_tokens":800,"output_tokens":340,'
        '"reasoning_output_tokens":210,"total_tokens":1540}}'
    )
    u = cfr.parse_codex_usage(line)
    assert u.input_tokens == 1200
    assert u.cached_input_tokens == 800
    assert u.output_tokens == 340
    assert u.reasoning_output_tokens == 210
    assert u.total_tokens == 1540


def test_parse_codex_usage_without_reasoning_tokens():
    """Codex 0.121.0 (the field's predecessor) omits reasoning_output_tokens.

    The parser MUST leave it None — "not reported" — not coerce it to 0,
    which would mean "reported zero reasoning" and corrupt quota math.
    """
    line = (
        '{"type":"token_count","usage":{"input_tokens":900,'
        '"output_tokens":120,"total_tokens":1020}}'
    )
    u = cfr.parse_codex_usage(line)
    assert u.input_tokens == 900
    assert u.output_tokens == 120
    assert u.total_tokens == 1020
    assert u.reasoning_output_tokens is None
    # cached_input_tokens also absent here → None, not 0.
    assert u.cached_input_tokens is None


def test_parse_codex_usage_picks_last_event_in_stream():
    """The --json stream reports usage per turn; the parser keeps the last
    (cumulative) usage object and ignores non-usage events."""
    stream = "\n".join([
        '{"type":"task_started"}',
        '{"type":"token_count","usage":{"input_tokens":100,"output_tokens":10,"total_tokens":110}}',
        '{"type":"agent_message","text":"working"}',
        '{"type":"token_count","usage":{"input_tokens":500,"output_tokens":80,'
        '"reasoning_output_tokens":40,"total_tokens":620}}',
    ])
    u = cfr.parse_codex_usage(stream)
    assert u.input_tokens == 500
    assert u.output_tokens == 80
    assert u.reasoning_output_tokens == 40
    assert u.total_tokens == 620


def test_parse_codex_usage_tolerates_info_total_token_usage_shape():
    """Some builds nest the cumulative total under info.total_token_usage."""
    line = (
        '{"msg":{"info":{"total_token_usage":'
        '{"input_tokens":7,"output_tokens":3,"total_tokens":10}}}}'
    )
    u = cfr.parse_codex_usage(line)
    assert u.input_tokens == 7
    assert u.output_tokens == 3
    assert u.total_tokens == 10


def test_parse_codex_usage_empty_and_garbage_return_empty():
    for bad in ("", "   ", "not json at all", "[1,2,3]", '{"type":"task_started"}'):
        u = cfr.parse_codex_usage(bad)
        assert u.input_tokens is None
        assert u.output_tokens is None
        assert u.reasoning_output_tokens is None
        assert u.total_tokens is None


def test_codex_usage_to_dict_roundtrip():
    u = cfr.CodexUsage(
        input_tokens=10, cached_input_tokens=4, output_tokens=5,
        reasoning_output_tokens=2, total_tokens=15,
    )
    assert u.to_dict() == {
        "input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 5,
        "reasoning_output_tokens": 2, "total_tokens": 15,
    }


def test_reviewer_unavailable_on_filenotfounderror():
    """If the CLI is not installed, FileNotFoundError propagates from
    subprocess.run; Reviewer.review() must catch and turn it into
    UNAVAILABLE without crashing the panel.
    """
    class _MissingCli(cfr.Reviewer):
        family = "claude"
        def _invoke_cli(self, prompt: str) -> str:
            raise FileNotFoundError("no such binary: claude")

    rv = _MissingCli().review("p")
    assert rv.verdict == cfr.Verdict.UNAVAILABLE
    assert "not found" in (rv.error or "")
    assert rv.duration_seconds is not None and rv.duration_seconds >= 0


def test_reviewer_unavailable_on_timeout():
    class _Slow(cfr.Reviewer):
        family = "codex"
        def _invoke_cli(self, prompt: str) -> str:
            raise subprocess.TimeoutExpired(cmd="codex", timeout=1)

    rv = _Slow().review("p")
    assert rv.verdict == cfr.Verdict.UNAVAILABLE
    assert "timed out" in (rv.error or "")


# --- serialization + factory -----------------------------------------------


def test_finding_to_dict_roundtrip():
    f = cfr.Finding(
        severity=cfr.Severity.CRITICAL,
        location="x.go:42",
        description="d",
        fix="f",
    )
    d = f.to_dict()
    assert d == {
        "severity": "CRITICAL", "location": "x.go:42",
        "description": "d", "fix": "f",
    }


def test_reviewer_verdict_to_dict_includes_findings():
    rv = cfr.ReviewerVerdict(
        family="claude",
        verdict=cfr.Verdict.CHANGES_REQUESTED,
        dimensions={"Correctness": 3},
        findings=[
            cfr.Finding(severity=cfr.Severity.HIGH, location="a:1", description="d", fix=""),
        ],
        notes="n",
        error=None,
        duration_seconds=12.3,
    )
    d = rv.to_dict()
    assert d["family"] == "claude"
    assert d["verdict"] == "CHANGES_REQUESTED"
    assert d["dimensions"] == {"Correctness": 3}
    assert d["findings"][0]["severity"] == "HIGH"
    assert d["duration_seconds"] == 12.3


def test_panel_verdict_to_dict_has_consensus_and_reviewers():
    p = cfr.aggregate([_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")])
    d = p.to_dict()
    assert d["consensus"] == "approve"
    assert len(d["reviewers"]) == 3
    assert d["blocking_findings"] == []


def test_default_reviewers_returns_three_families():
    revs = cfr.default_reviewers()
    # ForeverIndy cost optimisation: the authoritative panel is the three
    # FLAT-RATE-subscription families (Gemini, Codex, Grok). Claude is dropped
    # from the default panel (it is the metered agent and already the Tasker).
    assert [r.family for r in revs] == ["gemini", "codex", "grok"]
    assert all(isinstance(r, cfr.Reviewer) for r in revs)
    # Each carries the per-class default cli_bin. The gemini-family
    # reviewer uses agy (Antigravity, post-2026-05 rebrand of gemini); the
    # family identifier remains "gemini" for record compatibility.
    families_to_bins = {r.family: r.cli_bin for r in revs}
    assert families_to_bins == {"gemini": "agy", "codex": "codex", "grok": "grok"}


def test_default_reviewers_propagates_timeout():
    revs = cfr.default_reviewers(timeout_seconds=42)
    assert all(r.timeout_seconds == 42 for r in revs)


def test_reviewer_review_retry_path_catches_second_exception():
    """If the retry raises, the original PARSE_FAILED verdict is returned
    with the retry error recorded on it — never crashes the panel.
    """
    class _Flaky(cfr.Reviewer):
        family = "claude"
        def __init__(self):
            super().__init__()
            self.call_count = 0
        def _invoke_cli(self, prompt: str) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return "not a verdict"
            raise RuntimeError("retry boom")

    rv = _Flaky().review("p")
    assert rv.verdict == cfr.Verdict.PARSE_FAILED
    assert "retry boom" in (rv.error or "")


def test_collect_diff_truncation(tmp_path: Path):
    import subprocess
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "f.txt").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feat"], cwd=repo, check=True, capture_output=True)
    # Generate a big diff.
    (repo / "f.txt").write_text("\n".join(f"line {i}" for i in range(1000)) + "\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat"], cwd=repo, check=True, capture_output=True)

    diff = cfr.collect_diff(repo_root=repo, base_branch="main", branch="feat", max_lines=50)
    assert "diff truncated" in diff


# --- advisory tier (VG-5) -----------------------------------------------------


_GROK_APPROVE_STDOUT = (
    "## Verdict\nAPPROVE\n## Dimension scores\n- Correctness: 5\n## Findings\n"
)


def test_grok_reviewer_invokes_prompt_file_with_devnull_stdin(monkeypatch):
    """GrokReviewer must pass the prompt via a --prompt-file tempfile (never
    argv — E2BIG on big diffs), keep stdin at DEVNULL (the codex#20919 hang
    class), use the verified flag set, and unlink the tempfile afterward.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["stdin"] = kwargs.get("stdin")
        captured["input"] = kwargs.get("input")
        captured["timeout"] = kwargs.get("timeout")
        path = Path(cmd[cmd.index("--prompt-file") + 1])
        captured["prompt_file"] = path
        captured["prompt_contents"] = path.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout=_GROK_APPROVE_STDOUT,
            # grok 0.2.39 spams ANSI ERROR lines on stderr even on success;
            # the adapter must never parse stderr.
            stderr="\x1b[31mERROR noisy log line\x1b[0m",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = cfr.GrokReviewer()
    big_prompt = "hello grok" + "x" * 200000  # way past ARG_MAX per-arg limit
    out = r._invoke_cli(big_prompt)
    assert "## Verdict" in out

    # Full argv shape per the live-verified 0.2.39 contract.
    assert captured["cmd"] == [
        "grok",
        "--prompt-file", str(captured["prompt_file"]),
        "--output-format", "plain",
        "--always-approve",
    ]
    # The prompt landed in the file — verbatim — not on argv or stdin.
    assert captured["prompt_contents"] == big_prompt
    assert captured["input"] is None
    assert not any(len(a) > 1024 for a in captured["cmd"])
    assert captured["stdin"] == subprocess.DEVNULL
    # No internal grok timeout flag exists; the subprocess timeout is the budget.
    assert captured["timeout"] == r.timeout_seconds
    # Tempfile unlinked after the invocation.
    assert not captured["prompt_file"].exists()


@pytest.mark.parametrize("empty_stdout", ["", "   \n\t  \n"])
def test_grok_reviewer_empty_stdout_exit0_is_unavailable(monkeypatch, empty_stdout):
    """Edge 7a: exit 0 with empty/whitespace stdout (e.g. auth expired and
    grok only wrote to stderr) must become UNAVAILABLE with the verbatim
    ReviewerUnavailable reason — no parse attempt, no retry — and the
    prompt tempfile must still be unlinked.
    """
    calls = {"n": 0}
    paths = []

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        paths.append(Path(cmd[cmd.index("--prompt-file") + 1]))
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=empty_stdout,
            stderr="ERROR credentials expired",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    rv = cfr.GrokReviewer().review("review this")

    assert rv.verdict == cfr.Verdict.UNAVAILABLE
    assert rv.error == "empty stdout"
    assert calls["n"] == 1, "empty stdout must not trigger the parse-failure retry"
    assert not rv.findings
    assert all(not p.exists() for p in paths)


def test_grok_reviewer_nonzero_exit_is_unavailable(monkeypatch):
    """Edge 7b: nonzero exit raises RuntimeError with exit code + stderr
    tail; the base class maps it to UNAVAILABLE. Tempfile still unlinked.
    """
    paths = []

    def fake_run(cmd, **kwargs):
        paths.append(Path(cmd[cmd.index("--prompt-file") + 1]))
        return subprocess.CompletedProcess(
            args=cmd, returncode=2, stdout="",
            stderr="ERROR: credentials expired",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    rv = cfr.GrokReviewer().review("p")
    assert rv.verdict == cfr.Verdict.UNAVAILABLE
    assert "grok exit=2" in (rv.error or "")
    assert "credentials expired" in (rv.error or "")
    assert all(not p.exists() for p in paths)


def test_grok_reviewer_timeout_is_unavailable(monkeypatch):
    """Edge 7c: a subprocess timeout becomes UNAVAILABLE with the standard
    'cli timed out after Ns' reason. Tempfile still unlinked (finally).
    """
    paths = []

    def fake_run(cmd, **kwargs):
        paths.append(Path(cmd[cmd.index("--prompt-file") + 1]))
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(subprocess, "run", fake_run)
    rv = cfr.GrokReviewer(timeout_seconds=7).review("p")
    assert rv.verdict == cfr.Verdict.UNAVAILABLE
    assert rv.error == "cli timed out after 7s"
    assert all(not p.exists() for p in paths)


def test_advisory_reviewers_from_names_builds_grok_and_reports_unknown():
    """Edge 5 (factory half): known names instantiate real adapters with the
    requested timeout; unknown names are RETURNED, never raised, so the
    caller can journal them without crashing the panel.
    """
    reviewers, unknown = cfr.advisory_reviewers_from_names(
        ["grok", "foo"], timeout_seconds=42,
    )
    assert len(reviewers) == 1
    assert isinstance(reviewers[0], cfr.GrokReviewer)
    assert reviewers[0].family == "grok"
    assert reviewers[0].cli_bin == "grok"
    assert reviewers[0].timeout_seconds == 42
    assert unknown == ["foo"]


def test_advisory_reviewers_from_names_is_case_insensitive_and_empty_safe():
    reviewers, unknown = cfr.advisory_reviewers_from_names(["  Grok "])
    assert len(reviewers) == 1 and isinstance(reviewers[0], cfr.GrokReviewer)
    assert unknown == []
    reviewers, unknown = cfr.advisory_reviewers_from_names([])
    assert reviewers == [] and unknown == []


def test_advisory_families_registry_contains_grok_only():
    assert cfr.ADVISORY_FAMILIES == {"grok": cfr.GrokReviewer}


def _advisory_changes_verdict(family: str = "grok") -> cfr.ReviewerVerdict:
    return cfr.ReviewerVerdict(
        family=family, verdict=cfr.Verdict.CHANGES_REQUESTED,
        findings=[cfr.Finding(
            severity=cfr.Severity.CRITICAL, location="adv.go:7",
            description="advisory-only defect", fix="advisory fix",
        )],
    )


def test_aggregate_advisory_critical_never_blocks():
    """Edge 2 (unit): an advisory CHANGES_REQUESTED with a CRITICAL finding
    has zero effect on a 3/3-APPROVE panel — and the finding stays out of
    blocking_findings.
    """
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")],
        advisory=[_advisory_changes_verdict()],
    )
    assert panel.consensus == "approve"
    assert panel.is_approve
    assert panel.blocking_findings == []
    assert [r.family for r in panel.advisory] == ["grok"]
    assert panel.advisory[0].findings[0].severity == cfr.Severity.CRITICAL
    # The summary line is authoritative-only.
    assert "grok" not in panel.summary


def test_aggregate_advisory_unavailable_does_not_make_incomplete():
    """Edge 1 (unit): advisory UNAVAILABLE while authoritative 3/3 APPROVE
    → consensus stays "approve", never "incomplete".
    """
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")],
        advisory=[_unavailable_verdict("grok")],
    )
    assert panel.consensus == "approve"
    assert panel.advisory[0].verdict == cfr.Verdict.UNAVAILABLE


def test_aggregate_advisory_approve_does_not_rescue_block():
    """Edge 3 (unit): an authoritative block stands regardless of advisory
    APPROVE, and blocking_findings carries only authoritative findings.

    Under the corroboration gate a lone HIGH would not block, so the
    authoritative block here is driven by a CRITICAL (which blocks on a single
    family) — the advisory APPROVE must still not rescue it.
    """
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"),
         _changes_verdict("codex", cfr.Severity.CRITICAL)],
        advisory=[_approve_verdict("grok")],
    )
    assert panel.consensus == "block"
    assert [f.location for f in panel.blocking_findings] == ["x.go:1"]


def test_aggregate_advisory_parse_failed_is_non_blocking():
    """Edge 6 (unit): PARSE_FAILED blocks for authoritative reviewers (via
    is_blocker); an advisory PARSE_FAILED must bypass that path entirely.
    """
    adv = cfr.ReviewerVerdict(family="grok", verdict=cfr.Verdict.PARSE_FAILED)
    assert adv.is_blocker()  # would block if it were authoritative...
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")],
        advisory=[adv],
    )
    assert panel.consensus == "approve"  # ...but advisory never enters the math


def test_aggregate_authoritative_unavailable_stays_incomplete_despite_advisory_approve():
    """Edge 8 (unit): advisory APPROVE cannot rescue a fully-missing
    authoritative panel — consensus stays "incomplete".

    Under the corroboration gate a single missing seat is tolerated, so
    "incomplete" requires the whole authoritative set UNAVAILABLE; the advisory
    APPROVE must not turn that into "approve".
    """
    panel = cfr.aggregate(
        [_unavailable_verdict("claude"), _unavailable_verdict("gemini"),
         _unavailable_verdict("codex")],
        advisory=[_approve_verdict("grok")],
    )
    assert panel.consensus == "incomplete"
    assert not panel.is_approve


def test_aggregate_without_advisory_has_empty_advisory_list():
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")],
    )
    assert panel.advisory == []
    assert panel.to_dict()["advisory"] == []


def test_run_panel_advisory_runs_alongside_and_attaches():
    """run_panel executes advisory reviewers in the same parallel pass and
    attaches their verdicts to PanelVerdict.advisory without touching the
    consensus.
    """
    approve = textwrap.dedent("""\
        ## Verdict
        APPROVE
        ## Dimension scores
        - Correctness: 5
        ## Findings
    """)
    block = textwrap.dedent("""\
        ## Verdict
        CHANGES_REQUESTED
        ## Dimension scores
        - Correctness: 2
        ## Findings
        ### CRITICAL: adv.go:7
        Description: advisory-only defect.
        Fix: advisory fix.
    """)
    revs = [_StubReviewer(f, approve) for f in ("claude", "gemini", "codex")]
    adv = _StubReviewer("grok", block)
    panel = cfr.run_panel(
        ticket_key="T6", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t6", base_branch="main",
        reviewers=revs, advisory_reviewers=[adv],
    )
    assert panel.consensus == "approve"
    assert adv.call_count == 1
    assert [r.family for r in panel.reviewers] == ["claude", "gemini", "codex"]
    assert [r.family for r in panel.advisory] == ["grok"]
    assert panel.advisory[0].verdict == cfr.Verdict.CHANGES_REQUESTED
    assert panel.blocking_findings == []


def test_run_panel_advisory_leaked_exception_recorded_as_unavailable():
    """An advisory worker that leaks an exception OUTSIDE Reviewer.review()
    (here: build_review_prompt raising for a family with no prompt file)
    must not crash the panel — it is recorded as UNAVAILABLE for that family.
    """
    approve = textwrap.dedent("""\
        ## Verdict
        APPROVE
        ## Dimension scores
        - Correctness: 5
        ## Findings
    """)
    revs = [_StubReviewer(f, approve) for f in ("claude", "gemini", "codex")]
    adv = _StubReviewer("no-such-family", approve)  # no prompt preamble exists
    panel = cfr.run_panel(
        ticket_key="T7", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t7", base_branch="main",
        reviewers=revs, advisory_reviewers=[adv],
    )
    assert panel.consensus == "approve"
    assert panel.advisory[0].family == "no-such-family"
    assert panel.advisory[0].verdict == cfr.Verdict.UNAVAILABLE
    assert "advisory worker raised" in (panel.advisory[0].error or "")


def test_run_panel_no_advisory_unchanged():
    """Edge 4 (unit): omitting advisory_reviewers leaves run_panel's output
    shape exactly as before — empty advisory list.
    """
    approve = textwrap.dedent("""\
        ## Verdict
        APPROVE
        ## Dimension scores
        - Correctness: 5
        ## Findings
    """)
    revs = [_StubReviewer(f, approve) for f in ("claude", "gemini", "codex")]
    panel = cfr.run_panel(
        ticket_key="T8", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t8", base_branch="main", reviewers=revs,
    )
    assert panel.consensus == "approve"
    assert panel.advisory == []


def test_build_review_prompt_grok_family():
    """The grok preamble must exist, identify the reviewer as Grok (xAI),
    survive .format() over the whole concatenation (no literal braces), and
    must NOT reveal that the verdict is advisory (full-diligence reviews
    keep scorecards comparable).
    """
    p = cfr.build_review_prompt(
        family="grok", ticket_key="T-9", ticket_summary="sum",
        summary_md="md", diff="+x", branch="feat/g", base_branch="main",
    )
    assert "Grok (xAI) reviewer" in p
    assert "T-9" in p and "+x" in p
    assert "advisory" not in p.lower()
    assert "probation" not in p.lower()


def test_render_markdown_approve_includes_advisory_appendix():
    """Edge 2 (render, approve path): the advisory appendix appears, clearly
    labelled non-blocking, and no 'Blocking findings' section exists.
    """
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")],
        advisory=[_advisory_changes_verdict()],
    )
    md = cfr.render_findings_markdown(panel)
    assert "Verdict: APPROVE" in md
    assert "### Advisory reviewers (non-blocking, probationary)" in md
    assert "advisory-only defect" in md
    assert "adv.go:7" in md
    assert "*Fix:* advisory fix" in md
    assert "### Blocking findings" not in md


def test_render_markdown_block_keeps_advisory_separate_from_blocking():
    """Edge 2/3 (render, block path): advisory findings render ONLY under
    the advisory appendix, never inside 'Blocking findings'.
    """
    # A CRITICAL authoritative dissent drives the block render path (a lone HIGH
    # would not block under the corroboration gate).
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"),
         _changes_verdict("codex", cfr.Severity.CRITICAL)],
        advisory=[_advisory_changes_verdict()],
    )
    md = cfr.render_findings_markdown(panel)
    assert "### Blocking findings" in md
    assert "### Advisory reviewers (non-blocking, probationary)" in md
    blocking_section = md.split("### Blocking findings")[1].split(
        "### Advisory reviewers")[0]
    assert "x.go:1" in blocking_section
    assert "adv.go:7" not in blocking_section
    advisory_section = md.split("### Advisory reviewers")[1]
    assert "adv.go:7" in advisory_section
    assert "[advisory:grok]" in advisory_section


def test_render_markdown_approve_without_advisory_unchanged():
    """Zero-advisory approve render stays byte-identical to the legacy form."""
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")],
    )
    md = cfr.render_findings_markdown(panel)
    assert md == f"## Cross-family panel\n\nVerdict: APPROVE ({panel.summary})\n"


def test_panel_verdict_to_dict_includes_advisory():
    panel = cfr.aggregate(
        [_approve_verdict("claude"), _approve_verdict("gemini"), _approve_verdict("codex")],
        advisory=[_unavailable_verdict("grok")],
    )
    d = panel.to_dict()
    assert d["advisory"][0]["family"] == "grok"
    assert d["advisory"][0]["verdict"] == "UNAVAILABLE"
