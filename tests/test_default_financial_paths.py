"""Guard for `cli.DEFAULT_FINANCIAL_PATHS`.

`FINANCIAL_PATHS` is the human PR gate's second, path-based check — the
backstop for when the Tasker's tier judgment misses. A typo here is silent:
the globs simply match nothing and the gate stops firing, exactly the failure
that shipped for every money path outside `wallet/` until 2026-08-01 (GO-0).

These are cheap structural checks, not existence checks — the dispatcher does
not have evenplay-mono on disk. They catch the shape of the bug that actually
happened: a plausible-looking directory that is not there.
"""

from __future__ import annotations

from claude_dispatcher.cli import DEFAULT_FINANCIAL_PATHS


# First two segments of every path in the default list must name a real place
# in evenplay-mono. Source of truth: the `financial: true` rules in that repo's
# .agent/risk-paths.json.
KNOWN_ROOTS = {
    "apps/finance-domain",
    "apps/platform-domain",
    "apps/game-domain",
    "libs/go",
}

# The three directories the old default named. None of them exist; keeping them
# out by name means a revert cannot land quietly.
RETIRED_DEAD_PREFIXES = (
    "apps/finance-domain/settlement",
    "apps/finance-domain/recovery",
    "apps/finance-domain/payout",
)


def _entries() -> list[str]:
    return DEFAULT_FINANCIAL_PATHS.split(",")


def test_default_list_is_non_empty() -> None:
    entries = _entries()
    assert entries, "the human PR gate's path backstop must not be empty"
    assert all(e.strip() for e in entries), "no blank entries"


def test_every_entry_has_a_plausible_two_segment_prefix() -> None:
    for entry in _entries():
        segments = entry.split("/")
        assert len(segments) >= 3, (
            f"{entry!r} is too shallow to be a specific money path"
        )
        assert "" not in segments, f"{entry!r} has an empty path segment"
        root = "/".join(segments[:2])
        assert root in KNOWN_ROOTS, (
            f"{entry!r} starts with {root!r}, which is not a known "
            f"evenplay-mono location (expected one of {sorted(KNOWN_ROOTS)}). "
            "If this is intentional, add it here and to the target repo's "
            ".agent/risk-paths.json."
        )


def test_entries_are_normalised_globs() -> None:
    for entry in _entries():
        assert entry == entry.strip(), f"{entry!r} has surrounding whitespace"
        assert not entry.startswith("/"), f"{entry!r} must be repo-relative"
        assert "\\" not in entry, f"{entry!r} must use forward slashes"
        assert any(c in entry for c in "*?"), (
            f"{entry!r} has no glob wildcard — it would only ever match one "
            "exact file"
        )


def test_dead_finance_domain_directories_do_not_come_back() -> None:
    for entry in _entries():
        for dead in RETIRED_DEAD_PREFIXES:
            assert not entry.startswith(dead), (
                f"{entry!r} names {dead!r}, which does not exist in "
                "evenplay-mono — this glob would match nothing and the gate "
                "would be dead for that path (see GO-0)"
            )


def test_the_money_core_and_the_bay_session_paths_are_both_covered() -> None:
    """The 2026-08-01 bug was covering wallet/ and nothing else."""
    joined = DEFAULT_FINANCIAL_PATHS
    assert "apps/finance-domain/wallet/**" in joined
    assert "apps/finance-domain/paygate/**" in joined
    # settlement / refund / dispute reversal live under bay-session, not
    # finance-domain — that mismatch is what made the old default dead.
    assert "*settlement*" in joined
    assert "*refund*" in joined
    assert "admin_bet_dispute_reverse*" in joined
    assert "payout*" in joined


# --------------------------------------------------------------------------- #
# Parity with the source of truth
# --------------------------------------------------------------------------- #
#
# The checks above are structural: they catch a malformed or implausible entry,
# and they catch the three dead directories by name. They do NOT catch the
# failure that actually matters — the list silently falling behind the rule
# table it copies.
#
# That is not hypothetical. The panel on PR #71 flagged it, and it had already
# happened in the other direction: claude-workflow's pr-raise.md fallback
# omitted eight financial rules within a day of being written, because the rule
# table gained entries during a 98-PR validation sweep and its copy did not.
#
# So this asserts the real invariant: DEFAULT_FINANCIAL_PATHS equals the
# `financial: true` paths in the target repo's .agent/risk-paths.json. It skips
# when that checkout is absent (CI), making it a developer-machine guard rather
# than a gate — but a guard that tests the right thing beats a gate that tests
# the wrong one.

import json
import os
from pathlib import Path

import pytest


def _live_rule_table() -> Path | None:
    """The target repo's rule table, if this machine has that checkout."""
    override = os.environ.get("RISK_PATHS_CONFIG")
    candidates = [Path(override)] if override else []
    candidates.append(
        Path(os.environ.get("HOME", "")) / "Project/evenplay-mono/.agent/risk-paths.json"
    )
    return next((c for c in candidates if c.is_file()), None)


def _financial_paths_from(table: Path) -> list[str]:
    out: list[str] = []
    for rule in json.loads(table.read_text())["rules"]:
        if rule.get("financial"):
            for path in rule["paths"]:
                if path not in out:
                    out.append(path)
    return out


def test_default_matches_the_rule_table_exactly() -> None:
    table = _live_rule_table()
    if table is None:
        pytest.skip("evenplay-mono checkout not on this machine")

    expected = set(_financial_paths_from(table))
    actual = set(_entries())

    missing = expected - actual
    extra = actual - expected
    assert not missing, (
        f"{len(missing)} financial rule(s) in {table} are absent from "
        f"DEFAULT_FINANCIAL_PATHS, so the human PR gate's backstop is dead for "
        f"them: {sorted(missing)}\n"
        "Re-derive rather than hand-edit:\n"
        "  jq -r '.rules[] | select(.financial) | .paths[]' .agent/risk-paths.json"
    )
    assert not extra, (
        f"DEFAULT_FINANCIAL_PATHS names {len(extra)} path(s) with no matching "
        f"financial rule in {table}: {sorted(extra)}"
    )


def test_the_structural_checks_would_reject_the_old_broken_default() -> None:
    """The regression test for the tests themselves.

    Three of the structural checks above pass against the 2026-07 default that
    was dead for every money path outside wallet/ — the dead-prefix check is
    the only one that catches it. Assert that it does, so a future refactor
    cannot quietly drop the one check doing the work.
    """
    old_default = [
        "apps/finance-domain/wallet/**",
        "apps/finance-domain/settlement/**",
        "apps/finance-domain/recovery/**",
        "apps/finance-domain/payout/**",
    ]
    offenders = [
        entry
        for entry in old_default
        for dead in RETIRED_DEAD_PREFIXES
        if entry.startswith(dead)
    ]
    assert len(offenders) == 3, (
        "the dead-prefix guard no longer rejects the old default — the only "
        "structural check that catches this bug has been weakened"
    )
