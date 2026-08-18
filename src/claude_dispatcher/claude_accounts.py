"""A pool of Claude subscriptions, one `CLAUDE_CONFIG_DIR` each.

Rate limits are per ACCOUNT, so one subscription caps how much of the task graph
can run at once. An operator holding several can spread the load by giving each
spawn a different config dir.

Isolation is the CLI's, not ours. Measured against Claude Code 2.1.233: an empty
`CLAUDE_CONFIG_DIR` answers "Not logged in - Please run /login" and builds its
own config tree there, rather than falling back to `~/.claude`.

Accounts are SHARED, not leased. One implementer plus four panel seats already
share `~/.claude` concurrently on every run today, so exclusivity would cost
throughput and buy nothing.

NEVER reads a token. Readiness comes from the non-secret fields stored beside
one — `subscriptionType`, `rateLimitTier`, `expiresAt` — so an operator can be
told a login is stale without spending anything to find out.

Not on the floor, deliberately: this decides which subscription pays, not
whether a branch passes, so a task branch that edited it could not change how it
is itself judged. That is the property FLOOR_GLOBS protects.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

#: How long an account sits out after it reports quota exhaustion. Long enough
#: that a rotation is not immediately handed back the account that just failed,
#: short enough that a long run reclaims it.
DEFAULT_COOLDOWN_SECONDS = 15 * 60

#: The env var the CLI reads. One name, used everywhere.
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"


@dataclass(frozen=True)
class ClaudeAccount:
    """One subscription: a label for the ledger and the config dir that is it."""

    name: str
    config_dir: Path

    @property
    def credentials_path(self) -> Path:
        return self.config_dir / ".credentials.json"


@dataclass(frozen=True)
class AccountHealth:
    """What `doctor` can say about an account without spending anything."""

    name: str
    config_dir: str
    logged_in: bool
    subscription: str | None = None
    tier: str | None = None
    expires_at_ms: int | None = None
    detail: str = ""

    @property
    def expired(self) -> bool:
        """True only when an expiry is known AND has passed. Unknown is not
        expired — a missing field must not read as a dead account."""
        return (self.expires_at_ms is not None
                and self.expires_at_ms <= time.time() * 1000)


def probe(account: ClaudeAccount) -> AccountHealth:
    """Read an account's non-secret credential metadata.

    A file that exists but holds no `claudeAiOauth` block is a config dir that
    was created by a run and never logged into — the shape an empty
    `CLAUDE_CONFIG_DIR` leaves behind, and a likely operator mistake.
    """
    base = AccountHealth(name=account.name, config_dir=str(account.config_dir),
                         logged_in=False)
    path = account.credentials_path
    if not path.exists():
        return _with(base, detail=f"no credentials at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _with(base, detail=f"credentials unreadable: {exc}")
    oauth = raw.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return _with(base, detail="credentials hold no subscription login")
    return AccountHealth(
        name=account.name,
        config_dir=str(account.config_dir),
        logged_in=True,
        subscription=oauth.get("subscriptionType"),
        tier=oauth.get("rateLimitTier"),
        expires_at_ms=oauth.get("expiresAt")
        if isinstance(oauth.get("expiresAt"), int) else None,
    )


def _with(h: AccountHealth, *, detail: str) -> AccountHealth:
    return AccountHealth(name=h.name, config_dir=h.config_dir, logged_in=False,
                         detail=detail)


class AccountPool:
    """Round-robin over the configured accounts, skipping any that are cooling.

    Thread-safe: the orchestrator dispatches through a ThreadPoolExecutor and
    the panel fans its seats out concurrently, so `next_account` is called from
    several threads at once.

    An EMPTY pool is the normal configuration, not an error — it means "use the
    ambient login", which is what every run did before this existed. Callers get
    None and set no env var.
    """

    def __init__(
        self,
        accounts: Sequence[ClaudeAccount] = (),
        *,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._accounts = list(accounts)
        self._cooldown = cooldown_seconds
        self._cooling: dict[str, float] = {}
        self._cursor = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._accounts)

    @property
    def names(self) -> list[str]:
        return [a.name for a in self._accounts]

    def next_account(self) -> ClaudeAccount | None:
        """The next account not cooling off, or None.

        None means "no account is available": either the pool is empty, or every
        account has reported quota exhaustion. Both leave the caller on its
        existing behaviour — the ambient login, and the park-and-retry-later the
        quota classifier already implements.
        """
        with self._lock:
            if not self._accounts:
                return None
            now = time.monotonic()
            n = len(self._accounts)
            for offset in range(n):
                acct = self._accounts[(self._cursor + offset) % n]
                until = self._cooling.get(acct.name)
                if until is not None and until > now:
                    continue
                self._cursor = (self._cursor + offset + 1) % n
                return acct
            return None

    def penalize(self, name: str, *, seconds: float | None = None) -> None:
        """Sit `name` out. Called when a spawn reports quota exhaustion, so the
        retry does not hand the same exhausted account straight back."""
        with self._lock:
            self._cooling[name] = time.monotonic() + (
                self._cooldown if seconds is None else seconds)

    def cooling(self) -> list[str]:
        with self._lock:
            now = time.monotonic()
            return sorted(k for k, until in self._cooling.items() if until > now)

    def health(self) -> list[AccountHealth]:
        return [probe(a) for a in self._accounts]


def env_overlay(account: ClaudeAccount | None) -> dict[str, str]:
    """What to overlay on a spawn's environment. Empty for None, so a caller can
    apply it unconditionally."""
    return {} if account is None else {CONFIG_DIR_ENV: str(account.config_dir)}


def load_accounts(rows: Iterable[object] | None) -> list[ClaudeAccount]:
    """Build accounts from `.dispatcher.yaml`'s `claude_accounts:` rows.

    `~` is expanded — an operator writes `~/.claude-work`, and a config dir that
    silently resolved to a literal `./~` directory would be a new, unlogged-in
    account rather than an error.

    A malformed row raises. This decides which subscription is billed, so a typo
    that quietly fell back to the ambient login would spend the wrong account's
    quota without saying so.
    """
    out: list[ClaudeAccount] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            raise ValueError(f"claude_accounts entry must be a mapping, got {row!r}")
        name = str(row.get("name") or "").strip()
        raw_dir = str(row.get("config_dir") or "").strip()
        if not name or not raw_dir:
            raise ValueError(
                f"claude_accounts entry needs `name` and `config_dir`, got {row!r}")
        if name in seen:
            raise ValueError(f"duplicate claude_accounts name {name!r}")
        seen.add(name)
        out.append(ClaudeAccount(
            name=name,
            config_dir=Path(os.path.expanduser(raw_dir)).resolve(),
        ))
    return out


#: Where an operator writes the pool. `manual:` is the user-owned section of the
#: machine profile — doctor preserves it across re-probes, and the file is
#: machine-scoped rather than committed, which is what an account list is: the
#: same repo dispatched on another box has different accounts.
MACHINE_PROFILE_KEY = "claude_accounts"


def load_from_machine_profile(path: Path) -> list[ClaudeAccount]:
    """Accounts from `manual.claude_accounts` in a machine.yaml, or [].

    A missing or unreadable profile is an empty pool, not an error — running
    without one is the normal configuration. A profile that HAS the key and
    holds something malformed still raises, via `load_accounts`.
    """
    from . import yaml_io

    if not path.exists():
        return []
    try:
        doc = yaml_io.load(path)
    except Exception:  # noqa: BLE001 - an unreadable profile is not a pool
        return []
    if not isinstance(doc, dict):
        return []
    manual = doc.get("manual")
    if not isinstance(manual, dict):
        return []
    return load_accounts(manual.get(MACHINE_PROFILE_KEY))
