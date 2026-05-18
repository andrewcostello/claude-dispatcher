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


def test_missing_file_marks_malformed(tmp_path) -> None:
    s = summary.parse(tmp_path / "does-not-exist.md")
    assert s.malformed is True
    assert "not found" in s.malformed_reason


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
