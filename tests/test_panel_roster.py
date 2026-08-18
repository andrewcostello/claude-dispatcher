"""Seals for the seated panel families.

Gemini contributed ZERO findings across every recorded run — claude 115,
codex 127, grok 129, gemini 0 — while reporting UNAVAILABLE in 0.3-0.6s on every
panel. D-56 noticed the symptom and D-67 recorded a panel deciding on two seats
because of it; neither diagnosed it.

Cause, measured by running the seat's own invocation:

    $ agy --print "" --print-timeout 60s     (prompt on stdin)
    Error: Error: empty prompt. Usage: agy --print "your prompt here"

The empty positional is deliberate (see GeminiReviewer) and exists to keep a
large diff off argv and away from E2BIG. agy dropped support for an empty
prompt, so the seat died with nothing surfacing it.
"""

from __future__ import annotations

from claude_dispatcher import cross_family_reviewer as cfr


def test_gemini_is_not_seated() -> None:
    """A seat that contributes nothing is worse than an honestly absent one: the
    panel was CONFIGURED as four families and DECIDING as three, and the row
    recorded the same verdict either way.

    Measured under: re-add GeminiReviewer to `default_reviewers` and this reddens.
    Restoring it needs the prompt passed as `--print`'s argument (which
    reintroduces the ~128 KB argv cap the empty positional avoided) or
    `--input-format stream-json` (which changes the verdict parser).
    """
    assert [r.family for r in cfr.default_reviewers()] == ["claude", "codex", "grok"]


def test_the_class_is_kept_so_it_can_be_restored() -> None:
    """Unseated, not deleted. The diagnosis and the two candidate fixes are
    recorded against it, and deleting the class would take them with it.
    """
    assert hasattr(cfr, "GeminiReviewer")
    assert cfr.GeminiReviewer.family == "gemini"


def test_three_families_still_satisfy_the_corroboration_gate() -> None:
    """`aggregate` blocks on CRITICAL or on >= 2 families raising a blocking
    finding, so unseating one must not let a single seat solo-block a HIGH.

    Measured under: drop to two seats and one family's HIGH becomes half the
    panel, which is the property this row protects.
    """
    families = {r.family for r in cfr.default_reviewers()}
    assert len(families) >= 3, families
