"""Seals for the scope-excursion classifier.

The case that motivated it, WAL-HOLD-3, is asserted directly: a hold-unit
bodies task that deleted the ledger unit's body file must come back BLOCK.
"""

from __future__ import annotations

from claude_dispatcher.scope_excursion import (
    Severity, classify, owns_path,
)

HOLD = ["apps/finance-domain/wallet/v2/hold/**"]

# Exactly what `git diff --name-status --no-renames` reported for HOLD-3.
HOLD3_DIFF = [
    ("M", "apps/finance-domain/wallet/v2/hold/hold.go"),
    ("D", "apps/finance-domain/wallet/v2/ledger/body.go"),
    ("M", "apps/finance-domain/wallet/v2/ledger/ledger.go"),
]


def test_the_hold3_diff_blocks() -> None:
    r = classify(HOLD3_DIFF, HOLD)
    assert r.severity is Severity.BLOCK
    assert [e.path for e in r.blocking] == [
        "apps/finance-domain/wallet/v2/ledger/body.go"]


def test_the_reason_names_paths_worst_first() -> None:
    """It reaches a human as the row's blocked_reason. A count ("2 files
    outside scope") is not actionable."""
    reason = classify(HOLD3_DIFF, HOLD).reason()
    assert reason.startswith("D apps/finance-domain/wallet/v2/ledger/body.go")
    assert "M apps/finance-domain/wallet/v2/ledger/ledger.go" in reason
    assert "hold/hold.go" not in reason, "owned files are not excursions"


def test_a_task_inside_its_own_unit_is_clean() -> None:
    """The common case must cost nothing: no excursions, no reviewer."""
    r = classify([("M", "apps/finance-domain/wallet/v2/hold/hold.go"),
                  ("A", "apps/finance-domain/wallet/v2/hold/hold_test.go")],
                 HOLD)
    assert r.severity is Severity.NONE
    assert r.excursions == ()


def test_a_foreign_add_is_only_a_note() -> None:
    """Operator ruling: simple necessary fixes must not be stopped. A new call
    site or import in someone else's file is the shape that ruling protects."""
    r = classify([("A", "apps/finance-domain/wallet/v2/ledger/hold_hook.go")],
                 HOLD)
    assert r.severity is Severity.NOTE


def test_a_foreign_modify_goes_to_review_not_a_block() -> None:
    r = classify([("M", "apps/finance-domain/wallet/v2/ledger/ledger.go")],
                 HOLD)
    assert r.severity is Severity.REVIEW


def test_severity_is_the_worst_excursion_not_the_last() -> None:
    """A delete after an add must still block; order must not decide."""
    a = classify([("D", "other/x.go"), ("A", "other/y.go")], HOLD)
    b = classify([("A", "other/y.go"), ("D", "other/x.go")], HOLD)
    assert a.severity is b.severity is Severity.BLOCK


def test_no_declared_ownership_judges_nothing() -> None:
    """Opt-in, per row. Every worklist predating this keeps running -- and
    "declared nothing" must not read as "owns nothing", which would block
    every task in the epic at once."""
    r = classify(HOLD3_DIFF, [])
    assert r.severity is Severity.NONE
    assert r.excursions == ()


def test_a_sibling_unit_sharing_a_name_prefix_is_foreign() -> None:
    """`hold` and `holdings` share a prefix, so a bare startswith would call
    every file under holdings/ owned -- the excursion would be invisible in
    exactly the repos that name units this way."""
    assert not owns_path(
        "apps/finance-domain/wallet/v2/holdings/holdings.go", HOLD)
    r = classify(
        [("D", "apps/finance-domain/wallet/v2/holdings/holdings.go")], HOLD)
    assert r.severity is Severity.BLOCK


def test_both_ownership_spellings_work() -> None:
    p = "apps/finance-domain/wallet/v2/hold/hold.go"
    assert owns_path(p, ["apps/finance-domain/wallet/v2/hold/**"])
    assert owns_path(p, ["apps/finance-domain/wallet/v2/hold/"])
    assert owns_path(p, ["**/hold/*.go"])
    assert not owns_path(p, ["apps/finance-domain/wallet/v2/ledger/**"])


def test_an_unknown_change_letter_is_not_dropped() -> None:
    """A letter this module does not know is a present change. Dropping it
    would let an excursion through in silence, which is the failure mode the
    module exists to remove."""
    r = classify([("T", "apps/finance-domain/wallet/v2/ledger/ledger.go")],
                 HOLD)
    assert r.severity is Severity.REVIEW
    assert len(r.excursions) == 1
