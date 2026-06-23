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


def _sev_str(severity) -> str:
    """Normalize a severity (enum or str) to its uppercase string value."""
    return str(getattr(severity, "value", severity) or "").upper()


def finding_key(location: str, severity) -> str:
    """Clustering key for corroboration + dedup. BLOCKING findings
    (CRITICAL/HIGH) cluster by FILE, not file:line: reviewers reliably name the
    same file but cite the same defect at different line numbers, so file-level
    keying lets their agreement corroborate (3 reviewers flagging one bug at
    lines 10/15/16 count as corroboration 3, not three lone findings that each
    HOLD). Nits (MEDIUM/LOW) keep the full file:line so genuinely distinct nits
    don't falsely merge. Pure. (Granularity decision 2026-06-22, validated by a
    seeded-violation feature-review run where line-level keying held an
    all-reviewers-agree CRITICAL instead of accepting it.)"""
    if not location:
        return location
    if _sev_str(severity) in BLOCKING_SEVERITIES:
        return location.split(":", 1)[0]  # file part only
    return location


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
    if refutable:
        return Disposition.REJECT, "refutable"

    if severity in BLOCKING_SEVERITIES:
        if corroboration >= 2 or gate_grounded:
            return Disposition.ACCEPT, "blocking corroborated or gate-grounded"
        return Disposition.HOLD, "blocking lone ungrounded"

    return Disposition.DEFER, "non-blocking"


def corroboration(verdict) -> dict[str, int]:
    """Map each finding `finding_key` -> the number of DISTINCT reviewer families
    that flagged a finding under that key. This is the precision signal fed to
    `classify_disposition` (corroboration >= 2 lets a blocking finding auto-accept;
    a lone-reviewer blocking finding holds).

    Keys are `finding_key(location, severity)` — file-level for blocking
    severities, file:line for nits — NOT the raw location, so reviewers citing
    one defect at different lines corroborate (see `finding_key`). Reads
    `verdict.reviewers` (each with `.family` and `.findings`, each finding having
    `.location` + `.severity`), NOT the deduped `blocking_findings`. A reviewer
    flagging the same key twice counts once. Pure function.
    """
    counts: dict[str, int] = {}
    for rv in getattr(verdict, "reviewers", []) or []:
        keys = {
            finding_key(f.location, getattr(f, "severity", ""))
            for f in getattr(rv, "findings", []) or []
        }
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
    return counts


@dataclass
class DispositionLedger:
    """Append-only record of every finding's disposition for a run, with the
    caps/alarm that stop a fix-storm spiral. Enforces no-silent-drop: callers
    record EVERY finding."""
    records: list[DispositionRecord] = field(default_factory=list)
    max_fix_rounds: int = 3
    max_fix_tasks: int = 20

    # accept rate above this (with at least HIGH_RATE_MIN records) trips the
    # alarm — the skeleton/PRD is probably wrong if most findings are real bugs.
    HIGH_ACCEPT_RATE = 0.6
    HIGH_RATE_MIN_RECORDS = 4

    def record(self, rec: DispositionRecord) -> None:
        """Append a disposition. (No dedup here — `finding_id` lets callers /
        `regenerating` detect repeats across rounds.)"""
        self.records.append(rec)

    def tally(self) -> dict[str, int]:
        """Counts per Disposition value (e.g. {'accept': 3, 'defer': 5, ...}).
        Zero-count dispositions are omitted."""
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r.disposition.value] = counts.get(r.disposition.value, 0) + 1
        return counts

    def accepted_count(self) -> int:
        """Number of ACCEPT records (= fix tasks spawned)."""
        return sum(1 for r in self.records if r.disposition is Disposition.ACCEPT)

    def regenerating(self, finding_id: str) -> bool:
        """True if this finding_id has been ACCEPTed before (a fix didn't
        resolve it and it came back) — a signal the skeleton/PRD is wrong."""
        return any(
            r.finding_id == finding_id and r.disposition is Disposition.ACCEPT
            for r in self.records
        )

    def _has_regenerating(self) -> bool:
        seen: set[str] = set()
        for r in self.records:
            if r.disposition is Disposition.ACCEPT:
                if r.finding_id in seen:
                    return True
                seen.add(r.finding_id)
        return False

    def alarm_tripped(self, rounds_done: int) -> tuple[bool, str]:
        """(True, reason) if the loop should STOP and HOLD for a human; (False,
        "") otherwise. Trips on ALL four documented conditions: max rounds
        reached, fix-task cap exceeded, a regenerating finding (accepted twice),
        or a high accept rate. Pure."""
        if rounds_done >= self.max_fix_rounds:
            return True, f"max fix rounds reached ({rounds_done}/{self.max_fix_rounds})"
        accepted = self.accepted_count()
        if accepted > self.max_fix_tasks:
            return True, f"fix-task cap exceeded ({accepted}/{self.max_fix_tasks})"
        if self._has_regenerating():
            return True, "a finding regenerated (accepted again after a fix) — skeleton/PRD likely wrong"
        total = len(self.records)
        if total >= self.HIGH_RATE_MIN_RECORDS and accepted / total > self.HIGH_ACCEPT_RATE:
            return True, (f"high accept rate ({accepted}/{total} > "
                          f"{self.HIGH_ACCEPT_RATE:.0%}) — skeleton/PRD likely wrong")
        return False, ""
