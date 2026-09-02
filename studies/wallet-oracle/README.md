# The hidden oracle — wallet reserve/settle

**This directory must never be copied into `ep2.0`.** It lives in
`claude-dispatcher` precisely so that dispatched arms working in `ep2.0` cannot
read it. An arm that can see the tests is not being measured against
requirements it never saw; it is being given the answer.

## Why an independent suite

Mutation testing can only probe what the production code expresses. Measured
2026-09-02 on the GO-1-1 seals task: all 13 mutations landed inside one of the
contract's twelve numbered clauses, so every arm that delivered scored an
identical 11/13 — a two-rung scale that could not rank models whatever the
truth. Clause coverage separated them (12/12 vs 6/12 vs 4/12) but is grep-based
and only proves a suite MENTIONS a clause.

A withheld suite is a genuine oracle. It answers the actual question — did this
arm build something that satisfies requirements it never saw — has as many rungs
as we write, cannot be gamed by a vacuous test, and GROWS: when an arm handles a
case the suite missed, the case joins the suite and every later arm faces it.

## The assertions

Each is drawn from `wallet/docs/wallet-2-prd.md`, cited, and independently
pass/fail. Numbered so a result reads as "arm X satisfied 14 of 19".

### Double-entry integrity (PRD §3)
1. every transaction's entries sum to zero, per currency
2. no transaction has fewer than two entries
3. `entry.sequence_number` is gapless and unique per account

### Append-only (PRD §3)
4. an UPDATE against `wallet.entry` is refused
5. a DELETE against `wallet.entry` is refused
6. a correction is a NEW transaction that cites the one it corrects

### Hold semantics (PRD §8.1) — the PRD's own named defect
7. a hold of 100 settled for 100 moves EXACTLY 100
8. **a hold of 100 settled for 100 while the transaction debits 500 is
   REFUSED** — the PRD names this: "internally consistent, and the player has
   been charged five times what they authorised"
9. settling for less than the hold releases the remainder
10. settling for MORE than the hold is refused
11. an expired hold restores spending power and moves nothing
12. a settled hold cannot be settled twice
13. a hold on an account with insufficient balance is refused

### Balance as cache (PRD §3)
14. `account.balance` equals the sum of its entries after every commit
15. a balance written with no corresponding entry is detected

### Idempotency (schema: `wallet.idempotency_record`)
16. the same key replayed returns the original result and creates no second
    transaction
17. the same key with a DIFFERENT payload is refused, not silently answered
    with the first result

### Play/real separation (PRD §5.3) — looks well-formed, is a cash-out
18. a transaction with entries in both a social-currency and a real-currency
    account is refused, EVEN THOUGH it balances to zero per currency. The PRD:
    "every currency in a transaction balances to zero, so that last one looks
    perfectly well-formed and is a cash-out wearing another name."
19. buying social currency with real money IS permitted — the mirror is not
    symmetric, and an arm that blocks both has over-applied the rule

## Scoring

Pass rate over 19 independent assertions replaces mutation kill rate as the
headline. Reported alongside: which assertions this arm satisfied that no other
arm did (where genuine design difference shows), rounds, dev vs review time,
tokens, cost.

## Honest limits

* **19 assertions are my reading of the PRD.** An arm could satisfy the PRD in a
  way this suite fails. Every such case is a suite bug and gets added — which is
  the growth property, but it also means early arms are judged by a weaker
  oracle than later ones. Record which suite version each arm faced.
* **It tests an implementation.** Useless for a seals task; correct here only
  because the deliverable is working code.
* **Assertions 4 and 5 need real DDL**, so the suite needs a live postgres. An
  arm delivering code that cannot be stood up scores zero rather than being
  judged on inspection — deliberately, since unrunnable code is not a
  deliverable.
