"""Seals for the reviewer bake-off harness.

The harness exists to decide the panel's seat order, so a scoring bug here
picks the wrong seat to drop. Two of its rules are the load-bearing ones and
both were established by something that actually happened on the first run:

  * an UNREACHED family must never be scored as a family that MISSED. claude's
    seat exhausted its model quota 7 cases in and returned UNAVAILABLE in
    ~4.5s; scoring those 11 cases as misses would have reported 21% detection
    for the family that, once re-run, caught everything.
  * a MEDIUM note is not a catch. Every family "mentions" most defects
    somewhere; only a HIGH or CRITICAL finding stops the merge, so only that
    counts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_dispatcher import cross_family_reviewer as cfr
from claude_dispatcher import reviewer_bakeoff as rb

CORPUS = Path(__file__).resolve().parents[1] / "docs" / "reviewer-bakeoff" / "corpus"


class _Stub(cfr.Reviewer):
    """A seat that returns a fixed body, so scoring is tested without spend."""

    def __init__(self, family: str, body: str):
        super().__init__()
        self.family = family
        self._body = body

    def _invoke_cli(self, prompt: str) -> str:  # noqa: ARG002 - fixed reply
        return self._body


def _body(verdict: str, findings: str = "") -> str:
    return (
        f"## Verdict\n{verdict}\n\n"
        "## Dimension scores\n- Correctness: 4\n\n"
        f"## Findings\n\n{findings}\n"
    )


def _finding(sev: str, location: str, text: str = "problem here") -> str:
    return f"### {sev}: {location}\nDescription: {text}\nFix: do it differently.\n"


def _one_case(cid: str) -> rb.Case:
    return next(c for c in rb.load_corpus(CORPUS) if c.cid == cid)


# --- corpus -----------------------------------------------------------------


def test_every_case_declares_its_ground_truth() -> None:
    for case in rb.load_corpus(CORPUS):
        if case.control:
            assert case.defect_file is None
        else:
            assert case.defect_file, f"{case.cid} has no defect file"
            assert case.defect_description, f"{case.cid} has no defect description"
        assert case.summary, f"{case.cid} has no summary"
        assert case.diff.strip(), f"{case.cid} rendered an empty diff"


def test_the_diff_hides_the_corpus_scaffolding() -> None:
    """A reviewer must see `src/ledger.ts`, not `after/src/ledger.ts`. A path
    that looks like a fixture invites a different standard of review."""
    for case in rb.load_corpus(CORPUS):
        assert "before/" not in case.diff, case.cid
        assert "after/" not in case.diff, case.cid


def test_every_control_summary_matches_its_diff() -> None:
    """The harness's own first defect: every control was handed the summary
    "a refactor with no behaviour change", which was false of the case that
    adds a function. All three families flagged the mismatch, and the harness
    scored the strictest one as a false positive for the author's error."""
    for case in rb.load_corpus(CORPUS):
        if case.control and case.kind == "feature":
            assert "refactor" not in case.summary.lower(), (
                f"{case.cid} adds surface; its summary must not call it a refactor"
            )


# --- scoring ----------------------------------------------------------------


def test_a_blocking_finding_on_the_defect_file_is_a_catch() -> None:
    case = _one_case("ts-value-loss")
    revs = [_Stub("claude", _body("CHANGES_REQUESTED",
                                  _finding("HIGH", "src/ledger.ts:12")))]
    res = rb.run_bakeoff(corpus_dir=CORPUS, reviewers=revs,
                         only=[case.cid], log=lambda _m: None)
    assert res["scores"]["claude"]["detected"] == 1
    assert res["scores"]["claude"]["missed"] == 0


def test_a_medium_note_about_the_defect_is_not_a_catch() -> None:
    """Only HIGH/CRITICAL stops a merge. Counting a MEDIUM would score every
    family as catching almost everything and rank nothing."""
    case = _one_case("ts-value-loss")
    revs = [_Stub("claude", _body("APPROVE", _finding("MEDIUM", "src/ledger.ts:12")))]
    res = rb.run_bakeoff(corpus_dir=CORPUS, reviewers=revs,
                         only=[case.cid], log=lambda _m: None)
    assert res["scores"]["claude"]["detected"] == 0
    assert res["scores"]["claude"]["missed"] == 1


def test_a_blocking_finding_on_an_unrelated_file_is_not_a_catch() -> None:
    case = _one_case("ts-value-loss")
    revs = [_Stub("claude", _body("CHANGES_REQUESTED",
                                  _finding("CRITICAL", "src/unrelated.ts:3")))]
    res = rb.run_bakeoff(corpus_dir=CORPUS, reviewers=revs,
                         only=[case.cid], log=lambda _m: None)
    assert res["scores"]["claude"]["detected"] == 0


def test_an_unreachable_seat_is_not_scored_as_a_miss() -> None:
    """The one that matters. claude's seat hit its model quota mid-run; if
    UNAVAILABLE counted as a miss the report would have said 21% detection for
    a family that caught all 14 once re-run on an account with quota."""
    case = _one_case("ts-value-loss")

    class _Dead(cfr.Reviewer):
        family = "claude"

        def _invoke_cli(self, prompt: str) -> str:  # noqa: ARG002
            raise cfr.ReviewerUnavailable("quota exhausted")

    res = rb.run_bakeoff(corpus_dir=CORPUS, reviewers=[_Dead()],
                         only=[case.cid], log=lambda _m: None)
    s = res["scores"]["claude"]
    assert s["unavailable"] == 1
    assert s["missed"] == 0
    assert s["detected"] == 0
    assert s["detection_rate"] == 0.0


# --- controls ---------------------------------------------------------------


def test_a_blocking_finding_on_a_control_is_a_false_positive() -> None:
    revs = [_Stub("claude", _body("CHANGES_REQUESTED",
                                  _finding("HIGH", "src/clamp.ts:1")))]
    res = rb.run_bakeoff(corpus_dir=CORPUS, reviewers=revs,
                         only=["ctl-docs-only"], log=lambda _m: None)
    assert res["scores"]["claude"]["false_positives"] == 1
    assert res["scores"]["claude"]["clean_controls"] == 0


def test_a_non_blocking_note_on_a_control_is_clean() -> None:
    """Reviewers routinely observe something on a clean diff. Only a BLOCKING
    finding is a false positive — otherwise the metric punishes commentary."""
    revs = [_Stub("claude", _body("APPROVE", _finding("LOW", "src/clamp.ts:1")))]
    res = rb.run_bakeoff(corpus_dir=CORPUS, reviewers=revs,
                         only=["ctl-docs-only"], log=lambda _m: None)
    assert res["scores"]["claude"]["false_positives"] == 0
    assert res["scores"]["claude"]["clean_controls"] == 1


# --- report -----------------------------------------------------------------


def test_the_report_shows_adjudications_that_overrule_the_score() -> None:
    """A human overruled one scored false positive; the report must carry that
    and its reason, or the table silently misreports the family."""
    result = {
        "families": ["codex"], "rows": [], "defect_cases": 0, "control_cases": 0,
        "scores": {"codex": {"detection_rate": 1.0, "detected": 1, "missed": 0,
                             "false_positive_rate": 0.5, "false_positives": 1,
                             "findings_total": 2, "seconds_total": 1.0}},
        "adjudications": [{"case": "ctl-pure-refactor", "family": "codex",
                           "scored": "false-positive",
                           "adjudicated": "true-positive",
                           "note": "sparse arrays differ."}],
    }
    md = rb.render_markdown(result)
    assert "Adjudications" in md
    assert "sparse arrays differ." in md
    assert "true-positive" in md


def test_the_recorded_result_is_readable_and_matches_the_corpus() -> None:
    """The committed result is evidence for a seating decision, so it must
    stay in step with the corpus it claims to have run."""
    results = Path(__file__).resolve().parents[1] / "docs" / "reviewer-bakeoff" / "results.json"
    if not results.exists():          # not every checkout runs the bake-off
        pytest.skip("no recorded bake-off result")
    data = json.loads(results.read_text(encoding="utf-8"))
    corpus_ids = {c.cid for c in rb.load_corpus(CORPUS)}
    assert {r["case"] for r in data["rows"]} == corpus_ids
