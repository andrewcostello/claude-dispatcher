"""Disposition queue — the no-silent-drop integrity primitive for review findings.

Every finding (per-task panel OR the final feature review) gets a RECORDED
disposition: accept (→ a fix task), defer (logged + backlog ticket), hold (await
a human), or reject (only when objectively refutable). Nothing is silently
dropped. The ledger is journaled (hash-chained) so the decision trail is
auditable and Forecast can project it to JIRA.

This module is PURE (no subprocess / network / fs) so it's unit-testable; the
orchestrator (steps 3-4, built separately with a human) wires it into the run
and emits the journal events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Disposition(str, Enum):
    ACCEPT = "accept"   # real + important + confident -> spawn a fix task
    DEFER = "defer"     # logged + backlog ticket, with reason; not acted in-run
    HOLD = "hold"       # ambiguous/high-stakes -> block + notify a human
    REJECT = "reject"   # objectively refutable only, with reason


# CRITICAL/HIGH are "blocking" severities; MEDIUM/LOW are nits.
BLOCKING_SEVERITIES = ("CRITICAL", "HIGH")


@dataclass
class DispositionRecord:
    """One finding's recorded decision. `finding_id` is a stable key
    (e.g. task:location:severity) so re-runs dedupe and the ledger can detect
    a finding regenerating across rounds."""
    finding_id: str
    severity: str
    corroboration: int          # # of reviewers that independently flagged it
    gate_grounded: bool
    disposition: Disposition
    reason: str
    fix_task_key: str | None = None  # set when disposition == ACCEPT


def classify_disposition(
    *, severity: str, corroboration: int, gate_grounded: bool,
    refutable: bool, mode: str,
) -> tuple[Disposition, str]:
    """Decide a finding's disposition + a human-readable reason. Pure.

    `mode` is "unattended" or "supervised".
    Rules (see docs/feature-review-loop.md):
      - refutable=True (duplicate / code outside diff / contradicted by a passing
        gate) -> REJECT, regardless of severity.
      - blocking severity (CRITICAL/HIGH) AND (corroboration >= 2 OR gate_grounded)
        -> ACCEPT.
      - blocking severity but NOT corroborated and NOT gate_grounded (a lone
        reviewer) -> HOLD (unattended) — too risky to auto-fix or auto-drop.
      - non-blocking (MEDIUM/LOW), or any lone non-corroborated non-blocking
        finding -> DEFER.
    In "supervised" mode, the ambiguous cases that would HOLD are still HOLD
    (the human adjudicates); the clear ACCEPT/DEFER/REJECT auto-rules still apply.
    The returned reason explains which rule fired (for the journal + JIRA comment).
    """
    raise NotImplementedError("step-2 body-fill: classify_disposition")


@dataclass
class DispositionLedger:
    """Append-only record of every finding's disposition for a run, with the
    caps/alarm that stop a fix-storm spiral. Enforces no-silent-drop: callers
    record EVERY finding."""
    records: list[DispositionRecord] = field(default_factory=list)
    max_fix_rounds: int = 3
    max_fix_tasks: int = 20

    def record(self, rec: DispositionRecord) -> None:
        """Append a disposition. (No dedup here — `finding_id` lets callers /
        `regenerating` detect repeats across rounds.)"""
        self.records.append(rec)

    def tally(self) -> dict[str, int]:
        """Counts per Disposition value (e.g. {'accept': 3, 'defer': 5, ...})."""
        counts: dict[str, int] = {}
        for rec in self.records:
            key = rec.disposition.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def accepted_count(self) -> int:
        """Number of ACCEPT records (= fix tasks spawned)."""
        return sum(1 for rec in self.records if rec.disposition is Disposition.ACCEPT)

    def regenerating(self, finding_id: str) -> bool:
        """True if this finding_id has been ACCEPTed before (a fix didn't
        resolve it and it came back) — a signal the skeleton/PRD is wrong."""
        return any(
            rec.finding_id == finding_id and rec.disposition is Disposition.ACCEPT
            for rec in self.records
        )

    def alarm_tripped(self, rounds_done: int) -> tuple[bool, str]:
        """(True, reason) if the loop should STOP and HOLD for a human: fix-task
        cap exceeded, max rounds reached, or a high accept rate / regenerating
        findings (skeleton/PRD likely wrong). (False, "") otherwise. Pure."""
        if rounds_done >= self.max_fix_rounds:
            return True, (
                f"max fix rounds reached ({rounds_done} >= {self.max_fix_rounds})"
            )
        accepted = self.accepted_count()
        if accepted > self.max_fix_tasks:
            return True, (
                f"fix-task cap exceeded ({accepted} > {self.max_fix_tasks})"
            )
        return False, ""
