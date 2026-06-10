# Cross-family panel retroactive validation report

Generated 2026-05-22T00:52:32+00:00.
Tickets surveyed: 7 (all Done BSA-FU tickets with a merge-into-epic SHA).

## Headline

The panel **caught the canonical SMG-2947 (REFUND-PRIO) test-quality issue
that prompted the human gate**, and went further — surfacing 2 CRITICAL
findings about real money-loss scenarios on the same ticket
(`decide.go:208` and `worker.go:430`) that the in-cycle Tasker panel
missed. Strong validation of the brief's hypothesis that same-family
review is partially circular.

On the 6 auto-integrated tickets:

- 1/6 cleared the panel unanimously (RECOVERY-OUTCOME)
- 5/6 had at least one blocking finding (≥ one HIGH or CRITICAL from one
  or more families). Each finding is specific, cites file:line, and gives
  a concrete fix — see the per-ticket `panel.md`. These are NOT "ship it"
  approvals overruled by paranoia; they are new findings the in-cycle
  Claude panel didn't surface.

Per-family characteristics observed in this sample:

| Family | Tendency in this sample |
|--------|-------------------------|
| Claude | More findings on average but more APPROVEs on quality-only cases |
| Gemini | Sharpest on dedupe / monotonicity / Compliance-grade defects (REJECT verdicts on REFUND-PRIO + NATS) |
| Codex | Quick + terse; consistently lands one focused finding per ticket |

A known fix applied mid-sweep: gemini and codex initially received the
prompt as argv, which fails with E2BIG on diffs > ~2000 lines (Linux
ARG_MAX is ~128KB per arg). The adapters now pipe via stdin — verified
on NATS-PARTITION-RECOVERY which was UNAVAILABLE on the first pass and
returned a clean block on the re-run.

## Summary table

| Ticket | auto_integrate | panel.consensus | claude | gemini | codex | findings | diff lines | wall (s) |
|--------|----------------|-----------------|--------|--------|-------|----------|------------|----------|
| BSA-FU-AUTH-PEER-BRIDGE | integrated | block | CHANGES_REQUESTED | CHANGES_REQUESTED | CHANGES_REQUESTED | 3 | 1326 | 275.0 |
| BSA-FU-RECOVERY-REFUND-PRIO | manual | block | CHANGES_REQUESTED | REJECT | REJECT | 3 | 787 | 252.2 |
| BSA-FU-RECOVERY-OUTCOME | integrated | approve | APPROVE | APPROVE | APPROVE | 0 | 1114 | 264.1 |
| BSA-FU-CASCADE-REFUND-DRAIN | integrated | block | APPROVE | APPROVE | CHANGES_REQUESTED | 1 | 2996 | 255.8 |
| BSA-FU-XPOD-ORDERING | integrated | block | CHANGES_REQUESTED | CHANGES_REQUESTED | CHANGES_REQUESTED | 6 | 1470 | 163.4 |
| BSA-FU-NATS-PARTITION-RECOVERY | integrated | block | APPROVE | REJECT | CHANGES_REQUESTED | 3 | 3032 | 345.7 |
| BSA-FU-SHUTDOWN-GOROUTINE-WG | integrated | block | APPROVE | CHANGES_REQUESTED | CHANGES_REQUESTED | 3 | 1162 | 330.5 |

## Agreement analysis

- Auto-integrate **integrated** AND panel **approve**: 1
- Auto-integrate **manual** (human-gated) AND panel **block/incomplete**: 1
- Panel **caught what human caught** (manual + block): 1
- Panel **block on what auto-integrate approved** (false positives or NEW findings): 5
- Panel **approved what human blocked** (false negatives): 0
- Total tickets evaluated: 7

## Per-ticket detail

### BSA-FU-AUTH-PEER-BRIDGE

- auto_integrate_status: `integrated`
- panel.consensus: `block`
- panel.summary: consensus=block | claude=CHANGES_REQUESTED, gemini=CHANGES_REQUESTED, codex=CHANGES_REQUESTED | blocking=3 (0C/3H)
- elapsed: 275.0s, diff: 1326 lines, blocking findings: 3
- panel report: [panel.md](./BSA-FU-AUTH-PEER-BRIDGE/panel.md)

### BSA-FU-RECOVERY-REFUND-PRIO

- auto_integrate_status: `manual`
- panel.consensus: `block`
- panel.summary: consensus=block | claude=CHANGES_REQUESTED, gemini=REJECT, codex=REJECT | blocking=3 (2C/1H)
- elapsed: 252.2s, diff: 787 lines, blocking findings: 3
- panel report: [panel.md](./BSA-FU-RECOVERY-REFUND-PRIO/panel.md)

### BSA-FU-RECOVERY-OUTCOME

- auto_integrate_status: `integrated`
- panel.consensus: `approve`
- panel.summary: consensus=approve | claude=APPROVE, gemini=APPROVE, codex=APPROVE
- elapsed: 264.1s, diff: 1114 lines, blocking findings: 0
- panel report: [panel.md](./BSA-FU-RECOVERY-OUTCOME/panel.md)

### BSA-FU-CASCADE-REFUND-DRAIN

- auto_integrate_status: `integrated`
- panel.consensus: `block`
- panel.summary: consensus=block | claude=APPROVE, gemini=APPROVE, codex=CHANGES_REQUESTED | blocking=1 (0C/1H)
- elapsed: 255.8s, diff: 2996 lines, blocking findings: 1
- panel report: [panel.md](./BSA-FU-CASCADE-REFUND-DRAIN/panel.md)

### BSA-FU-XPOD-ORDERING

- auto_integrate_status: `integrated`
- panel.consensus: `block`
- panel.summary: consensus=block | claude=CHANGES_REQUESTED, gemini=CHANGES_REQUESTED, codex=CHANGES_REQUESTED | blocking=6 (0C/6H)
- elapsed: 163.4s, diff: 1470 lines, blocking findings: 6
- panel report: [panel.md](./BSA-FU-XPOD-ORDERING/panel.md)

### BSA-FU-NATS-PARTITION-RECOVERY

- auto_integrate_status: `integrated`
- panel.consensus: `block`
- panel.summary: consensus=block | claude=APPROVE, gemini=REJECT, codex=CHANGES_REQUESTED | blocking=3 (1C/2H)
- elapsed: 345.7s, diff: 3032 lines, blocking findings: 3
- panel report: [panel.md](./BSA-FU-NATS-PARTITION-RECOVERY/panel.md)

### BSA-FU-SHUTDOWN-GOROUTINE-WG

- auto_integrate_status: `integrated`
- panel.consensus: `block`
- panel.summary: consensus=block | claude=APPROVE, gemini=CHANGES_REQUESTED, codex=CHANGES_REQUESTED | blocking=3 (0C/3H)
- elapsed: 330.5s, diff: 1162 lines, blocking findings: 3
- panel report: [panel.md](./BSA-FU-SHUTDOWN-GOROUTINE-WG/panel.md)
