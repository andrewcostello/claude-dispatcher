# Mixed-agent routing policy

A reusable rule set for routing dispatcher tasks across implementer agents
(claude / codex / grok / gemini), derived from the 2026-06-18 DBF bake-off
(`evenplay-mono/docs/runs/bakeoff/REPORT.md`) and meant to be **re-validated by a
bake-off every major release** (see Cadence). Goal: spend the least to reach an
acceptable outcome — *outcome first, but don't pay big multiples for marginal
quality* (the "no 100× for 1%" rule).

## What the first bake-off showed
- **grok** — fastest (~200-325s), $0 measured, quality-competitive on bounded
  leaf work. Won the 3 leaf hooks.
- **claude** — best on the complex / stateful / auth core (fewest blocking
  findings), but slow (≤1270s) and the only metered cost (≈$43 total).
- **codex** — strong on the skeleton (its only win, a clean approve), but
  **failed the mechanical gate twice** on body-fills → gate-unreliable.
- **gemini** — never the worst, never strictly best; squeezed between grok
  (faster/cheaper) and claude (better on hard). No solo niche *yet* — but cost
  was unmeasured and runs were single-shot.

## The rules

### 1. Entry tier (deterministic, from labels / paths / size)
- **HARD** → start at **claude** directly (no cascade — claude won every hard
  task; a cheap attempt would just be thrown away).
  Triggers: label `security|auth|financial|critical`; a path on the risk
  denylist (auth, money, migrations); `size:L|XL`; or "skeleton / state-machine
  / core" work.
- **MEDIUM** (`size:M`, not HARD) → **cascade**, accept threshold 0 blocking.
- **EASY** (`size:XS|S`, bounded leaf, not HARD) → **cascade**, accept
  threshold ≤1 non-critical blocking.

### 2. The cascade (EASY / MEDIUM) — cheap-first, escalate on real failure
```
attempt = grok @ default effort
1. implement → gate + cross-family panel
2. if gate PASS and blocking ≤ threshold:        ACCEPT  (cheap win)
3. else escalate ONE rung and retry, passing the prior attempt's
   diff + gate output + panel findings as context. Escalate along TWO axes,
   cheapest move first — bump EFFORT before switching MODELS:
        grok@default → grok@high      (same model, more reasoning/turns — ~free)
        grok@high    → gemini@high     (a DIFFERENT cheap model — fresh blind
                                        spots, gives gemini its niche; ~$0)
        gemini@high  → claude@high     (the strong closer; fix or rewrite)
4. claude's result is final (accept or hand to human).
```
Rationale: (a) **bumping effort is cheaper than switching models** — try a
higher reasoning/turn budget on the cheap model before paying for a bigger one;
(b) a *different* cheap model fixing another's output beats self-fix (self-fix
repeats its own blind spots), and gemini is ~free, so that rung costs latency,
not much $. Keep it to **one attempt per rung** (no infinite loops). HARD tasks
start at **claude@high** directly.

### 3. Cost guard (the "no 100× for 1%" rule)
- Escalate to claude **only on a real quality failure**: gate-RED, OR
  **≥2 blocking findings**, OR any CRITICAL/security finding.
- Do **not** escalate for a single non-critical nit — accept the cheap solution
  and log the nit as a follow-up. (In the bake-off, claude's DBF-5/DBF-6 wins
  were a 1-finding edge at $10-20 vs grok's $0; under this guard those would
  stay with the cheap tier unless the finding was CRITICAL.)

### 4. Per-agent role summary
| Agent | Primary role |
|-------|--------------|
| **grok** | Default first implementer for EASY/MEDIUM. Fast, ~free, competitive. |
| **gemini** | Second cheap rung in the cascade; cross-family reviewer. Promote to a standalone tier only if a future bake-off (with cost measured) shows a niche. |
| **claude** | HARD tasks directly; final escalation rung; cross-family reviewer. |
| **codex** | Skeleton / scaffolding tasks; cross-family reviewer. NOT a default body-fill implementer (gate-unreliable). |

## Effort as a routing dimension
"Which agent" is only one lever; **how much effort** (reasoning level / thinking
budget / max agent turns) is the other, and it's usually the cheaper one to
turn. Per-CLI knobs: codex `reasoning_effort` (low|medium|high), gemini thinking
budget, grok `--max-turns` / verification loop, claude extended-thinking / model
tier. The first bake-off ran **every cell at default effort** — so it under-tests
each agent. Implications:
- The cascade bumps effort before switching models (§2).
- Future bake-offs should sweep effort (e.g. default vs high) as a second axis —
  it may resolve codex's gate failures or surface a gemini niche that default
  effort hid.
- HARD tasks default to high effort; trivial leaves stay at default to save cost.

## Provenance — record model, version, and effort (for posterity)
A bake-off result is only comparable across releases if you know **exactly what
produced it**. Record per cell (and per task in the dispatcher journal for real
runs):
- **agent family** (claude/codex/grok/gemini)
- **model id** (e.g. `claude-opus-4-8`, `gpt-5-codex`, `grok-4`, `gemini-2.x`)
- **CLI version** (e.g. `grok 0.2.39`, `codex-cli 0.139.0`) — capabilities shift
  between CLI releases independent of the model
- **effort setting** used for that cell
- harness/dispatcher version + the run timestamp
Without this, "grok won DBF-2" is unreproducible — next quarter's `grok` is a
different CLI + model + default effort. (The dispatcher already captures the
claude CLI version via `capture_agent_version`; extend it to all agents + record
model + effort in `CellResult` and the matrix.)

## What must improve before trusting this further
1. **Measure cost for ALL agents** — today only claude is metered; the cascade's
   economics (and gemini's case) need real cost for grok/codex/gemini, plus the
   panel-reviewer cost.
2. **≥2 trials per cell** — a 1-blocking-finding difference is within noise;
   single runs over-fit. Report variance.
3. **Relax the panel bar** — only 2/28 cells got unanimous APPROVE, so consensus
   was a near-useless discriminator; switch to majority-approve or
   block-only-on-≥1-blocking so consensus carries signal.
4. **Implement the cascade in the harness** — today the bake-off and dispatcher
   support static per-task `agent:` routing only; the escalate-on-failure cascade
   (§2) is a harness feature still to build.

## Cadence — run a bake-off every major release
- **When:** before promoting a major release, run a bake-off on *that release's*
  feature tasks (a representative set — not a blind cron; it needs real tasks
  with bases).
- **Why:** model capabilities + pricing shift between releases; the routing that
  was optimal last release may not be. Re-derive the routing table and update
  the entry-tier triggers / cost guard from fresh data.
- **Output:** an updated routing table in this doc + the per-release matrix under
  `docs/runs/bakeoff/<release>/`.
- **Checklist item:** add "run agent bake-off + update routing policy" to the
  major-release checklist.
