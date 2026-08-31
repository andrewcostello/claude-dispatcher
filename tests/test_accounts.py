"""Seals for quota failover.

Every `claude` spawn inherits the ambient `CLAUDE_CONFIG_DIR`, so one
subscription is the whole ceiling for a run. On 2026-08-30 that ended a dogfood
run mid-flight: GO-4-1 came back `api_error_status: 429`, "You've hit your
monthly spend limit", was classified correctly as INFRASTRUCTURE /
retryable_after_reset, and blocked — while four other authenticated accounts
sat unused.

The load-bearing rule is the one that does NOT rotate: an auth failure means
the account is misconfigured, and trying the next one turns a single clear
error into one per account, each costing a spawn.
"""

from __future__ import annotations

from pathlib import Path

from claude_dispatcher import accounts, spawn


# --- what may and may not rotate ---------------------------------------------


def test_a_quota_refusal_rotates() -> None:
    assert accounts.should_rotate(429) is True


def test_an_auth_failure_does_not_rotate() -> None:
    """The safety property. A 401 is a broken token, not a spent account, and
    rotating on it spreads one failure across every account the operator has."""
    assert accounts.should_rotate(401) is False
    assert accounts.should_rotate(403) is False


def test_an_overloaded_server_does_not_rotate() -> None:
    """A 529 is the provider, not the account — `spawn_failure` already retries
    it on the same rung, and changing account would not help."""
    assert accounts.should_rotate(529) is False


def test_no_status_does_not_rotate() -> None:
    assert accounts.should_rotate(None) is False


# --- the rotation itself ------------------------------------------------------


def test_the_ambient_account_leads(tmp_path) -> None:
    """A run must behave exactly as before until something goes wrong; failover
    is a recovery path, not a scheduler."""
    a, b, c = (tmp_path / n for n in ("a", "b", "c"))
    rot = accounts.build([a, b, c], ambient=b)
    assert rot.candidates[0] == b
    assert rot.active == b


def test_advance_skips_the_spent_account(tmp_path) -> None:
    a, b = (tmp_path / n for n in ("a", "b"))
    rot = accounts.build([a, b], ambient=a)
    rot.mark_exhausted(a)
    assert rot.advance() == b
    assert rot.active == b


def test_advance_returns_none_when_every_account_is_spent(tmp_path) -> None:
    """The run must stop rather than loop: the caller blocks the task here."""
    a, b = (tmp_path / n for n in ("a", "b"))
    rot = accounts.build([a, b], ambient=a)
    rot.mark_exhausted(a)
    rot.mark_exhausted(b)
    assert rot.advance() is None
    assert rot.remaining() == []


def test_an_exhausted_account_stays_exhausted(tmp_path) -> None:
    """A quota resets on the provider's clock, not ours. Re-probing per task
    would spend a spawn to learn what the last one already established."""
    a, b = (tmp_path / n for n in ("a", "b"))
    rot = accounts.build([a, b], ambient=a)
    rot.mark_exhausted(a)
    rot.advance()
    assert a in rot.exhausted
    assert rot.remaining() == [b]


def test_rotation_is_disabled_with_nowhere_to_go(tmp_path) -> None:
    """One account is not a pool. Arming failover here would add a branch that
    can only ever fail."""
    assert accounts.build([tmp_path / "a"], ambient=tmp_path / "a").enabled is False
    assert accounts.build([]).enabled is False


def test_two_accounts_enable_it(tmp_path) -> None:
    a, b = (tmp_path / n for n in ("a", "b"))
    assert accounts.build([a, b], ambient=a).enabled is True


def test_marking_the_ambient_none_account_is_harmless(tmp_path) -> None:
    """`active` is None when the run uses the inherited account and it is not
    among the discovered candidates. Recording that must not crash or poison
    the set."""
    rot = accounts.build([tmp_path / "a", tmp_path / "b"])
    rot.mark_exhausted(None)
    assert rot.exhausted == set()


# --- the account reaches the spawn -------------------------------------------


def test_build_env_sets_the_config_dir_when_given_one(tmp_path) -> None:
    env = spawn.build_env(
        base_env={}, task_key="T-1", summary_path=tmp_path / "s.md",
        run_id="r", max_iterations=8, financial_paths="**",
        claude_config_dir="/home/x/.claude-other",
    )
    assert env["CLAUDE_CONFIG_DIR"] == "/home/x/.claude-other"


def test_build_env_leaves_the_ambient_account_alone_by_default(tmp_path) -> None:
    """The normal case: no failover, no override, the child inherits whatever
    the operator's shell had."""
    env = spawn.build_env(
        base_env={"CLAUDE_CONFIG_DIR": "/home/x/.claude"}, task_key="T-1",
        summary_path=tmp_path / "s.md", run_id="r", max_iterations=8,
        financial_paths="**",
    )
    assert env["CLAUDE_CONFIG_DIR"] == "/home/x/.claude"


def test_the_bot_accounts_are_not_candidates(tmp_path) -> None:
    """Failover must never reach for the shared pr@ identity a cron job spends;
    discovery excludes it, and this row ties that to rotation."""
    from claude_dispatcher import first_run

    for name in (".claude", ".claude-work", ".claude-prreview"):
        d = tmp_path / name
        d.mkdir()
        (d / ".credentials.json").write_text("{}", encoding="utf-8")

    rot = accounts.build(first_run.discover_claude_accounts(tmp_path))
    assert [c.name for c in rot.candidates] == [".claude", ".claude-work"]
