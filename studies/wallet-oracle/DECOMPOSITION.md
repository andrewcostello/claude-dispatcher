# Wallet v2 in evenplay-mono — decomposition and model routing

Design source: `~/Project/ep2.0/wallet/` (PRD + `sql/schemas.sql`). ep2.0 decides
WHAT; the build lands in `evenplay-mono`.

Deployment shape, which drives the decomposition: **v2 runs beside v1 in shadow
for USD** (v1 stays authoritative and keeps receiving the writes) **and live for
points only**. So the shadow comparator is not an afterthought — it is the thing
that decides whether v2 is trustworthy, and it is a first-class deliverable.

---

## PREREQUISITE — the gate does not cover the wallet. Fix before dispatching.

**Two blockers, both measured 2026-09-02, either of which silently invalidates
every wallet task.**

1. `.dispatcher.yaml`'s `test:` runs bay-session, core/tournament and
   website-public-api. **It never touches `apps/finance-domain/wallet`.** Every
   wallet task would pass its mechanical gate no matter what it wrote — the gate
   would be judging nothing, exactly as `go vet` on a red baseline judges
   nothing.

2. **A fresh worktree cannot build the wallet.** `pb/` and `db/sqlc/` are
   gitignored generated code:

   ```
   no required module provides package .../wallet/pb
   no required module provides package .../wallet/db/sqlc
   ```

   Every arm would fail to compile before writing a line. Verified fix, in a
   clean detached worktree:

   ```
   cd apps/finance-domain/wallet && make sqlc && make proto && go build ./...
   ```
   → `GEN_BUILD_OK`

**W-0 — extend the gate to the wallet, generating first.** Must land before any
other row. `size:S`, and it is the highest-leverage task in this list: without
it the other tasks' green gates mean nothing.

---

## Task graph

Contract-first per unit: scaffold → seals → bodies → adjudicate. Criticality
drives the model, per Andrew's rule: **sol and fable only on critical rows.**

### W-1 — ledger core (CRITICAL)
Double-entry transaction + entry writing against the ep2.0 schema. Balanced
legs, append-only, gapless per-account sequence, hash chain.

| row | role | model | why |
|---|---|---|---|
| W-1-1 | scaffold | `claude-fable-5-1` | the contract every later unit reads; a wrong seam here propagates |
| W-1-2 | seals | `codex/gpt-5.6-sol@xhigh` | 12/12 clause coverage measured; seals are the safety net |
| W-1-3 | bodies | `codex/gpt-5.6-sol@xhigh` | money path |
| W-1-4 | adjudicate | `claude-fable-5-1` | judgement no gate grades |

### W-2 — reserve / settle / expire (CRITICAL)
PRD §8.1. The unit whose defect the PRD names: *"a hold of 100 settled for 100
while the transaction debits 500 is internally consistent, and the player has
been charged five times what they authorised."*

Same routing as W-1. **This is the bake-off row** — see below.

### W-3 — balance cache + reconciliation (CRITICAL)
`account.balance` provably equal to the sum of entries at every commit, not
eventually. Routing as W-1.

### W-4 — idempotency (CRITICAL)
Replay returns the original answer; the same key with a different payload is
refused rather than silently answered with the first. Routing as W-1.

### W-5 — shadow comparator (CRITICAL — and the one that decides go-live)
Runs v2 against v1 on live USD traffic, writes nothing authoritative, and
reports divergence. **Rows: fable scaffold, sol seals/bodies, fable adjudicate.**
A false "no divergence" here is the worst outcome available in this project — it
would authorise a cutover on a broken ledger — so it gets the same treatment as
the ledger itself.

### W-6 — points (social currency) live path (NON-CRITICAL)
The only path actually serving users at first. Social currency has no cash-out,
so a defect costs engagement, not money.

| row | role | model |
|---|---|---|
| W-6-1 | scaffold | `claude-opus-5` |
| W-6-2 | seals | `grok/grok-4.6@high` |
| W-6-3 | bodies | `grok/grok-4.6@high` |
| W-6-4 | adjudicate | `claude-opus-5` |

### W-7 — statements / as-of queries (NON-CRITICAL)
Read-only reconstruction from the ledger. Wrong output is visible and harmless.
Routing as W-6.

### W-8 — admin corrections (NON-CRITICAL to build, CRITICAL to review)
Corrections are new transactions citing the original. `grok` builds,
**`fable` adjudicates** — the asymmetry is deliberate: the build is mechanical,
the ruling on what counts as a valid correction is not.

---

## Why a mixed fleet is low-risk here

A bad non-critical row costs ONE REDO, and the redo is cheap because the
contract and seals survive — only the body is rewritten. That is the property
contract-first buys, and it is what makes it safe to let grok build W-6 and W-7.

It only holds if we can TELL a bad job, which is why W-0 is a prerequisite
rather than a nice-to-have.

## The bake-off row

**W-2** is dispatched to ALL of sol, fable, opus, grok, deepseek and haiku in
parallel, and judged by the hidden oracle in this directory (19 cited
assertions, withheld from every arm). Its winner is kept as the real
implementation; the rest are data.

W-2 is the right choice because the PRD names its interesting defects, its
invariants are machine-checkable, and it is small enough that six arms is
affordable.

## Retroactive analysis

Every row records agent, model and effort in `tasks.yaml`, and the dispatcher
stamps what ACTUALLY ran (see `--stay-in-family`, and the cascade defect that
made an earlier comparison unreadable). So after the fact,
`features/model-matrix/report.py` can be pointed at the wallet run and asked
which model produced which rows, at what round count, dev-vs-review split and
cost — a natural experiment with real stakes rather than a synthetic bake-off.

Recorded caveat: the rows are NOT randomly assigned. Critical rows get the
stronger models by design, so any cross-row comparison confounds model with
task difficulty. The bake-off row is the only clean comparison in the plan.
