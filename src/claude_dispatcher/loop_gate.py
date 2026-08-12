"""Unit D8 — the post-implementer role check inside the orchestrator's task loop.

**P1 scaffold, P2 seals, P3 bodies — this is the P3 state.** The contract and
the five tables below are P1's and are unchanged. The two stubs are now
implemented, and the call site the scaffold could only specify is MADE:
`orchestrator._run_task` calls :func:`check_after_implementer` inside its
cascade loop, at §1's position. What P3 changed outside this module, all of it
named by the scaffold as owed and none of it in a floored or sealed file:
`orchestrator.py` (the hook, one `TaskSnapshot` field per §7(a), the row stamp,
the `RunConfig` flag), `unblock.py` (§7(c), plus dispute P2-6 — see §7),
`journal.py` (one event type) and `cli.py` (the flag that turns the gate on).
Every ruling below is P1's; where P3 had to decide something P1 did not settle,
it is marked **P3** and raised as a dispute rather than settled quietly.

Every citation below carries `Measured under:` or `Predicted (unmeasured)
under:`. The revision is `81591e4` (`feat/D1-role-protocol`, the base of
`feat/D8-loop-gate`) unless a line says otherwise.

Why this unit exists — the module it hooks into already said so
===============================================================
`role_protocol`'s own header, unprompted, under "Wiring, and what is enforced
today":

    **NOT wired, stated rather than implied:** the post-implementer call the
    P1 rulings name as the point that actually saves a build cycle —
    :func:`check_branch` inside the orchestrator's task loop, right after the
    implementer returns and before verify — has no call site yet. Until it
    does, a role's diff is checked at PR time and in CI only, which is one
    build cycle later than the plan wants.

Measured under `81591e4`: `orchestrator.py` imports `role_protocol` at module
level (line 50) and calls exactly two of its functions — `validate` and
`agent_correlation_warnings`, both at lines 477-478 inside `execute`, i.e.
**plan time, before the first task is dispatched**. `check_branch` has no
caller in `orchestrator.py` and none in `plan.py`; the only production callers
are `role_protocol.main` and, through it, `scripts/check_body_branch.sh`.

**This is the last instance of the pattern this whole lineage has been
chasing**, and it is worth naming as such rather than treating as one more
wiring chore. D5 built a reachability mechanism nothing called. D6 built a Go
row nothing enrolled. D7 enrolled it and found the gate still had no
production caller until P4 wired step 6 of `check_branch`. Each time the
mechanism was correct, complete, sealed — and not invoked at the point where
it would have changed an outcome. `check_branch` is now the mechanism in that
position: it is the most heavily sealed function in this package and it runs,
today, only after a build cycle has already been spent. The gate is not
absent. It is late.

What "late" costs, concretely and measured
------------------------------------------
Measured under `81591e4` by reading `orchestrator._run_task`: between the
implementer returning and the branch reaching a PR, the dispatcher may spawn
up to five more agent sessions into the same worktree, four of which commit —
`_retry_for_commit` (line 1379), `_retry_for_test_fix` (line 4264, inside the
mechanical gate), `_spawn_verifier_iterate` (line 2947) and
`_spawn_panel_iterate` (line 2528) — and then runs a cross-family panel whose
reviewer spawns are billed per task. A BODIES branch that wrote to `tests/**`
in its first commit pays for every one of those before anything says so.

Contract surface
================
Five tables and two stubs. The tables are DATA and are implemented (see
"What is implemented rather than stubbed"); the stubs are the control flow,
which a scaffold does not write.

  * :class:`LoopGateDecision` — what the task loop does next. Two states.
  * :class:`LoopGateStatus` — why. Eight states, exhaustive, none of which
    reads as a pass by omission.
  * :data:`_DECISIONS` / :func:`decision_for` — status → decision, total.
  * :data:`_VERDICT_STATUSES` / :func:`status_for_verdict` — the
    :class:`~claude_dispatcher.role_protocol.DiffVerdict` a `check_branch`
    call returned → status, total.
  * :data:`_BLOCKED_REASON_PREFIXES` / :func:`blocked_reason` — the string the
    review queue prints, distinct per status.
  * :func:`sole_role` — the batch ruling, as a function, because a batch is
    one branch and `check_branch` takes one role.
  * :data:`ROW_STAMPS` — the row keys this gate writes, named here so
    `unblock` can clear them.
  * :class:`LoopGateInputs`, :class:`LoopGateOutcome` — the two records.
  * :func:`resolve_inputs`, :func:`check_after_implementer` — the control
    flow. Stubs at P1; implemented at P3, to the four steps each docstring
    already carried.

Two things this unit does not do, stated so a later reader does not have to
infer it: it does not weaken, widen or add a parameter to
:func:`~claude_dispatcher.role_protocol.check_branch` — where the loop needs a
different question answered it supplies different ARGUMENTS, which is a
facility `check_branch` already publishes; and it enrols nothing and does not
touch :data:`~claude_dispatcher.role_protocol.FLOOR_GLOBS` (see "The floor,
measured" below for what is owed instead).


1. THE HOOK POINT — the function, the state, and what is on the branch
=====================================================================
**Function:** `orchestrator._run_task`, inside its cascade loop
``for idx, (attempt_agent, attempt_effort) in enumerate(cascade):`` (opens at
line 1215).

**Exact position:** between line 1411 ``if final_status != plan_mod.DONE:
break`` and line 1414 ``# --- Mechanical gate ---``. Measured under `81591e4`;
line numbers are a convenience and the two statements are the anchor.

**State at that moment, measured by reading the function top-to-bottom:**

  ============================= =============================================
  name                          what it holds at the hook
  ============================= =============================================
  ``wt``                        the task's worktree. ``wt.branch`` is the ref
                                under judgement; ``wt.path`` is the checkout
  ``wt.branch``                 has commits — proven, not assumed: the
                                commit-retry at line 1372 already ran
                                ``_has_commits_on_branch`` and blocked the
                                task if none appeared
  ``pre_spawn_sha`` (line 1194) ``wt.branch``'s tip taken immediately BEFORE
                                the cascade. ``None`` on any git failure
  ``feat_baseline_sha`` (1110)  the post-dependency-merge tip, or ``None``
                                when nothing was merged
  ``base_sha_before`` (~1126)   ``cfg.base_branch``'s tip before the spawn
  ``result``                    the implementer's ``SpawnResult``; exit 0
  ``s``                         the parsed summary; not malformed
  ``final_status``              ``plan_mod.DONE`` — the hook is not reached
                                otherwise
  ``snap``                      the frozen ``TaskSnapshot``; ``snap.batch_keys``
                                names every row sharing this one branch
  ============================= =============================================

**Written to the branch by then:** the INT-4 dependency merges (line 1088,
*before* the implementer — other tasks' work, possibly other roles'), this
cascade rung's implementer commits, and a commit-retry commit if line 1379
fired.

**Not yet written:** everything the mechanical gate's `_retry_for_test_fix`
commits, everything `_spawn_verifier_iterate` commits, everything
`_spawn_panel_iterate` commits, the push, the PR. That is the whole argument
for "before verify" rather than "after": four later spawns write to this same
branch, and a violation found after them cannot be attributed to the agent
that committed it.

CHOICE — rejected: hook BEFORE `_resolve_summary` (line 1406). Rejected
because a task the agent itself declared Blocked or Escalated already has a
human's attention and a reason; adding a second, mechanical reason to the same
row buys nothing and costs a git diff on every failed task.

CHOICE — rejected: hook AFTER the mechanical gate. Rejected on a measured
fact, not a preference: `_verify_mechanical_and_maybe_retry` spawns
`_retry_for_test_fix`, which commits. A gate placed after it judges a diff two
agents wrote and reports one agent's key.

CHOICE — rejected: hook OUTSIDE the cascade loop, once, after ``break``.
Rejected because a cascade rung resets the worktree to ``pre_spawn_sha``
(line 1229, ``_reset_worktree``): a gate outside the loop would only ever see
the surviving rung, so a rung that committed to `tests/**` and was then
discarded for an unrelated quality failure would never be reported at all. The
protocol breach is a fact about the agent, not about the surviving diff.


2. WHAT A VIOLATION DOES TO THE TASK
====================================
**Ruling: Blocked, with a distinct `blocked_reason`, and NO cascade
escalation.** :data:`LoopGateStatus.CHECKED_VIOLATION` →
:data:`LoopGateDecision.BLOCK`.

The dispatcher's Blocked state is exactly this shape, measured in
`unblock.py`: `dispatcher blocked` prints the queue and exits 3 (line 90);
`dispatcher unblock` flips Blocked → To Do, clears the previous attempt's gate
stamps, optionally attaches a human note to the description, and its own
closing line says *"All gates re-run: unblocking grants a retry, not a
waiver"* (line 152). A role violation is precisely a thing a human adjudicates
once and an agent then re-earns.

**The alternative, weighed honestly.** Failing the task outright — a terminal
status with no clearing path — would lose the branch's work. Measured, that is
not a small loss: at the hook the branch carries the dependency merges plus a
whole implementer session, and the diff is also the *evidence*. A body agent
that edited a seal has produced something a human needs to read before
deciding whether the seal was wrong. Blocked keeps the branch, keeps the
worktree, and puts the row in front of a person, which is what the state
exists for. Failing outright optimises for a tidy worklist over a recoverable
one.

**Why not the cascade.** The loop's other gates escalate to the next
implementer rung on failure (mechanical at 1418, seal at 1440, verifier at
1513, panel at 1615). This one must not, on two measured grounds. First,
`_reset_worktree(wt, pre_spawn_sha, ...)` at line 1229 DISCARDS the rung's
diff before the next rung starts — so cascading on a violation destroys the
evidence of the violation before any human sees it, and the row's
`blocked_reason` would then describe a diff that no longer exists. Second, the
cascade's premise is that a stronger model produces better work; a role
violation is not weak work, it is out-of-scope work, and the same task
description handed to a stronger model has the same scope.

CHOICE — rejected: cascade on VIOLATION, so a second rung gets a chance to
stay in its lane. Rejected for the two reasons above; the second rung's
prompt would have to carry "you edited files you may not edit", which is the
self-report this whole unit replaces.

CHOICE — rejected: a warning only, letting the task proceed to PR where
`check_body_branch.sh` will catch it. Rejected because that is the status quo
with extra logging: the build cycle is still spent, which is the one thing the
hook exists to save.


3. WHAT UNDETERMINED DOES
=========================
**Ruling: Blocked, with a `blocked_reason` DISTINCT from a violation's.**
:data:`LoopGateStatus.CHECKED_UNDETERMINED` → :data:`LoopGateDecision.BLOCK`,
prefix ``role_diff_undetermined`` and not ``role_diff_violation``.

The precedent transfers. `check_branch`'s own contract, in its own words:
*"a BLOCKING unchecked signature status when the role is BODIES — a signature
check that started and could not finish, on the role whose gate that is, is
not a pass"*, and `branch_reachability`'s: *"on the ONE role whose gate it is,
a check that could not finish is not a pass"*. The loop is a third
enforcement point for the same decision and cannot hold the opposite view of
"I could not check" without the three points disagreeing on the same branch —
which is invariant 1's failure mode, one layer up.

Distinct reasons, because `check_body_branch.sh` already spends an exit code
on this distinction (measured, `role_protocol.ExitCode`: 2 for violation, 3
for undetermined, with the script's own comment *"a CI job that cannot tell
'violation' from 'could not check' will treat one as the other"*). A review
queue that collapses them makes the human's first question — is this a
misbehaving agent or a broken environment — unanswerable from the queue.

**And UNDETERMINED here is not rare.** Measured under `81591e4`: the D7
reachability arm engages only when a changed path has an
`call_site_reachability.ANALYZERS` row, and `ANALYZERS` is
``(GoReachabilityAnalyzer,)`` — one row, Go. On a Go tree the arm sweeps, and
`branch_reachability`'s own P4 ruling (module docstring, line 259) records
**445 s per sweep and two sweeps per check**, plus the finding that on a host
whose toolchain the tree outgrows the sweep does not merely slow down, it
abstains. Its conclusion, quoted because this unit must not contradict it:
*"the first week of UNDETERMINED-on-every-branch is the week the waiver
becomes routine, and that is not recoverable by later fixing the host."*

That is not an argument for making UNDETERMINED a pass. It is an argument for
the gate being **opt-in per run**, which is :data:`LoopGateStatus.NOT_ENABLED`
below — a named state, logged and journaled on every task, never a silence.
Blocking on UNDETERMINED is safe precisely because a run that cannot afford it
does not turn it on; a gate that answers UNDETERMINED loudly and off by
default is recoverable, and a gate that answers CLEAN quietly is not.

CHOICE — rejected: UNDETERMINED → PROCEED with a logged warning. Rejected
because it is the vacuous-seal shape one layer up: the row would carry a
`role_diff_loop` stamp for a check that never ran, and the next reader of that
row would take the stamp for a verdict. The whole point of
:class:`~claude_dispatcher.role_protocol.DiffVerdict` having three members
rather than two-plus-null is that this state has a name.

CHOICE — rejected: UNDETERMINED → PROCEED only when the reason is the
reachability arm, BLOCK otherwise. Rejected because the loop would then be
re-deriving which arm produced the answer, from a `detail` string — a second
notion of "why is this undetermined" that can disagree with
`check_branch`'s. If the reachability arm's cost is the problem, the fix is in
`branch_reachability` (its own escalation 2, "the second sweep must stop
costing a first sweep"), not a special case here.


4. WHICH ROLES ARE CHECKED, AND AGAINST WHAT BASE
=================================================
`check_branch(repo_root, base_ref, branch_ref, role, *, spec, policy, run)`
needs four positional facts. Where the loop knows each:

``repo_root``
    the `_run_task` parameter of that name. Free.

``branch_ref``
    ``wt.branch``. Free.

``role``
    **the loop does not know it today.** Measured under `81591e4`:
    `TaskSnapshot` (orchestrator.py:269) is a projection of `plan.Task` and
    carries no ``raw`` and no ``role``; `plan.Task` carries ``raw`` but models
    no ``role`` field either, deliberately (`role_protocol`'s "Notes for the
    seal author": *"P1 deliberately does not add a `role` field to `Task`"*).
    Owed: one field on `TaskSnapshot`, populated where the snapshot is built,
    from `role_protocol.parse_task_role_spec(t.raw, task_key=t.key)`.
    The precedent for reading an unmodeled row field at that exact spot is
    measured and adjacent: ``cfg.model_router(str(primary.raw.get("risk")))``
    at orchestrator.py:2396, four lines above the `TaskSnapshot(...)` call.

    Reading it **at dispatch time and freezing it** is not incidental. It is
    what makes the ADJUDICATE case safe: `TaskSnapshot`'s own docstring says
    *"a frozen copy of one task's data captured at dispatch time"*, and an
    adjudicate row's ``disputed_paths:`` IS its writable set. Frozen before
    the implementer runs, the branch cannot widen its own gate by editing the
    worklist — which is `check_branch`'s invariant-6 concern
    (`_task_role_spec_at_base`) reached by a different and, here, sufficient
    route. Note what is NOT claimed: this is weaker provenance than PR time,
    which reads the row out of the protected base's object store. See §5.

    **The batch problem, and it is real.** A batch group shares ONE worktree,
    ONE branch and ONE implementer session (`_take_batch_group`, line 902;
    `_combined_batch_description`, line 925: *"All succeed or all fail
    together"*). `check_branch` takes exactly one role. Measured under
    `81591e4` with a constructed worklist: unit A's BODIES row and unit B's
    SCAFFOLD row sharing ``batch_id: MIX`` load through `plan.load_tasks` with
    **zero errors and zero warnings** from `role_protocol.validate`, are both
    returned by `runnable_now`, and are returned as one group by
    `_take_batch_group` — one branch, two roles.

    Ruling: :func:`sole_role` returns ``None`` and the gate answers
    :data:`LoopGateStatus.ROLE_UNRESOLVED` → BLOCK. It does NOT pick the
    primary's role. Picking would judge unit B's scaffold work under unit A's
    BODIES rule, and the two rules deny different things, so the answer would
    be wrong in both directions on the same branch. Escalated to §7: this
    should be a plan-time refusal in `role_protocol.validate`, which is a
    floored file and therefore a P4 amendment.

``base_ref``
    **the hard one, and the ruling is ``pre_spawn_sha``** — the branch's own
    tip immediately before this cascade rung's implementer spawn
    (orchestrator.py:1194).

    Rejected, and each for a measured reason:

      * ``cfg.base_branch``. This is the spelling that has already cost this
        project three false-divergence alarms (recorded: *"panel/recheck diffs
        MUST use origin/main, not stale local main"*), and the loop has a
        worse version of the same problem — the base may move under a run that
        auto-integrates other tasks into it while this task is in flight
        (`auto_integrate.integrate`, called at line 1660). Worse still, it is
        wrong even when it is fresh: measured, `wt_mod.merge_dependencies`
        (line 1088) puts every blockedBy dependency's commits on this branch
        BEFORE the implementer runs, so a diff from `cfg.base_branch` contains
        another task's work — and in this protocol the dependency of a BODIES
        task is, by PO-2, its unit's SEALS task. Diffing from
        ``cfg.base_branch`` would report the seals author's `tests/**` commits
        as the body author's violation, on every well-formed unit.
      * ``base_sha_before``. Pins the base against movement, and keeps the
        entire dependency-merge problem.
      * ``feat_baseline_sha``. Right idea — it is defined (line 1110) as the
        post-merge tip *precisely* so merged dependency commits are not
        miscounted as the Tasker's own work — but it is ``None`` whenever
        nothing was merged, and it does not move on a cascade retry, so on
        rung 2 it would re-attribute rung 1's discarded work.
      * ``pre_spawn_sha``. Defined for the cascade and used by it: line 1229
        resets the worktree to exactly this SHA to start a new rung. So
        ``pre_spawn_sha...wt.branch`` is, by construction, this rung's
        implementer work and nothing else. It is a SHA, so it cannot move.

    ``pre_spawn_sha`` is ``None`` on any git failure (`_branch_sha` returns
    ``None`` and logs, line 3235). Ruling: that is
    :data:`LoopGateStatus.BASE_UNRESOLVED` → BLOCK. There is no fallback to
    ``cfg.base_branch``: a fallback base is a different question, silently
    answered, and the answer would be the wrong one described above.

``policy`` (keyword)
    **loaded from ``cfg.base_branch``, not from ``base_ref``.** This is the
    one place the loop must supply an argument rather than let `check_branch`
    derive it, and the reason is invariant 6: step 1 of `check_branch` loads
    the policy from ``base_ref``, and ``base_ref`` here is a commit on the
    task's own branch. A branch that edited `.dispatcher.yaml` in its
    dependency merge would then supply the policy that judges it.
    `check_branch` already publishes the seam — ``policy`` given *"wins
    verbatim — a PR-time pass and a task-loop pass cannot disagree if they can
    be handed the same one"*, its own step 1 comment — so the loop calls
    `load_role_policy_from_base(repo_root, cfg.base_branch)` and passes the
    result.

    CHOICE — rejected: pass ``base_ref=cfg.base_branch`` so `check_branch`
    loads the policy itself. Rejected because ``base_ref`` also bounds the
    DIFF (step 3) and the signature merge-base (step 5); using it to fix the
    policy would break the diff, which is the whole finding above.

    CHOICE — rejected: add a ``policy_ref`` parameter to `check_branch`.
    Rejected under this unit's standing rule — the loop asks a different
    question with the arguments it already has, and does not reshape the gate
    to suit itself.


5. IDEMPOTENCE, AND WHICH CHECK WINS
====================================
**Ruling: they are not the same check, they CAN disagree, and PR time wins.**

They are not duplicated work because they judge different diffs against
different bases with differently-sourced policy:

  ==================== ================================ ====================
  fact                 loop time (this unit)            PR time / CI
  ==================== ================================ ====================
  base                 ``pre_spawn_sha`` — one rung     the protected base
  diff contains        one implementer session          everything on the
                                                        branch: dependency
                                                        merges + every later
                                                        iterate spawn
  policy from          ``cfg.base_branch``              ``<base>`` (the
                                                        script's ``$1``)
  role/spec from       the frozen `TaskSnapshot`,       the row in
                       i.e. the working-tree worklist   ``<base>``'s object
                       as it stood at dispatch          store
  gate's own code      the running process              re-read from
                                                        ``<base>`` when the
                                                        checkout supplies it
  ==================== ================================ ====================

Measured directions of disagreement:

  * **loop CLEAN, PR VIOLATION** — expected and routine. Four spawns commit to
    this branch after the hook (§1), and the dependency merge predates it. The
    loop never saw those paths.
  * **loop VIOLATION, PR CLEAN** — possible only if the forbidden edit landed
    on the protected base in the interval, i.e. someone made the reviewed
    amendment `DEFAULT_ROLE_RULES` describes as the one escape hatch. That is
    the hatch working, not the gate failing.

**PR time wins**, for three reasons that are all provenance: it judges the
diff that will actually land; it reads its policy and its ADJUDICATE writable
set out of the protected base rather than out of a working tree; and when the
checkout supplies the gate's own code, it re-reads that code from the base
too (the 2026-08-09 S1 block in `check_body_branch.sh`). The loop has none of
those three properties and cannot acquire them without becoming the PR check.

The consequence is a naming rule, not a note: the row stamp this gate writes
is ``role_diff_loop``, never ``role_diff``. A stamp that reads like the
verdict is a stamp somebody will treat as one, and a loop CLEAN is not a
waiver for anything. :data:`ROW_STAMPS` is that decision as data.

**What stays unchecked, named rather than left silent.** The iterate spawns
(§1) commit after the hook and before the PR, and this unit does not check
them. Naming it here is not a substitute for fixing it; it is the thing
`role_protocol`'s "NOT wired" paragraph did for this hook, and it worked. Owed
to §7.


6. COST
=======
Measured under `81591e4`, wall clock, via `scripts/check_body_branch.sh`:

  * a 42-path BODIES branch pair on this repository (``2822a5b...81591e4``):
    **0.389 s**, VIOLATION, 34 forbidden paths and one changed signature. The
    D7 arm did not run, and its non-run is reported rather than assumed —
    the report line is the named skip `check_branch`'s step 6 describes.
  * a clean single-Python-file BODIES branch: **0.328 s**, CLEAN, with the
    reachability arm answering ``no_analyzable_file_in_diff``.

So on this tree the gate is free, and the second measurement shows why:
`ANALYZERS` is ``(GoReachabilityAnalyzer,)`` and a diff with no Go file exits
the expensive arm before it sweeps. Measured, not assumed.

On a Go tree it is not free. `branch_reachability`'s module docstring
(line 259, P4 2026-08-12) records **445 s per whole-tree sweep, two sweeps per
`check_branch` call — of the order of fifteen minutes per BODIES branch on the
primary target** — and rules that the gate must not go in front of that
repository's BODIES branches until the host toolchain is fixed and the base
sweep can be cached. This unit does not overrule that and must not be read as
doing so.

**Ruling on slowness: a per-task deadline, and exceeding it is a NAMED state
that BLOCKS.** :data:`LoopGateStatus.DEADLINE_EXCEEDED` →
:data:`LoopGateDecision.BLOCK`, with its own `blocked_reason` prefix.

A deadline that returns CLEAN is a gate that switches itself off exactly when
it is slow — and it is slow on precisely the trees where the expensive arm is
doing work. That is the vacuous-seal shape wearing a stopwatch. A deadline
that returns UNDETERMINED-shaped BLOCK is a gate that says "I ran out of time"
and hands the row to a human, which is a true statement somebody can act on.

CHOICE — rejected: a deadline whose expiry PROCEEDs with a warning. Rejected
per the paragraph above.

CHOICE — rejected: no deadline at all. Rejected because `_run_task` runs
inside a `ThreadPoolExecutor` worker (`_dispatch_drain`, line 2310) with
``max_workers=cfg.max_parallel``; a fifteen-minute uninterruptible call holds
a dispatch slot, and the run's only liveness signal is a separate heartbeat
thread, so the run would look alive while a quarter of an hour of nothing
happened per task.

**What the deadline costs, measured, and why it is not implemented here.**
`check_branch` is an ordinary Python call with no timeout parameter and this
unit may not add one. CPython cannot interrupt a running call in another
thread. So a real deadline needs the check to run in a killable process. The
two available process faces both cost something measured:

  * `scripts/check_body_branch.sh` — killable, and it brings the base-pinned
    gate-code provenance for free. But its argument contract is
    ``<base> <branch> <role> [--tasks PATH --task-key KEY]``, where ``<base>``
    is used for the diff bound, the policy AND the row, all three. §4's whole
    ruling is that those three want two different refs, and the script offers
    one. Passing ``pre_spawn_sha`` as ``<base>`` would take the policy and the
    adjudicate writable set off a commit on the branch under judgement.
  * a new module-level entry that accepts a frozen spec and a separate policy
    ref, run with `subprocess` — correct, and it is new machinery.

The scaffold therefore NAMES :data:`LoopGateStatus.DEADLINE_EXCEEDED`, rules
its decision, and records the mechanism as owed (§7). Until it exists the
state is unreachable, which is itself a thing a seal can and should assert
rather than a thing a reader should have to discover.

CHOICE — rejected: rule for the script face now and accept the weaker base.
Rejected because it silently re-introduces the invariant-6 hole §4 closes, in
exchange for a deadline that matters only on trees where §3's ruling says the
gate should not be enabled yet.


7. THE FLOOR, MEASURED — and what this unit owes
================================================
**The floor-closure seal does NOT fire for this unit.** Measured under
`81591e4`: a probe call to `role_protocol.check_branch` inserted into
`orchestrator._run_task` at the hook point, then
``PYTHONPATH=src python3 -m pytest -q -o addopts="" tests/test_floor_closure.py
tests/test_d5_floor.py tests/test_role_protocol_floor.py`` → **183 passed, 0
failed**. The reason is structural and worth stating so nobody re-measures it
by accident: `tests/test_floor_closure.py` seeds its walk at
``_FLOOR_DECISION_ROOTS = ("check_branch", "_floor_glob_named_by")`` and
follows imports DOWNWARD, out of those functions. The orchestrator is a
CALLER, not a delegate. Nothing about calling a floored function puts the
caller in the closure. (`orchestrator.py` already imports `role_protocol` at
module level — line 50 — so the wiring adds no import either.)

**That is not the same as safe, and this is the escalation.** `loop_gate.py`
decides whether a VIOLATION actually stops a task. A BODIES branch may write
`src/claude_dispatcher/loop_gate.py` and `src/claude_dispatcher/orchestrator.py`
today — measured: neither matches any entry of
`role_protocol.FLOOR_GLOBS`, and `DEFAULT_ROLE_RULES` denies BODIES `tests/**`
and the schema paths, not `src/`. So a body agent can turn
:data:`LoopGateDecision.BLOCK` into ``PROCEED`` with a one-line edit and be
judged by the gate it just switched off. That is the shape this lineage has
recorded twice — *"a branch could delete the floor from this module and then
walk through it (measured, 2026-08-08)"* — arriving through the caller instead
of the callee.

**What is owed, measured exactly.** Adding
``**/src/claude_dispatcher/loop_gate.py`` and
``**/src/claude_dispatcher/orchestrator.py`` to `FLOOR_GLOBS` and changing
nothing else: **1 failed / 182 passed**, and the single failure is
``tests/test_role_protocol_floor.py::
test_the_floor_is_exactly_the_written_out_set_of_globs``, naming both new
globs as unsealed. So the owed work is precisely: two `FLOOR_GLOBS` entries in
`role_protocol.py` (a floored file → **P4 amendment, not a P3 edit**) plus
their rows in ``_FLOOR_ROWS`` / ``_FLOOR_x_ROLE_ROWS`` in
`tests/test_role_protocol_floor.py` (a seal file → BODIES may not touch it),
in one commit, because either half alone is red. `tests/test_floor_closure.py`
needs no row: neither module is a delegation target.

Recorded rather than landed, per this unit's instructions. Note the glob
spelling must be PATH-QUALIFIED for the reason `FLOOR_GLOBS` re-measures at
every entry: ``**/orchestrator.py`` would also match
``vendor/thirdparty/orchestrator.py``, and a floor has no override.

**The rest of what is owed, from the sections above.**

  a. **LANDED (P3).** `TaskSnapshot` gains ``role_specs`` — the frozen
     :class:`TaskRoleSpec` of every row in the dispatched group, not the
     primary's only, because the batch shares one branch and §4's refusal
     needs to SEE both roles. Populated at the `_dispatch_drain` construction
     site from `role_protocol.parse_task_role_spec(t.raw, task_key=t.key)`, in
     the loop that already reads ``primary.raw`` for the risk tier. A row that
     will not parse is left OUT of the list rather than defaulted, so the gate
     answers ROLE_UNRESOLVED and blocks. Landed before the §7 floor entries,
     so it was a P3 edit; after them it would have been P4.

     **P3 finding, and it is about this owed item rather than about the code
     — dispute P3-3.** The scaffold says (a) is a P3 edit unless it lands
     after the floor entries. Measured: the FLOOR is not what makes it P4.
     Adding a field to a `@dataclass` CHANGES that class's signature, and
     `check_branch`'s step 5 refuses a changed signature on BODIES. So this
     very commit, judged by the gate it wires — role BODIES, base
     ``6d94190``, branch ``feat/D8-body`` — answers **VIOLATION: 0 forbidden
     path(s) and 2 changed scaffolded signature(s)**, naming
     ``orchestrator.RunConfig`` (gained ``enable_role_loop_gate``) and
     ``orchestrator.TaskSnapshot`` (gained ``role_specs``). Both fields are
     items this owed list ASKED P3 for. No path violation: the block is
     entirely the signature rule.

     That is the gate working, not misfiring — a body author really did widen
     two scaffolded records. What is wrong is the assignment: an owed item
     that adds a dataclass field cannot be a BODIES edit under this protocol,
     whatever the floor says. P4 owes a ruling — the orchestrator half of this
     unit is SCAFFOLD-shaped or ADJUDICATE-shaped work with the two records in
     its ``disputed_paths:``, or (a) moves to P4 with the floor entries for a
     second, independent reason. Recorded here because the alternative is a
     unit whose own gate refuses its own owed list, discovered later by
     whoever first switches the gate on.

     **RULED (P4, 2026-08-12) — dispute P3-3. P3's diagnosis is adopted in
     full, and the ruling is written to generalise, because this will recur.**
     Reproduced by P4 at ``90ddca0``, role BODIES, base ``6d94190``: VIOLATION,
     ``0 forbidden path(s) and 2 changed scaffolded signature(s)``, naming
     ``RunConfig`` (gained ``enable_role_loop_gate``) and ``TaskSnapshot``
     (gained ``role_specs``). No path violation. The block is entirely step 5.

     **THE RULE. An edit that changes a scaffolded signature is SCAFFOLD work.
     It may not appear on an owed list handed to P3, and no ordering of
     commits makes it legal.**

     TWO INDEPENDENT TESTS disqualify BODIES, and the scaffold applied only
     one:

       1. **the floor test** — does the edit touch a :data:`~claude_dispatcher.
          role_protocol.FLOOR_GLOBS` path? If yes, it is P4, for every role.
       2. **the signature test** — does the edit change a
          ``_scaffolded_signatures`` fingerprint of a ``*.py`` file that exists
          at the merge-base? If yes, it is not BODIES work, whatever (1) says.

     The scaffold reasoned from (1) alone and concluded (a) was a P3 edit that
     would BECOME P4 if it landed after the floor entries. That is wrong twice
     over. Order does not enter into it: step 5 compares the merge-base of
     ``base_ref`` and ``branch_ref`` against the branch tip, so a field added
     anywhere in the branch's history is a changed signature at judgement time.
     And (2) disqualifies it with the floor out of the picture entirely — which
     is the whole content of P3's finding.

     **WHERE THE FIELD BELONGS: the scaffold commit.**
     :func:`~claude_dispatcher.role_protocol._class_fingerprint` counts every
     annotated class field — name, annotation and has-default — so a dataclass
     field IS a declared type shape, and declaring type shapes is the entirety
     of what a scaffold does. The second reason is the ordering the whole
     protocol is built on: a field that arrives at P3 arrives AFTER P2 wrote
     the seals, so no seal could have bound to it. Measured here, and it is not
     hypothetical — see the routing block at the end of this docstring: no row
     in the seal file drives the orchestrator's write of either new field.

     **FOR A SCAFFOLD AUTHOR.** If your hook needs a field on a record you do
     not otherwise own, put the field in the SCAFFOLD COMMIT, typed and
     defaulted, and put it in the contract. Do not put it on the owed list.
     "Owed" is for work whose SHAPE is already declared; a field is the shape.

     **FOR A BODY AUTHOR WHO FINDS ONE ON ITS LIST.** Do not add it — escalate,
     exactly as P3 did here. The field then lands either in a fresh
     SCAFFOLD-role task on the same base (measured: step 5 gives every role but
     BODIES :data:`~claude_dispatcher.role_protocol.SignatureCheckStatus.
     NOT_APPLICABLE`, and SCAFFOLD's deny list does not cover ``src/``), or, if
     the record's file is floored, in a P4 commit. Either way it must precede
     the body commit that is judged.

     **WHICH OF THE TWO SHAPES THE BODY NAMED.** For a future unit whose record
     lives in an UNFLOORED file: SCAFFOLD-shaped, not ADJUDICATE-shaped.
     ADJUDICATE exists for disputes and an omission is not a dispute; and its
     writable set is the per-row ``disputed_paths:``, so routing a type
     declaration through it makes the declaration depend on a worklist line,
     which is the direction invariant 6 spends this whole module resisting.
     For the orchestrator SPECIFICALLY, neither shape survives this
     adjudication: as of the floor commit ``orchestrator.py`` is on
     ``FLOOR_GLOBS`` and no declaration buys it back (measured — an ADJUDICATE
     spec naming it is still refused with ``FLOOR_RATIONALE``). §7(a)-shaped
     work on the task loop is P4-only from here, which is the same fact the
     floor entry records as its accepted cost.

     **WHAT IS NOT DONE ABOUT ``90ddca0``, and why.** Reverting the two fields
     and re-landing them in a P4 commit does NOT clear the branch: step 5
     compares merge-base to tip, so a revert-and-reland leaves the net
     signature change identical and the report identical — it names the FIELD
     DIFF, not the commit. The honest disposition is recorded rather than
     engineered away: ``feat/D8-body``'s orchestrator half was never BODIES
     work, it is carried onto the adjudicate branch where P4 owns it, and a
     true gate finding is not made false by rearranging commits.

     **A GAP THIS RULING EXPOSES, named because nothing else names it.** There
     is no role under which a P4 branch comes out CLEAN. Measured on
     ``feat/D8-adj``: as BODIES, VIOLATION (the floor, plus ``tests/**``); as
     ADJUDICATE with every changed path declared, ``signature status:
     NOT_APPLICABLE`` and VIOLATION on the three floored paths alone. That is
     CORRECT by construction — ``FLOOR_RATIONALE`` says a change to a floored
     path is *"a reviewed edit on the protected base (a plan amendment), never
     a line in the branch being judged"* — but it means the adjudicator's own
     work has no mechanical check at all, which is the honour system this
     protocol replaces, one level up. Not closable inside this unit; recorded
     so the next unit that wants to close it starts from a measurement.
  b. `role_protocol.validate` should refuse a batch whose rows carry more
     than one role (§4, measured to load clean today). Floored file → P4.
     Until it lands, :data:`LoopGateStatus.ROLE_UNRESOLVED` is the only thing
     standing between a mixed-role batch and an unjudgeable branch. **P3 adds
     one case to what P4 should refuse there**: rows that share a role but
     carry DIFFERENT ``immutable_paths:`` / ``disputed_paths:`` additions are
     the same defect one level down, and :func:`resolve_inputs` refuses them
     through ROLE_UNRESOLVED for want of a better-named state. Dispute P3-1.

     **EXTENDED AND STILL OWED (P4, 2026-08-12, ruling on dispute P3-1).** P3
     is right that this is the better shape and the ruling adopts BOTH halves
     of it: `validate` owes TWO refusals, not one — a batch whose rows do not
     share a role, and a batch whose rows share a role and not a rule. Both
     are worklist defects and plan time is where a worklist defect belongs;
     the two loop states are the safety net for a worklist that reached the
     dispatcher another way, which is why they are named rather than made
     unreachable and deleted (the DEADLINE_EXCEEDED rule, applied here).

     **NOT LANDED IN THIS ADJUDICATION, deliberately.** The seal file's own
     dispute P2-3 assigns the consequence to this item's commit: *"Row 18
     measures that a mixed-role batch loads clean today, and §7(b) owes a
     plan-time refusal that will redden it. The amendment belongs to §7(b)'s
     own commit."* Landing the refusal here would make this ruling carry a
     whole owed item AND perform a seal amendment another commit is specified
     to make. Re-measured on this tree: row 18
     (``test_todays_dispatcher_really_does_hand_one_branch_two_roles``) is
     GREEN and is the reachability proof for row 17's input, so it is doing
     its job today and will redden exactly once, by design, when §7(b) lands.
  c. **LANDED (P3).** `unblock._STALE_STAMPS` gains :data:`ROW_STAMPS` — by
     splatting the constant, not by re-spelling the keys, for the reason
     dispute P2-1 gives. Measured under `81591e4` and re-measured under
     `6d94190`: `_STALE_STAMPS` listed nine keys and neither of ours, so a
     cleared row carried a stale loop verdict into its re-run.

     **And `unblock._DETAIL_FIELDS` gains ``ROW_STAMPS[1]``** — the seal
     author's dispute P2-6, which this owed list did not name. `list_blocked`
     prints ONLY the keys in `_DETAIL_FIELDS`, so without the row this gate
     would write a detail nobody can read, and :data:`ROW_STAMPS`'s own
     justification for splitting one stamp into a short verdict key plus an
     excerptable detail key would be vacuous. P3 agrees it is in scope: it is
     one line in the same unfloored, unsealed file §7(c) already hands P3, and
     it makes the scaffold's own stated reason TRUE rather than widening the
     spec. No seal asserts it — it was landed on the argument, not on a row.
  d. `role_protocol`'s module docstring must move this hook from the "NOT
     wired" paragraph into "Wired by P3", and this is MECHANICALLY CHECKED:
     `tests/test_role_protocol_wiring.py::
     test_every_wired_by_p3_claim_has_its_call_site` parses that section and
     verifies each claimed subject really calls its claimed target, and
     ``REQUIRED_WIRED_TARGETS`` pins the minimum set so a bullet cannot be
     deleted to make a claim true. Floored file + seal file → P4, exactly as
     D7's step-6 wiring was.
  e. the killable face a deadline needs (§6). Until then
     :func:`check_after_implementer` RAISES on a non-``None``
     ``deadline_seconds`` — the disjunction's honest branch, and the reason
     :data:`LoopGateStatus.DEADLINE_EXCEEDED` is still unreachable.
  f. a check of the post-hook iterate spawns (§5), or an explicit ruling that
     PR time is the only gate on them.
  g. **CLOSED (P4, 2026-08-12) — dispute P3-2, ruled FOR the unconditional
     emit.** P3 raised that §3's "logged and journaled per task" was landed at
     three quarters: logged per task, stamped on every row, journalled only
     when the gate RAN; and that emitting unconditionally reddens three rows
     pinning the EXACT per-task sequence
     (``tests/test_orchestrator_journal.py::
     test_full_run_journal_chain_and_sequence``,
     ``::test_single_task_exact_sequence``,
     ``tests/test_mechanical_verify.py::
     test_no_config_skips_and_preserves_done_flow``), which BODIES may not
     amend. Re-measured by P4 at ``90ddca0``: exactly those three, and the
     insertion point is index 3 in every one — immediately after
     ``summary_parsed`` and before ``verification_mechanical``, which is where
     the hook is.

     **The ruling, and the argument is not the precedent P3 offered.** That
     precedent does run the same way — `verification_mechanical` and
     `verification_skipped` journal their own skips and already sit in the
     sequences being amended — but a precedent is a habit, not a reason. The
     reason is that the two records P3 offered as the stronger substitute are
     the two this unit itself makes erasable. `unblock._STALE_STAMPS` POPS both
     :data:`ROW_STAMPS` (§7(c), measured at unblock.py:148-149) — deliberately,
     because unblocking grants a retry and not a waiver — so one `dispatcher
     unblock` removes the row's record that the gate was off on the attempt
     that produced the block, and run.log is an unchained text file. The
     journal is hash-chained and append-only and is the ONLY per-task record
     that survives the clearing this unit performs on itself. A named state
     whose every witness can be erased by the next command a human runs is a
     silence with a delay on it, which is precisely what NOT_ENABLED exists not
     to be.

     Landed in ONE commit with the three-line amendment, because either half
     alone is red, and falsified in both directions: guard present + seals
     unamended → those three red; guard restored + seals amended → the same
     three red. A seal amendment forced by a ruling is the one thing P4 may
     write into a seal file, and each amended row names the ruling in place.


Notes for the seal author (P2)
==============================
  * The vacuity trap here is the same one D7 named and then fell into. D7
    implemented its three verdict tables *because* a stub that raises for
    everything satisfies "raises on an unmapped member" vacuously — and the
    implemented tables then shipped a real defect, because ``x in SomeEnum``
    is a VALUE lookup on Python 3.12+, not a member test. So: assert
    totality as ``set(_DECISIONS) == set(LoopGateStatus)``, never with ``in``
    against the enum class, and prove the guard by deleting a row rather than
    by reading one.
  * Seal the hook point itself, not the tables only. The tables here are
    correct and inert; the unit's whole content is that a call exists at one
    place. The seal that matters is D7's shape:
    `test_check_branch_actually_calls_the_reachability_gate` reddens if the
    call leaves the function. Its counterpart here reddens if
    `orchestrator._run_task` stops calling this module — and it must locate
    the call by AST inside `_run_task`, because a call anywhere else in
    `orchestrator.py` is not the hook.
  * A CLEAN from this gate must never satisfy a seal that means "the branch
    is role-clean". §5 rules PR time wins; a seal that treats the loop stamp
    as the verdict encodes the opposite.
  * :data:`LoopGateStatus.DEADLINE_EXCEEDED` is unreachable until §7(e)
    lands. Assert that it is unreachable rather than skipping it — an
    unreachable named state that nobody asserts is how a state quietly
    becomes reachable with the wrong decision attached.
  * :func:`sole_role` deserves an empty-sequence row. Zero specs is not one
    role, and "the batch had no rows" must not resolve to anything.

What is implemented rather than stubbed, and why
================================================
Under the standing exception (D5 implemented `Diverge` and its validating
dispatches; D7 implemented its three verdict tables), the following are real
because a stub makes their contract untestable:

  * :data:`_DECISIONS`, :data:`_VERDICT_STATUSES`,
    :data:`_BLOCKED_REASON_PREFIXES` and their three accessor functions —
    "total over the enum, and an unmapped member raises" is not checkable
    against a function that raises for everything.
  * :func:`sole_role` — the batch ruling IS the function. A stub raising for
    every input satisfies "a mixed batch does not resolve to a role"
    vacuously, and would also satisfy "a single-role batch resolves", which
    is the half that matters.
  * :data:`ROW_STAMPS` — data, and §7(c) is owed against its exact contents.

Everything else was a stub at P1: :func:`resolve_inputs` and
:func:`check_after_implementer` are the control flow, and control flow is what
a scaffold does not write. **P3 wrote it**, and the two functions' own
docstrings carry the P3-marked decisions the four steps did not settle.

What P3 measured about its own closes, recorded because a green row is not
evidence
=========================================================================
Every mutation below was applied to this implementation in a ``cp -a`` clone
and the whole seal file re-run. Measured under `6d94190` + this commit.

  * ``base_ref=base_branch`` → 4 red (rows 1, 2, 3, 15).
    ``base_ref=pre_spawn_sha or base_branch`` → 2 red (2, 15). Dropping
    ``policy=`` → 2 red (3, 16). Letting the policy failure fall through to
    `check_branch` → 1 red (16). Disabled returning CHECKED_CLEAN → 2 red
    (13, 15). Ignoring ``deadline_seconds`` → 1 red (14). Picking the primary's
    role → 2 red (15, 17). Moving the hook below the mechanical gate → 1 red
    (4). ``continue`` on the block path → 1 red (7). Dropping :data:`ROW_STAMPS`
    from `unblock._STALE_STAMPS` → 1 red (9). Re-spelling the stamps as
    orchestrator literals → 1 red (21). Every one reproduces the seal author's
    own matrix.
  * **Three mutations of the P3 code redden NOTHING**, and they are the honest
    limits of this file's coverage: dropping the rule-equivalence guard in
    :func:`resolve_inputs` (dispute P3-1) — 22 green; making
    `orchestrator._run_task` never WRITE the row stamp while still referencing
    :data:`ROW_STAMPS` — 22 green, because row 21 reads the source and no row
    drives the orchestrator's row write; and hardcoding ``enabled=True`` at the
    call site — 22 green, because no row in this file drives the run flag.
  * **A second implementation of the gate** — `changed_paths_between` +
    `evaluate_changed_paths` inline, agreeing with `check_branch` on every
    fixture in the seal file — reddens row 22 **alone**, 21 of 22 green. P3
    re-derived that rather than taking it on trust. It means what the seal
    author said it means: closing a behavioural row here is not evidence that
    this implementation is the intended one, and row 22 is the only row that
    can tell one gate from two.


P4 ROUTING — the seal-coverage gap, and whether D8 is complete without it
========================================================================
**Writing these rows is a P2's job and P4 did not write them.** A P4 that
writes the seal it wants its own rulings judged by is the circular oracle this
protocol opens by naming, and it is a worse instance than the ordinary one:
the rows below are about work P4 just landed.

**RE-DERIVED BY P4 on this tree, not carried from P3's report.** Each mutation
applied to a `cp -a` clone, `tests/test_loop_gate.py` re-run whole:

  * drop the rule-equivalence guard in :func:`resolve_inputs` — **22 green**;
  * make `orchestrator._run_task` never WRITE the row stamp while still
    referencing :data:`ROW_STAMPS` — **22 green**;
  * hardcode ``enabled=True`` at the call site — **22 green**.

And one measurement P4 added, because the P3-2 ruling might have been thought
to close the third and does not: with ``enabled=True`` hardcoded, the three
journal-sequence rows amended by that ruling stay **31 passed**. They pin the
event TYPE and its POSITION, never its payload. The amendment proves the gate
speaks on every task; it proves nothing about what it says.

FOUR ROWS ARE OWED, with their shapes named so a P2 does not have to
rediscover them:

  1. **The rule-equivalence refusal.** Now writable in its own name: the P3-1
     ruling gives it :data:`LoopGateStatus.RULE_UNRESOLVED`. Drive
     :func:`check_after_implementer` with two ADJUDICATE specs differing only
     in ``disputed_paths:`` and assert status RULE_UNRESOLVED, decision BLOCK,
     and a `blocked_reason` distinct from the mixed-role one. It must go
     through the hook and NOT through :func:`sole_role`, which returns a role
     for this input and is not where the refusal lives.
  2. **The row stamp is actually written.** Row 21 reads `orchestrator.py`'s
     SOURCE for a reference to :data:`ROW_STAMPS`; no row drives the write.
     The shape is a real run — the fixture machinery in
     `tests/test_orchestrator_journal.py` and `tests/test_mechanical_verify.py`
     already builds one — asserting the task's YAML row carries
     ``ROW_STAMPS[0]`` with the expected VALUE.
  3. **The run flag is honoured.** Same fixture, default config, asserting the
     stamp and the journal PAYLOAD both read ``not_enabled``; then a second
     row with the flag on. This is the row the P3-2 amendment does not
     substitute for, measured above.
  4. **Row 22 is alone, and a fifth behavioural row will not help.** The seal
     author disclosed it and P3 re-derived it: a second implementation
     agreeing on every fixture reddens row 22 and nothing else. The right P2
     move is to STRENGTHEN row 22's closure walk, not to add behaviour — the
     fixtures in that file are exactly the fixtures a reimplementation would be
     written against, so more of them buy nothing.

**IS D8 COMPLETE WITHOUT THEM? No, and the honest counter is recorded with
the answer.** The counter is real: this file's rows are about WIRING, and a
gate that is wired but whose flag is hardcoded is still wired — row 4 locates
the call by AST inside `_run_task`, and it would still hold. So the unit's
stated subject is sealed.

It is still not complete, because two of the three uncovered mutations are not
about wiring at all — they are about whether the wiring DOES anything. A gate
whose flag is hardcoded ``True`` runs on every task of every repository,
including the Go tree where §3 measured fifteen minutes per BODIES branch and
ruled the gate must not go in front of it; a gate that never writes its stamp
leaves `dispatcher blocked` unable to say why a row was blocked and leaves
`unblock._STALE_STAMPS` clearing keys that were never set. Neither is a wiring
defect and neither reddens anything. **The unit is wired and it is not
guarded.** D8 is complete as a wiring unit and incomplete as a shipped one,
and the gate should not be switched on by default until rows 1-3 exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from .role_protocol import (
    DiffVerdict,
    Role,
    RoleDiffResult,
    TaskRoleSpec,
    check_branch,
    load_role_policy_from_base,
)

# CHOICE — this module imports `role_protocol` at MODULE level rather than
# inside its functions. Rejected alternative: a function-local import, the
# spelling `check_branch` itself uses for `branch_reachability`. That spelling
# exists there to keep a module OFF the derived floor closure until the call
# is real; here the direction is reversed — this module is a CALLER of the
# gate, not a delegate of it, and `tests/test_floor_closure.py` walks
# delegations out of `check_branch`, never callers into it (measured under
# 81591e4: 183 passed with a probe call in place). A function-local import
# would buy nothing and hide the dependency.


class LoopGateError(RuntimeError):
    """A fault in the loop gate's own dispatch — never a verdict about a branch.

    Raised by the total dispatches below when handed an enum member no table
    maps. It is deliberately NOT the way this module reports "the check could
    not be made": that is :data:`LoopGateStatus.GATE_ERROR`, which carries a
    decision. An exception escaping into `_run_task` would be caught by
    `_dispatch_drain`'s worker guard (orchestrator.py:2440, measured) and turn
    into ``worker_exception``, losing the reason.

    **P3 note — two more raisers, both named rather than left to be
    discovered.** The scaffold's sentence "raised only by the total dispatches
    below" was true of the scaffold and is not true of the body, because
    :func:`resolve_inputs`'s own contract instructs P3 to raise this type
    (steps 1 and 2), and §6 permits P3 to raise it for a ``deadline_seconds``
    it cannot honour. Both are still "a fault in the loop gate's own
    dispatch"; neither is a verdict about a branch. The resolution raises are
    caught by :func:`check_after_implementer` and become
    :class:`LoopGateStatus` members with decisions — see
    :class:`_UnresolvedInput`, which is what carries the status across the
    ``raise``. The deadline raise is deliberately NOT caught: a parameter this
    unit cannot honour must reach the caller, not be recorded as a verdict.
    """


class _UnresolvedInput(LoopGateError):
    """A resolution failure that already knows which status it is.

    Private, and a subclass rather than a second exception type, because
    :func:`resolve_inputs`'s contract says it raises :class:`LoopGateError`
    and row 14 catches exactly that. Carrying the status on the exception is
    the alternative :func:`resolve_inputs`'s own CHOICE block rules FOR: a
    ``None`` return would collapse ROLE_UNRESOLVED and BASE_UNRESOLVED into
    one answer, and re-deriving which one happened from the message text at
    the catch site would be a second notion of "why did this not resolve".
    """

    def __init__(self, status: LoopGateStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
# What the loop does, and why
# --------------------------------------------------------------------------- #


class LoopGateDecision(Enum):
    """What `orchestrator._run_task` does with the answer. Two states.

    PROCEED
        Continue to the mechanical gate. **Not** "the branch is clean" — it is
        "this gate does not stop the task", which is also what
        :data:`LoopGateStatus.NOT_ENABLED` produces. The distinction is
        carried by the status, never by this enum, which is why every
        :class:`LoopGateOutcome` carries both.
    BLOCK
        Flip the task to ``plan.BLOCKED`` with a `blocked_reason` from
        :func:`blocked_reason`, emit the terminal event, and return. The row
        joins the `dispatcher blocked` queue (exit 3) and is cleared, if a
        human agrees, by `dispatcher unblock` — which re-runs every gate.
    """

    PROCEED = "proceed"
    BLOCK = "block"


class LoopGateStatus(Enum):
    """Why the gate produced the decision it did. NINE states, exhaustive.

    **Eight until 2026-08-12; the ninth is P4's ruling on dispute P3-1 and it
    is recorded at :data:`LoopGateStatus.RULE_UNRESOLVED` below.**


    Every one is NAMED, and the naming is the point: the requirement comes
    from `skills/explicit-state.md` by way of
    :class:`~claude_dispatcher.role_protocol.DiffVerdict`'s own docstring —
    "three states, not two-plus-null" — and from
    :class:`~claude_dispatcher.branch_reachability.ReachabilitySweepStatus`'s
    nine. A state that has to be inferred is a state somebody will infer
    wrongly, and on this gate the wrong inference is always "it passed".

    NOT_ENABLED
        The run did not turn the loop gate on. → PROCEED. This is a real
        state and not an absence: it is logged and journaled per task, so a
        run with the gate off says so on every row rather than looking like a
        run whose every branch was clean. §3 rules why the default is off.
    CHECKED_CLEAN
        `check_branch` returned CLEAN over a non-empty diff. → PROCEED.
        Records nothing about the paths four later spawns will commit (§5).
    CHECKED_VIOLATION
        `check_branch` returned VIOLATION. → BLOCK. §2.
    CHECKED_UNDETERMINED
        `check_branch` returned UNDETERMINED — an unreadable policy, an empty
        diff, a branch that moved mid-check, a blocking unchecked signature
        status on BODIES, or a blocking reachability abstention. → BLOCK. §3.
    ROLE_UNRESOLVED
        The dispatched rows did not yield exactly one :class:`Role`: a
        mixed-role batch (measured to load clean today, §4), a snapshot
        carrying no role spec, or an empty group. → BLOCK. The gate does not
        pick one, because a branch judged under a rule its author was not
        working to is wrong in both directions at once.

        Its scope is now EXACTLY the role, because the case that used to
        borrow it has its own member below. Read the two together: this one is
        "which rulebook", the next is "which page of it".
    RULE_UNRESOLVED
        The dispatched rows DID yield exactly one :class:`Role` and did not
        yield one RULE: they carry different ``immutable_paths:`` additions, or
        different ``disputed_paths:``, which are the two per-row fields
        `check_branch` reads off a :class:`TaskRoleSpec`. → BLOCK, and the gate
        does not pick ``specs[0]``, for §4's argument one level down from the
        role: an ADJUDICATE row's ``disputed_paths:`` IS its writable set, so
        judging row B's work under row A's set reports legitimate work as a
        violation and clears work nobody authorised — wrong in both directions
        on the same branch.

        **P4 ruling, 2026-08-12, dispute P3-1.** P3 implemented the refusal and
        raised it through ROLE_UNRESOLVED "for want of a better-named state",
        offering P4 three ways out: widen that state's wording, add a ninth
        member, or extend the plan-time refusal. The ruling takes the second
        and ALSO extends §7(b); the wording option is refused. The reason the
        wording is not enough is this module's own standard, applied evenly:
        §4 rules that a human reading the queue must be able to tell "your
        worklist batches two roles" from "git would not resolve a SHA", and the
        mechanism that carries that distinction is
        :data:`_BLOCKED_REASON_PREFIXES`, which is keyed by STATUS. Two defects
        sharing a status share a queue label and differ only in a detail
        excerpt. They are also two different things to fix: a mixed-role batch
        is a protocol error, while two ADJUDICATE rows with different
        ``disputed_paths:`` may each be perfectly legal and merely unable to
        share a branch.

        It is also the answer that makes the gap P3 measured writable. Dropping
        the rule-equivalence guard leaves the seal file 22-of-22 green (P3's
        own measurement, re-derived by P4 on this tree), so no row covers this
        refusal at all. A refusal with no state of its own is a refusal a seal
        cannot name in its title; this member is what a P2 row binds to.

        Cost, measured rather than asserted: adding a member reddens exactly
        one seal row —
        ``test_the_decision_table_is_exactly_the_status_enum_and_is_a_member_
        lookup``'s ``len(LoopGateStatus) == 8`` — whose own message says "a
        member added without a ruling gets whichever decision the table
        happened to give it". That row is a tripwire REQUIRING a ruling, not a
        prohibition; this is the ruling, and the bound moves 8 → 9 in the same
        commit.
    BASE_UNRESOLVED
        ``pre_spawn_sha`` is ``None`` — `_branch_sha` returned ``None`` on a
        git failure. → BLOCK. There is deliberately no fallback base (§4).
    DEADLINE_EXCEEDED
        The check ran past this task's deadline. → BLOCK. **Unreachable until
        §7(e) lands**, and named anyway: a state invented later, under
        pressure, gets the permissive decision.
    GATE_ERROR
        Resolving the inputs raised. → BLOCK. `check_branch` itself never
        raises (its own contract: "this function never raises. Every failure
        … becomes UNDETERMINED"), so this covers the loop's own resolution
        step and nothing else.
    """

    NOT_ENABLED = "not_enabled"
    CHECKED_CLEAN = "checked_clean"
    CHECKED_VIOLATION = "checked_violation"
    CHECKED_UNDETERMINED = "checked_undetermined"
    ROLE_UNRESOLVED = "role_unresolved"
    RULE_UNRESOLVED = "rule_unresolved"
    BASE_UNRESOLVED = "base_unresolved"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    GATE_ERROR = "gate_error"


#: **Status → decision, as DATA.** NINE rows (eight until the P4 ruling on
#: dispute P3-1, 2026-08-12) and every :class:`LoopGateStatus` member is one.
#:
#: A table and not a chain of ``if``\ s, for the reason
#: :data:`~claude_dispatcher.branch_reachability._ROLE_OBLIGATIONS` records: a
#: chain grows a default branch, and a default branch on this dispatch is how
#: the permissive answer gets a new spelling. A new member lands in
#: :func:`decision_for`'s raise, never in a silent PROCEED.
#:
#: Read the column: exactly TWO rows proceed, and one of those two is the gate
#: being switched off. Everything else — including all FOUR "the rows/refs did
#: not resolve" states — blocks. That asymmetry is §2 and §3, as data, and it is
#: what makes adding a member cheap in the safe direction and never in the
#: other: a new member absent from this table raises out of :func:`decision_for`.
_DECISIONS: Mapping[LoopGateStatus, LoopGateDecision] = {
    LoopGateStatus.NOT_ENABLED: LoopGateDecision.PROCEED,
    LoopGateStatus.CHECKED_CLEAN: LoopGateDecision.PROCEED,
    LoopGateStatus.CHECKED_VIOLATION: LoopGateDecision.BLOCK,
    LoopGateStatus.CHECKED_UNDETERMINED: LoopGateDecision.BLOCK,
    LoopGateStatus.ROLE_UNRESOLVED: LoopGateDecision.BLOCK,
    LoopGateStatus.RULE_UNRESOLVED: LoopGateDecision.BLOCK,
    LoopGateStatus.BASE_UNRESOLVED: LoopGateDecision.BLOCK,
    LoopGateStatus.DEADLINE_EXCEEDED: LoopGateDecision.BLOCK,
    LoopGateStatus.GATE_ERROR: LoopGateDecision.BLOCK,
}


#: **Verdict → status, as DATA.** Three rows, one per
#: :class:`~claude_dispatcher.role_protocol.DiffVerdict` member.
#:
#: Deliberately a separate table from :data:`_DECISIONS` rather than a direct
#: verdict → decision map. The loop has five ways of not reaching a verdict at
#: all, and collapsing "check_branch said UNDETERMINED" into the same cell as
#: "the base ref would not resolve" would put two different human actions —
#: read the detail, versus fix git — behind one `blocked_reason`.
_VERDICT_STATUSES: Mapping[DiffVerdict, LoopGateStatus] = {
    DiffVerdict.CLEAN: LoopGateStatus.CHECKED_CLEAN,
    DiffVerdict.VIOLATION: LoopGateStatus.CHECKED_VIOLATION,
    DiffVerdict.UNDETERMINED: LoopGateStatus.CHECKED_UNDETERMINED,
}


#: **Status → `blocked_reason` prefix, as DATA.** One row per BLOCKING status;
#: the two PROCEED statuses are absent by construction and
#: :func:`blocked_reason` raises for them rather than inventing a reason for a
#: task that was not blocked.
#:
#: Distinct per status because the review queue (`unblock.list_blocked`) prints
#: the reason and nothing else on its first line, and the human's first
#: question is which of these SEVEN happened. `check_body_branch.sh` already
#: spends two exit codes on the violation/undetermined half of that
#: distinction; this table spends seven strings on all of it.
#:
#: The seventh is ``role_diff_loop_rule_unresolved`` (P4, dispute P3-1,
#: 2026-08-12), and this table is WHY that ruling took a ninth status rather
#: than a widened wording: the queue label is keyed by STATUS, so two defects
#: sharing a status share a label. Neither new string is a prefix of any other,
#: which is the property row 8 asserts — measured, `..._role_unresolved` and
#: `..._rule_unresolved` differ at their eighteenth character.
#:
#: Prefixed ``role_diff_loop_`` and not ``role_diff_``: §5 rules that PR time
#: is the check that judges what lands, and a reason that reads like the
#: verdict is a reason somebody will treat as one.
_BLOCKED_REASON_PREFIXES: Mapping[LoopGateStatus, str] = {
    LoopGateStatus.CHECKED_VIOLATION: "role_diff_loop_violation",
    LoopGateStatus.CHECKED_UNDETERMINED: "role_diff_loop_undetermined",
    LoopGateStatus.ROLE_UNRESOLVED: "role_diff_loop_role_unresolved",
    LoopGateStatus.RULE_UNRESOLVED: "role_diff_loop_rule_unresolved",
    LoopGateStatus.BASE_UNRESOLVED: "role_diff_loop_base_unresolved",
    LoopGateStatus.DEADLINE_EXCEEDED: "role_diff_loop_deadline_exceeded",
    LoopGateStatus.GATE_ERROR: "role_diff_loop_gate_error",
}


#: The row keys this gate writes on a task's YAML row.
#:
#: Named as data, and named HERE rather than at the write site, because
#: `unblock._STALE_STAMPS` must clear them: an unblocked row carrying a stale
#: `role_diff_loop` from the previous attempt is exactly the contradiction
#: that list exists to prevent ("so a To Do row doesn't carry contradictory
#: 'failed' stamps into its re-run"). Measured under `81591e4`: neither key is
#: in `_STALE_STAMPS` today. §7(c).
#:
#: CHOICE — rejected: a single stamp holding a rendered sentence. Rejected
#: because `unblock._DETAIL_FIELDS` (measured) shows the established shape is
#: a short verdict key plus a separate `_detail` key it can excerpt to 400
#: characters; a single field would either be truncated past usefulness or
#: printed whole into a queue meant to be scanned.
ROW_STAMPS: tuple[str, ...] = ("role_diff_loop", "role_diff_loop_detail")


def decision_for(status: LoopGateStatus) -> LoopGateDecision:
    """What the loop does, given a status. Total over :class:`LoopGateStatus`.

    **IMPLEMENTED, not stubbed**, under the standing exception and for D7's
    recorded reason: "every member is mapped, and an unmapped one raises" is
    not checkable against a function that raises for everything.
    """
    try:
        return _DECISIONS[status]
    except KeyError:
        raise LoopGateError(
            f"no loop-gate decision is defined for {status!r}; a new "
            "LoopGateStatus member must be given a decision here, not fall "
            "through to whichever branch happens to be last — and on this "
            "dispatch the permissive branch is always the one that is last"
        ) from None


def status_for_verdict(verdict: DiffVerdict) -> LoopGateStatus:
    """A `check_branch` verdict's status. Total over :class:`DiffVerdict`.

    **IMPLEMENTED**, same reason as :func:`decision_for`. A fourth
    :class:`DiffVerdict` member — which this package has already added members
    to enums under, twice — must land in this raise and not in a default.
    """
    try:
        return _VERDICT_STATUSES[verdict]
    except KeyError:
        raise LoopGateError(
            f"verdict {verdict!r} has no loop-gate status; DiffVerdict grew a "
            "member and this table did not, so the loop would be judging a "
            "branch by a verdict it does not understand"
        ) from None


def blocked_reason(status: LoopGateStatus, detail: str = "") -> str:
    """The `blocked_reason` string for a blocking status.

    Raises :class:`LoopGateError` for a status whose decision is PROCEED: a
    reason for a task that was not blocked is a row that lies, and the two
    PROCEED statuses are absent from :data:`_BLOCKED_REASON_PREFIXES` by
    construction rather than by omission.

    **IMPLEMENTED**, because the property a seal wants — "every blocking
    status has a distinct reason and no non-blocking status has one" — is not
    checkable against a stub, and because the distinctness is §2's and §3's
    ruling rather than a formatting detail.
    """
    prefix = _BLOCKED_REASON_PREFIXES.get(status)
    if prefix is None:
        raise LoopGateError(
            f"{status!r} has no blocked_reason because its decision is "
            f"{decision_for(status).value!r}; asking for one means a caller "
            "is about to block a task this gate did not block"
        )
    text = (detail or "").strip()
    return f"{prefix}: {text}" if text else prefix


def sole_role(specs: Sequence[TaskRoleSpec]) -> Role | None:
    """The single :class:`Role` a dispatched group shares, or ``None``.

    ``None`` means "this branch has no one role", which the caller turns into
    :data:`LoopGateStatus.ROLE_UNRESOLVED` → BLOCK. Three inputs produce it,
    and all three are real:

      * **an empty sequence.** Zero rows is not one role. A group with no
        specs is a snapshot that lost its rows, not a legacy branch.
      * **two or more distinct roles.** The measured case (§4): a batch group
        shares one worktree and one branch, and a worklist putting two roles
        in one ``batch_id`` loads today with zero errors and zero warnings.
      * nothing else. Repeated rows carrying the SAME role are one role and
        resolve normally — that is the ordinary batch, and it is fine: the
        rows differ but the rule they are judged by does not.

    Note what is NOT a ``None``: :data:`Role.LEGACY`. A group of role-less
    rows resolves to LEGACY and IS checked, because `check_branch` rules on
    LEGACY — CLEAN unless a floor path was touched — and the 2026-08-07 floor
    ruling turns on exactly that: *"a floor LEGACY escapes is bypassed by
    deleting one line"*. Skipping the call for LEGACY here would rebuild that
    bypass in the loop.

    CHOICE — rejected: return the primary row's role and warn. Rejected in
    §4; picking judges half the branch under the wrong rule.

    CHOICE — rejected: run `check_branch` once per distinct role and take the
    worst verdict. Rejected because the diff is shared: each run would report
    the OTHER role's legitimate work as a violation, so the worst verdict is
    VIOLATION for every mixed batch regardless of behaviour — a refusal
    dressed as a measurement. If mixed-role batches should be refused, refuse
    them in as many words (which is §7(b), at plan time).

    **IMPLEMENTED**, because a stub raising for everything satisfies "a mixed
    batch does not resolve" vacuously while failing the half that matters —
    that an ordinary single-role batch DOES resolve.
    """
    roles = {spec.role for spec in specs}
    if len(roles) != 1:
        return None
    return roles.pop()


# --------------------------------------------------------------------------- #
# The two records
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LoopGateInputs:
    """Everything one loop-time `check_branch` call needs, resolved.

    A record rather than seven parameters threaded through `_run_task`,
    because §4's rulings are about WHICH ref goes in WHICH slot and a
    positional call at the hook site would make that invisible at the one
    place a reader looks.

    ``base_ref``
        ``pre_spawn_sha`` — this cascade rung's pre-implementer tip. Never
        ``cfg.base_branch``, never ``base_sha_before``. §4.
    ``policy``
        loaded from ``cfg.base_branch``, NOT from ``base_ref``, so a branch
        cannot supply the policy that judges it. Passed to `check_branch`'s
        ``policy=`` seam, which takes it verbatim. §4.
    ``spec``
        the row's :class:`TaskRoleSpec`, frozen at dispatch time. Required
        when ``role`` is ADJUDICATE (`check_branch` answers UNDETERMINED
        without it, by its own step 2) and carried for every role so an
        ``immutable_paths:`` addition is applied.

    ``policy`` is typed loosely on purpose: naming
    :class:`~claude_dispatcher.role_protocol.RolePolicy` here is correct but
    the field is only ever produced by `load_role_policy_from_base` and only
    ever consumed by `check_branch`, so P3 may tighten it without a contract
    change.
    """

    repo_root: Path
    base_ref: str
    branch_ref: str
    role: Role
    spec: TaskRoleSpec | None = None
    policy: object | None = None


@dataclass(frozen=True)
class LoopGateOutcome:
    """One hook invocation's answer.

    Carries the decision AND the status AND, when there was one, the whole
    :class:`~claude_dispatcher.role_protocol.RoleDiffResult`. All three,
    because a caller that keeps only the decision cannot tell a clean branch
    from a switched-off gate, and a caller that keeps only the verdict cannot
    report the five ways of never reaching one.

    ``result`` is ``None`` whenever `check_branch` was not called — five of
    the eight statuses. **``None`` is not "clean"**, the same warning
    :attr:`RoleDiffResult.reachability` carries about itself, for the same
    reason: the sub-record names every way of not having run, and ``None``
    means the question was never put.
    """

    decision: LoopGateDecision
    status: LoopGateStatus
    result: RoleDiffResult | None = None
    detail: str = ""

    @property
    def verdict(self) -> DiffVerdict | None:
        """The underlying verdict, or ``None`` when no check was made.

        Implemented — it is a field read, and a stub property would make
        "``None`` when `check_branch` did not run" untestable.
        """
        return self.result.verdict if self.result is not None else None


# --------------------------------------------------------------------------- #
# The hook. This is the control flow: stubbed by the scaffold, written by P3.
# --------------------------------------------------------------------------- #


def resolve_inputs(
    *,
    repo_root: Path,
    base_branch: str,
    branch_ref: str,
    pre_spawn_sha: str | None,
    specs: Sequence[TaskRoleSpec],
) -> LoopGateInputs:
    """Turn the loop's live state into one :class:`LoopGateInputs`.

    Implemented by P3 to §4 exactly, which is the four steps P1 wrote here:

      1. :func:`sole_role` over ``specs``; ``None`` → raise
         :class:`LoopGateError` so :func:`check_after_implementer` can report
         :data:`LoopGateStatus.ROLE_UNRESOLVED`.
      2. ``pre_spawn_sha`` is ``None`` → raise, for
         :data:`LoopGateStatus.BASE_UNRESOLVED`. No fallback base.
      3. ``role_protocol.load_role_policy_from_base(repo_root, base_branch)``
         for ``policy`` — from ``base_branch``, never from ``pre_spawn_sha``.
      4. the group's own spec for ``spec`` when :func:`sole_role` resolved.

    CHOICE — rejected: return a ``LoopGateInputs | None`` and let ``None``
    mean "could not resolve". Rejected because ``None`` would collapse the
    two distinct failures at (1) and (2) into one, and §4 rules that a human
    reading the queue must be able to tell "your worklist batches two roles"
    from "git would not resolve a SHA". The exception carries the reason; the
    caller maps it to a status.

    CHOICE — rejected: take the whole ``TaskSnapshot`` and ``RunConfig``.
    Rejected so this module has no import of, and no opinion about, the
    orchestrator's shapes. The five scalars above are the entire dependency,
    which is also what makes the seals need no dispatcher fixture.

    **P3 — the one thing the four steps do not say, and it is reachable.**
    Step 4 says "the group's own spec", singular. A group that resolves to ONE
    role may still carry SEVERAL specs, and those specs may differ in the two
    fields `check_branch` reads off them — ``added_immutable_globs`` and
    ``disputed_paths``. Measured under `6d94190`: `plan.load_tasks` and
    `role_protocol.validate` accept two ADJUDICATE rows with different
    ``disputed_paths:`` in one ``batch_id``, exactly as row 18 measures for two
    roles. Passing ``specs[0]`` there would judge row B's disputed work under
    row A's writable set, which is §4's own "wrong in both directions on the
    same branch" argument one level down from the role. So: specs that agree on
    both fields are interchangeable and the first is passed; specs that
    disagree do not yield one RULE and are refused through the same raise as a
    mixed-role group. Recorded as **dispute P3-1** — the status is spelled
    ROLE_UNRESOLVED and its docstring says "did not yield exactly one
    :class:`Role`", which this case technically does; P4 owes either a widened
    wording, a ninth status, or (better, and the shape §7(b) already takes) a
    plan-time refusal. What P3 will not do is pick one and say nothing.

    **RULED (P4, 2026-08-12): the ninth status, AND the plan-time refusal.**
    The refusal P3 wrote is kept exactly as written; only the status it raises
    changes, to :data:`LoopGateStatus.RULE_UNRESOLVED`, which is reasoned in
    full on that member. The widened-wording option is refused there. §7(b) is
    extended in the same ruling to owe BOTH plan-time refusals, and it is
    deliberately NOT landed here — see §7(b) for why the seal author assigned
    the row-18 amendment to that item's own commit.

    What did NOT change, and it is the load-bearing half: this function still
    refuses rather than picking, and P3's reason for refusing is the ruling's
    reason too. The ninth status is about what the queue is TOLD; the refusal
    itself was already right.
    """
    role = sole_role(specs)
    if role is None:
        raise _UnresolvedInput(
            LoopGateStatus.ROLE_UNRESOLVED,
            "the dispatched rows do not share exactly one role "
            f"({sorted({spec.role.value for spec in specs})} over "
            f"{[spec.task_key for spec in specs]}), and check_branch takes "
            "one: judging this branch under either role would report the "
            "other role's legitimate work as a violation",
        )

    # One role, but possibly several rows. See the P3 block above and the P4
    # ruling on it at :data:`LoopGateStatus.RULE_UNRESOLVED`.
    rules = {(spec.added_immutable_globs, spec.disputed_paths) for spec in specs}
    if len(rules) != 1:
        raise _UnresolvedInput(
            LoopGateStatus.RULE_UNRESOLVED,
            f"the dispatched rows {[spec.task_key for spec in specs]} share "
            f"role {role.value!r} but not one rule: their immutable_paths / "
            "disputed_paths additions differ, so one branch would be judged "
            "under one row's writable set and the other row's work reported "
            "against it. The role IS resolved; the rulebook page is not — "
            "which is why this is RULE_UNRESOLVED and not ROLE_UNRESOLVED "
            "(P4 ruling on dispute P3-1, 2026-08-12)",
        )

    if pre_spawn_sha is None:
        raise _UnresolvedInput(
            LoopGateStatus.BASE_UNRESOLVED,
            "pre_spawn_sha is None — _branch_sha reported a git failure for "
            "this rung's pre-implementer tip. There is deliberately no "
            "fallback to the base branch: the diff would then contain the "
            "dependency merge, i.e. the SEALS author's tests/** on every "
            "well-formed unit (§4)",
        )

    # Step 3. From ``base_branch`` and never from ``pre_spawn_sha``: base_ref
    # is a commit ON the branch under judgement, and a branch that merged a
    # dependency touching `.dispatcher.yaml` would otherwise supply the policy
    # that judges it (invariant 6). Raised failures are the caller's
    # GATE_ERROR — `load_role_policy_from_base` has deliberately no fallback.
    policy = load_role_policy_from_base(repo_root, base_branch)

    return LoopGateInputs(
        repo_root=repo_root,
        base_ref=pre_spawn_sha,
        branch_ref=branch_ref,
        role=role,
        spec=specs[0],
        policy=policy,
    )


def check_after_implementer(
    *,
    enabled: bool,
    repo_root: Path,
    base_branch: str,
    branch_ref: str,
    pre_spawn_sha: str | None,
    specs: Sequence[TaskRoleSpec],
    deadline_seconds: float | None = None,
) -> LoopGateOutcome:
    """THE hook. Called from `orchestrator._run_task` at §1's position.

    Implemented by P3, to the four steps P1 wrote here:

      1. ``enabled`` false → :data:`LoopGateStatus.NOT_ENABLED`, PROCEED. The
         caller still logs and journals it: §3's default-off ruling only works
         if a run with the gate off says so on every row.
      2. :func:`resolve_inputs`; :class:`LoopGateError` → the status its
         raiser named, BLOCK.
      3. ``role_protocol.check_branch(inputs.repo_root, inputs.base_ref,
         inputs.branch_ref, inputs.role, spec=..., policy=...)`` — the SAME
         function `scripts/check_body_branch.sh` reaches, so the three
         enforcement points cannot disagree about a rule (invariant 1). It
         never raises; every failure arrives as UNDETERMINED.
      4. :func:`status_for_verdict` then :func:`decision_for`.

    ``deadline_seconds`` is in the signature and is NOT honoured by this
    scaffold. §6: a real deadline needs a killable face that does not yet
    exist, and this unit will not pretend otherwise by, for example, timing
    the call and reporting :data:`LoopGateStatus.DEADLINE_EXCEEDED` after it
    has already completed — which measures nothing and blocks a task whose
    check succeeded. P3 either implements §7(e) or raises
    :class:`LoopGateError` for a non-``None`` value; it may not silently
    ignore it.

    CHOICE — rejected: perform the block (mutate the row, emit the event)
    here. Rejected because that is the orchestrator's control flow and its
    locking discipline (`_mutate_row` holds the FileLock), and because a gate
    that mutates rows cannot be sealed without a worklist fixture. This
    function ANSWERS; `_run_task` acts.

    CHOICE — rejected: accept a ``run=`` subprocess seam and pass it through
    to `check_branch`. Rejected for the scaffold: `check_branch` already
    publishes that seam, so a passthrough here would be a second place a test
    can substitute git, and two seams for one fact is invariant 5's shape. P3
    may add it if the seals need it — and if it does, it is one parameter
    forwarded verbatim, never a second seam of this module's own.

    **P3 — which branch of §6's disjunction was taken, and where the raise
    sits.** §7(e) is not implemented here (it is a killable process face, new
    machinery, and owed), so a non-``None`` ``deadline_seconds`` RAISES. The
    raise is the FIRST statement, before the ``enabled`` short-circuit and
    outside every ``except``: a caller asking for a facility this unit does not
    have must not have that request recorded as a verdict about a branch, and
    a refusal swallowed into :data:`LoopGateStatus.GATE_ERROR` would be exactly
    that. No production caller passes the parameter today (measured under
    `6d94190`: `orchestrator._run_task`'s call omits it), so the raise is
    unreachable from the dispatcher and reachable from anyone who tries to use
    the parameter — which is the point of it.

    **P3 — what GATE_ERROR catches, and what it deliberately does not.** The
    ``except`` covers :func:`resolve_inputs` and nothing else, because that is
    the only step of the four that can raise: `check_branch`'s own contract is
    that it never does, and every failure of its own arrives as UNDETERMINED.
    If `check_branch` ever breaks that contract the exception propagates rather
    than being relabelled — a gate that reports GATE_ERROR for a crash inside
    the shared callable would hide invariant 1's most important failure behind
    this unit's own name.
    """
    if deadline_seconds is not None:
        raise LoopGateError(
            f"deadline_seconds={deadline_seconds!r} was given and this unit "
            "cannot honour it: a real deadline needs a killable process face "
            "(§7(e)) and check_branch is an ordinary in-process call CPython "
            "cannot interrupt. Timing the call and reporting DEADLINE_EXCEEDED "
            "after it completed measures nothing and blocks a task whose check "
            "succeeded, so this refuses instead of pretending"
        )

    if not enabled:
        # A named state, not an absence — the caller logs and journals it on
        # every task, so a run with the gate off says so per row rather than
        # looking like a run whose every branch was clean (§3).
        return LoopGateOutcome(
            decision=decision_for(LoopGateStatus.NOT_ENABLED),
            status=LoopGateStatus.NOT_ENABLED,
        )

    try:
        inputs = resolve_inputs(
            repo_root=repo_root,
            base_branch=base_branch,
            branch_ref=branch_ref,
            pre_spawn_sha=pre_spawn_sha,
            specs=specs,
        )
    except _UnresolvedInput as exc:
        return LoopGateOutcome(
            decision=decision_for(exc.status),
            status=exc.status,
            detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 — see the docstring block above
        return LoopGateOutcome(
            decision=decision_for(LoopGateStatus.GATE_ERROR),
            status=LoopGateStatus.GATE_ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )

    result = check_branch(
        inputs.repo_root,
        inputs.base_ref,
        inputs.branch_ref,
        inputs.role,
        spec=inputs.spec,
        policy=inputs.policy,
    )
    status = status_for_verdict(result.verdict)
    return LoopGateOutcome(
        decision=decision_for(status),
        status=status,
        result=result,
        detail=result.detail,
    )
