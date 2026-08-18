"""Seals for the Claude subscription pool.

Rate limits are per ACCOUNT, so one subscription caps how much of the graph can
run at once. The pool spreads spawns across several, and rotates off one that
reports quota exhaustion instead of parking the task.

The property that makes it safe to land: an EMPTY pool must be
indistinguishable from the world before it existed. Most rows here are that
property from one angle or another.
"""

from __future__ import annotations

import json
import os
import textwrap
import time
from pathlib import Path

import pytest

from claude_dispatcher import claude_accounts as ca


def _acct(name: str, path: Path) -> ca.ClaudeAccount:
    return ca.ClaudeAccount(name=name, config_dir=path)


def _creds(dir_: Path, **oauth) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    body = {"claudeAiOauth": {"subscriptionType": "max",
                              "rateLimitTier": "default_claude_max_20x",
                              "expiresAt": int(time.time() * 1000) + 3_600_000,
                              **oauth}}
    (dir_ / ".credentials.json").write_text(json.dumps(body))
    return dir_


# --------------------------------------------------------------------------
# Rotation
# --------------------------------------------------------------------------

def test_spawns_are_spread_across_every_account(tmp_path: Path) -> None:
    """The whole point: consecutive spawns do not all bill one subscription.

    Measured under: return `self._accounts[0]` and this reddens.
    """
    pool = ca.AccountPool([_acct("a", tmp_path / "a"), _acct("b", tmp_path / "b"),
                           _acct("c", tmp_path / "c")])
    drawn = [pool.next_account().name for _ in range(6)]
    assert drawn == ["a", "b", "c", "a", "b", "c"]


def test_an_exhausted_account_is_skipped(tmp_path: Path) -> None:
    """A 429 sits an account out, so the retry lands somewhere else. A rotation
    that handed the same exhausted account straight back would spend a second
    spawn to learn what the first already proved.

    Measured under: make `penalize` a no-op and this reddens.
    """
    pool = ca.AccountPool([_acct("a", tmp_path / "a"), _acct("b", tmp_path / "b")])
    pool.penalize("a")
    assert {pool.next_account().name for _ in range(4)} == {"b"}
    assert pool.cooling() == ["a"]


def test_a_cooldown_expires(tmp_path: Path) -> None:
    """Sitting out is temporary — a long run must reclaim the account when the
    window resets, or a pool degrades to one account and never recovers.
    """
    pool = ca.AccountPool([_acct("a", tmp_path / "a")], cooldown_seconds=0.01)
    pool.penalize("a")
    assert pool.next_account() is None
    time.sleep(0.05)
    assert pool.next_account().name == "a"
    assert pool.cooling() == []


def test_every_account_exhausted_yields_None(tmp_path: Path) -> None:
    """None is "nothing left to try", which returns the caller to the existing
    park-and-retry-later. Handing back an exhausted account instead would burn a
    spawn on a certainty.

    Measured under: fall back to the first account when all are cooling and this
    reddens.
    """
    pool = ca.AccountPool([_acct("a", tmp_path / "a"), _acct("b", tmp_path / "b")])
    pool.penalize("a")
    pool.penalize("b")
    assert pool.next_account() is None


def test_rotation_is_thread_safe(tmp_path: Path) -> None:
    """The orchestrator dispatches through a ThreadPoolExecutor and the panel
    fans its seats out concurrently, so `next_account` is called from several
    threads at once. Every draw must be served, and the spread must stay even.

    Measured under: drop the lock and this goes flaky rather than red — kept
    because the failure it guards is a lost update under real concurrency.
    """
    from concurrent.futures import ThreadPoolExecutor

    pool = ca.AccountPool([_acct(n, tmp_path / n) for n in "abc"])
    with ThreadPoolExecutor(max_workers=12) as ex:
        drawn = [f.result().name for f in [ex.submit(pool.next_account)
                                           for _ in range(300)]]
    assert len(drawn) == 300
    counts = {n: drawn.count(n) for n in "abc"}
    assert all(90 <= c <= 110 for c in counts.values()), counts


# --------------------------------------------------------------------------
# The empty pool is the old world
# --------------------------------------------------------------------------

def test_an_empty_pool_selects_nothing_and_sets_no_env() -> None:
    """No accounts configured is the DEFAULT, not an error: the run uses the
    ambient login, exactly as every run did before this existed.

    Measured under: raise on an empty pool, or have `env_overlay` emit the var
    with an empty value, and this reddens — an empty CLAUDE_CONFIG_DIR is not
    "the ambient login", it is a config dir named "".
    """
    pool = ca.AccountPool()
    assert len(pool) == 0
    assert pool.next_account() is None
    assert ca.env_overlay(None) == {}


def test_env_overlay_names_the_config_dir(tmp_path: Path) -> None:
    assert ca.env_overlay(_acct("a", tmp_path)) == {
        ca.CONFIG_DIR_ENV: str(tmp_path)}
    assert ca.CONFIG_DIR_ENV == "CLAUDE_CONFIG_DIR"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def test_a_home_relative_path_is_expanded(tmp_path: Path, monkeypatch) -> None:
    """An operator writes `~/.claude-work`. Left unexpanded that is a literal
    `./~` directory — which is not an error, it is a NEW, unlogged-in account,
    so the run would fail authentication rather than say what was wrong.

    Measured under: drop `expanduser` and this reddens.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    [acct] = ca.load_accounts([{"name": "work", "config_dir": "~/.claude-work"}])
    assert acct.config_dir == (tmp_path / ".claude-work").resolve()
    assert "~" not in str(acct.config_dir)


@pytest.mark.parametrize("row, why", [
    ({"name": "a"}, "no config_dir"),
    ({"config_dir": "/tmp/x"}, "no name"),
    ({"name": "", "config_dir": "/tmp/x"}, "empty name"),
    ("not-a-mapping", "not a mapping"),
])
def test_a_malformed_entry_raises(row, why: str) -> None:
    """Fatal, not skipped. This decides which subscription is BILLED — an entry
    that quietly fell back to the ambient login would spend the wrong account's
    quota and say nothing.

    Measured under: skip malformed rows instead of raising and this reddens.
    """
    with pytest.raises(ValueError):
        ca.load_accounts([row])


def test_duplicate_names_raise(tmp_path: Path) -> None:
    """Names are the ledger key. Two accounts sharing one makes the per-account
    cost column ambiguous, and `penalize` would sit out both.
    """
    with pytest.raises(ValueError, match="duplicate"):
        ca.load_accounts([
            {"name": "same", "config_dir": str(tmp_path / "a")},
            {"name": "same", "config_dir": str(tmp_path / "b")},
        ])


def test_no_accounts_configured_is_an_empty_pool_not_an_error() -> None:
    assert ca.load_accounts(None) == []
    assert ca.load_accounts([]) == []


# --------------------------------------------------------------------------
# The machine profile
# --------------------------------------------------------------------------

def _profile(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "machine.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_accounts_are_read_from_the_manual_section(tmp_path: Path) -> None:
    """`manual:` is the user-owned half of machine.yaml — doctor preserves it
    across re-probes, so an account list survives `dispatcher doctor`.
    """
    p = _profile(tmp_path, f'''
        schema_version: 1
        agents: {{}}
        manual:
          claude_accounts:
            - name: personal
              config_dir: {tmp_path}/p
            - name: work
              config_dir: {tmp_path}/w
    ''')
    got = ca.load_from_machine_profile(p)
    assert [a.name for a in got] == ["personal", "work"]
    assert got[0].config_dir == (tmp_path / "p").resolve()


def test_a_profile_without_accounts_is_an_empty_pool(tmp_path: Path) -> None:
    assert ca.load_from_machine_profile(
        _profile(tmp_path, "schema_version: 1\nmanual:\n")) == []
    assert ca.load_from_machine_profile(
        _profile(tmp_path, "schema_version: 1\n")) == []


def test_a_missing_profile_is_an_empty_pool(tmp_path: Path) -> None:
    """Running without a machine profile is normal. Measured under: raise on a
    missing file and every run on a fresh machine dies at startup.
    """
    assert ca.load_from_machine_profile(tmp_path / "nope.yaml") == []


def test_a_MALFORMED_account_in_a_readable_profile_still_raises(
    tmp_path: Path,
) -> None:
    """The one thing a missing profile's tolerance must not buy: a profile that
    HAS the key and holds nonsense is an operator error, not an empty pool.

    Measured under: wrap the `load_accounts` call in the same try/except that
    swallows an unreadable profile and this reddens.
    """
    p = _profile(tmp_path, '''
        manual:
          claude_accounts:
            - name: broken
    ''')
    with pytest.raises(ValueError):
        ca.load_from_machine_profile(p)


# --------------------------------------------------------------------------
# Readiness, without spending anything
# --------------------------------------------------------------------------

def test_probe_reports_a_logged_in_account(tmp_path: Path) -> None:
    """Read from the non-secret fields beside the token, so `doctor` can report
    readiness without an API call.
    """
    h = ca.probe(_acct("a", _creds(tmp_path / "a")))
    assert h.logged_in is True
    assert h.subscription == "max" and h.tier == "default_claude_max_20x"
    assert h.expired is False


def test_probe_reports_a_never_logged_in_dir(tmp_path: Path) -> None:
    """The likely operator mistake: a config dir that exists because a run
    created it, with no login in it. Measured under: report `logged_in` from the
    directory's existence and this reddens.
    """
    (tmp_path / "a").mkdir()
    h = ca.probe(_acct("a", tmp_path / "a"))
    assert h.logged_in is False and "no credentials" in h.detail


def test_probe_rejects_credentials_without_a_subscription_login(
    tmp_path: Path,
) -> None:
    """A credentials file holding only MCP OAuth entries is not a Claude login —
    the shape an empty CLAUDE_CONFIG_DIR leaves behind once a tool authenticates.
    """
    d = tmp_path / "a"
    d.mkdir()
    (d / ".credentials.json").write_text(json.dumps({"mcpOAuth": {"x": {}}}))
    h = ca.probe(_acct("a", d))
    assert h.logged_in is False and "no subscription login" in h.detail


def test_probe_survives_unreadable_credentials(tmp_path: Path) -> None:
    d = tmp_path / "a"
    d.mkdir()
    (d / ".credentials.json").write_text("{not json")
    h = ca.probe(_acct("a", d))
    assert h.logged_in is False and "unreadable" in h.detail


def test_an_expired_token_is_reported_but_an_unknown_one_is_not(
    tmp_path: Path,
) -> None:
    """`expired` must mean "known to have passed", not "not known to be valid".
    An account with no expiry field reading as expired would send an operator to
    re-login an account that is fine.

    Measured under: treat a missing expiry as expired and this reddens.
    """
    past = ca.probe(_acct("a", _creds(tmp_path / "a", expiresAt=1)))
    assert past.expired is True
    unknown = ca.probe(_acct("b", _creds(tmp_path / "b", expiresAt="soon")))
    assert unknown.expires_at_ms is None and unknown.expired is False


def test_probe_never_returns_a_token(tmp_path: Path) -> None:
    """A health report is printed and journaled. Measured under: carry the token
    onto AccountHealth and this reddens.
    """
    h = ca.probe(_acct("a", _creds(tmp_path / "a", accessToken="sk-SECRET-VALUE",
                                   refreshToken="rt-SECRET")))
    assert "SECRET" not in repr(h)
