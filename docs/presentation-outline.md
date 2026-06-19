# Claude for Development — Best Practices + The Dispatcher

Presentation outline. Two parts that stand on their own:

1. **A fair walkthrough of how people get great results with Claude** — the
   real working styles and the cross-cutting techniques, presented neutrally so
   a newcomer can try several and decide what fits them. *No tooling required;
   none of this depends on Part 2.*
2. **One opinionated approach built on top — the dispatcher** — what it does
   differently and the reasoning behind each decision, offered as "here's the
   set of constraints I had and the answer I reached," not as the place everyone
   should end up.

Suggested length: ~50 min + demo. Part 1 ~30 min (it's the part most of the
room can use tomorrow), Part 2 ~15 min, ~5 min Q&A. **[S]** = slide,
**[DEMO]** = live moment.

> Opening promise to the audience: *"By the end of Part 1 you'll have several
> distinct ways to work with Claude that each get strong results — try them,
> keep what fits your brain and your codebase. Part 2 is just where one of those
> roads led me; take it or leave it."*

---

## Part 1 — How people actually get great results with Claude

### 1. The mental model (one slide, sets up everything)
- **[S]** Claude is a *fast, broad, literal collaborator with no standing memory
  of your intent.* It's astonishingly capable and confidently wrong in the same
  breath.
- The skill that pays off isn't typing code — it's **specifying, steering, and
  verifying.** Your leverage lives in how well you set the task up and how
  cheaply you can check the result.
- Everything that follows is a different answer to the same question: *given
  that, how do I get the most out of it?* There's more than one good answer.

### 2. The spectrum of working styles (the heart of Part 1)
> **[S]** A single slide showing a spectrum, left→right by *how much you stay in
> the loop*: Pairing → Plan-first → Test-driven → Exploratory → Autonomous →
> Parallel/fan-out. None is "advanced/beginner"; they suit different tasks and
> different people. Most pros fluidly switch.

For each style: **what it looks like · why people swear by it · where it breaks ·
who/what it suits.** Encourage the audience to try the same small task in two
styles and feel the difference. **[DEMO]** idea: implement one small function
two ways live.

**a) Conversational pairing (tight loop)** — *the default, and underrated.*
- Looks like: you and Claude in a chat, small steps, you read each diff, you
  course-correct constantly. Inline IDE or terminal.
- Why people love it: maximum control, you learn the codebase as you go, errors
  caught instantly, great for unfamiliar or delicate code.
- Where it breaks: serial and supervised — you're the bottleneck; tedious for
  bulk/boilerplate; long threads drift.
- Suits: exploring new code, surgical changes, anyone who wants to stay hands-on.

**b) Plan-first / spec-driven** — *think before it types.*
- Looks like: ask for a written plan or design *before any code*; read it,
  argue with it, then say "go." (Plan mode / "don't write code yet.")
- Why people love it: misunderstanding is cheap to fix in prose and brutal to
  fix in a 2,000-line diff. Disagreement at plan time is a gift. Scales to
  bigger tasks than pure pairing.
- Where it breaks: a plan that looks good can still be wrong at contact with
  reality; over-planning trivial work is friction.
- Suits: medium/large features, anything touching architecture, teams who want a
  reviewable intent artifact.

**c) Test-driven with the agent** — *make "done" objective.*
- Looks like: you (or Claude) write the failing test first; Claude makes it
  green; repeat. "Here's the spec as a test — satisfy it."
- Why people love it: the test *is* the definition of done — you trust the
  result without reading every line; resistant to plausible-but-wrong code; the
  agent can iterate against the check by itself.
- Where it breaks: only as good as the test; weak tests let subtly-wrong code go
  green; some work is hard to test (UI, integration).
- Suits: logic-heavy code, refactors, anything with a clear contract.

**d) Exploratory / research / rubber-duck** — *use it to think, not just type.*
- Looks like: "explain how X works," "where does this data flow," "what are 3
  ways to do this and the tradeoffs," "review this design." Often read-only.
- Why people love it: enormous breadth; fastest way into an unfamiliar codebase
  or a new library; great for de-risking *before* committing to an approach.
- Where it breaks: confident hallucination of APIs/behavior — verify claims
  against the actual code/docs; it's a starting point, not an oracle.
- Suits: onboarding, design exploration, debugging a mystery, learning.

**e) Autonomous agentic loop ("let it drive")** — *delegate a whole task.*
- Looks like: give a well-scoped goal + the ability to run tests/build, and let
  it work for many steps — read files, edit, run, self-correct — checking in at
  the end (or at checkpoints).
- Why people love it: huge throughput on bounded, verifiable work; you spend
  attention on the result, not the keystrokes; frees you for other things.
- Where it breaks: drifts or thrashes if the task is under-specified or the
  architecture is implicit; can "reward-hack" a weak check (e.g. delete a test);
  the more autonomous, the more it *must* be mechanically checkable.
- Suits: boilerplate, mechanical migrations, well-contracted features, first
  drafts — *anything where "done" is objective.*
- **Key heuristic to put on the slide: match autonomy to checkability. Autonomy
  is earned by how cheaply you can verify the output.**

**f) Parallel / multi-agent fan-out** — *more than one at once.*
- Looks like: several agents working independent slices simultaneously
  (subagents for search; separate sessions/worktrees for separate tasks), then
  you integrate.
- Why people love it: wall-clock speed on decomposable work; each agent gets a
  clean, focused context.
- Where it breaks: coordination/integration cost; harder to supervise; needs
  isolation so they don't collide; review burden multiplies.
- Suits: large search/audit sweeps, independent tasks, batch work. *(This is the
  road Part 2 walks down — but it's a legitimate style on its own with plain
  tools.)*

### 3. Cross-cutting superpowers (apply to every style above)
> **[S]** "Whatever style you pick, these multiply it." Frame as a toolbox, not
> a process.

- **Curate the context window — it's the product.** Point at the seam, not the
  whole repo. Too little *and* too much both degrade output.
- **`CLAUDE.md` / project memory** = standing context you don't retype:
  conventions, domain vocabulary, "don't touch X," commit style. Keep it tight —
  a bloated one is just noise it weighs unevenly.
- **Start fresh when the task changes.** Long threads drift; a stale plan
  poisons new work. Restarting is cheap; debugging a confused agent isn't.
- **Plans are cheap correction points.** Even mid-pairing, "show me the approach
  first" catches the wrong path before it's expensive.
- **Make "done" objective wherever you can.** A failing test, a type, a concrete
  example. The more objective, the less you read to trust it.
- **Give it eyes and hands (tools / MCP).** Let it run the tests, hit the build,
  read the DB schema, query the API. An agent that can *check itself* is a
  different animal than one guessing.
- **Encode repeated judgment into reusable artifacts.** Skills (slash commands),
  role/system prompts (a good *reviewer* prompt), house style. A great reviewer
  prompt outscales ten great task prompts.
- **Use subagents for breadth.** Fan out a search across many files and keep the
  conclusion, not the file dumps — your main context stays clean.
- **Verify in tiers, cheapest first:** compiler/types → tests → lint → human
  read. Push as much down to the first three as possible.
- **Keep diffs small and single-concern.** Optimize for the reviewer (often
  future-you). If you can't describe it in a sentence, it's two tasks.
- **Match comment density to the surrounding code.** Over-commented output is a
  tell and a review tax.

### 4. Failure modes to name out loud (so people recognize them)
- **[S]** Confident hallucination of APIs/flags → verify the symbol exists.
- Plausible-but-wrong → the expensive bug, because it survives a skim. This is
  *why* objective checks matter.
- Reward-hacking the check → it may "make tests pass" by gutting the test; guard
  with review or mutation checks on risky changes.
- Architecture drift → it reverse-engineers your system and gets it subtly
  wrong; the more autonomous the style, the bigger this bites.
- Silent scope creep → "helpful" refactors of unrelated code; constrain it.

### 5. Find your own style (the honest close to Part 1)
- **[S]** There is no one right way. The best practitioners *switch styles by
  task*: pair on the scary code, let it drive the boilerplate, plan the big
  feature, fan out the audit.
- Two questions to pick a style for any task: **(1) How well can I specify
  "done"? (2) How cheaply can I check the result?** High on both → more
  autonomy/parallelism pays off. Low on either → stay in the loop.
- Action for the room: this week, take one real task and do it two different
  ways. Keep what fits.
- **Bridge (no push):** *"Part 2 is what happened when I pushed style (e) and
  (f) — autonomous + parallel — as far as I could for my constraints. If those
  styles don't appeal to you, Part 1 already stands on its own. Here's the road
  I took and exactly why, so you can judge whether your constraints rhyme with
  mine."*

---

## Part 2 — One approach built on top: the Dispatcher

> Framing slide: **"This is *not* the recommended way to use Claude. It's the
> answer I reached for a specific problem — running many autonomous agents on
> one feature without reading every line they write. Steal the ideas that fit;
> ignore the rest."**

### 6. The problem I was solving (and the constraints that shaped it)
- **[S]** I wanted style (e)+(f) at scale: batch a whole feature's worth of
  tasks across isolated sessions, in dependency order, and only spend my
  attention where it's load-bearing.
- My constraints: small team (so no RBAC/HA complexity needed), but regulated /
  ISO-27001-adjacent software (so *auditability* and *earned trust* matter a
  lot). Those constraints drive nearly every decision below — **if yours
  differ, your answers should too.**
- The dispatcher = an orchestrator: a `tasks.yaml` → each task in its own git
  worktree/branch → verify → integrate, in parallel with dependency ordering.

### 7. Decision: isolated worktrees + a run-level feature branch (pr-mode)
- **[S]** Each task gets its own worktree/branch; tasks PR into a *run-level
  feature branch*, not straight to main.
- **Why:** isolation lets parallel tasks not corrupt each other; the feature
  branch is a whole-feature staging area to review/gate; PRs give the normal
  GitHub review surface (+ reviewer bot) for free.
- **Dependency-merge rule:** a dependent task's worktree gets its dependencies'
  branches merged at dispatch, so it builds on real upstream work, not a stale
  base — avoiding end-of-run integration surprises.

### 8. Decision: a two-stage gate — mechanical first, LLM second
- **[S]** Every task must pass the repo's real `test:` command (**mechanical
  gate**) *before* an LLM verifier judges it against the spec.
- **Why mechanical-first:** objective truth is cheaper and more reliable than a
  judge. Red suite → no eloquent verification matters.
- **Why an LLM verifier at all:** catches "passed the tests but didn't do the
  task" — spec conformance the tests don't encode. Produces a *gap list* that
  re-spawns the Tasker, bounded by a retry cap.
- **The honest scar:** the verifier gave 7 truncation false-positives on a huge
  diff in one run — which directly motivated the contract-first pivot below
  (*shrink what the judge must read*).

### 9. Decision: a risk classifier that decides autonomy
- **[S]** Not all changes deserve equal trust. Score each task by **effective
  diff size** + a **path denylist**.
- **Effective diff excludes test and generated code** — to *encourage* tests and
  not punish codegen. A 2,000-line generated client is low-risk; 50 lines in the
  auth path is not.
- The size threshold is admittedly arbitrary — *and that's fine.* It's a
  tripwire that routes, not a law that judges.
- **Path denylist** flags security-critical/load-bearing files (auth, money,
  migrations) → human review regardless of size.

### 10. Decision: tiered approval — self-approve low risk, escalate the rest
- **[S]** Low-risk PRs: dispatcher self-approves + merges. Elevated: requires
  **external approval** (our PR-reviewer bot). Critical: **human gate.**
- **Why:** the Part 1 heuristic, mechanized — *autonomy earned by checkability.*
- **Why a separate reviewer bot, not self-review:** independence. A second model
  with a different prompt catches what the author rationalized. (Fallback
  reviewer tiers if the primary's down.)

### 11. Decision: a hash-chained journal
- **[S]** Every dispatch/spawn/verify/merge is an append-only, hash-chained
  JSONL event.
- **Why:** auditability without trust — for regulated software, "what did the
  machine do, in what order" must be tamper-evident and reconstructable. The
  journal *is* the run; status/report/**resume** read off it.

### 12. Decision: no-deferral disposition queue
- **[S]** Findings/deviations can't be silently dropped — each gets a recorded
  disposition (accept / reject / defer-with-reason).
- **Why:** "we'll get to it" is where quality dies; forcing a disposition keeps
  the backlog honest and the review surface finite.

### 13. Decision: notifications instead of polling (ntfy / Slack)
- **[S]** When a run needs a human (gate/block/escalation), it pushes.
- **Why:** the failure I actually hit was a run stalling ~a day because I didn't
  know it needed me. If autonomy has a ceiling, the ceiling must page you.

### 14. The pivot: contract-first decomposition with audited deviations
> The most important "why," and the newest. **[S]** problem, then fix.
- **Two real features exposed the limits of everything above:**
  1. *Review burden* — thousands of lines + comments I couldn't meaningfully
     review (the wall all of Part 2 was fighting).
  2. *Architecture thrash* — a long unattended run reverse-engineered an
     implicit architecture *wrong* and spiraled for hours (legacy vs. new system
     confusion). Prose guardrails got under-read.
- **The fix — flip what's authored where:**
  - **Human authors the skeleton** — types, interfaces, state machine, mutation
    points, data-flow seams, contracts-as-tests. Small, high-leverage.
  - **The skeleton generates the plan** — the call graph *is* the task graph +
    `blockedBy`. Decomposition stops being guessed.
  - **Agents fill function bodies** against fixed contracts — bounded, parallel,
    mechanically checkable. You review the skeleton; you skim conforming bodies;
    you never read a conforming body in full.
- **Why this retires each scar:** review → the right *small* surface;
  verification → mechanical ("make the test pass"), killing the judge-truncation
  problem; architecture → enforced by types not prose (wandering becomes a *type
  error*, not a 6-hour spiral); cheap models → a fixed signature + a passing test
  is bounded enough for a fast model (Grok), reserving strong models for the
  skeleton and complex core.

### 15. Why "deviations" — not rigid contract-first
- **[S]** Pure contract-first is too rigid: the human's architecture is often
  wrong, and *the agent hitting reality is who discovers it.*
- **Rule:** an agent **may** alter a contract — *if it logs a deviation.*
  Conformance default; deviation = deliberate, reviewed exception.
- **The deviation log is the single highest-signal review surface** — each entry
  is where design met reality and they disagreed.
- **Double feedback loop:** *design wrong* → update skeleton / *contract too
  tight* → loosen process / *agent wrong* → reject + reinforce.
- **Three anti-drift rules:** (1) type by **blast radius** — internal = free,
  *shared* contract = blocks dependents + review now; (2) **deviation costs an
  escalation** — wanting to deviate bumps a cheap model up to a stronger
  model/human; (3) **deviation *rate* is an alarm** — many ⇒ under-designed
  skeleton ⇒ redesign, don't patch.

### 16. Honest limits (credibility — say them)
- **[S]** Integration/seam behavior still needs real e2e tests; correctly-
  contracted functions can be wrong *together.*
- Contract quality is load-bearing — weak test ⇒ subtly-wrong-but-green code
  (argues for mutation checks).
- Authoring a good skeleton is expert work — but it's the *right* place to spend
  human effort, and far less volume than reviewing all the code.

### 17. The throughline / close
- **[S]** Every Part 2 decision answers one question: **how do I trust the
  output without reading every line?** That's the same question Part 1's
  "checkability" heuristic asks — Part 2 just industrializes one answer to it.
- **It's not "let the AI write the code." It's "design the system so correctness
  is cheap to check, then let the AI fill it in."**
- **Take-home:** even if you never run a dispatcher, the transferable ideas are —
  *make done objective, match autonomy to checkability, review the design not
  the diff, and keep an audit trail.* Use them in whichever Part 1 style you
  picked.
- **[DEMO]** The live experiment: skeleton task → review the skeleton → fan out
  body-fills → deviations surface → merge (the dual-backend FullSwing run).

---

## Appendix / backup slides
- Architecture diagram: tasks.yaml → planner → worktrees → gate (mechanical +
  LLM) → risk classifier → tiered approval → journal → merge.
- "We eat our own dogfood": the two logged dispatcher bugs + fixes (feature
  branch not pushed; stale local feature ref).
- Why YAML+journal over JIRA today, and the path to a JIRA/web front-end later.
- Model-tiering economics: strong model on the skeleton, cheap on the leaves.
- A "try-it-yourself" slide for Part 1: 5 concrete starter prompts, one per
  working style, the audience can paste in tonight.
