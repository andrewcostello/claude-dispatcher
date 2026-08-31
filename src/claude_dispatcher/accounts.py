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
  * An exhausted account stays exhausted FOR THE RUN. A quota resets on the
    provider's clock, not ours, so re-probing it per task would spend a spawn
    to learn what the last one already established.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: `spawn_failure` already separates these, and the separation is the whole
#: safety property of this module: only the first list may rotate.
QUOTA_STATUSES = frozenset({429})
AUTH_STATUSES = frozenset({401, 403})


@dataclass
class AccountRotation:
    """The accounts a run may use, and which are spent.

    `active` is None when the run uses the ambient `CLAUDE_CONFIG_DIR`, which is
    the normal case and the one that must keep working unchanged.
    """

    candidates: list[Path] = field(default_factory=list)
    exhausted: set[Path] = field(default_factory=set)
    active: Path | None = None

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
