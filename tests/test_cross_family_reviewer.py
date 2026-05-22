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


def test_aggregate_single_dissenter_blocks():
    panel = cfr.aggregate([_approve_verdict("claude"), _approve_verdict("gemini"), _changes_verdict("codex")])
    assert panel.consensus == "block"
    assert not panel.is_approve
    assert len(panel.blocking_findings) == 1


def test_aggregate_unavailable_yields_incomplete():
    panel = cfr.aggregate([_approve_verdict("claude"), _approve_verdict("gemini"), _unavailable_verdict("codex")])
    assert panel.consensus == "incomplete"
    assert not panel.is_approve


def test_aggregate_critical_finding_alone_blocks_even_if_verdict_is_approve():
    # A reviewer that returns APPROVE but lists a CRITICAL finding is
    # self-contradicting — the finding wins, panel blocks.
    rv = _approve_verdict("claude")
    rv.findings = [cfr.Finding(severity=cfr.Severity.CRITICAL, location="x:1",
                                description="d", fix="f")]
    panel = cfr.aggregate([rv, _approve_verdict("gemini"), _approve_verdict("codex")])
    assert panel.consensus == "block"
    assert len(panel.blocking_findings) == 1


def test_aggregate_parse_failed_blocks():
    rv = cfr.ReviewerVerdict(family="codex", verdict=cfr.Verdict.PARSE_FAILED)
    panel = cfr.aggregate([_approve_verdict("claude"), _approve_verdict("gemini"), rv])
    assert panel.consensus == "block"


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


def test_run_panel_one_dissenter_blocks():
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
    revs = [
        _StubReviewer("claude", approve),
        _StubReviewer("gemini", approve),
        _StubReviewer("codex", block),
    ]
    panel = cfr.run_panel(
        ticket_key="T2", ticket_summary="s", summary_md="sm", diff="d",
        branch="feat/t2", base_branch="main", reviewers=revs,
    )
    assert panel.consensus == "block"
    assert len(panel.blocking_findings) == 1
    assert panel.blocking_findings[0].severity == cfr.Severity.HIGH


def test_run_panel_unavailable_reviewer_yields_incomplete():
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
    revs = [
        _StubReviewer("claude", out),
        _StubReviewer("gemini", out),
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


def test_run_panel_parse_failure_twice_blocks():
    """Reviewer that fails to produce a parseable verdict on BOTH attempts
    must end up PARSE_FAILED — which counts as a blocker.
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
    assert panel.consensus == "block"
    claude_rv = next(r for r in panel.reviewers if r.family == "claude")
    assert claude_rv.verdict == cfr.Verdict.PARSE_FAILED
    assert revs[0].call_count == 2  # the flaky reviewer was retried


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


def test_gemini_reviewer_uses_yolo_and_text_output(monkeypatch):
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
    assert "gemini" in cmd[0]
    assert "--yolo" in cmd
    assert "-o" in cmd and "text" in cmd
    assert "-p" in cmd
    # Prompt MUST be on stdin, NOT in argv — argv limit is ~128KB.
    assert captured["input"].startswith("hello gemini")
    assert not any(len(a) > 1024 for a in cmd), "no argv element should carry the prompt"


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
    assert "--full-auto" in cmd
    assert "--color" in cmd and "never" in cmd
    assert "--skip-git-repo-check" in cmd
    assert "--output-last-message" in cmd
    # `-` MUST be the positional prompt — tells codex to read from stdin.
    assert cmd[-1] == "-", f"expected '-' as the last argv (stdin marker), got {cmd[-1]!r}"
    # Prompt MUST be on stdin, NOT in argv.
    assert captured["input"].startswith("hello codex")
    assert not any(len(a) > 1024 for a in cmd), "no argv element should carry the prompt"
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
    assert [r.family for r in revs] == ["claude", "gemini", "codex"]
    assert all(isinstance(r, cfr.Reviewer) for r in revs)
    # Each carries the per-class default cli_bin.
    families_to_bins = {r.family: r.cli_bin for r in revs}
    assert families_to_bins == {"claude": "claude", "gemini": "gemini", "codex": "codex"}


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
