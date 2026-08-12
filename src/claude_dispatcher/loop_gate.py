"""Unit D8 — the post-implementer role check inside the orchestrator's task loop.

**P1 scaffold. This module is CONTRACT plus five implemented tables; the hook
itself and its input resolution are stubs. P2 writes the seals, P3 the bodies,
P4 adjudicates. Nothing here changes `orchestrator.py`: the call site is
specified, not made.**

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
  * :func:`resolve_inputs`, :func:`check_after_implementer` — STUBS.

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

  a. `TaskSnapshot` gains a frozen role spec, populated in `_dispatch_drain`
     (§4). `orchestrator.py` is not floored today, so this is a P3 edit —
     unless (a) lands after the floor entries above, in which case it is P4.
     Sequence matters; name it in the plan.
  b. `role_protocol.validate` should refuse a batch whose rows carry more
     than one role (§4, measured to load clean today). Floored file → P4.
     Until it lands, :data:`LoopGateStatus.ROLE_UNRESOLVED` is the only thing
     standing between a mixed-role batch and an unjudgeable branch.
  c. `unblock._STALE_STAMPS` must gain :data:`ROW_STAMPS`. Measured under
     `81591e4`: `_STALE_STAMPS` (unblock.py:44) lists nine keys and neither of
     ours; a cleared row would carry a stale `role_diff_loop` into its re-run,
     which is the contradiction that list exists to prevent. `unblock.py`
     matches no `FLOOR_GLOBS` entry — measured — so this is a P3 edit.
  d. `role_protocol`'s module docstring must move this hook from the "NOT
     wired" paragraph into "Wired by P3", and this is MECHANICALLY CHECKED:
     `tests/test_role_protocol_wiring.py::
     test_every_wired_by_p3_claim_has_its_call_site` parses that section and
     verifies each claimed subject really calls its claimed target, and
     ``REQUIRED_WIRED_TARGETS`` pins the minimum set so a bullet cannot be
     deleted to make a claim true. Floored file + seal file → P4, exactly as
     D7's step-6 wiring was.
  e. the killable face a deadline needs (§6).
  f. a check of the post-hook iterate spawns (§5), or an explicit ruling that
     PR time is the only gate on them.


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

Everything else is a stub: :func:`resolve_inputs` and
:func:`check_after_implementer` are the control flow, and control flow is what
a scaffold does not write.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from .role_protocol import DiffVerdict, Role, RoleDiffResult, TaskRoleSpec

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

    Raised only by the total dispatches below when handed an enum member no
    table maps. It is deliberately NOT the way this module reports "the check
    could not be made": that is :data:`LoopGateStatus.GATE_ERROR`, which
    carries a decision. An exception escaping into `_run_task` would be caught
    by `_dispatch_drain`'s worker guard (orchestrator.py:2440, measured) and
    turn into ``worker_exception``, losing the reason.
    """


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
    """Why the gate produced the decision it did. Eight states, exhaustive.

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
    BASE_UNRESOLVED = "base_unresolved"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    GATE_ERROR = "gate_error"


#: **Status → decision, as DATA.** Eight rows and every :class:`LoopGateStatus`
#: member is one.
#:
#: A table and not a chain of ``if``\ s, for the reason
#: :data:`~claude_dispatcher.branch_reachability._ROLE_OBLIGATIONS` records: a
#: chain grows a default branch, and a default branch on this dispatch is how
#: the permissive answer gets a new spelling. A new member lands in
#: :func:`decision_for`'s raise, never in a silent PROCEED.
#:
#: Read the column: exactly TWO rows proceed, and one of those two is the gate
#: being switched off. Everything else — including all three "I could not
#: check" states — blocks. That asymmetry is §2 and §3, as data.
_DECISIONS: Mapping[LoopGateStatus, LoopGateDecision] = {
    LoopGateStatus.NOT_ENABLED: LoopGateDecision.PROCEED,
    LoopGateStatus.CHECKED_CLEAN: LoopGateDecision.PROCEED,
    LoopGateStatus.CHECKED_VIOLATION: LoopGateDecision.BLOCK,
    LoopGateStatus.CHECKED_UNDETERMINED: LoopGateDecision.BLOCK,
    LoopGateStatus.ROLE_UNRESOLVED: LoopGateDecision.BLOCK,
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
#: question is which of these six happened. `check_body_branch.sh` already
#: spends two exit codes on the violation/undetermined half of that
#: distinction; this table spends six strings on all of it.
#:
#: Prefixed ``role_diff_loop_`` and not ``role_diff_``: §5 rules that PR time
#: is the check that judges what lands, and a reason that reads like the
#: verdict is a reason somebody will treat as one.
_BLOCKED_REASON_PREFIXES: Mapping[LoopGateStatus, str] = {
    LoopGateStatus.CHECKED_VIOLATION: "role_diff_loop_violation",
    LoopGateStatus.CHECKED_UNDETERMINED: "role_diff_loop_undetermined",
    LoopGateStatus.ROLE_UNRESOLVED: "role_diff_loop_role_unresolved",
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
# The hook — STUBS. This is the control flow, and a scaffold does not write it.
# --------------------------------------------------------------------------- #


def resolve_inputs(
    *,
    repo_root: Path,
    base_branch: str,
    branch_ref: str,
    pre_spawn_sha: str | None,
    specs: Sequence[TaskRoleSpec],
) -> LoopGateInputs:
    """Turn the loop's live state into one :class:`LoopGateInputs`. **STUB.**

    P3 implements, to §4 exactly:

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
    """
    raise NotImplementedError(
        "D8 P1 scaffold: resolve_inputs is a contract, not an implementation. "
        "P3 implements it to the four steps in this docstring."
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
    """THE hook. Called from `orchestrator._run_task` at §1's position. **STUB.**

    P3 implements:

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
    """
    raise NotImplementedError(
        "D8 P1 scaffold: check_after_implementer is the contract for the call "
        "site, not the call site. Wiring it into orchestrator._run_task is "
        "P3's edit, and the docstring's four steps are its specification."
    )
