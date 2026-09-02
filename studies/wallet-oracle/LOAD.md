# Withheld load benchmark — wallet v2

**Not in `wallet-v2-tasks.yaml`, and not attached to SMG-4240.** Same principle
as the assertion oracle: an arm that can see the benchmark optimises for the
benchmark. Withheld so "does this implementation hold up under load it was never
shown" stays a real question.

Lives here rather than in `evenplay-mono` so a dispatched agent working there
cannot read it.

## Pass marks, derived from ep2.0's measured results

From `ep2.0/bay-session/docs/03-load-results.md`, revision 3. These are the
numbers the platform actually achieved on one host, so they are the bar wallet
v2 has to clear rather than an invented target.

| # | what | ep2.0 achieved | wallet v2 pass mark | why this mark |
|---|---|---|---|---|
| WL1 | reserve→settle round trip, single account, 10/s | money loop p99 **44 ms** (whole loop, INCLUDING wallet v1 calls) | **p99 < 25 ms** | v2's own two RPCs are a fraction of a loop that also did arm/decision/outcome. Clearing 44 ms would be no evidence at all |
| WL2 | same at 40/s | loop p99 **49.5 ms** | p99 < 30 ms | ep2.0 degraded 44→49.5 ms across 4x load; v2 should degrade no worse proportionally |
| WL3 | one-account ceiling, unthrottled | **197 shots/s** at one station (one session lock) | report, no mark | the analogous limit is one account's row lock. Reported so the shard story is grounded rather than assumed |
| WL4 | fleet: 100,000 accounts, 48 workers, 60 s | **1,463–1,499 shots/s**, decision p99 12–14.9 ms | **> 1,400 reserve+settle pairs/s**, p99 < 40 ms | v2 must not be the new bottleneck. ep2.0's ceiling was the host, not the code |
| WL5 | **the fence** — `account.balance = sum(entry.amount_minor)` over the whole estate after the fleet run | **0 violations** over 100,000 sessions / 6,183,067 transitions, 2.7 s to check | **0 violations**, and the check itself < 10 s | this is WAL-BALANCE's whole claim ("provably equal at EVERY commit"). One violation fails the unit outright — it is not a latency target |
| WL6 | expiry sweep: 100,000 due holds, one pass | recovery **16.4 s** first run, **25.0 s** on rev 3; 0 double holds | **< 30 s, 0 double settles** | ep2.0's own sweeper MISSED its <30 s mark at 42.1 s and that was ruled a miss. v2 inherits the real bar, not the failed one |
| WL7 | idempotent replay under concurrency: same key from 8 workers at once | not measured in ep2.0 | **exactly one transaction, 8 identical answers** | new. ep2.0's harness never raced a single key, and WAL-IDEM's contract is exactly that |
| WL8 | CHIPS live path at the same fleet rate | — | p99 < 40 ms, 0 real-money entries | the only path serving users. A CHIPS transaction touching a real-money account is a licensing failure, not a perf one |

## Harness shape

Follow `ep2.0/bay-session/load/main.go` (546 lines): a `hist` with percentile
extraction, `buildEstate` to seed, per-scenario workers against a pgxpool, JSON
emit per run. Reuse it rather than inventing a second style — the numbers have
to be comparable to ep2.0's or the whole exercise is pointless.

## Two things the marks are deliberately NOT

**Not the numbers ep2.0 achieved.** WL1 asks for 25 ms against a measured 44 ms,
because that 44 ms was a whole money loop including wallet v1 round trips. Asking
v2 to merely match it would let a slower wallet pass by hiding inside a budget
it no longer spends.

**Not ep2.0's failures.** Its sweeper came in at 42.1 s against a <30 s mark and
that was recorded as a miss. WL6 keeps the 30 s bar. Inheriting a target because
the last system missed it is how a miss becomes the standard.

## When to run it

After `WAL-SETTLE-4` and `WAL-BALANCE-4` (the units WL1/WL5 exercise), and
before any USD shadow cutover decision. WL5 in particular gates the cutover: a
comparator that says "no divergence" while the balance cache drifts is the worst
outcome in this project, and WL5 is the check that would catch it.

## Honest limit

These marks come from ONE host and ONE workload shape — simulator golf shot
traffic. A wallet also sees deposit/withdrawal bursts, month-end reconciliation
and regulator extracts, none of which ep2.0 measured and none of which these
marks cover. Clearing WL1–WL8 means "no worse than the platform we already
run", not "correct under all load".
