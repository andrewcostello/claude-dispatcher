# Agent evaluation harness — the objective framework

Purpose: a **repeatable, objective** way to decide two things, re-run **every
major release** (model capabilities + pricing drift):

- **A. Implementer routing** — which agent (× effort) should implement which
  kind of task.
- **B. Reviewer-panel composition** — which reviewers to keep/weight/drop. The
  panel is the load-bearing trust component; if it rubber-stamps or cries wolf,
  the system fails silently, so it must be measured, not assumed.

Both come out of one run. Supersedes the first DBF bake-off (which conflated
stacks, ran one effort level, saved only finding *counts*, and metered only
claude). Output feeds `agent-routing-policy.md`.

## Agents & reviewers
- **Implementers:** claude, codex, grok, gemini(`agy`).
- **Reviewers (panel):** claude, codex, gemini, **+ grok** (promoted from
  advisory). The authoring agent is excluded from its own solution's jury.

## Run protocol (per cell = task × implementer × effort)
1. **Implement** at the chosen effort.
2. **Gate** (per-stack: jest+tsc for React, `go test`+sqlc for Go) **+ panel**
   (all 4 reviewers minus author) → persist **full findings** (text, severity,
   location), not just counts.
3. **Repair round (≥1, required):** re-spawn the SAME agent with the gate output
   + panel findings to fix. Re-gate + re-panel. Record **pre- and post-repair**
   (so we see who self-repairs well).
4. Accept/score the post-repair result.

**Effort:** 3 levels (low/medium/high) for claude (`--effort`), grok
(`--effort`/`--reasoning-effort`), codex (`-c model_reasoning_effort=`). gemini/
`agy` has no effort flag → runs default only (record as `effort=default`).

**Relaxed panel bar:** consensus blocks only on **≥1 CRITICAL/HIGH** finding
(MEDIUM/LOW are nits, logged not blocking). Validated by review of persisted
findings. (On the first run this would have flipped DBF-2/claude, DBF-2/grok,
DBF-4/gemini, DBF-4/grok from block→approve.)

**Provenance (record per cell):** agent family, **model id**, **CLI version**,
**effort**, harness version, run timestamp, **stack** (react|go). Without this a
result is unreproducible across releases.

## Metrics

### A. Implementer routing
- Per cell: gate pass, CRITICAL/HIGH findings (post-relax), repair-needed?,
  duration, cost, tokens.
- **Per (agent × effort), aggregated over the whole project:** total wall-clock,
  total cost, total tokens. (The headline "if one agent@effort did everything,
  what does it cost/take?")
- **Per-stack tables (React vs Go)** — routing likely differs by language.
- **Mixed-agent cascade** (`grok@default→grok@high→gemini→claude`, escalate on
  gate-red/≥2-blocking/CRITICAL) scored as its own config: its total
  clock/cost/tokens + acceptance quality vs the pure agents.

### B. Reviewer evaluation (objective-first)
Per reviewer, across every solution it judged:
- **Recall** — of the real issues in a solution, how many it caught.
- **Precision** — of its findings, how many are real.
- **Rubber-stamp rate** — how often it approves (esp. approving a gate-failing
  solution = a measured false-negative).
- **Uniqueness** — issues only it finds (signal) vs noise.

Ground truth, in order of objectivity:
1. **Gate cross-check (free, objective):** approve a gate-failing solution → FN.
2. **Planted-bug control set (gold standard):** a fixed set of solutions with K
   known defects + a clean copy; measure each reviewer's catch rate (recall) and
   false-alarm rate on the clean copy (precision) — independent of model opinion.
3. **Adjudication:** a strong judge + human spot-check label persisted findings
   real/bogus → precision on the live solutions.

→ **Panel-composition recommendation:** keep reviewers with high precision×recall;
drop/down-weight rubber-stampers and noise generators. This is re-evaluated every
release so a model regressing as a reviewer is caught before it erodes the gate.

## Honest limits / guardrails
- **Model-judging-model circularity** — mitigated by the planted-bug control set
  (objective) + a human spot-check; never rely on adjudication alone.
- **Single-run noise** — run **≥2 trials per cell**; report variance. A
  1-finding difference is within noise.
- **gemini gaps** — no effort flag, likely no token/cost usage; mark its data
  partial, don't over-conclude.
- **Cost is real and claude-dominated** — log per-agent cost+tokens; the cascade
  + relaxed bar exist partly to cap claude spend.

## Cadence
Run on a **balanced React+Go feature's tasks** (≥4-5 tasks per stack for signal)
every major release. Store the run under `docs/runs/bakeoff/<release>/` (matrix
+ full findings + provenance), update `agent-routing-policy.md` from the result,
and re-confirm the panel composition.

## Harness build status (to implement before the next run)
- [ ] Repair round (re-spawn agent with gate+panel feedback, record pre/post)
- [ ] Effort sweep param (claude/grok/codex flags; gemini default)
- [ ] Capture cost + tokens for all agents that emit usage (claude/codex/grok)
- [ ] Provenance capture (model id, CLI version, effort, stack) in CellResult
- [ ] Persist FULL panel findings per cell (not just counts)
- [ ] Add grok to the reviewer panel
- [ ] Relaxed bar (block only on ≥1 CRITICAL/HIGH)
- [ ] Reviewer-eval analysis (precision/recall/rubber-stamp via gate-cross-check
      + planted-bug set + adjudication)
- [ ] Per-stack tagging + per-language report
- [ ] Stop claude implementer cells from running the full Tasker role (no PR/push)
