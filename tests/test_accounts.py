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


# --- blind round-robin, and a cap that expires ------------------------------
#
# Failover alone still burns one account to its ceiling before moving. Blind
# round-robin spreads a run across every account instead, and needs no usage
# figure to do it — which matters because none is readable: `claude auth
# status` says loggedIn for an account that is over its limit, and /usage is
# computed in-session and never written to disk.


def _rot(tmp_path, n=3):
    cs = [tmp_path / f"a{i}" for i in range(n)]
    for c in cs:
        c.mkdir()
    return accounts.build(cs, ambient=cs[0]), cs


def test_round_robin_hands_out_each_account_in_turn(tmp_path) -> None:
    """Consecutive tasks get different accounts, cycling back around."""
    r, cs = _rot(tmp_path)
    got = [r.next_account(now=0.0) for _ in range(6)]
    assert got == [cs[0], cs[1], cs[2], cs[0], cs[1], cs[2]], got


def test_a_capped_account_is_skipped_until_its_cooldown_expires(tmp_path) -> None:
    """A 429 pulls an account out for a few hours, not for the whole run: a
    long run outlives a rolling window, so retiring it permanently throws away
    capacity that came back."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=1000.0)
    assert cs[1] not in r.available(now=1000.0)
    assert cs[1] not in r.available(now=1000.0 + accounts.DEFAULT_COOLDOWN_SECONDS - 1)
    assert cs[1] in r.available(now=1000.0 + accounts.DEFAULT_COOLDOWN_SECONDS + 1)


def test_a_monthly_cap_outlasts_the_short_cooldown(tmp_path) -> None:
    """The refusal text decides the cooldown. A monthly spend limit cannot
    clear in hours, so re-probing it on the short cooldown spends a spawn to
    learn what the last one already established — GO-4-1's measured case."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=0.0,
                  provider_message="You've hit your monthly spend limit.")
    assert cs[1] not in r.available(now=accounts.DEFAULT_COOLDOWN_SECONDS + 1)
    assert cs[1] not in r.available(now=24 * 3600)


def test_a_rate_limit_takes_the_short_cooldown(tmp_path) -> None:
    """A rolling-window limit does clear in hours, so it must not be treated
    like a monthly cap."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=0.0,
                  provider_message="rate limit exceeded, please try again later")
    assert cs[1] in r.available(now=accounts.DEFAULT_COOLDOWN_SECONDS + 1)


def test_round_robin_never_hands_out_a_capped_account(tmp_path) -> None:
    """The load-bearing property: whatever the cursor is doing, a capped
    account is never returned while it is still capped."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=0.0)
    got = [r.next_account(now=100.0) for _ in range(8)]
    assert cs[1] not in got, got
    assert set(got) == {cs[0], cs[2]}


def test_every_account_capped_returns_none(tmp_path) -> None:
    """No account available is a real state the caller must handle, not a
    silent fallback to a capped one."""
    r, cs = _rot(tmp_path)
    for c in cs:
        r.mark_capped(c, now=0.0)
    assert r.next_account(now=100.0) is None
    assert r.available(now=100.0) == []


def test_capacity_returns_after_the_window(tmp_path) -> None:
    """All capped, then the window passes: the run continues rather than
    ending. This is the whole reason the cap expires."""
    r, cs = _rot(tmp_path)
    for c in cs:
        r.mark_capped(c, now=0.0)
    assert r.next_account(now=100.0) is None
    later = accounts.DEFAULT_COOLDOWN_SECONDS + 1
    assert r.next_account(now=later) in cs


# --- the wiring: rotation is inert unless something advances it per task -----


class _Cfg:
    def __init__(self, rotation, rotate):
        self.account_rotation = rotation
        self.rotate_accounts = rotate


def _logp(tmp_path):
    """A real log path: `_log` appends to it, as it does in a run."""
    return tmp_path / "run.log"


def test_round_robin_off_keeps_the_ambient_account(tmp_path) -> None:
    """The default must be untouched: failover-only runs stay on the account
    they started on until something refuses."""
    from claude_dispatcher import orchestrator as orch
    r, cs = _rot(tmp_path)
    cfg = _Cfg(r, rotate=False)
    got = [orch._account_for_task(cfg, "T", _logp(tmp_path)) for _ in range(3)]
    assert got == [str(cs[0])] * 3, got


def test_round_robin_on_advances_every_task(tmp_path) -> None:
    """With rotation on, consecutive TASKS land on different accounts. Without
    this per-task advance the module is inert -- failover alone only moves
    after a refusal, so one account still absorbs the whole run."""
    from claude_dispatcher import orchestrator as orch
    r, cs = _rot(tmp_path)
    cfg = _Cfg(r, rotate=True)
    got = [orch._account_for_task(cfg, "T", _logp(tmp_path)) for _ in range(4)]
    assert got == [str(cs[0]), str(cs[1]), str(cs[2]), str(cs[0])], got


def test_no_rotation_configured_means_ambient(tmp_path) -> None:
    """No rotation object at all -- neither flag passed -- returns None so the
    spawn inherits the ambient CLAUDE_CONFIG_DIR."""
    from claude_dispatcher import orchestrator as orch
    assert orch._account_for_task(_Cfg(None, rotate=True), "T", _logp(tmp_path)) is None


def test_all_capped_falls_back_to_ambient_rather_than_stalling(tmp_path) -> None:
    """Every account capped: attempt the ambient one instead of stalling. The
    caller cannot conjure quota, and the 429 path handles the refusal."""
    from claude_dispatcher import orchestrator as orch
    r, cs = _rot(tmp_path)
    for c in cs:
        r.mark_capped(c, now=1e12)
    assert orch._account_for_task(_Cfg(r, rotate=True), "T", _logp(tmp_path)) is None


# --- a monthly cap clears on the calendar, not on a stopwatch ---------------

import datetime as _dt


def _epoch(y, m, d, h=0) -> float:
    return _dt.datetime(y, m, d, h, tzinfo=_dt.timezone.utc).timestamp()


def test_a_monthly_cap_clears_at_the_start_of_next_month(tmp_path) -> None:
    """Capped on 2 Sept, eligible 1 Oct -- not 32 days later on 4 Oct."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=_epoch(2026, 9, 2),
                  provider_message="You've hit your monthly spend limit.")
    assert cs[1] not in r.available(now=_epoch(2026, 9, 30, 23))
    assert cs[1] in r.available(now=_epoch(2026, 10, 1))


def test_a_late_month_cap_does_not_wait_a_further_month(tmp_path) -> None:
    """THE discriminator against a fixed 32-day delta. Capped on 28 Sept, the
    limit clears on 1 Oct; a stopwatch would idle the account until 30 Oct and
    throw away a month of capacity."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=_epoch(2026, 9, 28),
                  provider_message="monthly spend limit reached")
    assert cs[1] in r.available(now=_epoch(2026, 10, 1))


def test_a_december_cap_rolls_into_january(tmp_path) -> None:
    """Year rollover: December's next month is January of the NEXT year."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=_epoch(2026, 12, 15),
                  provider_message="monthly limit")
    assert cs[1] not in r.available(now=_epoch(2026, 12, 31, 23))
    assert cs[1] in r.available(now=_epoch(2027, 1, 1))


def test_a_rate_limit_still_uses_the_short_stopwatch(tmp_path) -> None:
    """A rolling window is a duration, not a calendar boundary -- capping late
    in the month must not make a 3-hour limit wait for the 1st."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=_epoch(2026, 9, 28),
                  provider_message="rate limit exceeded")
    assert cs[1] in r.available(
        now=_epoch(2026, 9, 28) + accounts.DEFAULT_COOLDOWN_SECONDS + 1)


# --- three tiers, and the provider's own answer when it gives one -----------
#
# Measured limit tiers (support.claude.com, checked 2026-09-02): a ~5-hour
# session window, a weekly limit that resets at a fixed time ASSIGNED TO THE
# ACCOUNT, and monthly spend caps. Only the monthly one is a calendar boundary
# we can compute; the weekly reset day is not knowable from here.


def test_a_weekly_cap_is_probed_daily_not_held_for_a_week(tmp_path) -> None:
    """A weekly limit resets on a fixed day/time assigned to the account, which
    the dispatcher cannot know. Holding a full 7 days errs late and wastes up
    to a week; probing daily errs early, and erring early costs one spawn that
    re-caps itself."""
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=0.0, provider_message="weekly limit reached")
    assert cs[1] not in r.available(now=accounts.DEFAULT_COOLDOWN_SECONDS + 1)
    assert cs[1] not in r.available(now=23 * 3600)
    assert cs[1] in r.available(now=25 * 3600)


def test_a_stated_reset_time_beats_every_inference(tmp_path) -> None:
    """When the provider names the reset, use it. Inference exists only for
    refusals that do not say -- guessing over a stated fact is never right."""
    r, cs = _rot(tmp_path)
    now = _epoch(2026, 9, 2, 10)
    r.mark_capped(cs[1], now=now,
                  provider_message="limit reached, resets at 2026-09-02T14:00:00Z")
    assert cs[1] not in r.available(now=_epoch(2026, 9, 2, 13))
    assert cs[1] in r.available(now=_epoch(2026, 9, 2, 15))


def test_a_stated_reset_overrides_the_monthly_calendar(tmp_path) -> None:
    """A monthly-sounding refusal that also states a reset uses the STATED
    time, not the calendar boundary. The signature is a fallback, not a
    priority."""
    r, cs = _rot(tmp_path)
    now = _epoch(2026, 9, 2, 10)
    r.mark_capped(cs[1], now=now, provider_message=(
        "You've hit your monthly spend limit, resets at 2026-09-02T18:00:00Z"))
    assert cs[1] in r.available(now=_epoch(2026, 9, 2, 19))


def test_an_unparseable_reset_falls_back_to_inference(tmp_path) -> None:
    """The message format is not contractual. Anything unparseable must fall
    through to the tier inference rather than crash or return a bogus time."""
    r, cs = _rot(tmp_path)
    assert accounts.parse_reset_time("resets at half past whenever", now=0.0) is None
    r.mark_capped(cs[1], now=0.0, provider_message="resets at some point, monthly limit")
    assert cs[1] in r.available(now=accounts.next_month_start(0.0) + 1)


def test_a_stated_reset_in_the_past_is_not_trusted(tmp_path) -> None:
    """A parsed time already behind us would un-cap the account instantly and
    spin: refuse, re-parse, refuse. Treated as unparseable."""
    assert accounts.parse_reset_time(
        "resets at 2026-09-02T08:00:00Z", now=_epoch(2026, 9, 2, 10)) is None


def test_a_shaped_but_impossible_timestamp_degrades(tmp_path) -> None:
    """Reaches the parse, not just the regex. "2026-13-45T99:99Z" satisfies the
    pattern and is not a date, and this runs INSIDE 429 handling -- raising
    there would turn a recoverable quota refusal into a crashed run.
    """
    assert accounts.parse_reset_time(
        "limit reached, resets at 2026-13-45T99:99Z", now=0.0) is None
    r, cs = _rot(tmp_path)
    r.mark_capped(cs[1], now=0.0,
                  provider_message="monthly limit, resets at 2026-13-45T99:99Z")
    # Fell through to the monthly calendar rather than raising.
    assert cs[1] not in r.available(now=24 * 3600)
    assert cs[1] in r.available(now=accounts.next_month_start(0.0) + 1)
