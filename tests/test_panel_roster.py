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


# ------------------------------------------------ the per-seat timeout -------

def test_the_seat_timeout_is_set_from_the_measured_distribution() -> None:
    """600s was killing the strongest seat one run in seven.

    Measured over 172 recorded seat runs: claude 6 timeouts of 43 (14%), and the
    longest seat that ever COMPLETED finished at 563s — 37 seconds of headroom on
    a censored distribution, because anything slower was killed and never
    recorded. D-67's "the strongest panel seat timed out, and two seats decided
    alone" is that number showing up as a verdict.

    Measured under: drop it back to 600 and this reddens.
    """
    assert cfr.DEFAULT_REVIEWER_TIMEOUT_SECONDS >= 1800


def test_the_timeout_default_lives_in_exactly_one_place() -> None:
    """The CLI used to carry its own literal 600. Two copies of a bound is how
    one gets raised and the other does not — the same defect the runs_dir literal
    had in five subcommands.

    Measured under: re-add a literal default to the argparse flag and this
    reddens.
    """
    from pathlib import Path
    from claude_dispatcher import cli
    src = Path(cli.__file__).read_text()
    at = src.index('"--cross-family-panel-timeout"')
    block = src[at:at + 300]
    assert "cfr_mod.DEFAULT_REVIEWER_TIMEOUT_SECONDS" in block
    assert "default=600" not in block


def test_every_seat_gets_the_configured_timeout() -> None:
    revs = cfr.default_reviewers(timeout_seconds=1234)
    assert all(r.timeout_seconds == 1234 for r in revs)
