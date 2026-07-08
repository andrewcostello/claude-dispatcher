# Feature review loop — design (PRD oracle + final review + disposition loop + haiku log)

Status: design for build (2026-06-19). Closes three gaps between the
improvement-plan design and the shipped system (verified absent in code):
no agent-conversation log/haiku summary, no final whole-feature review, no
loop-until-no-new-findings / disposition queue.

## The closed loop
```
Planner (skill)
  └─ emits: PRD.md (intent oracle) + skeleton (contracts) + tasks.yaml
Dispatcher run
  └─ per task: spawn → gate → per-task panel  (as today)
  └─ [1] per task: save transcript + haiku summary → YAML row {summary, log_ref}
  └─ when ALL tasks terminal-success:
       [2] FINAL REVIEW: cross-family panel over the CUMULATIVE feature diff,
           reviewed AGAINST PRD.md (intent + acceptance + contracts)
       [3] DISPOSITION LOOP: every finding gets accept | reject | defer(reason);
           accepted → fix task dispatched into the SAME run; re-run final review;
           loop until no new accept-worthy findings (or K dry rounds)
```
Each piece is independently useful; together they make the run self-closing.

## [PRD] Planner emits a PRD/design file (the review oracle)
- New Planner output, committed at `features/<feature>/PRD.md`, referenced from
  the tasks.yaml top-level (`prd: features/<feature>/PRD.md`).
- Contents: problem/intent, the contracts + data-flow seams (from the skeleton),
  **acceptance criteria** (what "feature done" means, beyond per-task tests),
  non-goals, known feature-asymmetry / degradation decisions, and a
  **Deviations** section the run appends to.
- Why: gives [2] something to review *against* (not just diff-internal quality)
  and gives humans + audit a single intent record. Authored at Planner GATE 1.

## [2] Final feature review
- Trigger: all tasks Done/Merged/AwaitingReview (run-level, after the per-task
  loop drains).
- Input: cumulative feature diff (base..feature-branch) + `PRD.md`.
- Mechanism: reuse `cross_family_reviewer.run_panel` with a FEATURE-review prompt
  ("does this satisfy the PRD's intent + acceptance + contracts; is it coherent
  across tasks; what's missing/regressed?"). Author excluded N/A (no single
  author). Persist full findings (full text, not just counts).
- Output: a `PanelVerdict` whose findings feed [3].

## [3] Disposition loop + queue (the integrity mechanism)
- Every finding (final-review AND per-task panel) gets a **disposition**:
  `accept` (→ becomes a fix task), `reject(reason)`, `defer(reason)`. No silent
  drops — this is the "no-deferral" rule made real.
- Disposition assignment: auto-rules first (CRITICAL/HIGH + gate-grounded →
  accept; duplicate/already-fixed → reject), human gate for the ambiguous ones in
  supervised mode; unattended uses a conservative default (accept CRITICAL/HIGH,
  defer the rest with reason).
- Accepted findings → synthesized fix tasks (key `FIX-<n>`, blockedBy the tasks
  they touch) dispatched into the same run.
- Loop: after fixes land, re-run [2]; stop when a full round yields no new
  accept-worthy findings, or after K consecutive dry rounds (config
  `feature_review_rounds`, default ~3), or a hard cap. Persist the disposition
  ledger to the run dir + journal (hash-chained, auditable).

## [1] Agent transcript log + haiku summary
- Capture the per-task agent transcript. `claude --print --output-format json`
  gives only the final envelope; switch the captured stream to one that yields
  the transcript (or read the agent's session jsonl) and write
  `run_dir/<key>/transcript.jsonl`.
- A `claude-haiku` pass summarizes it (cheap) → write `run_dir/<key>/summary-haiku.md`.
- YAML row gains `transcript_log` + `haiku_summary` (path refs) alongside the
  existing Tasker `summary_path`. Cross-family agents: capture their stdout
  similarly (best-effort).
- Value: review/audit context + feeds [2]'s reviewers if they want "how did this
  task get here". Not correctness-critical → lowest priority.

## Build order (dependencies)
1. **[PRD]** Planner emits PRD.md + `prd:` in tasks.yaml — small; unblocks [2]'s oracle.
2. **[3-core] disposition queue** data model + ledger (pure, unit-testable) — the
   integrity primitive [2] feeds.
3. **[2]** final feature review stage (run-level, after per-task drain) producing
   findings → dispositions.
4. **[3-loop]** wire the loop: accepted findings → fix tasks → re-review → until dry.
5. **[1]** transcript + haiku summary (independent; can land anytime).

## How it maps onto the orchestrator
- New run-level phase after the per-task scheduler drains (orchestrator `execute`
  end, before the terminal tally).
- Reuses: `run_panel` (review), the worktree/spawn machinery (fix tasks), the
  journal (disposition ledger + review events), the risk classifier (auto-accept
  rules).
- Config: `feature_review` (on/off), `feature_review_rounds`, `prd` path.

## Where artifacts + decisions live (3 layers)
- **Journal (hash-chained JSONL) — canonical, always.** Every disposition
  (accept/reject/defer + reason), every review (per-task + final), every loop
  iteration is a journal event. Append-only + tamper-evident (ISO-27001). Does
  NOT move to JIRA.
- **tasks.yaml — task definition + light state + REFERENCES.** status, branch,
  and path/link refs to artifacts (summary_path, transcript_log, haiku_summary,
  review). NOT the audit log — never bloat a mutable file with per-iteration
  decision comments.
- **Forecast = the human-facing projection (NOT in the dispatcher).** Do NOT
  build a JIRA sink into the dispatcher — keep it a pure engine. Instead, the
  Forecast CLI (`~/Project/forecast`, already wraps JIRA for project SMG) gains a
  `forecast ingest <run>` that PULLS the journal + run-dir artifacts and projects
  them: haiku summary + final review → ticket comments; transcript → attachment/
  link; **one comment per disposition/iteration** ("found X → accept → FIX-3";
  "final review round 2: clean"); status transitions (In Development → In
  Internal QA → …); deferred findings → backlog tickets. This reuses Forecast's
  existing SMG workflow/labels/statuses and matches the CLAUDE.md convention
  ("memorialize decisions as ticket comments as they happen"). The dispatcher's
  only obligation is a COMPLETE journal (disposition reasons, full findings,
  artifact paths, task↔ticket key mapping) — no JIRA coupling.

### Unattended auto-disposition (detail)
Signals: severity, **corroboration** (# reviewers independently flagging it —
the precision lever), gate-grounding.
- **auto-accept → FIX task:** CRITICAL/HIGH AND (≥2 reviewers agree OR
  gate-grounded).
- **auto-defer** (logged + Forecast backlog ticket, with reason): MEDIUM/LOW.
  Deferred HIGHs are release-blocking: the backlog ticket carries the next prod
  fix-version (2026-07 audit: 17 deferred highs shipped live on the honor system).
- **HOLD for human** (block + notify): any BLOCKING finding (CRITICAL or HIGH)
  not corroborated and not gate-grounded (one reviewer, others silent — matches
  `classify_disposition`), reviewer conflict, or a cap/alarm trip. Lone-reviewer
  blocking findings are often the unique-lens catches (evidence-vs-decision,
  failure-under-load) that other reviewers structurally cannot corroborate —
  they are the last class to auto-drop.
- **auto-reject** (with reason) only when objectively refutable: duplicate, or
  contradicted by a passing gate. **"References code outside the diff" is NOT
  refutable and must never auto-reject** — the 2026-07 escape audit found 36% of
  shipped escapes (62/171, incl. the v1.0.9 prod rollback) lived exactly in
  code-outside-the-diff interactions (sibling paths, legacy consumers). Such a
  finding routes to HOLD with a sibling-surface check: does the referenced code
  actually read/write state the diff touches? (See the blast-radius artifact.)
- Caps: max fix rounds (~3) + max FIX tasks; high disposition rate or
  regenerating findings → stop + hold + notify (skeleton/PRD likely wrong).
Supervised mode: human adjudicates the ambiguous; auto-rules handle the clear.

## Retrospective / escape analysis (the OUTER feedback loop)
After QA/prod finds a defect the pipeline shipped, that bug is a labeled *miss*
of the whole system — the realest ground truth there is (vs the bake-off's
synthetic tasks). A `escape-analyst` role ingests (the bug + the run's PRD,
contracts, transcripts, per-task + final reviews, disposition ledger from the
journal) and answers **"which stage should have caught this, and why didn't
it?"**:
- contract too weak/missing (e.g. the case-sensitivity class) → improve Planner
  contract-authoring;
- reviewer false-negative → feeds reviewer-eval / panel composition;
- integration/seam gap → strengthen the final-review prompt + PRD acceptance;
- deviation wrongly accepted → tighten disposition rules.
Output: concrete process refinements **+ the regression contract test that would
have caught it** (so the class can't escape twice). This operationalizes the
contract-first double-feedback-loop and pairs with the bake-off (bake-off =
precision/recall on known tasks; escape analysis = recall on real escapes).

## Honest limits
- The final review's value tracks PRD quality (load-bearing, like contract tests).
- Auto-disposition risks accepting noise or rejecting real issues — keep the
  human gate for ambiguous findings in supervised mode; log every disposition.
- Fix-task storms: cap rounds + total fix tasks; a high disposition rate is an
  alarm (the skeleton/PRD was wrong) — surface it, don't grind.

## 2026-07 audit-derived gates (implemented)

Additions from the evenplay-mono escape audit (171 shipped escapes analyzed;
ledger at `~/Project/evenplay-review-audit-2026-07/`):

- **Committed-tree gate** (in VG-2, `mechanical_verify.uncommitted_changes`):
  the test command's verdict only counts over a clean `git status --porcelain`
  — a green suite over a dirty tree shipped a build break once (PR #671
  class). Blocks with reason `uncommitted_changes`, no retry.
- **Seal-inversion gate (VG-3, `seal_verify.py`)**: fix-shaped tasks (FIX-*
  keys, `type:fix`/`seal-check` labels) must prove their new tests FAIL with
  the non-test half of the change reverted to base. Catches the
  false-passing-seal class (13 audit findings). Journal event
  `verification_seal`; blocks with `seal_verification_failed`.
- **Blast-radius artifact** (`blast_radius.py`, injected into every panel
  prompt): touched symbols → their non-test references OUTSIDE the diff, so
  reviewers adjudicate sibling surfaces instead of grepping (wrong-scope was
  36% of shipped escapes).
- **Lens-based panel seats** (`reviewer_prompts/*.md`): claude = money &
  state integrity, gemini = systems & seams, codex = evidence & claims,
  grok = environment & operations. Same shared core; differentiated primary
  sweeps replace three overlapping generalists.
- **Implementer prior** (`cross_family_reviewer.implementer_prior_for`):
  every panel prompt carries the agent-authored defect signature (vacuous
  tests, fail-open defaults, sibling gaps, docs drift, overclaimed
  completeness).
- **Epic capstone** (`orchestrator._maybe_append_capstone`): runs with
  `capstone: true` or an `epic/` base branch get a synthesized final
  CAPSTONE-INTEGRATION task — seam audit + runtime sweep before the epic
  merges (the #582 mega-merge class: 54 of 171 escapes rode one squash).
- **Review-and-clear loop** (`unblock.py`): `dispatcher blocked tasks.yaml`
  prints every Blocked task with its reason + gate detail (exit 3 when
  non-empty, alertable from cron); `dispatcher unblock tasks.yaml KEY --note
  "..."` flips it back to To Do, clears the stale gate stamps, and appends
  the human's adjudication to the description the re-spawned Tasker reads.
  Unblocking grants a retry, never a waiver — every gate re-runs. Blocked
  stays the only stop state; this is the human half of its lifecycle.
