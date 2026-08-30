"""Tests for the summary file parser.

The parser must be resilient: malformed sections set `malformed=True` rather
than raising. The dispatcher then marks the task Blocked with reason
"summary file malformed" — never crashes the whole run.
"""

from __future__ import annotations

import textwrap

from claude_dispatcher import summary


# --- helpers ----------------------------------------------------------------

def _summary_text(status: str, **kwargs) -> str:
    """Render a minimal summary file with the given Status.

    Multi-line substituted values are appended after section headings as-is
    (not interpolated into an indented f-string), so each line stays at
    column 0 regardless of its source indentation.
    """
    iterations = kwargs.get("iterations", 1)
    linter_cycles = kwargs.get("linter_cycles", 0)
    human_gate = "yes" if kwargs.get("human_gate", False) else "no"
    score = kwargs.get("score_repr", "23/25")
    deferred = kwargs.get("deferred_block", "- something minor — file.go:42")
    pr_block = kwargs.get("pr_block", "https://github.com/test/repo/pull/1")

    return "\n".join([
        "# SMOKE-A: trivial unblocked task",
        "",
        f"**Status:** {status}",
        "**Started:** 2026-05-18T09:15:00-07:00",
        "**Completed:** 2026-05-18T09:17:00-07:00",
        f"**Iterations:** {iterations}",
        f"**Linter cycles:** {linter_cycles}",
        f"**Human gate fired:** {human_gate}",
        f"**Final quality score:** {score}",
        "",
        "## What landed",
        "Echoed the placeholder.",
        "",
        "## Key decisions",
        "None notable.",
        "",
        "## Deferred findings",
        deferred,
        "",
        "## Review consensus",
        "| Reviewer | Score | Verdict |",
        "|----------|-------|---------|",
        "| A | 23/25 | APPROVE |",
        "| B | 22/25 | APPROVE |",
        "| C | 23/25 | APPROVE |",
        "",
        "## Files changed",
        "- README.md",
        "",
        "## PR",
        pr_block,
        "",
    ])


# --- happy paths ------------------------------------------------------------

def test_parses_done_status() -> None:
    s = summary.parse_text(_summary_text("Done"))
    assert s.status == "Done"
    assert s.task_key == "SMOKE-A"
    assert s.iterations == 1
    assert s.final_quality_score == 23
    assert s.human_gate_fired is False
    assert s.pr_url == "https://github.com/test/repo/pull/1"
    assert s.malformed is False


def test_parses_review_consensus() -> None:
    s = summary.parse_text(_summary_text("Done"))
    assert len(s.review_consensus) == 3
    assert s.review_consensus[0]["reviewer"] == "A"
    assert s.review_consensus[0]["score"] == "23/25"
    assert s.review_consensus[0]["verdict"] == "APPROVE"


def test_parses_deferred_findings() -> None:
    s = summary.parse_text(_summary_text(
        "Done",
        deferred_block="- finding one — a.go:1\n- finding two — b.go:2",
    ))
    assert s.deferred_findings_count == 2


def test_parses_files_changed() -> None:
    s = summary.parse_text(_summary_text("Done"))
    assert s.files_changed == ["README.md"]


def test_parses_not_raised_pr() -> None:
    s = summary.parse_text(_summary_text(
        "Blocked",
        pr_block="Not raised: iteration cap reached",
    ))
    assert s.pr_url is None
    assert s.pr_not_raised_reason == "iteration cap reached"


def test_parses_prepared_pr_section() -> None:
    """Critical/financial-paths-touched APPROVE: gate fired, PR prepared but not raised."""
    pr_block = textwrap.dedent("""\
        Prepared, awaiting human approval

        ### Prepared PR
        **Title:** fix(wallet): [SMG-1657] add escrow state
        **Branch:** fix/SMG-1657-escrow-state
        **Body:**
        ```
        ## What
        Added an escrow state to prevent silent payout loss.

        ## Ticket
        SMG-1657
        ```
    """).rstrip()
    s = summary.parse_text(_summary_text("Blocked", pr_block=pr_block, human_gate=True))
    assert s.awaiting_human_approval is True
    assert s.prepared_pr_title == "fix(wallet): [SMG-1657] add escrow state"
    assert s.prepared_pr_branch == "fix/SMG-1657-escrow-state"
    assert "Added an escrow state" in s.prepared_pr_body
    assert "## Ticket" in s.prepared_pr_body


# --- malformed cases --------------------------------------------------------

def test_invalid_status_marks_malformed() -> None:
    s = summary.parse_text(_summary_text("Garbage"))
    assert s.malformed is True
    assert "Status" in s.malformed_reason
    # The specific reason names the invalid value and is mirrored into problems.
    assert s.problems == [s.malformed_reason]
    assert any("invalid status value" in p and "Garbage" in p for p in s.problems)


def test_missing_status_line_marks_malformed() -> None:
    """No `**Status:**` line at all is distinct from an invalid value."""
    no_status = textwrap.dedent("""\
        # SMOKE-A: trivial task

        **Started:** 2026-05-18T09:15:00-07:00
        **Completed:** 2026-05-18T09:17:00-07:00

        ## What landed
        Nothing.

        ## PR
        Not raised: low-risk dry run
    """)
    s = summary.parse_text(no_status)
    assert s.malformed is True
    assert any("missing Status line" in p for p in s.problems)


def test_missing_file_marks_malformed(tmp_path) -> None:
    s = summary.parse(tmp_path / "does-not-exist.md")
    assert s.malformed is True
    assert "not found" in s.malformed_reason
    assert any("not found" in p for p in s.problems)


def test_unterminated_fence_marks_malformed() -> None:
    """A dangling code fence (truncated/fence-confused file) is recorded."""
    truncated = textwrap.dedent("""\
        # SMOKE-A: trivial task

        **Status:** Done
        **Started:** 2026-05-18T09:15:00-07:00
        **Completed:** 2026-05-18T09:17:00-07:00

        ## PR
        Prepared, awaiting human approval

        ### Prepared PR
        **Title:** fix(x): [SMG-1] thing
        **Branch:** fix/SMG-1-thing
        **Body:**
        ```
        ## What
        Body got cut off before the closing fence
    """)
    s = summary.parse_text(truncated)
    assert s.malformed is True
    assert any("unterminated code fence" in p for p in s.problems)


def test_unparseable_pr_section_marks_malformed() -> None:
    """A PR section whose first line matches none of the known forms is flagged."""
    s = summary.parse_text(_summary_text(
        "Done",
        pr_block="raised it somewhere, check slack",
    ))
    assert s.malformed is True
    assert any("unparseable PR section" in p for p in s.problems)


def test_awaiting_approval_missing_fields_marks_malformed() -> None:
    """'Awaiting approval' without the prepared-PR metadata is unparseable."""
    pr_block = textwrap.dedent("""\
        Prepared, awaiting human approval

        ### Prepared PR
        **Title:** fix(wallet): [SMG-1657] add escrow state
    """).rstrip()
    s = summary.parse_text(_summary_text("Blocked", pr_block=pr_block, human_gate=True))
    assert s.malformed is True
    problem = next(p for p in s.problems if "awaiting human approval" in p)
    assert "Branch" in problem and "Body" in problem


def test_multiple_problems_recorded() -> None:
    """All distinct problems accumulate; malformed_reason joins them."""
    s = summary.parse_text(_summary_text(
        "Garbage",
        pr_block="totally unexpected pr line",
    ))
    assert len(s.problems) == 2
    assert s.malformed_reason == "; ".join(s.problems)
    assert any("invalid status value" in p for p in s.problems)
    assert any("unparseable PR section" in p for p in s.problems)


def test_score_not_reviewed_returns_none() -> None:
    s = summary.parse_text(_summary_text("Done", score_repr="— not reviewed"))
    assert s.final_quality_score is None


def test_handles_missing_optional_sections() -> None:
    """A truly minimal valid summary should parse without crashing.

    Sections that don't appear yield defaults — empty strings, empty lists.
    """
    minimal = textwrap.dedent("""\
        # SMOKE-A: trivial task

        **Status:** Done
        **Started:** 2026-05-18T09:15:00-07:00
        **Completed:** 2026-05-18T09:17:00-07:00
        **Iterations:** 0
        **Linter cycles:** 0
        **Human gate fired:** no
        **Final quality score:** — not reviewed

        ## What landed
        Nothing.

        ## PR
        Not raised: low-risk dry run
    """)
    s = summary.parse_text(minimal)
    assert s.status == "Done"
    assert s.malformed is False
    assert s.deferred_findings == []
    assert s.files_changed == []
    assert s.review_consensus == []


# ── an unfinished summary is not evidence ───────────────────────────────────
# The summary is written LAST and is the artifact the dispatcher judges, so a
# session that spends its budget on the work reports over an unfinished file.
# Measured across W2-3-5, W2-1-3 and W2-1-4 (2026-08-29): all three declared a
# status with their work COMMITTED and their tree CLEAN, and each blocked with
# no stated reason at all — leaving the operator to open the file to find out
# why. W2-1-4 spent two rounds and ~$25 that way.


def test_an_unfilled_placeholder_token_is_malformed() -> None:
    """W2-1-4 shipped this literal token where its whole-suite result belonged.
    What caught it was a panel seat opening the file — a HIGH finding that cost
    a three-seat review. A regex is cheaper and always runs."""
    s = summary.parse_text(
        "# T\n**Status:** Blocked\n\n## Tests\n- whole suite: WHOLE_SUITE_PLACEHOLDER\n"
    )
    assert s.malformed
    assert any("WHOLE_SUITE_PLACEHOLDER" in p for p in s.problems)


def test_a_bare_placeholder_token_is_malformed() -> None:
    s = summary.parse_text("# T\n**Status:** Done\n\n## Tests\n- PLACEHOLDER\n")
    assert s.malformed


def test_the_word_placeholder_in_prose_is_not_a_placeholder() -> None:
    """The check must not fire on a summary that TALKS about placeholders.
    Flagging honest prose would teach agents to avoid the word rather than the
    practice."""
    s = summary.parse_text(
        "# T\n**Status:** Done\n\n## Tests\n"
        "- 10 passed; no placeholder rows remain in the ledger\n"
    )
    assert not s.malformed, s.problems


def test_a_summary_that_reports_its_own_session_as_unfinished_is_malformed() -> None:
    """"Session in progress" is a session state, not an outcome. The work may
    well be complete — W2-1-4's was, committed and clean — but this file is not
    evidence of it, and the operator is owed that distinction by name."""
    s = summary.parse_text(
        "# T\n**Status:** Blocked\n\n## Tests\n"
        "- (suites in flight — rewritten with the real numbers later)\n\n"
        "## Escalation reason\nSession in progress.\n"
    )
    assert s.malformed
    assert any("unfinished" in p for p in s.problems)


def test_a_finished_summary_reporting_a_real_failure_is_not_malformed() -> None:
    """The check is about UNFINISHED, not about bad news. A summary that says
    the suite failed is complete evidence and must pass."""
    s = summary.parse_text(
        "# T\n**Status:** Blocked\n\n## Tests\n"
        "- whole suite: 3 failed, 3708 passed\n\n"
        "## Escalation reason\nThe three rows need a ruling I cannot make.\n"
    )
    assert not s.malformed, s.problems
