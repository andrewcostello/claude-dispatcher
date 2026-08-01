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
