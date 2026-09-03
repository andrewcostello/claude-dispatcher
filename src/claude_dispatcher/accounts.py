"""Fail a run over to another account when one hits its quota.

Every `claude` spawn inherits the ambient `CLAUDE_CONFIG_DIR`, so one
subscription is the whole ceiling for a run. On 2026-08-30 that ceiling ended a
dogfood run mid-flight: GO-4-1's spawn came back

    api_error_status: 429 ... "You've hit your monthly spend limit."

classified correctly as INFRASTRUCTURE / retryable_after_reset, and the task
blocked. Every remaining task would have blocked the same way, against the same
dead account, while four other authenticated accounts sat unused.

This is REACTIVE FAILOVER, deliberately not weighted rotation:

  * It moves only on a QUOTA refusal (429). An auth failure (401/403) means the
    account is misconfigured, and rotating through the others on a bad token
    spreads one failure across every account instead of surfacing it.
  * It does not balance load. Choosing "the least used" account needs a usage
    figure no local surface exposes — `claude auth status` reports `loggedIn`
    for an account that is over its limit, and the `/usage` percentages are
    computed inside an interactive session and never written to disk. A
    denominator nobody can read is not a denominator to schedule on.
  * A capped account is pulled out for a COOLDOWN, not for the run. The
    original reasoning here -- that re-probing spends a spawn to learn what the
    last one established -- held for short runs and stops holding for long
    ones: a 73-task run outlives a rolling window, so retiring an account
    permanently throws away capacity that came back. Re-probing costs at most
    one spawn per account per window, and the refusal text keeps even that
    off the case where it cannot help.

BLIND ROUND-ROBIN sits on top of the same structure. Each task takes the next
account in turn, which spreads a run across every subscription instead of
burning one to its ceiling first. It is blind deliberately -- weighting needs a
usage figure nothing exposes, and a cursor needs none.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

#: `spawn_failure` already separates these, and the separation is the whole
#: safety property of this module: only the first list may rotate.
QUOTA_STATUSES = frozenset({429})
AUTH_STATUSES = frozenset({401, 403})

#: How long a capped account sits out. Rolling-window limits clear in hours.
DEFAULT_COOLDOWN_SECONDS = 3 * 3600

#: Measured tiers (support.claude.com, checked 2026-09-02): a ~5-hour session
#: window, a weekly limit resetting at a fixed time ASSIGNED TO THE ACCOUNT,
#: and monthly spend caps. Only the monthly one is a boundary computable from
#: here -- the weekly reset day is account-specific and not exposed.
_MONTHLY_SIGNATURES = ("monthly spend limit", "monthly limit", "spend limit")
_WEEKLY_SIGNATURES = ("weekly limit", "weekly usage limit", "weekly cap")

#: A weekly cap is re-probed daily rather than held for seven days. The reset
#: day is fixed but unknowable here, so any fixed hold is a guess; a daily
#: probe bounds the waste at a day and costs at most seven spawns to find the
#: reset, where a 7-day hold can idle an account that came back on day one.
WEEKLY_PROBE_SECONDS = 24 * 3600

#: "limit reached, resets at <time>" -- the provider sometimes states the
#: reset. The format is NOT contractual, so parsing fails closed to inference.
_RESET_ISO_RE = re.compile(
    r"resets?\s+(?:at|on)\s+(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?\s*Z?)",
    re.IGNORECASE,
)
_RESET_CLOCK_RE = re.compile(
    r"resets?\s+(?:at|on)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)


def is_monthly(provider_message: str = "") -> bool:
    """Whether the refusal names a monthly cap rather than a shorter window."""
    haystack = (provider_message or "").lower()
    return any(sig in haystack for sig in _MONTHLY_SIGNATURES)


def is_weekly(provider_message: str = "") -> bool:
    haystack = (provider_message or "").lower()
    return any(sig in haystack for sig in _WEEKLY_SIGNATURES)


def parse_reset_time(provider_message: str, *, now: float) -> float | None:
    """The reset the provider STATED, or None when it stated none.

    A stated reset beats every inference below it: inference exists for
    refusals that do not say, and guessing over a stated fact is never right.

    Fails closed. An unrecognised format, or a time already behind `now`,
    returns None -- a past reset would un-cap the account immediately and spin
    refuse/re-parse/refuse. The message format is not part of any contract, so
    this must degrade rather than break when it changes.
    """
    if not provider_message:
        return None
    m = _RESET_ISO_RE.search(provider_message)
    if m:
        raw = m.group(1).strip().replace(" ", "T").rstrip("Z")
        try:
            parsed = dt.datetime.fromisoformat(raw).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None
        return parsed.timestamp() if parsed.timestamp() > now else None
    m = _RESET_CLOCK_RE.search(provider_message)
    if m:
        hour, minute, meridiem = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if meridiem:
            meridiem = meridiem.lower()
            if hour == 12:
                hour = 0 if meridiem == "am" else 12
            elif meridiem == "pm":
                hour += 12
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        base = dt.datetime.fromtimestamp(now, tz=dt.timezone.utc)
        target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target.timestamp() <= now:
            target += dt.timedelta(days=1)
        return target.timestamp()
    return None


def next_month_start(now: float) -> float:
    """The start of the calendar month after `now`, in UTC.

    A monthly allowance resets on the calendar, not on a stopwatch started when
    it ran out. A fixed delta gets this wrong in the expensive direction: an
    account capped on the 28th would idle until the 30th of the NEXT month for
    a limit that cleared on the 1st.
    """
    d = dt.datetime.fromtimestamp(now, tz=dt.timezone.utc)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return dt.datetime(year, month, 1, tzinfo=dt.timezone.utc).timestamp()


def eligible_at(now: float, provider_message: str = "") -> float:
    """When a capped account may be tried again.

    A rolling-window limit is a DURATION from the refusal; a monthly cap is a
    calendar BOUNDARY, so the two cannot share a unit.

    Unrecognised text takes the short duration: inferring "monthly" from
    silence would idle an account for weeks over a limit that clears in hours.
    Erring early is the cheap direction -- a premature retry costs one spawn
    and re-caps itself, while a late one wastes real capacity.
    """
    stated = parse_reset_time(provider_message, now=now)
    if stated is not None:
        return stated
    if is_monthly(provider_message):
        return next_month_start(now)
    if is_weekly(provider_message):
        return now + WEEKLY_PROBE_SECONDS
    return now + DEFAULT_COOLDOWN_SECONDS


@dataclass
class AccountRotation:
    """The accounts a run may use, and which are spent.

    `active` is None when the run uses the ambient `CLAUDE_CONFIG_DIR`, which is
    the normal case and the one that must keep working unchanged.
    """

    candidates: list[Path] = field(default_factory=list)
    exhausted: set[Path] = field(default_factory=set)
    active: Path | None = None
    #: account -> the time it becomes eligible again.
    cooling: dict[Path, float] = field(default_factory=dict)
    #: Round-robin position. Advances per task, never per retry.
    cursor: int = 0

    @property
    def enabled(self) -> bool:
        """Rotation is only meaningful with somewhere to rotate TO."""
        return len(self.candidates) > 1

    def remaining(self) -> list[Path]:
        return [c for c in self.candidates if c not in self.exhausted]

    def mark_exhausted(self, account: Path | None) -> None:
        """Record an account as spent for the rest of the run.

        A None `active` means the ambient account was in use; it is recorded
        under its resolved path so the same directory is not selected next.
        """
        if account is not None:
            self.exhausted.add(account)

    def advance(self) -> Path | None:
        """The next account not yet spent, or None when all are.

        Sets `active`, so the caller's next `build_env` picks it up.
        """
        for candidate in self.candidates:
            if candidate not in self.exhausted:
                self.active = candidate
                return candidate
        self.active = None
        return None

    def available(self, *, now: float) -> list[Path]:
        """Candidates not capped at `now`, in rotation order."""
        return [
            c for c in self.candidates
            if c not in self.exhausted and self.cooling.get(c, 0.0) <= now
        ]

    def mark_capped(
        self, account: Path | None, *, now: float, provider_message: str = "",
    ) -> None:
        """Pull `account` out until its cooldown expires.

        Unlike `mark_exhausted` this is reversible, which is the point: the
        account is expected back.
        """
        if account is None:
            return
        self.cooling[account] = eligible_at(now, provider_message)

    def next_account(self, *, now: float) -> Path | None:
        """The next uncapped account in turn, or None when all are capped.

        Advances the cursor over `candidates` so the sequence is stable, and
        skips capped accounts rather than stalling on them.
        """
        n = len(self.candidates)
        for step in range(n):
            candidate = self.candidates[(self.cursor + step) % n]
            if candidate in self.exhausted or self.cooling.get(candidate, 0.0) > now:
                continue
            self.cursor = (self.cursor + step + 1) % n
            self.active = candidate
            return candidate
        self.active = None
        return None


def should_rotate(api_error_status: int | None) -> bool:
    """True only for a quota refusal.

    An auth failure must NOT rotate: the account is misconfigured, and trying
    the next one turns one clear error into several identical ones and burns a
    spawn per account doing it.
    """
    return api_error_status in QUOTA_STATUSES


def build(candidates: list[Path], *, ambient: Path | None = None) -> AccountRotation:
    """A rotation over `candidates`, starting from the ambient account.

    The ambient account leads when it is among the candidates, so a run behaves
    exactly as before until something goes wrong. Failover is a recovery path,
    not a scheduler.
    """
    ordered = list(candidates)
    if ambient is not None and ambient in ordered:
        ordered.remove(ambient)
        ordered.insert(0, ambient)
    return AccountRotation(candidates=ordered, active=ambient)
