"""The P1/P2/P3/P4 build-protocol: task roles, immutable paths, phase order.

**Unit D1. P1 wrote these signatures and their contract docstrings, P2 wrote
the seals against them, P3 (this pass) wrote the bodies and the wiring. The
docstrings remain the contract; where a 2026-08-04 operator ruling overrode
one, the ruling is named at that spot. See "Wiring, and what is enforced
today" for the call sites that exist and the ones that do not.**

**Unit D2 (P1 scaffold, in progress) adds the comparator registry: the section
headed "Unit D2 — the comparator registry" and everything it names. Its
contents are contracts, not behaviour, with two exceptions stated at their
definitions (:func:`validate_registry`, :func:`support_for_path`) and one move
(the Python comparator, now behind :class:`SignatureFingerprinter`, unchanged).
Read that section's header before adding a language: the signature half of this
gate protects zero files in the target repo today, and the registry's existence
is not coverage.**

Why this module exists
----------------------
`docs/plans/2026-08-03-classification-gating-implementation-plan.md` §2a
decomposes every unit into three mandatory phases plus one conditional:
P1 scaffold → P2 seals (author ≠ P1's) → P3 bodies (author ≠ P2's) → P4
adjudicate (author ≠ P1–P3). The value of that split comes entirely from the
separation: a seal written by the author of the code it seals is a circular
oracle, and the A-stream produced **24 vacuous seals** exactly that way. The
plan's §2a therefore forbids body agents from touching tests, schemas and
generated files.

Until now that prohibition was honour-system — and honour-system is what
produced the 24 vacuous seals. This module makes it expressible (a typed
`role:` on a task row) and enforceable (a role → immutable-paths table plus a
diff comparator that two independent call sites run).

What is deliberately NOT here
-----------------------------
The plan's v3.1 row for D1 demanded a refusal when a unit's seals-phase agent
equals its scaffold-phase agent. That rule was **withdrawn** (see the italic
correction under §3's Stream D row): `agent:` names a *model*, and the
dispatcher already spawns a fresh session per task, so two tasks are already
different authors in the sense that matters — the seal author cannot see the
scaffold author's reasoning. Refusing on model equality would enforce nothing
real. What is enforced instead: the phases **are** separate tasks (one task
may not carry two roles), they run **in order**, and each role's immutable
paths hold. Sharing a model family between a unit's seals and bodies tasks is
a *correlation* risk and produces a **warning** — never a refusal
(:func:`agent_correlation_warnings`).

The five states of `role:`
--------------------------
Four are authorable (`scaffold|seals|bodies|adjudicate`); the fifth,
:data:`Role.LEGACY`, is the **named state for a row with no `role:` key at
all** (`skills/explicit-state.md`: absence is a state, and it must be
nameable). Every `features/*/tasks.yaml` in this repo predates the protocol
and carries no role, so LEGACY must behave *exactly* as today — no immutable
paths, no ordering obligations, no warnings. LEGACY is derived, never
authored: the literal string ``legacy`` in a YAML row is a typed error, so
LEGACY cannot be spelled by hand to opt out of the protocol.

An unknown, blank, null, list-valued or multiply-spelled role is a typed
error (:class:`RoleProtocolError`) — never "treat it as legacy". A typo must
not buy a task its way out of the gate.

Immutable paths: one table, additive only
-----------------------------------------
:data:`DEFAULT_ROLE_RULES` is **compiled in**, not config-only. A table that
lived only in `.dispatcher.yaml` would evaporate with the file, and an absent
policy would read as "no restrictions" — invariant 4's exact failure mode.
Config and per-task overrides may therefore only **ADD** denied paths, never
remove one. A narrowing override is a self-weakening policy — the defect class
this whole project exists to close — and is a typed error, not a
silently-ignored line.

That additive argument used to be stated here as the reason this module "needs
no separate 'floor' tier the way `risk.py` does". **It was wrong, and
:data:`FLOOR_GLOBS` is the correction** (2026-08-07 operator ruling). The
argument covers only the DENY_GLOBS roles — two of them since the 2026-08-10
SEALS inversion, :data:`Role.SCAFFOLD` and :data:`Role.BODIES`.
:data:`Role.ADJUDICATE` is ALLOW_ONLY_GLOBS and :func:`effective_rule` builds
its writable set out of the task's own `disputed_paths:`, so an adjudicate row
that declared
`.dispatcher.yaml` got that path *allowed* — the most privileged role granted
the file that configures every role's permissions, its own included, by naming
it. There is now a real floor tier, matched at decision time against the paths
git reported and applying to all five roles, LEGACY included; see
:data:`FLOOR_GLOBS`.

The floor's first version held the policy FILE and not the code, which made it
exactly as strong as the weakest role's write permission on `src/`: a branch
could delete the floor from this module and then walk through it (measured,
2026-08-08). Since 2026-08-09 the floor also holds the gate's own two halves —
this module and `scripts/check_body_branch.sh` — and the plan-time point
covers the whole floor rather than the config file alone (P4 ruling, recorded
on `_DECLARATIONS_THAT_NAME_THE_FLOOR`). Declaring a floor path claims the
right to WRITE it; an adjudication may still RULE on the gate while writing
only its seals.

Naming the two halves was still not enough, for the same reason naming the
config file alone was not: this module decides nothing by itself. Every glob
decision it makes — the floor's own included — is handed to
`risk.matches_any_glob`, so a branch whose only change was
`src/claude_dispatcher/risk.py` was CLEAN and could dissolve the floor while
touching nothing the floor named. The floor therefore holds the whole
DELEGATION CLOSURE of its decision (five more modules, derived from source by
AST in `tests/test_floor_closure.py`, not enumerated by hand); see
:data:`FLOOR_GLOBS`. A module leaves the closure by leaving the gate path, not
by being trusted.

The one escape hatch is a reviewed edit to :data:`DEFAULT_ROLE_RULES` on the
protected base, i.e. a plan amendment. That is intentional: see the
`**/generated/**` note on :data:`DEFAULT_ROLE_RULES`.

Two independent enforcement points
----------------------------------
A check that fires only at PR time has already let a whole build cycle burn.
So:

  a. **Plan time** — :func:`validate` is a pure function of the task list. It
     rejects unparseable roles, missing phase-order edges and illegal
     (narrowing) overrides. `plan.load_tasks` raises before it returns, so a
     worklist that fails role validation never partially plans (invariant 2).
     Note what plan time can and cannot see: task rows do **not** declare the
     paths they will touch, so "a bodies task touching `tests/**`" is not
     knowable here. What *is* knowable — and what the plan-time point
     actually refuses — is a bodies task that **declares** it may touch
     `tests/**` by narrowing its override.
  b. **Diff time** — :func:`check_branch` compares a branch's diff against
     its role's effective rule. `scripts/check_body_branch.sh` is the PR-time
     and CI face of it, and the orchestrator's task loop should call the same
     function right after the implementer returns (that is the call that
     saves the build cycle, since the PR does not exist yet). All three call
     sites go through :func:`check_branch` — one public entrypoint per
     decision (invariant 1); none of them re-derive the rule.

Wiring, and what is enforced today
----------------------------------
Wired by P3 (invariant 7 — each claim here has its call site):

  * `plan.load_tasks` → calls :func:`validate` after `_validate_blocked_by`
    and raises `plan.ValidationError` on `.errors`, so a worklist that fails
    role validation never partially plans. The cross-row rules run over the
    whole list, never per row.
  * `plan.runnable_now` → consults :func:`dispatch_satisfied_statuses` per
    `blockedBy` edge instead of the module-level `_DISPATCH_SATISFIED_*`
    sets, which is what makes the seals→bodies narrowing real in `pr` mode.
  * `orchestrator.execute` → :func:`agent_correlation_warnings` alongside the
    preflight warnings (printed at run start and replayed into run.log once
    it exists). The subject read `orchestrator.run` until P3 wired it, and
    that module defines no top-level `run`: the entry point is `execute`, so
    the claim named a function that does not exist. Corrected rather than
    deleted — the claim was true about the intent and wrong about the name.
  * `repo_config.load` → validates a `roles:` section via
    :func:`role_policy_from_mapping`, so an invalid or narrowing section is a
    load failure rather than a line dropped into `RepoConfig.unknown_keys`.
    It deliberately does not *use* the parsed policy: `load` reads the
    working tree, and the gating path takes its policy from the protected
    base (:func:`load_role_policy_from_base`, invariant 6).
  * `scripts/check_body_branch.sh` → runs :func:`main` and passes its exit
    code through, so CI, PR time and any hand invocation go through
    :func:`check_branch`. Since 2026-08-09 that script also decides WHICH copy
    of this module runs: when its own `src/` lies inside the checkout under
    judgement — the shape CI has when this repository judges itself — the
    branch supplied the library, so the script reads the gate's code out of
    `<base>`'s object store instead, exactly as it already reads the policy
    and the task row from there. The one hole it cannot close is itself: a
    branch that rewrites the script owns the exit code, so the CALLER must
    invoke a copy of the script the branch cannot write. Stated in the script;
    this repository tracks no CI configuration to pin it against.
  * `loop_gate.check_after_implementer` → :func:`check_branch` inside the
    orchestrator's task loop, right after the implementer returns and before
    verify. This is the post-implementer call the P1 rulings name as the point
    that actually saves a build cycle, and until unit D8 it was the one entry
    in this section's neighbourhood that said "no call site yet". It has one:
    `orchestrator._run_task` calls `loop_gate.check_after_implementer` inside
    its cascade loop, between ``if final_status != plan_mod.DONE: break`` and
    the mechanical gate, and acts on the answer — BLOCK flips the row to
    `plan.BLOCKED` with a distinct `blocked_reason` and does NOT escalate the
    cascade, because the next rung opens with `_reset_worktree` and would
    destroy the diff a human is being blocked to read.

    Two honest qualifications, stated here because a claim in this section is
    checked mechanically and its PROSE is not. **The gate is OFF by default**
    (`RunConfig.enable_role_loop_gate`, opt-in): on a tree where
    :func:`check_branch`'s reachability arm engages, that arm costs minutes per
    branch, so a run that cannot afford it does not turn it on. Off is a NAMED
    state — `loop_gate.LoopGateStatus.NOT_ENABLED` — logged, journalled and
    stamped on every row, never a silence. And a CLEAN from the loop is NOT a
    verdict about what will land: four later spawns commit to the same branch,
    so PR time and CI remain the gate on the diff that ships. The loop saves
    the build cycle; it does not replace the two enforcement points above it.

**NOT wired, stated rather than implied**, and this paragraph is kept — with
its contents replaced — because the shape of it is what stopped this module
from reading as more enforced than it is. Three items, each owed and each
named at `loop_gate`'s §7:

  1. :func:`validate` does not refuse a batch whose rows carry more than one
     role, and it does not refuse rows that share a role but carry different
     ``immutable_paths:`` / ``disputed_paths:`` additions. Measured: such a
     worklist loads with zero errors and zero warnings. Both are caught at
     diff time by `loop_gate.LoopGateStatus.ROLE_UNRESOLVED` → BLOCK, which is
     one build cycle later than plan time and is the whole reason the item is
     still listed here.
  2. There is no deadline on the loop-time call. `loop_gate` NAMES
     `DEADLINE_EXCEEDED` and refuses a ``deadline_seconds`` it cannot honour
     rather than timing the call after the fact; the state is unreachable
     until a killable process face exists.
  3. Nothing checks the diffs the post-hook iterate spawns commit —
     `_retry_for_test_fix`, `_spawn_verifier_iterate`, `_spawn_panel_iterate`.
     PR time is the only gate on those today.

Notes for the seal author (P2)
------------------------------
  * Seals should bind to this module's public API, not to `plan.Task`. P1
    deliberately does not add a `role` field to `Task`: a field defaulting to
    `Role.LEGACY` while `load_tasks` does not yet parse it would assert
    "legacy" for rows that carry a role — a fail-open by construction. Roles
    are read off `Task.raw` (the precedent is `orchestrator`'s read of the
    unmodeled `risk:` field). P3 may add the modeled field *in the same
    commit that parses it*.
  * A coherence seal is wanted, in the spirit of `test_risk.py`'s
    `test_go_table_critical_paths_are_all_authority_paths`: every path that
    `seal_verify._TEST_PATH` calls a test **must** be denied to
    :data:`Role.BODIES`. Two independent notions of "is this a test file"
    that can disagree is invariant 5's failure mode, and `_TEST_PATH` matches
    things `tests/**` does not (`src/foo_test.go`, `**/testdata/**`).
  * The vacuity trap here is specific: a deny-row seal that passes because
    the *path list was empty* proves nothing. Assert on the returned
    :class:`PathViolation` (path AND matched glob), and include an
    empty-changed-paths row that asserts :data:`DiffVerdict.UNDETERMINED`
    rather than CLEAN.
  * :data:`DiffVerdict` has three members on purpose. "I could not compute
    the diff" must never be reported as "clean".
"""

from __future__ import annotations

import ast
import dataclasses
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping, Protocol, Sequence

if TYPE_CHECKING:  # `plan` imports this module at its own call site (P3), so a
    # module-level import here would be a cycle. plan.load_tasks must import
    # role_protocol inside the function, as preflight.run_preflight already
    # does for spawn. Type-only here; nothing at runtime.
    from . import plan as plan_mod

    # D7 (P1 scaffold, `feat/D7-gate-wiring`). Same reason and the same
    # spelling: `branch_reachability` imports THIS module at its own module
    # level, for `Role` and `DiffVerdict`, so a runtime import here would be a
    # cycle. Type-only, and deliberately so — `tests/test_floor_closure.py`
    # excludes `if TYPE_CHECKING:` from the derived delegation closure exactly
    # because such an import executes nothing and can rebind nothing, so
    # `RoleDiffResult` may name the type without putting a new module on the
    # gate path. **The moment `check_branch` actually CALLS it (step 6 below,
    # not done here), that stops being true** — measured on this revision by
    # inserting one function-local in-package import into `check_branch`:
    # `tests/test_floor_closure.py` goes 2 failed / 82 passed and names the new
    # module as an unfloored delegation. See `branch_reachability`'s
    # escalations.
    from .branch_reachability import BranchReachability

# --------------------------------------------------------------------------- #
# The closed role universe
# --------------------------------------------------------------------------- #


class Role(Enum):
    """The closed set of build-protocol roles a task may hold.

    Four authorable members map 1:1 to the plan's §2a phases. LEGACY is the
    named state for "this row has no ``role:`` key", i.e. a pre-protocol
    single-role task; it is derived by :func:`parse_role_field` and is never
    a legal YAML value.

    Every consumer dispatches over all five members with ``else: raise``
    (invariant 3). Adding a member is a plan amendment, and the exhaustiveness
    seal must redden for every consumer that has not been updated.
    """

    SCAFFOLD = "scaffold"
    SEALS = "seals"
    BODIES = "bodies"
    ADJUDICATE = "adjudicate"
    LEGACY = "legacy"


#: The roles a YAML row may spell. LEGACY is excluded by construction.
AUTHORABLE_ROLES: frozenset[Role] = frozenset(
    {Role.SCAFFOLD, Role.SEALS, Role.BODIES, Role.ADJUDICATE}
)

#: Phase order for the three mandatory phases, earliest first. ADJUDICATE is
#: conditional and out-of-band (it rules on a dispute raised by any phase), so
#: it is deliberately absent from this ordering rather than appended to it.
MANDATORY_PHASE_ORDER: tuple[Role, ...] = (Role.SCAFFOLD, Role.SEALS, Role.BODIES)

#: Canonical spelling of the role field, plus the near-miss spellings that are
#: recognised so they cannot be silently ignored. Same rationale as
#: ``plan._DEP_FIELD_ALIASES``: a dropped ``roles: bodies`` would restore the
#: honour system, which is what this unit exists to end. More than one present
#: is an error, not a merge.
ROLE_FIELD_CANONICAL = "role"
ROLE_FIELD_ALIASES: tuple[str, ...] = ("role", "roles", "task_role")

#: Per-task override field: additional immutable globs. ADD-only.
IMMUTABLE_OVERRIDE_FIELD = "immutable_paths"

#: Per-task field naming the artifact under dispute. REQUIRED for
#: :data:`Role.ADJUDICATE` and forbidden on every other role.
DISPUTED_PATHS_FIELD = "disputed_paths"

#: The ``.dispatcher.yaml`` section this module reads (base-pinned).
CONFIG_SECTION = "roles"

#: The ``matched_glob`` a violation carries when the rule is ALLOW_ONLY_GLOBS
#: and the path matched **none** of the allowed globs. There is no glob that
#: "says so" for an allowlist miss, and the two alternatives are both worse: a
#: magic string invites callers to compare against a literal, and a nullable
#: field makes every consumer handle None (D1 P2 ruling — "a named state, not a
#: magic string and not a nullable"). Deliberately not glob-shaped, so it can
#: never be mistaken for a pattern or accidentally match a path.
ALLOWLIST_MISS = "<allowlist miss: path is outside the role's writable set>"

#: The ``matched_glob`` a violation carries when the path was denied by
#: ``seal_verify.is_test_path`` rather than by a glob — see
#: :data:`TEST_PATH_DELEGATED_ROLES`. Also the marker whose PRESENCE in a
#: rule's ``globs`` turns that delegation on, so the delegation is a property
#: of the rule (data), not of the role (a hardcode a caller-supplied policy
#: could not switch off).
#:
#: The marker names a FACT — *this repo's test files* — and the rule's KIND is
#: what turns that fact into a verdict. :func:`evaluate_changed_paths` reads it
#: in BOTH glob kinds (2026-08-10): on a DENY_GLOBS rule it FORBIDS the test
#: files and is reported as the ``matched_glob``; on an ALLOW_ONLY_GLOBS rule it
#: GRANTS them, and a path outside the writable set is still reported as
#: :data:`ALLOWLIST_MISS`, never as this marker — on the allow side the marker
#: is the reason a path was permitted, so it can never be the reason one was
#: refused. :data:`Role.SEALS` is the rule that needs the allow reading.
SEAL_VERIFY_TEST_PATHS = "<seal_verify.is_test_path: this repo's test files>"

#: The roles whose deny set includes ``seal_verify``'s test-path predicate.
#: D1 P2 ruling: the role gate does not keep its own notion of what a test
#: file is. Six of eleven ``seal_verify._TEST_PATH`` alternatives were
#: uncovered by the globs below — ``handler_test.js``, singular ``test/`` at
#: root and nested, ``__tests__/``, ``spec/``, ``fixtures/`` — so a body agent
#: could add a file `seal_verify` already treats as a seal and this gate said
#: CLEAN. One matcher, one fact.
#:
#: :data:`Role.SEALS` is deliberately NOT here, and after the 2026-08-10
#: inversion that is a ruling rather than an oversight. This constant means
#: "roles whose **DENY** set delegates" — :func:`built_in_policy` reads it to
#: APPEND the marker to a deny set — and for SEALS the same marker is an ALLOW.
#: Adding SEALS here would hand the seal author a rule denying the only files it
#: exists to write. The marker lives in the SEALS row's own ``globs``, where the
#: rule's kind decides its verdict.
TEST_PATH_DELEGATED_ROLES: tuple[Role, ...] = (Role.SCAFFOLD, Role.BODIES)


class RoleProtocolError(ValueError):
    """Raised when a row's role/override/disputed-paths fields are invalid.

    A `ValueError` subclass so `plan.load_tasks` can surface it as a
    `plan.ValidationError` without a second error vocabulary. The message
    always names the task key, because these are diagnosed from a run log.
    """


# --------------------------------------------------------------------------- #
# The immutable-path table (real data — a contract, not logic)
# --------------------------------------------------------------------------- #


class RuleKind(Enum):
    """How a role's glob set is read.

    DENY_GLOBS
        The role may write anything EXCEPT a path matching one of the globs.
    ALLOW_ONLY_GLOBS
        The role may write ONLY paths matching one of the globs; everything
        else is immutable. Used by ADJUDICATE, whose writable set is the
        disputed artifact and is therefore per-task data, not a static table.
    UNRESTRICTED
        No path restriction at all. Held solely by :data:`Role.LEGACY`, and
        named rather than encoded as "DENY_GLOBS with an empty tuple" so that
        an accidentally-emptied deny list can never read as a pass
        (`skills/explicit-state.md`: "could this pass without doing
        anything?").

    Consumers dispatch over all three with ``else: raise``.
    """

    DENY_GLOBS = "deny_globs"
    ALLOW_ONLY_GLOBS = "allow_only_globs"
    UNRESTRICTED = "unrestricted"


@dataclass(frozen=True)
class RoleRule:
    """One role's path policy.

    ``globs`` is gitignore-style, matched by :func:`first_matching_glob` via
    ``risk.matches_any_glob`` — this module owns no second glob translator.
    Patterns are written ``**/x/**`` rather than ``x/**``: a leading ``**/``
    matches zero directories in ``risk._glob_to_regex``'s translation
    (``(?:.*/)?``), so one pattern covers both the root and the vendored
    ``sub/project/...`` layout and a root-anchored twin would be dead weight —
    one pattern, one fact. :data:`FLOOR_GLOBS` is spelled the same way for the
    same reason.

    (Until 2026-08-09 this paragraph cited ``risk.AUTHORITY_FLOOR_GLOBS`` as the
    precedent. No such constant exists in this repository — it lives on an
    unmerged branch — so the citation sent the reader to code they could not
    read, which is the claim-without-mechanism shape this unit exists to
    remove. Replaced with the mechanism itself and with a constant that is
    actually here.)

    ``rationale`` is not decoration: it is the disposition a violated row
    prints, so an agent that trips the gate is told *why* the path is not its
    to touch.

    Invariants a constructed rule must satisfy (checked by
    :func:`validate_rule`): DENY_GLOBS and ALLOW_ONLY_GLOBS carry at least one
    glob for a static rule; UNRESTRICTED carries none; no glob is blank.
    """

    role: Role
    kind: RuleKind
    globs: tuple[str, ...]
    rationale: str


# The compiled-in default table. Every entry is effectively a floor, because
# neither config nor a per-task override may remove one.
#
# This tuple holds GLOBS ONLY. The test-file category is not in it as a
# concept — it is delegated to `seal_verify.is_test_path` — but the specific
# test-shaped globs below stay, because they are what makes a violation report
# name the pattern that forbade the path (``**/tests/**`` rather than "the
# predicate"), and because each is pinned by its own mutation-resistance seal.
# The delegation marker is added by `built_in_policy`, not here: it is not a
# glob, so it has no probe path and belongs to no row of the glob table.
#
# Deviations from the operator's proposed defaults, and why:
#
#   * ``**/tests/**`` rather than ``tests/**``, and the test-shaped-filename
#     globs alongside it: a body agent that adds ``src/foo_test.go`` or edits
#     ``**/testdata/**`` has written its own seal just as surely as one that
#     edits ``tests/``. Path-shape only — no keyword matching. Everything
#     `seal_verify` calls a test and these globs miss is caught by the
#     delegation (:data:`TEST_PATH_DELEGATED_ROLES`).
#   * ``**/.dispatcher.yaml`` is refused to ALL FOUR authorable roles, scaffold
#     included (2026-08-04 P1 ruling, overriding P1's own contrary note here).
#     A unit's per-task override lives in its task row, so no role ever needs
#     to edit the policy file, and a role that can edit the file configuring
#     its own permissions is the self-widening shape this unit exists to
#     remove. Since the 2026-08-10 SEALS inversion it is a named deny glob on
#     two rows and an ALLOWLIST MISS on the SEALS row — the same refusal
#     reached two ways — and :data:`FLOOR_GLOBS` refuses it to all five roles
#     regardless of what any row says.
#   * ``**/generated/**`` appears NOWHERE (2026-08-04 P1 ruling, overriding
#     P1's SEALS/BODIES entries). The property wanted is not "bodies never
#     touch generated files" but "generated files equal generator output",
#     which the regenerate-and-diff gate owns for every role in every unit.
#     Denying the path made generator units (A3/A4's ``fsmgen``, whose bodies
#     legitimately commit regenerated output) undrivable, and ADD-only
#     overrides gave no escape. Any unit with generated output carries that
#     gate in its seals instead.
#   * ``**/roles/*.md`` + ``**/reviewer_prompts/**`` + ``**/verifier_prompts/**``
#     for every DENY_GLOBS role (all three when this was written; SCAFFOLD and
#     BODIES since SEALS was inverted, which refuses all three trees as an
#     allowlist miss instead): those are machine-read instructions that
#     the review gate executes, so editing them edits the reviewer that is about
#     to judge the change. SCAFFOLD was added 2026-08-09 (S4): the rationale is
#     not role-specific, and `src/` — where both prompt directories live — is
#     the one tree SCAFFOLD exists to write in, so it was the role with the
#     easiest reach and the only one without the deny. `_shared.md` is
#     concatenated into EVERY reviewer seat's prompt by
#     `cross_family_reviewer._load_prompt`, which is why the directory glob is
#     the right grain and a list of family names would have missed it.
#: The one path every role may write regardless of its rule: the per-unit
#: RULINGS record (D-66, operator ruling 2026-08-14).
#:
#: **A COMMONS, and the exact mirror of :data:`FLOOR_GLOBS`.** The floor is a
#: deny set unioned into the DECISION rather than into any policy, because
#: ADJUDICATE's rule is ALLOW_ONLY and a deny set cannot be expressed as a glob
#: in an allow list. This is the same move from the other end: an allow that
#: every role has, applied at the decision, so no role's RULE changes.
#:
#: That placement was not the first attempt and the seals are why. Adding this
#: glob to ADJUDICATE's built rule broke
#: ``test_effective_rule_for_allow_only_is_exactly_the_disputed_paths`` and
#: ``test_effective_rule_never_builds_an_allow_only_rule_that_allows_nothing``
#: — correctly. They pin a real property: **the writable set of the most
#: privileged role is entirely visible in its task row.** A compiled-in glob
#: silently added to that set is the ADJUDICATE self-widening hazard in
#: miniature, with the operator holding the pen. The rule stays exactly the
#: row; the commons is applied beside it.
#:
#: **Why it exists.** DF-1-4 (adjudicate) ruled on a condemned seal, then wrote
#: two docstrings recording that it had ruled — and was blocked, because
#: ``disputed_paths`` names the file to RULE ON and never the files that POSE
#: the dispute. The instinct was right: a module saying "P4 will rule on this"
#: is false the moment P4 rules. Every role has that need, and none could write
#: the prose carrying it except into ``summary.md``, archived per run and read
#: by nobody afterwards.
#:
#: **Why this shape and not a docstring carve-out.** The alternative was to let
#: a role edit docstrings inside files it may not otherwise write, enforced by
#: an AST-with-docstrings-stripped comparison. Enforceable, and it puts the
#: record where the reader is — but it widens EVERY role to touch EVERY file.
#: This is one directory that four of five roles could already write (measured;
#: only ADJUDICATE refused it).
#:
#: **The line that must not be crossed.** These files are DOCUMENTATION. If a
#: gate is ever built that READS them, a role writing its own rulings becomes a
#: role influencing its own judgement — D-65's lesson (a prose contract no gate
#: can enforce) running in reverse, and worse. Sealed by
#: ``test_rulings_channel.py::test_seal_D66_no_verdict_machinery_reads_...``.
RULINGS_GLOB: str = "**/docs/rulings/**"


class SuiteExpectation(Enum):
    """What the repo's test command is EXPECTED to say at the end of a role's
    task. The mechanical gate reads this instead of assuming green.

    **Why this exists (D-58, found by dogfooding DF-1-2).** The dispatcher was
    built around FIX-SHAPED tasks: one task writes the fix AND its test, the
    suite ends green, and :mod:`seal_verify` then reverts the fix and requires
    red. The scaffold-first protocol inverts that: a SEALS task writes ONLY
    tests, by a different author, and they must end RED — the body arrives in a
    later task.

    Measured on DF-1-2: the mechanical gate read its six own red seals as a
    failure, spawned a fix-the-tests agent, then cascaded to a higher effort
    rung which RESET the seals away. `seal_verify` skipped the same branch
    ("test-only change — no fix to invert"), so the task got the worst of both
    gates: accused by one, unexamined by the other.
    """

    #: The suite must end green. Every role's behaviour before D-58.
    GREEN = "green"

    #: The suite must end RED, and red ONLY because of rows this branch wrote.
    #: Two exit codes, no output parsing (see :func:`seal_verify.
    #: run_seal_redness`): the suite as committed must be red, and the suite
    #: with the branch's own test files reverted to base must be green.
    #:
    #: **BUILT AND SEALED, NOT CURRENTLY ASSIGNED TO ANY ROLE.** See
    #: :data:`SuiteExpectation.UNJUDGED` for why SEALS does not use it yet.
    RED_FROM_OWN_ROWS = "red_from_own_rows"

    #: The gate does not judge this role's suite state, and says so. A NAMED
    #: state, journaled with its reason — never a silent pass, and never the
    #: green check that would accuse the role of failing for doing its job.
    #:
    #: **Why SEALS sits here (operator ruling, 2026-08-14).** Two P2 authors in
    #: wave 1 produced two different, both defensible, shapes:
    #:
    #:   * DF-1-2 wrote PLAINLY RED seals — the suite exits non-zero.
    #:   * DF-4-2 wrote CONDITIONAL XFAIL seals:
    #:     ``@pytest.mark.xfail(<seam still raises the P1 stub>,
    #:     raises=NotImplementedError, strict=True)``. The condition is computed
    #:     at import by CALLING the seam, so the marker self-retires when the
    #:     body lands with no test edit — which matters because P3 may not touch
    #:     ``tests/``. ``strict=True`` makes an unexpectedly PASSING seal a hard
    #:     failure, so vacuity is caught by the marker itself, and ``raises=``
    #:     makes any other exception a real failure.
    #:
    #: The second is the more disciplined shape and it EXITS ZERO. So run 1 and
    #: run 2 of :func:`seal_verify.run_seal_redness` both exit 0 and are
    #: indistinguishable — "eight xfailed seals" and "no seals at all" are the
    #: same exit code. Exit codes cannot separate them, and the whole reason
    #: that gate refuses to parse test output is that this project has twice
    #: shipped a false green from doing so.
    #:
    #: Judging SEALS by the RED rule would therefore FAIL DF-4-2, which already
    #: passed its panel and merged. Rather than standardise the weaker style to
    #: fit the gate, the gate abstains until the style question is ruled. What
    #: is NOT parked: a SEALS task still never gets a fix-the-tests re-spawn —
    #: this returns before the suite is ever run, so the corrective prompt that
    #: would tell an agent to weaken its own seals cannot fire.
    UNJUDGED = "unjudged"


#: Per-role suite expectation. TOTAL over :class:`Role` — a new member must
#: land in :func:`suite_expectation`'s raise, not in a default, because the
#: permissive answer here is "green" and green is what silently accused DF-1-2.
#:
#: ONLY ``SEALS`` differs from the pre-D-58 behaviour. The other four are
#: written down as GREEN because that is what they already did, NOT because a
#: ruling was made about them — and one of those rulings is measurably not safe
#: to make yet. ``BODIES: GREEN`` here means "unchanged", not "a body task must
#: end fully green": on this very branch D6 has THREE ``body(...)`` commits and
#: D5 has two, so a unit's seals are turned green incrementally and an
#: intermediate body task legitimately ends RED. Ruling BODIES explicitly would
#: fail those tasks exactly the way SEALS is failing now. When partial-body
#: units have been measured, this table is where that ruling lands — one entry,
#: not a rewrite.
_SUITE_EXPECTATIONS: dict[Role, SuiteExpectation] = {
    Role.SCAFFOLD: SuiteExpectation.GREEN,
    Role.SEALS: SuiteExpectation.UNJUDGED,
    Role.BODIES: SuiteExpectation.GREEN,
    Role.ADJUDICATE: SuiteExpectation.GREEN,
    Role.LEGACY: SuiteExpectation.GREEN,
}


def suite_expectation(role: Role) -> SuiteExpectation:
    """The suite state `role` is expected to leave behind. Total over
    :class:`Role`; raises on an unmapped member rather than defaulting.

    **IMPLEMENTED, not stubbed**, under the standing exception and for the
    reason :func:`loop_gate.decision_for` gives: "every member is mapped, and
    an unmapped one raises" is not checkable against a function that raises for
    everything.
    """
    try:
        return _SUITE_EXPECTATIONS[role]
    except KeyError:
        raise RoleProtocolError(
            f"no suite expectation is defined for {role!r}; a new Role member "
            "must be given one here, not fall through to whichever branch "
            "happens to be last — and on this dispatch the permissive branch "
            "is GREEN, which is the answer that accused DF-1-2 of failing for "
            "doing its job"
        ) from None


DEFAULT_ROLE_RULES: tuple[RoleRule, ...] = (
    RoleRule(
        role=Role.SCAFFOLD,
        kind=RuleKind.DENY_GLOBS,
        globs=(
            "**/tests/**",
            "**/test_*.py",
            "**/*_test.py",
            "**/*_test.go",
            "**/*.test.*",
            "**/*.spec.*",
            "**/testdata/**",
            "**/conftest.py",
            "**/.dispatcher.yaml",
            # D7, P4 2026-08-12, and this row goes BEYOND the escalation, which
            # named BODIES alone. The wider reading is the one that survives,
            # and the reason is a measured composition rather than symmetry:
            # `_DISPOSITION_VERDICTS` maps ACCEPTED to CLEAN, and the head
            # declarations are read out of `branch_ref`'s object store — which
            # holds every commit on the branch's history, not only the ones the
            # judged phase made. So a SCAFFOLD branch that lands an appeal
            # beside its stub pre-clears the BREACH the BODY has not written
            # yet: at P3 the finding is introduced, `adjudicate` turns it
            # ACCEPTED, `verdict_of` answers CLEAN, and the body discloses
            # nothing and touches nothing. That is the rubber stamp the appeal
            # was designed to make expensive, arriving one commit early.
            #
            # It costs SCAFFOLD nothing real: its own obligation is NOT_RUN, so
            # a scaffold branch is never shown a finding, and an appeal written
            # without one is a declaration about something nobody measured.
            # SEALS needs no row — its rule is ALLOW_ONLY_GLOBS and this path
            # is neither a test file nor under `docs/`, so it is refused as an
            # allowlist miss. LEGACY is UNRESTRICTED and is out of scope here
            # by construction; the floor is the only thing that reaches it, and
            # the entry above records why this path is not on the floor.
            "**/.dispatcher.staged.yaml",
            "**/roles/*.md",
            "**/reviewer_prompts/**",
            "**/verifier_prompts/**",
        ),
        rationale=(
            "P1 must not write the seals it will be judged by, nor the "
            "instructions the reviewer and verifier execute over its own "
            "branch; a scaffold author who writes tests re-creates the "
            "circular oracle that produced 24 vacuous seals (plan §5)"
        ),
    ),
    # SEALS is the one authorable role stated as an ALLOWLIST (2026-08-10 P4
    # ruling, `tests/test_role_layout_coverage.py`). It was a deny list of
    # ``**/src/**``, ``**/schema/**`` and the three instruction trees, and that
    # list protected NO implementation source in the layouts the target repos
    # are written in: Go lives in ``cmd/``, ``internal/`` and ``pkg/``, and
    # evenplay-mono is 2,288 Go / 996 TS+TSX / 781 SQL / 316 Java / 0 Python. A
    # seal author could write the code its own seal judges — a vacuous seal, by
    # the row's own rationale. The fault ran both ways: ``**/src/**`` also
    # DENIED ``web/src/app.test.tsx`` and the Maven-layout Java seal to the one
    # role that exists to write them, and ``immutable_paths:`` is ADD-only with
    # no negation form, so nothing could buy them back.
    #
    # Extending the deny list is not available and that is a fact about the
    # LANGUAGE, not about these spellings: Go co-locates ``ledger_test.go`` with
    # ``ledger.go``, so every directory-shaped glob denies the seal exactly when
    # it denies the body (measured: adding ``**/cmd/**``, ``**/internal/**`` and
    # ``**/pkg/**`` turns 3 layout rows green and 4 red). Repo-configurable
    # ``immutable_paths:`` is the same move through the same monotone engine.
    #
    # So the writable set is stated as the CLOSED set it always was: this
    # repo's test files, plus documentation.
    #
    #   * :data:`SEAL_VERIFY_TEST_PATHS` is the repo's ONE matcher for "is this
    #     a seal", carried in the row's own globs rather than through
    #     :data:`TEST_PATH_DELEGATED_ROLES` — that constant means "roles whose
    #     DENY set delegates", and ``built_in_policy`` reads it to append the
    #     marker to a deny set. Here the same marker is an ALLOW. One marker,
    #     one fact; the rule's KIND decides the verdict.
    #   * ``**/docs/**`` is not optional. A seal author writes the ADR and the
    #     note that go with the seal, and a false refusal has no override in
    #     this system. Spelled ``**/docs/**`` and not ``docs/**`` for the reason
    #     given on :class:`RoleRule`: root-anchoring it would repeat, in
    #     documentation, the exact mistake ``**/src/**`` made in source. No
    #     extension filter, because ``docs/`` already holds .json and .log.
    #
    # What the five departed globs cost, and where each is paid instead: all
    # five are still refused to SEALS, as an ALLOWLIST MISS rather than by a
    # named pattern, because none is one of this repo's test files and none is
    # under ``docs/``. ``**/.dispatcher.yaml`` is refused twice over — the miss
    # and :data:`FLOOR_GLOBS`. ``README.md`` at the root becomes unwritable to
    # SEALS, deliberately.
    RoleRule(
        role=Role.SEALS,
        kind=RuleKind.ALLOW_ONLY_GLOBS,
        globs=(
            SEAL_VERIFY_TEST_PATHS,
            "**/docs/**",
        ),
        rationale=(
            "P2 commits its seals RED against P1's stubs; a seal author who "
            "may edit the implementation can make its own seal pass, which is "
            "the definition of a vacuous seal. P2 writes the seal and the "
            "documentation that goes with it, and nothing else — a deny list "
            "of implementation directories cannot say that in a repository "
            "where Go puts ledger_test.go beside ledger.go"
        ),
    ),
    RoleRule(
        role=Role.BODIES,
        kind=RuleKind.DENY_GLOBS,
        globs=(
            "**/tests/**",
            "**/test_*.py",
            "**/*_test.py",
            "**/*_test.go",
            "**/*.test.*",
            "**/*.spec.*",
            "**/testdata/**",
            "**/conftest.py",
            "**/schema/**",
            "**/.dispatcher.yaml",
            # D7 escalation 3, ruled 2026-08-12 (P4). This is
            # `branch_reachability.DECLARATION_PATH`, and the sentence that
            # forces the row is that module's own: without it, the ONE tooth
            # between a BREACH and the word "TODO" is `wiring` being
            # non-whitespace, and P4's earlier ruling already said four teeth
            # were not enough. BODIES is the role the reachability gate BLOCKS,
            # and an appeal written by the party being judged is the honour
            # system this whole protocol opens by naming as the thing that
            # produced 24 vacuous seals.
            #
            # Spelled `**/.dispatcher.staged.yaml` and measured under the
            # module's own lens on this revision: it matches the file at the
            # root, at `sub/project/`, and under any directory, and does NOT
            # match `.dispatcher.yaml` one row up — the two files are
            # different artifacts with different rules and one glob must not
            # quietly cover both.
            #
            # NOT on `FLOOR_GLOBS`, and that is the ruling rather than an
            # oversight: a floored path is writable by NOBODY, so the appeal
            # would not exist. The floor is for things no role may touch; this
            # is a thing exactly one role may touch, and ADJUDICATE reaches it
            # through `disputed_paths:`, which is per-task, reviewed, and
            # names the artifact out loud.
            "**/.dispatcher.staged.yaml",
            "**/roles/*.md",
            "**/reviewer_prompts/**",
            "**/verifier_prompts/**",
        ),
        rationale=(
            "P3 makes the seals pass by implementing them, never by editing "
            "them (plan §2a); the schema is the sole source, the role policy "
            "is not the body agent's to widen, and the reachability appeal "
            "(.dispatcher.staged.yaml) is written by the adjudicator that "
            "reviewed the finding, never by the branch the finding is against"
        ),
    ),
    RoleRule(
        role=Role.ADJUDICATE,
        kind=RuleKind.ALLOW_ONLY_GLOBS,
        globs=(),  # supplied per task by `disputed_paths:` — see below
        rationale=(
            "P4 rules on ONE disputed artifact and touches nothing else; its "
            "writable set is the task's `disputed_paths:`, which is REQUIRED "
            "(an absent list means 'nothing', never 'anything')"
        ),
    ),
    RoleRule(
        role=Role.LEGACY,
        kind=RuleKind.UNRESTRICTED,
        globs=(),
        rationale=(
            "a row with no `role:` key is a pre-protocol single-role task and "
            "must behave exactly as it does today; every features/*/tasks.yaml "
            "in this repo is such a row"
        ),
    ),
)

#: Globs a `disputed_paths:` entry may never be, in any role. A wildcard
#: adjudication is not an adjudication: it converts ALLOW_ONLY into
#: UNRESTRICTED with extra steps.
#:
#: This is a NAMED denylist and it is not the enforcement. Six literals is an
#: OPEN set in the unit whose whole doctrine is closed ones (D1-inputs I2):
#: `**/**`, `**/**/*`, `**/**/**`, `*/**`, `**/*/**` and `*/*` are none of
#: them, all parse today, and each grants the whole repo. The closed rule is
#: :func:`_names_no_artifact`, which refuses every one of these six literals
#: too — so a deletion from this set changes no verdict, and the rows in
#: `test_role_protocol_table.py` and `test_role_protocol_parse.py` that pin
#: these six by name keep pinning the spellings the doctrine calls out
#: explicitly.
FORBIDDEN_DISPUTED_GLOBS: frozenset[str] = frozenset(
    {"*", "**", "**/*", "/", "./**", "."}
)

#: The glob metacharacters this repo's engine (``risk._glob_to_regex``) reads.
#: Everything else in a declaration is literal text — a name.
_GLOB_METACHARACTERS = "*?[]"

#: The non-overridable floor: globs NO authorable role may write, whatever the
#: policy says and whatever the task declared (2026-08-07 operator ruling).
#:
#: The table above is "effectively a floor" only because config and per-task
#: overrides may not *remove* a deny entry — and that argument covers the
#: DENY_GLOBS roles and nothing else, which since the 2026-08-10 SEALS
#: inversion is :data:`Role.SCAFFOLD` and :data:`Role.BODIES` alone.
#: :data:`Role.ADJUDICATE` is
#: ALLOW_ONLY_GLOBS, and :func:`effective_rule` builds its writable set out of
#: the task's own ``disputed_paths:``, so an adjudicate row that declared
#: ``.dispatcher.yaml`` got that path *allowed* and the gate reported CLEAN —
#: the most privileged role rewriting the policy file that configures every
#: role's permissions, its own included. That is the self-widening shape this
#: unit exists to remove, and the table cannot close it because the table is
#: not what ADJUDICATE is judged by.
#:
#: Two properties this constant carries that the table does not:
#:
#:   * it is unioned into the decision **at evaluation time**, not merged into
#:     a :class:`RolePolicy` — so a policy handed to :func:`check_branch` that
#:     omits it entirely (a base-pinned ``roles:`` section, a caller-supplied
#:     policy) still gets it;
#:   * it is matched against the paths **git reports as changed**, never
#:     against the strings a task declared. That is the crux: the floor cannot
#:     be spelled around, because it never reads the spelling. ``sub/**`` in
#:     ``disputed_paths:`` contains no trace of the floor path and still cannot
#:     buy ``sub/project/.dispatcher.yaml``.
#:
#: Read at exactly two places, one per enforcement point (D1 P3):
#: :func:`_floor_violations`, called from :func:`check_branch` for EVERY role
#: including :data:`Role.LEGACY`, and :func:`_floor_glob_named_by`, called from
#: :func:`parse_task_role_spec` so a row that declares a floor path is refused
#: at plan time instead of after a build cycle. Adding a glob here without
#: adding its literal rows to ``tests/test_role_protocol_floor.py`` reddens the
#: totality seal.
#:
#: **The gate's own two halves, 2026-08-09 (S2/S3).** The config file was on the
#: floor and the code that *implements* every rule the config merely tunes was
#: not, so the floor was exactly as strong as the weakest role's write
#: permission on ``src/``: a branch that rewrote this module deleted the floor
#: and then walked through it. The entrypoint is here for the same reason and
#: cannot be separated from it — protecting the library while leaving the script
#: writable protects nothing (the branch replaces the script), and protecting
#: the script while leaving the library writable protects nothing either (the
#: script faithfully executes the branch's rules). One artifact, two files.
#:
#: Both are spelled PATH-QUALIFIED rather than by basename (P4 ruling,
#: 2026-08-09, recorded on ``_FLOOR_ROWS``): a floor has no override, so
#: ``**/role_protocol.py`` would permanently forbid every file that ever
#: acquires that basename — a vendored copy, a fixture, an unrelated future
#: module — with nothing able to buy it back. The leading ``**/`` still covers
#: the nested layout, because it matches zero directories in this module's
#: translation. The move-then-edit bypass is closed by
#: :func:`changed_paths_between`'s ``--no-renames``: each side of a move is its
#: own path, and the old path is a floor hit, so a sanctioned move must edit
#: this tuple on the protected base rather than happen silently.
#:
#: **The gate's THIRD artifact, 2026-08-09 (D2 P4): the Go signature helper.**
#: The signature half of this gate stopped being pure Python the moment a
#: language needed a toolchain. `src/claude_dispatcher/go_signature_fingerprint/`
#: is a program that decides what a Go signature IS, and its answer is what
#: `compare_signatures` compares — so a bodies branch that rewrote it to emit an
#: empty symbol list would have every Go file in its diff report as unchanged
#: and would walk through the signature gate it had just switched off. That is
#: the 2026-08-08 measurement (`FLOOR_GLOBS = ()` appended to the branch's own
#: `role_protocol.py`, told `CLEAN … against the 0-glob floor`) one file to the
#: left, and the same reasoning that put the library and the entrypoint here
#: applies to it unchanged: an artifact whose output the verdict is computed
#: from is part of the machinery, not part of the work.
#:
#: A DIRECTORY glob, not a file glob, and the whole subtree: the helper is a Go
#: module, so its `go.mod` chooses the language version the parse is done
#: against and any future file under it is a parser input. A floor that covered
#: `main.go` alone would leave the rest of the program writable, which protects
#: the shape of the helper and not its behaviour — the struct-tag lesson at
#: :class:`GoSignatureFingerprinter`, applied to the gate's own source.
#:
#: The floor entry landed FIRST on purpose: a floor that arrives with enrolment
#: is a floor that was absent for every commit that built the thing it protects.
#:
#: **CORRECTED BY P4, ``feat/D6-enrol2``, base ``d8fd825``, 2026-08-11.** This
#: read "It is deliberately NOT enrolled yet (:data:`GO_SUPPORT` is in
#: :data:`PENDING_COMPARATORS`)". That was TRUE when it landed at ``fcb4900``,
#: 2026-08-09, and went stale at ``f45b2ab``, 2026-08-10, when the row moved.
#: Measured at ``d8fd825``: ``COMPARATORS`` holds python, go and typescript and
#: ``PENDING_COMPARATORS`` is ``()``. The ORDERING claim is what this note was
#: for and it is kept; the registry-state claim is struck rather than updated,
#: because a note about the floor has no reason to restate a registry's contents
#: and restating them is how it went stale. ``enrolled_languages()`` and
#: ``test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees`` are
#: where that question is answered.
#:
#: **The DELEGATION CLOSURE, 2026-08-09 (P4, second ruling).** Naming the two
#: halves protected the file that CALLS the matcher and not the matcher. This
#: module delegates every glob decision — including every floor decision — to
#: ``risk.matches_any_glob``; the deny table delegates "is this a test file" to
#: ``seal_verify.is_test_path``; :func:`check_branch` reads the base-pinned
#: policy and every base blob the signature half compares through
#: ``repo_config`` (and ``yaml_io``, which parses the pinned ``roles:``); and
#: ``seal_verify`` imports ``mechanical_verify`` at MODULE level, so that body
#: executes on the gate path and can rebind anything the gate is about to call.
#: All five are on the floor for the same reason this module is. The closure is
#: DERIVED by AST from this module's source in ``tests/test_floor_closure.py``
#: rather than listed, so a delegation added later reddens instead of widening
#: the trusted base in silence; a module leaves it by leaving the gate path.
#:
#: Two costs, recorded because they were accepted rather than avoided. Both
#: sibling CRITICALs (``seal_verify.is_test_path``'s regex anchor bypass,
#: ``risk.py``'s quoted-path escalation) are now inside the closure, so neither
#: is fixable by a branch under review — each is a protected-base edit. And the
#: floor went from three unusual basenames to eight including ``risk.py`` and
#: ``yaml_io.py``: :func:`_floor_glob_named_by` matches by BASENAME, so
#: declaring a path called ``risk.py`` anywhere is now refused at plan time
#: while ``vendor/thirdparty/risk.py`` stays writable at diff time. That
#: asymmetry runs in the safe direction — plan time strictly stricter than diff
#: time, so it can only false-refuse — and the false refusal has a spelling
#: that works (``vendor/**``).
#:
#: **Integrating the two rulings (P4 adjudication, 2026-08-09).** The Go helper
#: and the delegation closure landed in parallel and each raised the floor from
#: the same three globs, so their union — NINE globs — is larger than either
#: ruling wrote and neither ruling's arithmetic describes it. Two corrections
#: the merge makes explicit rather than leaves to be rediscovered:
#:
#:   * "three basenames to eight" above counts FILE globs, and it survives the
#:     union unchanged at eight of the nine, because the Go entry is the one
#:     floor glob that contributes no basename.
#:   * That is not a typing detail. :func:`_floor_glob_named_by` takes each
#:     floor glob's LAST SEGMENT as the probe, and the Go entry's last segment
#:     is ``**``; a declaration can only name it with a pure-wildcard tail, and
#:     a pure-wildcard tail is exactly what that function refuses (it names a
#:     TREE, not a file). Measured 2026-08-09 against the merged tuple: no
#:     declaration reaches the Go glob at plan time —
#:     ``go_signature_fingerprint``, ``main.go``, ``go.mod`` and the full
#:     ``src/claude_dispatcher/go_signature_fingerprint/main.go`` all return
#:     None. So the closure ruling's "plan time strictly stricter than diff
#:     time" holds for the eight file globs and NOT for the ninth, which is
#:     plan-time invisible and diff-time enforced like everything else. The
#:     floor is not weaker for it — :func:`_floor_violations` is the
#:     enforcement point and it reads the whole tuple — but a subtree glob buys
#:     no early refusal, and a later ruling adding one should expect that.
#:
#: **The gate's FOURTH artifact, 2026-08-10 (D4 P4): the TypeScript parser
#: subtree.** ``src/claude_dispatcher/ts_signature_fingerprint/`` is the Go
#: entry's argument in a language where it is strictly worse, and the floor
#: lands BEFORE anything is vendored into it — which is the whole reason this is
#: a P4 commit and not part of the vendoring one. Three differences from the Go
#: subtree, each of which raises the stake rather than lowering it:
#:
#:   * The subtree will hold a **9.1 MB third-party blob** (``typescript.js``,
#:     5.9.3). Nobody re-reads that in a diff. The Go helper is a few hundred
#:     reviewable lines; this one is an artifact whose only practical review is
#:     a digest, and a digest that a branch could edit alongside the bytes is no
#:     review at all. :data:`TS_VENDORED_PARSER_SHA256` therefore lives in THIS
#:     module — already the third entry below — and the parser bytes live under
#:     this glob, so defeating the check needs two floor violations rather than
#:     one consistent edit.
#:   * Unlike ``go``, which is a system binary outside every repository, the
#:     only TypeScript parser on a typical machine is inside the tree under
#:     judgement. The resolution rule (:func:`ts_parser_home`) keeps the gate
#:     out of it; this glob is what keeps the branch out of the gate's own copy
#:     when the repository judges ITSELF, which is the case where
#:     "dispatcher-owned" and "branch-writable" stop being opposites.
#:   * The subtree is FLAT by contract (:data:`TS_HELPER_PACKAGE_DIR`), so the
#:     trailing ``/**`` protects three named files today. It is still a subtree
#:     glob and not three file globs, for the Go entry's reason: a later file
#:     beside them — a second parser, a config, a second helper entry point —
#:     is a parser input the day it lands, and a floor that had to be extended
#:     for it is a floor that was absent for the commit that added it.
#:
#: TEN globs now. The arithmetic above is unchanged where it counts: the new
#: entry is the SECOND that contributes no basename, because its last segment is
#: also ``**``, so eight of ten are refused at plan time and two are diff-time
#: only. Measured 2026-08-10 against this tuple, and it is the same measurement
#: the Go entry recorded: ``ts_signature_fingerprint``, ``typescript.js``,
#: ``main.cjs`` and the full
#: ``src/claude_dispatcher/ts_signature_fingerprint/typescript.js`` all return
#: None from :func:`_floor_glob_named_by`.
#:
#: ``scripts/check_body_branch.sh`` needs no change, and that was MEASURED
#: rather than inherited from the Go entry (2026-08-10, in a clone: a
#: self-judging checkout whose branch replaced a file under the TS subtree was
#: run with a ``$PYTHON`` that dumps what it was handed, and it was handed the
#: BASE's bytes). The property is TRUE BY LOCATION — the base-pinned block
#: reads a whole-subtree ``ls-tree -r`` of the ``src/`` prefix, not a list of
#: named files — and it is stronger here than for Go: the Go helper's directory
#: could be moved out from under ``src/``, while this one cannot, because
#: :func:`ts_parser_home` resolves it against ``Path(__file__).parent`` and
#: :data:`TS_HELPER_PACKAGE_DIR` is sealed FLAT.
#:
#: **SEVENTEEN globs as of unit D8 (2026-08-12): FOURTEEN FILE globs, refused
#: at plan time as well as at diff time, and THREE subtree globs, diff-time
#: only.** Measured on this revision under this module's own lens, not counted
#: by hand. The two D8 entries are the twelfth and thirteenth basenames and
#: they are the first added for a CALLER-SIDE hole: the derived closure in
#: ``tests/test_floor_closure.py`` seeds at :func:`check_branch` and follows
#: delegations DOWNWARD, so a module that CALLS the gate is invisible to it
#: however much of the verdict's effect that module decides. Measured: a probe
#: call at the D8 hook point leaves the three floor files at 183 passed, 0
#: failed. The lesson generalises past this unit and is written beside the
#: entries: the closure walk proves nothing about callers, and a caller that
#: turns a VIOLATION into a control-flow decision has to be named by hand.
#:
#: **FOURTEEN globs as of unit D7 (2026-08-12): ELEVEN FILE globs, refused at
#: plan time as well as at diff time, and THREE subtree globs, diff-time
#: only.** The D7 entry is the eleventh basename and it is the first one added
#: by a commit that WIRED something rather than by one that protected an
#: artifact already in place — see the last entry in the tuple for why "before
#: the thing it protects" was not available there. The paragraph below is the
#: D6 arithmetic, left standing because each entry's reasoning is written
#: beside the entry itself and this header has been stale twice.
#:
#: **THIRTEEN globs as of unit D6 (2026-08-11), and the arithmetic is restated
#: here because "TEN globs now" above was already stale.** Unit D5 added
#: ``call_site_reachability.py`` (eleven, and the ninth basename); unit D6 adds
#: the Go reachability ROW and its helper subtree. Each entry's reasoning is
#: written beside the entry itself rather than here, so that a reader who greps
#: for a string lands on the argument for that string. The counts, MEASURED
#: 2026-08-11 under this module's own lens: **ten FILE globs, refused at plan
#: time as well as at diff time, and THREE subtree globs, diff-time only** —
#: ``go_signature_fingerprint/**``, ``ts_signature_fingerprint/**`` and now
#: ``go_call_reachability/**``. The subtree rule generalises exactly as the D4
#: paragraph above predicted it would, and D6 is its third instance rather than
#: a new discovery: a ``**`` tail is what :func:`_floor_glob_named_by` refuses,
#: so any artifact protected as a TREE buys diff-time enforcement only.
FLOOR_GLOBS: tuple[str, ...] = (
    "**/.dispatcher.yaml",
    "**/scripts/check_body_branch.sh",
    "**/src/claude_dispatcher/role_protocol.py",
    # The gate's third artifact (D2 P4 ruling, 2026-08-09). A SUBTREE, not a
    # file: `go.mod` fixes the language version the parse runs under and is a
    # parser input as much as `main.go`.
    "**/src/claude_dispatcher/go_signature_fingerprint/**",
    # The gate's fourth artifact (D4 P4 ruling, 2026-08-10). A SUBTREE, and it
    # lands BEFORE anything is vendored into it: a floor that arrives with the
    # 9.1 MB parser is a floor that was absent for the commit that added it.
    # The digest that vouches for those bytes is `TS_VENDORED_PARSER_SHA256`,
    # in this module, which is on the floor three entries up — so a branch
    # cannot make tampered bytes match by editing the expectation.
    "**/src/claude_dispatcher/ts_signature_fingerprint/**",
    # The delegation closure (D1 P4 ruling, 2026-08-09). FIVE SEPARATE STRINGS
    # — do NOT compress them into `**/src/claude_dispatcher/{risk,seal_verify,
    # repo_config,yaml_io,mechanical_verify}.py`. Measured under this module's
    # own lens (`risk._glob_to_regex`): this engine has NO brace expansion, so
    # that alternation is literal text and matches exactly one path — a file
    # named `{risk,seal_verify,repo_config,yaml_io,mechanical_verify}.py` —
    # covering none of the five modules. A floor written that way is a silent
    # no-op that reads as protection, which is the one failure mode a floor may
    # not have.
    "**/src/claude_dispatcher/risk.py",
    "**/src/claude_dispatcher/seal_verify.py",
    "**/src/claude_dispatcher/repo_config.py",
    "**/src/claude_dispatcher/yaml_io.py",
    "**/src/claude_dispatcher/mechanical_verify.py",
    # Known-red register's decision module (D-68, 2026-08-17, operator).
    # `mechanical_verify.py` above decides whether the suite passed; this decides
    # which FAILING ROWS DO NOT COUNT — the same verdict one step earlier. Absent
    # this entry, BODIES/SCAFFOLD (deny-list roles, `src/**` writable) could edit
    # `rows_for_task` to hide any row and green their own gate.
    # Hand-placed: `test_floor_closure.py` walks the ROLE gate out of
    # `check_branch` and will not catch this module leaving the mechanical path.
    "**/src/claude_dispatcher/known_red.py",
    # The register FILE. BODIES/SCAFFOLD are deny-list roles and neither table
    # names `config/`, so without this a body agent could append an entry naming
    # its own red rows against ANOTHER task's `body_task` — `applies_to` only
    # exempts the entry's own body, so the rows would be hidden from its own gate
    # too. The floor binds task branches, not operator commits, so a human may
    # still add entries; a role that needs one must report it.
    "**/config/known-red.yaml",
    # The gate's FIFTH artifact (D5 P4 ruling, 2026-08-11). A FILE glob, and
    # PATH-QUALIFIED, for the reason points 1-3 give and re-measured under this
    # module's own lens on 2026-08-11 rather than inherited:
    #   * the basename-only spelling `**/call_site_reachability.py` also
    #     matches `vendor/thirdparty/call_site_reachability.py`, and a floor
    #     has no override to buy that back;
    #   * the package subtree `**/src/claude_dispatcher/**` also matches
    #     `plan.py` and `blast_radius.py` — five still-writable controls — and
    #     buys NO plan-time reach, because a `**` tail is exactly what
    #     `_floor_glob_named_by` refuses. This entry is the ninth BASENAME, not
    #     the third subtree;
    #   * the brace-compressed spelling
    #     `**/src/claude_dispatcher/{call_site_reachability,blast_radius}.py`
    #     matches none of the five probes — this engine has no brace expansion
    #     (point 7 above, restated because it was re-measured here) — so it
    #     is a silent no-op that reads as protection.
    # The module decides, per seal, whether a subject is reachable from a
    # production root and turns that into a `Disposition` a branch is judged
    # by; measured 2026-08-11 at 59a648d, four of the five roles could rewrite
    # it. It lands BEFORE enrolment (`ANALYZERS` is still `()`), which is the
    # Go entry's rule unchanged: a floor that arrives with enrolment is a floor
    # that was absent for every commit that built the thing it protects.
    #
    # LOAD-BEARING, measured on this revision in a `.git`-less clone re-inited
    # as its own repository with `__pycache__` cleared. Deleting this one
    # string and changing nothing else: 17 failed / 2296 passed, whole suite.
    # The "19" the D5 P4 ruling records is a DIFFERENT mutation counted over a
    # NARROWER scope — delete the glob AND enrol `ANALYZERS` in the same edit,
    # counted over `test_d5_floor.py` + `test_role_protocol_floor.py` only;
    # the same mutation over the whole suite is 21, the two extra rows being
    # the D5 unit seals on `ANALYZERS == ()`. Both re-measured 2026-08-11, and
    # both against a tree with the import guard REMOVED: with the guard in
    # `call_site_reachability` present, that mutation no longer produces FAILED
    # lines at all — the module refuses to import and the run ends in a
    # collection error, which is the guard doing exactly what it is for.
    "**/src/claude_dispatcher/call_site_reachability.py",
    # The gate's SIXTH artifact (D6 P4 ruling, 2026-08-11). A FILE glob, and
    # PATH-QUALIFIED, measured under this module's own lens on 2026-08-11:
    #   * it matches `src/claude_dispatcher/go_reachability.py` and the vendored
    #     `sub/project/...` layout, and does NOT match
    #     `vendor/thirdparty/go_reachability.py`, `plan.py` or
    #     `blast_radius.py`;
    #   * the basename-only spelling `**/go_reachability.py` also matches
    #     `vendor/thirdparty/go_reachability.py`, and a floor has no override to
    #     buy that back;
    #   * the brace-compressed spelling
    #     `**/src/claude_dispatcher/{go_reachability,call_site_reachability}.py`
    #     matches NONE of those probes — this engine has no brace expansion, the
    #     point the delegation-closure block above makes and which was
    #     re-measured here rather than inherited.
    # WHY IT IS HERE. `call_site_reachability.py` is the MECHANISM and it is
    # already floored one entry up; this module is the ROW — the thing that
    # answers "what does this Go tree start from" and "what calls what", from
    # which the `Disposition` a branch is judged by is computed. Flooring the
    # registry while leaving the only row writable protects the table and not
    # the answer, which is the 2026-08-09 "one artifact, two files" argument
    # about the library and the entrypoint, one unit later.
    "**/src/claude_dispatcher/go_reachability.py",
    # The gate's SEVENTH artifact (D6 P4 ruling, 2026-08-11). A SUBTREE, not a
    # file, for `go_signature_fingerprint`'s recorded reason: `go.mod` fixes the
    # language version the parse runs under and pins the module to stdlib-only,
    # so it is a parser input as much as `main.go` is, and any future file
    # beside them is one the day it lands.
    #
    # This is the THIRD entry whose last segment is `**`, so it inherits the
    # generalisation the Go and TypeScript subtrees already recorded and it is
    # named here rather than rediscovered: a subtree glob has NO PLAN-TIME
    # REACH, because `_floor_glob_named_by` probes each floor glob's last
    # segment and refuses a pure-wildcard tail by design. Measured 2026-08-11
    # against this tuple: `go_call_reachability`, `main.go`, `go.mod` and the
    # full `src/claude_dispatcher/go_call_reachability/main.go` all return None.
    # The entry is diff-time enforced like every other, because
    # `_floor_violations` reads the whole tuple.
    #
    # The basename-only spelling `**/go_call_reachability/**` is refused for the
    # file globs' reason, measured the same way: it also matches
    # `vendor/thirdparty/go_call_reachability/main.go`. The directory spelling
    # WITHOUT the `**` tail — `**/src/claude_dispatcher/go_call_reachability` —
    # matches the directory path and NOTHING INSIDE IT, so it is a floor that
    # protects no file in the helper it names; measured 2026-08-11, it misses
    # `main.go`, `go.mod` and a nested `internal/parse/decl.go` alike.
    "**/src/claude_dispatcher/go_call_reachability/**",
    # The gate's EIGHTH artifact (D5 P4 ruling, 2026-08-11, on the composed
    # tree): the shared VOCABULARY. A FILE glob, and PATH-QUALIFIED. All four
    # alternatives were re-measured under this module's own lens on the
    # composed tree rather than inherited from the D5/D6 entries above, against
    # six probes — the module, its `sub/project/...` spelling, a vendored
    # `vendor/thirdparty/...` copy, an installed `site-packages/...` copy, and
    # the two still-writable controls `plan.py` and `blast_radius.py`:
    #   * the entry below matches the first two and none of the other four;
    #   * the basename-only spelling `**/call_site_contract.py` also matches
    #     BOTH the `vendor/thirdparty/` copy and the `site-packages/` copy, and
    #     a floor has no override to buy either back;
    #   * the package subtree `**/src/claude_dispatcher/**` also matches
    #     `plan.py` and `blast_radius.py`, and buys NO plan-time reach, because
    #     a pure-wildcard tail is exactly what `_floor_glob_named_by` refuses.
    #     This entry is a BASENAME, not a fourth subtree;
    #   * the brace-compressed spelling
    #     `**/src/claude_dispatcher/{call_site_contract,call_site_reachability}.py`
    #     matches NONE of the six — this engine has no brace expansion, the
    #     point the delegation-closure block above makes and which was
    #     re-measured here, not inherited. It is a silent no-op that reads as
    #     protection;
    #   * a `**` tail on a file — `.../call_site_contract.py/**` — matches none
    #     of the six either.
    #
    # WHY IT IS HERE, and why it is not "just a vocabulary file". This module
    # holds no `def` and imports nothing in-package (measured on this
    # revision: 0 module-level functions, 0 in-package imports). It is
    # nevertheless on the D5 decision path, and the seal that says so —
    # `test_every_module_a_d5_decision_reaches_is_already_on_the_floor` — was
    # RED for exactly this row from `84e7c10` until this edit. What it holds is
    # `RootKind`, `EntrypointKind`, `ROOT_KIND_BY_ENTRYPOINT`, `Edge`,
    # `EdgeKind`, `CallGraph` and the rest of the eighteen names BOTH the
    # mechanism and the row import at module level. A branch that can rewrite
    # one row of `ROOT_KIND_BY_ENTRYPOINT` changes which entrypoints count as
    # PRODUCTION roots, and therefore changes the `Disposition` it is itself
    # judged by, while touching neither of the two files the floor already
    # names. Flooring the mechanism and the row while leaving the vocabulary
    # they both read writable protects the two halves and not the words they
    # agree in — the same "one artifact, two files" argument the sixth entry
    # makes, one extraction later.
    #
    # It lands BEFORE enrolment (`ANALYZERS` is still `()`), which is the rule
    # the Go and D5 entries above set and which this one does not get to
    # shortcut by being new: a floor that arrives with enrolment is a floor
    # that was absent for every commit that built the thing it protects.
    "**/src/claude_dispatcher/call_site_contract.py",
    # The gate's NINTH artifact (D7 P4 ruling, 2026-08-12): the BRANCH gate
    # itself. A FILE glob, and PATH-QUALIFIED. Every alternative was
    # re-measured under this module's own lens (`risk.matches_any_glob`) on
    # THIS revision rather than inherited from the D5/D6 entries, against seven
    # probes — the module, its `sub/project/...` spelling, a vendored
    # `vendor/thirdparty/...` copy, an installed `site-packages/...` copy, a
    # `.venv/lib/python3.12/site-packages/...` copy, and the two still-writable
    # controls `plan.py` and `blast_radius.py`:
    #
    #   * the entry below matches the first two and NONE of the other five;
    #   * the basename-only spelling `**/branch_reachability.py` also matches
    #     the `vendor/thirdparty/` copy AND both installed copies, and a floor
    #     has no override to buy any of them back;
    #   * the package subtree `**/src/claude_dispatcher/**` also matches
    #     `plan.py` and `blast_radius.py`, and buys NO plan-time reach, because
    #     a pure-wildcard tail is exactly what `_floor_glob_named_by` refuses
    #     by design. This entry is a BASENAME, not a fourth subtree;
    #   * the brace-compressed spelling
    #     `**/src/claude_dispatcher/{branch_reachability,call_site_reachability}.py`
    #     matches NONE of the seven — this engine has no brace expansion, the
    #     point the delegation-closure block above makes and which was
    #     re-measured here, not inherited. It is a silent no-op that reads as
    #     protection, which is the one failure mode a floor may not have;
    #   * a `**` tail on a file — `.../branch_reachability.py/**` — matches
    #     none of the seven either.
    #
    # WHY IT IS HERE, and it is the least optional entry in this tuple. This
    # module is not a delegate the gate happens to reach: as of this commit
    # `check_branch` CALLS `check_branch_reachability` at step 6 and unions
    # `verdict_of`'s answer into the verdict at `_VERDICT_PRECEDENCE`. It is
    # therefore machinery "that computes the verdict" in FLOOR_RATIONALE's own
    # words, in the most literal sense the phrase has — a branch that could
    # rewrite `_ROLE_OBLIGATIONS` to `NOT_RUN`, or `verdict_of` to `return
    # DiffVerdict.CLEAN`, would switch this gate off for itself and then walk
    # through it, which is the 2026-08-08 `FLOOR_GLOBS = ()` measurement one
    # module to the left.
    #
    # It lands IN THE SAME COMMIT as the call, and not before and not after,
    # which is the one place this entry's rule differs from the sixth and
    # eighth entries' "it lands BEFORE enrolment". Those protect an artifact
    # that already existed; here the call and the exposure are the same edit,
    # so "before" is not available and "after" would be a floor absent for the
    # commit that created what it protects.
    #
    # LOAD-BEARING, and measured on this revision rather than predicted: with
    # the step-6 call present and this ONE STRING deleted and nothing else
    # changed, the whole suite goes **14 failed / 2464 passed / 13 skipped**
    # (plus the 7 clone-only provenance rows, which error rather than fail for
    # their usual unrelated reason). Thirteen of the fourteen are the floor's
    # own files: `test_every_module_in_the_derived_closure_is_on_the_floor`
    # ("floor them, or take them off the gate path: branch_reachability"),
    # `test_every_delegation_target_is_on_the_floor[branch_reachability]`,
    # `test_the_floor_glob_over_a_delegation_target_is_path_qualified`, the ten
    # role×probe rows, and `test_every_floor_glob_the_ruling_wrote_out_is_in_
    # the_constant`. The
    # other two modules the call newly pulls into the derived closure —
    # `call_site_reachability` and `call_site_contract`, through this module's
    # own MODULE-LEVEL imports — are already floored, two and four entries up,
    # so the closure grows by three rows and the floor by one string.
    "**/src/claude_dispatcher/branch_reachability.py",
    # The gate's TENTH and ELEVENTH artifacts (D8 P4 ruling, 2026-08-12): the
    # loop gate and its ONE caller. TWO FILE globs, both PATH-QUALIFIED, and
    # they are the first entries in this tuple added for a CALLER-SIDE hole
    # rather than for a delegate.
    #
    # WHY THE CLOSURE WALK DID NOT FIND THEM, stated first because it is the
    # generalisation and not a detail of this unit. `tests/test_floor_
    # closure.py` seeds at `_FLOOR_DECISION_ROOTS = ("check_branch",
    # "_floor_glob_named_by")` and follows delegations DOWNWARD, out of those
    # functions. `loop_gate` and `orchestrator` are CALLERS of `check_branch`,
    # and nothing about calling a floored function puts the caller in a walk
    # that only ever descends. Measured under `81591e4` by the D8 scaffold, and
    # re-derived at `90ddca0`: a probe call to `check_branch` inserted at the
    # hook point leaves `test_floor_closure.py` + `test_d5_floor.py` +
    # `test_role_protocol_floor.py` at **183 passed, 0 failed**. The derived
    # closure is sound and it is not complete in this direction; a caller that
    # decides whether a VIOLATION stops anything has to be named by hand.
    #
    # WHAT IS AT STAKE. `loop_gate` maps VIOLATION → BLOCK and `orchestrator`
    # is what performs the block. Measured at `90ddca0` before this commit:
    # neither path matched any entry of this tuple, and `DEFAULT_ROLE_RULES`
    # denies BODIES `tests/**` and the schema paths, not `src/`. So a BODIES
    # branch could flip `_DECISIONS[CHECKED_VIOLATION]` to PROCEED, or delete
    # the four-line call at the hook, and then be judged by the gate it had
    # just switched off. That is the 2026-08-08 `FLOOR_GLOBS = ()` measurement
    # — *"a branch could delete the floor from this module and then walk
    # through it"* — arriving through the CALLER instead of the callee, and the
    # floor is the only thing that closes it: every seal that would catch it
    # lives in `tests/**` and is evaluated by the very module the branch
    # rewrote.
    #
    # THE SPELLINGS, measured under this module's own lens (`risk.matches_any_
    # glob`) on THIS revision rather than inherited from the D5/D6/D7 entries,
    # against ten probes — each module, each module's `sub/project/...`
    # spelling, a `vendor/thirdparty/...` copy of each, a
    # `.venv/lib/python3.12/site-packages/...` copy of each, `notsrc/claude_
    # dispatcher/orchestrator.py`, and the two still-writable controls
    # `plan.py` and `blast_radius.py`:
    #
    #   * the two entries below match their own module and its `sub/project/`
    #     spelling, and NOTHING else in the ten — not the other module, not
    #     either vendored copy, not either installed copy, not `notsrc/`, and
    #     neither control;
    #   * the basename-only spellings are refused and the refusal is worse here
    #     than at any previous entry, because these are ORDINARY names.
    #     `**/loop_gate.py` also matches `vendor/thirdparty/loop_gate.py` AND
    #     `.venv/.../site-packages/someproj/loop_gate.py`; `**/orchestrator.py`
    #     also matches BOTH of those AND `notsrc/claude_dispatcher/
    #     orchestrator.py`. "Orchestrator" is a name a third-party package is
    #     genuinely likely to carry, and a floor has no override to buy any of
    #     them back;
    #   * the package subtree `**/src/claude_dispatcher/**` also matches
    #     `plan.py` and `blast_radius.py` — still-writable controls — and buys
    #     NO plan-time reach, because a pure-wildcard tail is exactly what
    #     `_floor_glob_named_by` refuses by design. These are the eleventh and
    #     twelfth BASENAMES, not a fourth subtree;
    #   * the brace-compressed spelling
    #     `**/src/claude_dispatcher/{loop_gate,orchestrator}.py` matches NONE
    #     of the ten — this engine has no brace expansion, the point the
    #     delegation-closure block above makes and which was re-measured here,
    #     not inherited. It is a silent no-op that reads as protection, which
    #     is the one failure mode a floor may not have.
    #
    # PLAN-TIME REACH, measured 2026-08-12 against the tuple WITH these two
    # entries: `loop_gate.py`, `orchestrator.py` and both full paths all return
    # their glob from `_floor_glob_named_by`, where against the tuple WITHOUT
    # them all four returned None. So both entries are refused at plan time as
    # well as at diff time, and the accepted asymmetry the delegation-closure
    # block records widens by two on the same terms: a declaration naming
    # either basename is refused at plan time even where diff time would clear
    # the path, it can only false-refuse, and the false refusal has a spelling
    # that works. Measured on this revision: no worklist in this repository
    # carries an `immutable_paths:` or `disputed_paths:` key at all, so the
    # widening costs nothing today.
    #
    # WHEN IT LANDS. `orchestrator.py` is where the call already is, so
    # "before the thing it protects" is not available — this is the D7 branch
    # gate's position, not the sixth and eighth entries' "before enrolment".
    # It lands in the FIRST P4 commit after the wiring, which is the earliest
    # point at which the party that may write this file is not the party being
    # judged.
    #
    # THE COST OF THE SECOND ENTRY, MEASURED, AND IT IS THE LARGEST ANY ENTRY
    # IN THIS TUPLE HAS CARRIED. Every glob above names a single-purpose
    # artifact: a comparator, a matcher, a config reader, a gate module.
    # `orchestrator.py` is 5,304 lines and is the dispatcher itself, of which
    # roughly eighty are this gate. Measured 2026-08-12 on this branch's
    # history: **76 of the last 200 commits touch it.** From this commit every
    # one of those is a protected-base edit — and NOT buyable back by a
    # `disputed_paths:` declaration, measured on this revision:
    # `_floor_violations` is unioned in at step 3b against the path git
    # reported, so an ADJUDICATE row naming this file is still refused with
    # FLOOR_RATIONALE. The practical consequence, stated in as many words
    # rather than discovered by the first unit that hits it: **no future unit
    # may wire anything into the orchestrator's task loop from inside this
    # protocol.** D8 is the last one that could.
    #
    # It is landed anyway, because the alternative was measured and is worse,
    # and because nothing narrower buys the property. What the entry buys is
    # exactly one thing — "the four-line call at the hook may not be deleted or
    # moved by the branch the call judges" — and that call lives in this file,
    # so no smaller glob can say it. Extracting the hook into a module of its
    # own does not help: whatever then calls THAT is the caller, and the
    # caller-side hole moves with it. The seals catch a deleted call site
    # (rows 4, 7 and 21 of `tests/test_loop_gate.py`, in `tests/**`, which
    # BODIES may not write) — but they catch it at TEST time, and the window
    # this entry closes is the one where the gate running live inside the loop
    # has already been switched off by the diff it is judging.
    #
    # RECORDED AS AN OPEN QUESTION FOR THE OPERATOR, not settled here: whether
    # the 76-in-200 price is worth the window, or whether the orchestrator
    # entry should be reverted and the call site left to the seals alone. That
    # is a policy call about how this repository develops itself, it is not a
    # fact this module can measure, and an adjudicator that quietly made it by
    # landing a string would be doing the thing this protocol exists to stop.
    # The entry is here so the question is asked against a floor that holds
    # rather than against one that does not.
    "**/src/claude_dispatcher/loop_gate.py",
    "**/src/claude_dispatcher/orchestrator.py",
)

#: What a floor violation prints, and deliberately NOT the violated role's own
#: rationale. For :data:`Role.ADJUDICATE` the role's rationale reads "its
#: writable set is the task's ``disputed_paths:``" — which, for a floor path, is
#: the one sentence that cannot explain the refusal: the path IS in
#: ``disputed_paths:``, and that is exactly why it is refused. Printing it would
#: tell the agent the opposite of the truth. The floor reports its own reason,
#: for every role, so the report never has to be read against the rule it did
#: not come from.
FLOOR_RATIONALE = (
    "this path is on the non-overridable floor (FLOOR_GLOBS): it is part of "
    "the machinery that decides every role's permissions or that computes the "
    "verdict — the policy file, the module that implements the rules, the "
    "entrypoint that runs them, a comparator the verdict is derived from, or "
    "one of the modules that machinery delegates a decision to (the glob "
    "matcher, the test-path matcher, the config and YAML readers it pins its "
    "policy through, and anything they import at module level) — "
    "so no role may write it, not through the repo's `roles:` section, not "
    "through a per-task `immutable_paths:` or `disputed_paths:` declaration, "
    "and not by omitting `role:` and becoming legacy. A change here is a "
    "reviewed edit on the protected base (a plan amendment), never a line in "
    "the branch being judged. The floor is matched against the path git "
    "reported, so how the declaration was spelled makes no difference"
)


class PolicySource(Enum):
    """Where the effective policy came from — a named state, always reportable.

    BUILT_IN_DEFAULTS
        No `roles:` section at the pinned base: :data:`DEFAULT_ROLE_RULES`
        verbatim. This is a real and common state, and it is the strictest
        thing the module has, so it is safe.
    BASE_PINNED_CONFIG
        A `roles:` section was read out of ``base_ref``'s object store and its
        additions are merged in.
    CONFIG_MAPPING
        A `roles:` mapping was parsed by :func:`role_policy_from_mapping` and
        the caller has not said where it came from. Its own member rather than
        a borrowed BASE_PINNED_CONFIG (D1 P2 ruling): the pure parser cannot
        know whether its input was base-pinned, and labelling it
        base-pinned would make an unpinned policy *report* as pinned — the
        provenance claim invariant 6 rests on. :func:`load_role_policy_from_base`
        re-stamps it to BASE_PINNED_CONFIG because it is the function that
        did the pinning.

    There is deliberately no ``WORKING_TREE`` member: nothing on the gating
    path reads its parameters from the branch under review (invariant 6).
    `repo_config.load` parses a working-tree `roles:` section only to refuse
    an invalid one, and never hands the result to a gate.
    """

    BUILT_IN_DEFAULTS = "built_in_defaults"
    BASE_PINNED_CONFIG = "base_pinned_config"
    CONFIG_MAPPING = "config_mapping"


@dataclass(frozen=True)
class RolePolicy:
    """The effective role → immutable-paths policy for one evaluation.

    Constructed by :func:`built_in_policy` or :func:`load_role_policy_from_base`
    and thereafter read-only. ``rules`` holds exactly one entry per
    :class:`Role` member — a missing role is a bug, not "unrestricted".
    """

    rules: tuple[RoleRule, ...]
    source: PolicySource
    base_ref: str | None = None

    def rule_for(self, role: Role) -> RoleRule:
        """This policy's rule for ``role``.

        Raises :class:`RoleProtocolError` when the table has no entry for the
        role — including for a Role member added later without updating the
        table. The absent entry must never be treated as UNRESTRICTED.
        """
        for rule in self.rules:
            if rule.role is role:
                return rule
        raise RoleProtocolError(
            f"this policy ({self.source.value}) has no rule for role "
            f"{role.value!r}; a missing entry is a bug in the table, never "
            "'no restrictions'"
        )


# --------------------------------------------------------------------------- #
# Per-task role facts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TaskRoleSpec:
    """One task row's protocol facts, after parsing and per-row validation.

    ``added_immutable_globs`` are the row's ADD-only additions to its role's
    deny set (empty for ALLOW_ONLY / UNRESTRICTED roles, where an addition has
    no meaning and is a typed error). ``disputed_paths`` is non-empty only for
    :data:`Role.ADJUDICATE`, where it is required. ``declared_agent`` is the
    row's ``agent:`` verbatim (None when absent) — the *effective* family
    needs the run-level default and is resolved by
    :func:`agent_correlation_warnings`, never guessed here.
    """

    task_key: str
    role: Role
    added_immutable_globs: tuple[str, ...] = ()
    disputed_paths: tuple[str, ...] = ()
    declared_agent: str | None = None


# --------------------------------------------------------------------------- #
# Private helpers (no decisions of their own — every rule they serve is stated
# in the public function that calls them)
# --------------------------------------------------------------------------- #

#: Characters that join two role names into one string. Whitespace is checked
#: separately (any whitespace, not just a literal space).
_ROLE_SEPARATORS = (",", "+", "/", "|", "\\", ";", "&")

#: Prefixes and infixes that make an ``immutable_paths:`` entry a NEGATION in
#: shape. There is no subtraction syntax to reject, so this is the failure the
#: schema actually permits an author to write.
_NEGATION_PREFIXES = ("!", "-", "^", "~")
_NEGATION_INFIXES = (":",)


def _authorable_values() -> str:
    return ", ".join(sorted(role.value for role in AUTHORABLE_ROLES))


def _default_kind(role: Role) -> RuleKind:
    """The compiled-in :class:`RuleKind` for ``role``.

    The kind is a property of the protocol, not of a policy: config may add
    globs but may never turn a DENY role into an ALLOW_ONLY one. Read off
    :data:`DEFAULT_ROLE_RULES` so per-row validation (which has no policy in
    hand) and policy construction cannot disagree about it.
    """
    for rule in DEFAULT_ROLE_RULES:
        if rule.role is role:
            return rule.kind
    raise RoleProtocolError(
        f"no compiled-in rule for role {role.value!r}: DEFAULT_ROLE_RULES must "
        "carry one entry per Role member"
    )


def _dedup(globs: Sequence[str]) -> tuple[str, ...]:
    """``globs`` with later duplicates dropped, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for glob in globs:
        if glob not in seen:
            seen.add(glob)
            out.append(glob)
    return tuple(out)


def _string_list(
    value: object, *, task_key: str, field_name: str
) -> tuple[str, ...]:
    """``value`` as a tuple of non-blank strings, or raise.

    A bare string is an error rather than a one-element list: a one-element
    list is cheap to write, and a string that looks like a list is exactly how
    a policy line gets silently dropped.
    """
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise RoleProtocolError(
            f"task {task_key} has {field_name}: {value!r}; it must be a list "
            "of non-blank path globs (a bare string is not a one-element list)"
        )
    out: list[str] = []
    for entry in value:
        if isinstance(entry, bool) or not isinstance(entry, str) or not entry.strip():
            raise RoleProtocolError(
                f"task {task_key} has {field_name} entry {entry!r}; every "
                "entry must be a non-blank string"
            )
        out.append(entry)
    return tuple(out)


def _names_no_artifact(entry: str) -> bool:
    """True when ``entry`` is wildcards and separators only — it names nothing.

    The CLOSED form of "a wildcard adjudication is not an adjudication"
    (D1-inputs I2). :data:`FORBIDDEN_DISPUTED_GLOBS` states that sentence as
    six literals, so it is true of six strings and false of every other
    spelling of the same thing: `**/**`, `**/**/*`, `**/**/**`, `*/**`,
    `**/*/**` and `*/*` all parse today and all grant the entire repo, and so
    does `**/*.*`, which is refused right now only by the accident that
    `.dispatcher.yaml` happens to contain a dot.

    The test is one sentence: **strike out the wildcards and at least one
    literal alphanumeric character must remain.** A declaration is an
    adjudication when it NAMES something — a tree, a file, a class of files —
    and `/` and `.` are structure, not names.

    Where the boundary sits, and why it sits there rather than anywhere
    broader (P4, 2026-08-08; a floor has no override, so a false refusal makes
    a path permanently unplannable):

      * refused: `**/*.*` — matches every path in the probe set, and after the
        strike-out only `/.` remains. It names nothing.
      * ALLOWED: `*.yaml` — `*` crosses `/` in this repo's glob engine, so this
        is "every YAML file", a real and bounded class of artifacts,
        structurally identical to `docs/*.md`. Refusing extension-only
        declarations would also stop `*.md` and `**/*.md` in a repo whose docs
        live both under `docs/` and at the root. Its refusal today is the
        FLOOR's business and on the floor's own grounds — it does name
        `.dispatcher.yaml` — which is two independent rules refusing for two
        different reasons, the design; not one rule refusing for the other's.
      * ALLOWED: `sub/**`, one wildcard segment away from the refused `*/**`.
        An implementation that cannot tell those apart has not closed the set,
        it has closed the door.

    A bracket expression counts as literal text, on the same reading
    :func:`_floor_glob_named_by` already uses: `[abc]` enumerates names.
    """
    residue = entry.strip()
    for metacharacter in _GLOB_METACHARACTERS:
        residue = residue.replace(metacharacter, "")
    return not any(character.isalnum() for character in residue)


def _reject_negation_shape(entry: str, *, where: str) -> None:
    """Raise when ``entry`` is shaped like a removal.

    ``immutable_paths:`` has no negation form by design, so the expressible
    failure is an entry that LOOKS like one. Accepting it as a literal filename
    would let an agent believe it had been granted an exemption it never had.
    """
    text = entry.strip()
    if text.startswith(_NEGATION_PREFIXES) or any(
        infix in text for infix in _NEGATION_INFIXES
    ):
        raise RoleProtocolError(
            f"{where}: {entry!r} is shaped like a removal. An override may "
            "only ADD immutable paths — a narrowing policy is the "
            "self-weakening shape this protocol exists to refuse, and it is "
            "an error rather than a path with an odd name"
        )


def _floor_glob_named_by(entry: str) -> str | None:
    """The floor glob a ``disputed_paths:`` entry NAMES, or None.

    The plan-time half of the floor (point 2 of the 2026-08-07 operator
    ruling), and deliberately narrower than the diff-time half. It asks one
    question — *does this declaration name the floor FILE?* — by comparing the
    declaration's last path segment, as a pattern, against each floor glob's
    last segment. So ``.dispatcher.yaml``, ``./.dispatcher.yaml``,
    ``**/.dispatcher.yaml``, ``sub/project/.dispatcher.yaml``,
    ``.dispatcher.*`` and ``**/.dispatcher.yam?`` all name it.

    What it deliberately does NOT answer is "could this declaration CONTAIN a
    floor path", which is why a tail that is nothing but wildcards (``docs/**``,
    ``src/claude_dispatcher/**``, ``sub/**``) is not a hit: such a glob names a
    TREE, not a file, and whether the tree holds a config file is a fact about a
    branch that does not exist yet. Only the diff knows, and
    :func:`_floor_violations` answers it there for real — that is what makes the
    two enforcement points independent rather than two attempts at one check. A
    false refusal here would make the two commonest shapes a real adjudication
    takes (``docs/**``, ``src/**``) unplannable, with no override, because a
    floor has no override.

    The comparison runs through :func:`first_matching_glob`, so this function
    introduces no second glob translator (invariant 5): the declaration's
    basename is the pattern and the floor's basename is the probe.

    **What the delegation closure did to this function (2026-08-09).** It reads
    the WHOLE of :data:`FLOOR_GLOBS`, so the five closure globs arrived here
    with no edit — which is the point ("one floor, one meaning"), and is sealed
    rather than assumed in ``tests/test_floor_closure.py``. But the floor's
    basenames are no longer unusual: comparing by basename means a declaration
    of ``risk.py``, ``yaml_io.py`` or ``repo_config.py`` ANYWHERE is now refused
    at plan time, including ``vendor/thirdparty/risk.py``, which the diff-time
    half would let through because the floor globs are path-qualified. That
    asymmetry is accepted, not overlooked: this half is deliberately narrower in
    one direction and now stricter in another, and being stricter at plan time
    is the safe direction — it can only false-refuse, never let a floor edit
    land, and the false refusal has a spelling that works (``vendor/**``, whose
    pure-wildcard tail is not a hit). Do not "fix" it by path-qualifying the
    comparison; that would make this half read the declaration's DIRECTORY, and
    "could this tree contain a floor path" is the question the paragraph above
    exists to refuse.
    """
    candidate = entry.strip().rstrip("/")
    if not candidate:
        return None
    basename = candidate.rsplit("/", 1)[-1]
    if not basename.strip("*?[]"):
        # A tail of pure wildcards names a tree, not a file — see above.
        return None
    for floor in FLOOR_GLOBS:
        floor_basename = floor.rstrip("/").rsplit("/", 1)[-1]
        if first_matching_glob(floor_basename, (basename,)) is not None:
            return floor
    return None


def parse_role_field(row: Mapping[str, object], *, task_key: str) -> Role:
    """The :class:`Role` a task row declares.

    Exhaustive outcomes:

      * none of :data:`ROLE_FIELD_ALIASES` present → :data:`Role.LEGACY`.
        This is the ONLY path to LEGACY.
      * exactly one alias present, value a string that strips to a member of
        :data:`AUTHORABLE_ROLES` (case-insensitive) → that member.
      * more than one alias present → error, even when the values agree: one
        fact, one place, and the same reasoning as
        ``plan._dependency_list``.
      * value is a list/tuple/mapping (``role: [scaffold, seals]``) → error.
        "A task carrying two roles is a typed error, not a coercion", and a
        single-element list is an error too — the row is not shaped like the
        contract.
      * value is a string containing a separator (``,`` ``+`` ``/`` ``|`` or
        whitespace) → error. ``role: "scaffold+seals"`` is two roles.
      * value is None (``role:`` with nothing after it) or blank → error. The
        author wrote the key and meant something; treating presence-with-null
        as absence would default a policy field to the permissive value.
      * value is the literal ``legacy`` → error. LEGACY is derived, never
        authored: spelling it would be an opt-out of the protocol.
      * anything else (unknown word, bool, int) → error naming the value and
        the legal set.

    Pure function of ``row``; never reads the filesystem or git.
    """
    present = [alias for alias in ROLE_FIELD_ALIASES if alias in row]
    if not present:
        return Role.LEGACY
    if len(present) > 1:
        raise RoleProtocolError(
            f"task {task_key} sets {' and '.join(sorted(present))}; use only "
            f"{ROLE_FIELD_CANONICAL!r} — one fact, one place, even when the "
            "values agree"
        )
    field_name = present[0]
    value = row[field_name]

    if isinstance(value, (list, tuple, set, frozenset, dict, Mapping)):
        raise RoleProtocolError(
            f"task {task_key} has {field_name}: {value!r}; a task carrying "
            "two roles is a typed error, not a coercion, and a one-element "
            f"list is not the shape of the contract either. Legal values: "
            f"{_authorable_values()}"
        )
    if value is None:
        raise RoleProtocolError(
            f"task {task_key} has {field_name}: with no value. The key was "
            "written, so it meant something; presence-with-null must not "
            f"default to the permissive state. Legal values: "
            f"{_authorable_values()}"
        )
    if isinstance(value, bool) or not isinstance(value, str):
        raise RoleProtocolError(
            f"task {task_key} has {field_name}: {value!r} "
            f"({type(value).__name__}); legal values: {_authorable_values()}"
        )

    text = value.strip()
    if not text:
        raise RoleProtocolError(
            f"task {task_key} has a blank {field_name}:; legal values: "
            f"{_authorable_values()}"
        )
    if any(sep in text for sep in _ROLE_SEPARATORS) or any(
        ch.isspace() for ch in text
    ):
        raise RoleProtocolError(
            f"task {task_key} has {field_name}: {value!r}, which names more "
            f"than one role; one task holds one role. Legal values: "
            f"{_authorable_values()}"
        )

    lowered = text.lower()
    if lowered == Role.LEGACY.value:
        raise RoleProtocolError(
            f"task {task_key} spells {field_name}: {value!r}. LEGACY is "
            "derived from an ABSENT role key and can never be authored — "
            "spelling it would be an opt-out of the protocol. Legal values: "
            f"{_authorable_values()}"
        )
    for role in AUTHORABLE_ROLES:
        if role.value == lowered:
            return role
    raise RoleProtocolError(
        f"task {task_key} has unknown {field_name}: {value!r}; legal values: "
        f"{_authorable_values()}"
    )


def parse_task_role_spec(
    row: Mapping[str, object], *, task_key: str
) -> TaskRoleSpec:
    """Parse and per-row-validate one task row's protocol fields.

    Calls :func:`parse_role_field`, then:

      * ``immutable_paths:`` — must be absent or a list of non-blank strings
        (a bare string is an error: a one-element list is cheap and a string
        that looks like a list is how a policy line gets silently dropped).
        Present on a role whose rule kind is not DENY_GLOBS → error. An entry
        that is already covered by the role's default is accepted (it is not a
        narrowing; it is redundant) but reported by :func:`validate` as a
        warning, because a duplicated protection is invariant 5's failure
        mode. Legality *against the policy* — that an override only ADDs — is
        :func:`validate_override` and needs the policy, so it is not decided
        here.
      * ``disputed_paths:`` — REQUIRED and non-empty for ADJUDICATE, forbidden
        on every other role (including LEGACY). Entries must be non-blank
        strings and must not appear in :data:`FORBIDDEN_DISPUTED_GLOBS`. An
        entry that NAMES a floor path (:func:`_floor_glob_named_by`) is refused
        too — the plan-time half of the 2026-08-07 floor ruling, so the mistake
        surfaces at planning rather than after a build cycle. It is an
        independent early warning, not the enforcement: the enforcement is
        :func:`check_branch`, over the paths git reports.
      * ``agent:`` — recorded verbatim, validated by ``plan.load_tasks``
        against ``plan.KNOWN_AGENTS`` (not re-validated here: one fact, one
        place).

    Raises :class:`RoleProtocolError` on the first violation. Pure.
    """
    role = parse_role_field(row, task_key=task_key)
    kind = _default_kind(role)

    added: tuple[str, ...] = ()
    if IMMUTABLE_OVERRIDE_FIELD in row:
        if kind is not RuleKind.DENY_GLOBS:
            raise RoleProtocolError(
                f"task {task_key} is role {role.value!r} ({kind.value}) and "
                f"carries {IMMUTABLE_OVERRIDE_FIELD}:; adding denied paths has "
                "no meaning for a role that is not deny-based — ADJUDICATE's "
                f"writable set is {DISPUTED_PATHS_FIELD}: and a role-less "
                "(legacy) row has no immutable paths at all"
            )
        added = _string_list(
            row[IMMUTABLE_OVERRIDE_FIELD],
            task_key=task_key,
            field_name=IMMUTABLE_OVERRIDE_FIELD,
        )

    disputed: tuple[str, ...] = ()
    if role is Role.ADJUDICATE:
        if DISPUTED_PATHS_FIELD not in row:
            raise RoleProtocolError(
                f"task {task_key} is role 'adjudicate' and has no "
                f"{DISPUTED_PATHS_FIELD}:. It is REQUIRED: an absent list "
                "means 'nothing', never 'anything', and an adjudicator with "
                "no named artifact has nothing to rule on"
            )
        disputed = _string_list(
            row[DISPUTED_PATHS_FIELD],
            task_key=task_key,
            field_name=DISPUTED_PATHS_FIELD,
        )
        if not disputed:
            raise RoleProtocolError(
                f"task {task_key} has an empty {DISPUTED_PATHS_FIELD}:; an "
                "adjudicate task rules on at least one artifact"
            )
        for entry in disputed:
            if entry.strip() in FORBIDDEN_DISPUTED_GLOBS or _names_no_artifact(
                entry
            ):
                raise RoleProtocolError(
                    f"task {task_key} has {DISPUTED_PATHS_FIELD} entry "
                    f"{entry!r}; a wildcard adjudication is not an "
                    "adjudication — it converts allow-only into unrestricted "
                    "with extra steps. Strike out the wildcards and nothing "
                    "is left: an adjudication names the tree, the file or the "
                    "class of files it rules on"
                )
            floor = _floor_glob_named_by(entry)
            if floor is not None:
                raise RoleProtocolError(
                    f"task {task_key} has {DISPUTED_PATHS_FIELD} entry "
                    f"{entry!r}, which names a path on the non-overridable "
                    f"floor ({floor!r}). The file that configures every role's "
                    "permissions is not an adjudicable artifact: declaring it "
                    "is how the most privileged role would grant itself the "
                    "policy, and the floor has no override, so the task could "
                    "never have landed. Refused here rather than after a build "
                    "cycle has been spent on it"
                )
    elif DISPUTED_PATHS_FIELD in row:
        raise RoleProtocolError(
            f"task {task_key} is role {role.value!r} and carries "
            f"{DISPUTED_PATHS_FIELD}:, which is forbidden on every role but "
            "'adjudicate' (including a role-less legacy row): a writable set "
            "is only meaningful where the rule is allow-only"
        )

    agent_val = row.get("agent")
    declared_agent: str | None = None
    if isinstance(agent_val, str) and agent_val.strip():
        # Verbatim, and NOT re-validated against plan.KNOWN_AGENTS: that check
        # lives in plan.load_tasks. Two validators of one fact would diverge.
        declared_agent = agent_val

    return TaskRoleSpec(
        task_key=task_key,
        role=role,
        added_immutable_globs=added,
        disputed_paths=disputed,
        declared_agent=declared_agent,
    )


def validate_rule(rule: RoleRule) -> None:
    """Raise :class:`RoleProtocolError` unless ``rule`` is well-formed.

    DENY_GLOBS: at least one glob, none blank. ALLOW_ONLY_GLOBS: globs may be
    empty ONLY for the static table entry (the writable set arrives per task);
    no glob blank, none in :data:`FORBIDDEN_DISPUTED_GLOBS`. UNRESTRICTED:
    globs must be empty — a rule that claims to be unrestricted while
    carrying globs is a contradiction, and silently honouring either half
    would be a guess. Dispatch over :class:`RuleKind` is total.
    """
    role_name = getattr(rule.role, "value", rule.role)
    for glob in rule.globs:
        if not isinstance(glob, str) or not glob.strip():
            raise RoleProtocolError(
                f"rule for {role_name} carries a blank glob {glob!r}; a blank "
                "pattern protects nothing while looking like protection"
            )

    if rule.kind is RuleKind.DENY_GLOBS:
        if not rule.globs:
            raise RoleProtocolError(
                f"rule for {role_name} is deny-based with no globs; an "
                "emptied deny list reads as a pass without doing anything"
            )
        return
    if rule.kind is RuleKind.ALLOW_ONLY_GLOBS:
        # Empty is legal ONLY here: the static table entry's writable set
        # arrives per task via `disputed_paths:`.
        for glob in rule.globs:
            if glob.strip() in FORBIDDEN_DISPUTED_GLOBS or _names_no_artifact(
                glob
            ):
                raise RoleProtocolError(
                    f"rule for {role_name} allows {glob!r}; a wildcard "
                    "allow-only set is an unrestricted rule with extra steps. "
                    "Strike out the wildcards and nothing is left: an "
                    "allow-only rule names what it allows"
                )
        return
    if rule.kind is RuleKind.UNRESTRICTED:
        if rule.globs:
            raise RoleProtocolError(
                f"rule for {role_name} claims to be unrestricted while "
                f"carrying globs {rule.globs!r}; honouring either half would "
                "be a guess about which the author meant"
            )
        return
    raise RoleProtocolError(
        f"rule for {role_name} has unknown kind {rule.kind!r}; a new RuleKind "
        "must be handled everywhere it is dispatched, not fall through to the "
        "permissive branch"
    )


def validate_override(
    spec: TaskRoleSpec, policy: RolePolicy
) -> None:
    """Raise unless ``spec``'s override only ADDs to its role's policy.

    The check is stated over the *protected* set, not the literal list, so it
    reads the same for both rule kinds: an override is legal iff every path
    the role could not write under ``policy`` is still unwritable after the
    override is applied. For DENY_GLOBS that means additions only. There is no
    subtraction syntax to reject — ``immutable_paths:`` has no negation form,
    by design — so the failure this catches is the one that *is* expressible:
    an entry shaped like a negation (``!tests/**``, ``-tests/**``,
    ``tests/**:allow``) is a narrowing attempt and is an ERROR rather than a
    path literally named ``!tests/**``. Silently treating it as an odd
    filename would let an agent believe it had been granted an exemption.
    """
    if not spec.added_immutable_globs:
        return
    rule = policy.rule_for(spec.role)
    if rule.kind is not RuleKind.DENY_GLOBS:
        raise RoleProtocolError(
            f"task {spec.task_key} is role {spec.role.value!r} "
            f"({rule.kind.value}) and carries added immutable globs; only a "
            "deny-based role has a deny set to add to"
        )
    for entry in spec.added_immutable_globs:
        if not entry.strip():
            raise RoleProtocolError(
                f"task {spec.task_key} adds a blank immutable glob"
            )
        _reject_negation_shape(
            entry, where=f"task {spec.task_key} {IMMUTABLE_OVERRIDE_FIELD}"
        )
    # Stated over the protected set rather than the literal list: every path
    # the role could not write under `policy` must still be unwritable after
    # the override applies. It holds by construction because `effective_rule`
    # unions, and it is asserted here anyway so a future `effective_rule` that
    # replaced instead of unioning could not pass silently.
    effective = _dedup((*rule.globs, *spec.added_immutable_globs))
    lost = [glob for glob in rule.globs if glob not in effective]
    if lost:
        raise RoleProtocolError(
            f"task {spec.task_key}'s override would drop {lost!r} from the "
            "role's protected set; an override may only ADD"
        )


def effective_rule(spec: TaskRoleSpec, policy: RolePolicy) -> RoleRule:
    """The rule actually applied to ``spec``'s branch: policy + row.

    Total over :class:`RuleKind`:

      * DENY_GLOBS → the policy globs plus ``spec.added_immutable_globs``,
        deduplicated, order preserved (policy first) so the reported
        ``matched_glob`` is stable.
      * ALLOW_ONLY_GLOBS → one of two NAMED states, never a union (for
        ALLOW_ONLY a union would *widen*):

          - the spec declares ``disputed_paths:`` → globs = exactly those. The
            role's writable set is per-task data; that is ADJUDICATE, and its
            static table globs are empty by design.
          - the spec declares none → globs = the POLICY's own allow set,
            returned unchanged. That is :data:`Role.SEALS` since the
            2026-08-10 inversion: a static writable set, and a role that may
            not carry ``disputed_paths:`` at all.

        Until 2026-08-10 this branch was written to ADJUDICATE's semantics and
        applied to the KIND — ``globs = tuple(spec.disputed_paths)``
        unconditionally — so any other allow-only role had its policy allow set
        thrown away and was judged under an empty allowlist: every path in the
        repository a violation, for a role that had declared nothing wrong. A
        false refusal has no override in this system.

      * UNRESTRICTED → returned unchanged; an override on it was already
        rejected by :func:`parse_task_role_spec`.

    **An allow-only rule this function builds is never empty.** That is a
    stricter contract than :func:`validate_rule`'s, deliberately and at the
    boundary that function's own docstring already draws: an empty ALLOW_ONLY
    tuple is legal for a STATIC TABLE ENTRY, whose writable set arrives per
    task, and is never legal for the rule a BRANCH IS JUDGED BY. Reaching
    evaluation with one is always a bug and never a policy — ADJUDICATE without
    ``disputed_paths:`` is already refused a step earlier by
    :func:`check_branch`, so no role can arrive here empty legitimately. It
    raises rather than returning, because the alternative is the worst verdict
    this gate can produce: a SILENT total false refusal. The raise is role-free
    and :func:`check_branch` turns it into UNDETERMINED carrying this reason,
    which fails closed and says why. (:class:`RuleKind.UNRESTRICTED`'s docstring
    states the mirror for deny sets — "an accidentally-emptied deny list can
    never read as a pass". This is that sentence from the other end.)

    Calls :func:`validate_override` first, so an illegal override cannot
    produce a rule at all (validate before apply — invariant 2), and
    :func:`validate_rule` on the rule it BUILT before handing it back — the
    second half of D1-inputs I2.

    That second call is not belt-and-braces. ALLOW_ONLY's globs come straight
    off ``spec.disputed_paths`` and were validated by nothing: an adjudicate
    spec declaring ``**`` produced ``RoleRule(kind=ALLOW_ONLY_GLOBS,
    globs=('**',))`` — an allow-only rule that allows the whole repo, which is
    UNRESTRICTED with extra steps and is the exact glob :func:`validate_rule`
    exists to refuse. :func:`parse_task_role_spec` is no defence: nothing
    obliges a :class:`TaskRoleSpec` reaching :func:`check_branch` to have come
    through it, and the plan-time denylist is never consulted there. The rule
    a branch is judged by is validated at the point it is built, so the two
    entry points cannot disagree. :func:`check_branch` turns the raise into
    UNDETERMINED, which fails closed.
    """
    validate_override(spec, policy)
    rule = policy.rule_for(spec.role)

    if rule.kind is RuleKind.DENY_GLOBS:
        built = dataclasses.replace(
            rule, globs=_dedup((*rule.globs, *spec.added_immutable_globs))
        )
    elif rule.kind is RuleKind.ALLOW_ONLY_GLOBS:
        if spec.disputed_paths:
            # The writable set is per-task data (ADJUDICATE).
            built = dataclasses.replace(rule, globs=tuple(spec.disputed_paths))
        else:
            # The writable set is the policy's own (SEALS). Not a fallthrough:
            # discarding it here is what handed the role an empty allowlist.
            built = rule
    elif rule.kind is RuleKind.UNRESTRICTED:
        built = rule
    else:
        raise RoleProtocolError(
            f"task {spec.task_key}: cannot build an effective rule for unknown "
            f"kind {rule.kind!r}"
        )

    try:
        validate_rule(built)
    except RoleProtocolError as exc:
        raise RoleProtocolError(
            f"task {spec.task_key}'s effective rule is one this module would "
            f"refuse to validate: {exc}. A rule is validated where it is "
            "BUILT, not only where it is declared — nothing obliges a spec "
            "reaching the diff-time check to have been parsed by "
            "`parse_task_role_spec`"
        ) from exc

    # Stricter than `validate_rule` on purpose, and only here. Empty is a legal
    # STATIC table entry and never a legal judgement rule: under one, every path
    # in the repository is a violation for a role that declared nothing wrong.
    if built.kind is RuleKind.ALLOW_ONLY_GLOBS and not built.globs:
        raise RoleProtocolError(
            f"task {spec.task_key}'s effective rule for role "
            f"{spec.role.value!r} is allow-only and allows NOTHING: every path "
            "in the repository would be a violation, a total false refusal with "
            "no override. An empty allow-only tuple is legal for a static table "
            "entry, whose writable set arrives per task, and never for the rule "
            "a branch is judged by — either the task's "
            f"{DISPUTED_PATHS_FIELD!r} is missing or the policy names no "
            "writable set for this role"
        )
    return built


# --------------------------------------------------------------------------- #
# Units and phase order
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class UnitView:
    """One unit's role-carrying tasks, derived — never declared.

    ``unit_id`` is the key of the unit's SCAFFOLD task. See :func:`units_of`
    for why a unit is identified this way rather than by a new grouping field.
    """

    unit_id: str
    scaffold_key: str
    seals_keys: tuple[str, ...] = ()
    bodies_keys: tuple[str, ...] = ()
    adjudicate_keys: tuple[str, ...] = ()


def units_of(tasks: Sequence[plan_mod.Task]) -> tuple[UnitView, ...]:
    """Group role-carrying tasks into units using ONLY existing fields.

    A unit is identified by **the key of its SCAFFOLD task**, and membership
    is derived from the dependency graph that already exists
    (``blockedBy``/``blocked_by``/``depends_on``/``dependsOn``, normalised by
    ``plan._dependency_list``):

      * a SCAFFOLD task's unit is itself;
      * a SEALS task's unit is that of the SCAFFOLD task named **directly** in
        its ``blockedBy``;
      * a BODIES task's unit is that of the SEALS task named directly in its
        ``blockedBy``;
      * an ADJUDICATE task's unit is that of the SCAFFOLD/SEALS/BODIES task
        named directly in its ``blockedBy``.

    Why not a new ``unit:`` key: the plan asks for reuse, and every grouping
    field this repo already has is worse. ``batch_id`` means "co-runnable in
    ONE worktree and ONE implementer session" — the exact opposite of role
    separation, and reusing it would make the protocol's separation
    unexpressible. A ``unit:`` label (``labels: [unit:D1]``) would work
    mechanically but adds a second fact that can disagree with the dependency
    edges the dispatcher actually orders by; when they disagreed, the
    dispatcher would order by one and report by the other. Key-prefix parsing
    (``D1-P1``) is a naming convention masquerading as a schema.

    Deriving the unit from the edges means the ordering enforcement needs no
    new runtime machinery at all: the edge that names the unit is the same
    edge ``runnable_now`` already gates on.

    Why **direct** edges and not transitive reachability: transitively, a
    BODIES task could satisfy "has a seals predecessor" through some *other*
    unit's seals, and the check would pass while its own unit's seals never
    existed. Requiring the edge to be named on the row makes the unit visible
    in the file the human reviews, and makes an ambiguous membership
    (two seals predecessors resolving to different scaffold roots) a typed
    error instead of a silent choice.

    LEGACY tasks are in no unit and never appear here. Deterministic order:
    units sorted by ``unit_id``, member keys sorted within each unit.

    A row whose role does not parse, and a row whose membership is ambiguous or
    missing, belongs to NO unit: this function reports the units that exist and
    :func:`validate` reports why the others do not. Silently inventing a unit
    for an unparseable row would be a guess, and dropping the row without a
    report is what :func:`validate`'s PO-1..PO-4 errors exist to prevent.
    """
    roles, _unparseable = _roles_of(tasks)
    unit_of = _unit_roots(tasks, roles)[0]

    members: dict[str, dict[Role, list[str]]] = {}
    for task in tasks:
        role = roles.get(task.key)
        if role is None or role is Role.LEGACY:
            continue
        root = unit_of.get(task.key)
        if root is None:
            continue
        members.setdefault(root, {}).setdefault(role, []).append(task.key)

    units: list[UnitView] = []
    for root in sorted(members):
        by_role = members[root]
        # A unit is identified by its SCAFFOLD task, so a root with no scaffold
        # row in this file is not a unit we can name.
        if root not in by_role.get(Role.SCAFFOLD, []):
            continue
        units.append(
            UnitView(
                unit_id=root,
                scaffold_key=root,
                seals_keys=tuple(sorted(by_role.get(Role.SEALS, ()))),
                bodies_keys=tuple(sorted(by_role.get(Role.BODIES, ()))),
                adjudicate_keys=tuple(sorted(by_role.get(Role.ADJUDICATE, ()))),
            )
        )
    return tuple(units)


def _roles_of(
    tasks: Sequence[plan_mod.Task],
) -> tuple[dict[str, Role], dict[str, str]]:
    """``({key: Role}, {key: parse error})`` over ``tasks``.

    Roles are read off ``Task.raw`` (the precedent is `orchestrator`'s read of
    the unmodeled `risk:` field): P1 deliberately did not add a `role` field to
    `Task`, because a field defaulting to LEGACY while `load_tasks` did not
    parse it would assert "legacy" for rows that carry a role. P3 did not add
    one either — the parse happens in `load_tasks` and the row is the single
    source, so a modeled field would be a second copy of the same fact.
    """
    roles: dict[str, Role] = {}
    errors: dict[str, str] = {}
    for task in tasks:
        try:
            roles[task.key] = parse_role_field(task.raw or {}, task_key=task.key)
        except RoleProtocolError as exc:
            errors[task.key] = str(exc)
    return roles, errors


def _unit_roots(
    tasks: Sequence[plan_mod.Task], roles: Mapping[str, Role]
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """``({key: unit root}, {key: the roots its direct predecessors gave})``.

    Resolved in phase order, because a SEALS row's root is named directly on it
    (its scaffold edge) while a BODIES row's root comes through its seals edge.
    A row whose predecessors yield zero or more than one root gets no entry in
    the first mapping; the second mapping keeps what they yielded so
    :func:`validate` can say which rule was broken and with what evidence.
    """
    by_key = {task.key: task for task in tasks}
    unit_of: dict[str, str] = {}
    candidates: dict[str, tuple[str, ...]] = {}

    def _deps_with_role(key: str, wanted: tuple[Role, ...]) -> list[str]:
        task = by_key.get(key)
        if task is None:
            return []
        return [
            dep
            for dep in task.blocked_by
            if roles.get(dep) in wanted
        ]

    for task in tasks:
        if roles.get(task.key) is Role.SCAFFOLD:
            unit_of[task.key] = task.key
            candidates[task.key] = (task.key,)

    # SEALS -> its directly-named SCAFFOLD; BODIES -> its directly-named SEALS;
    # ADJUDICATE -> any directly-named mandatory-phase task. Direct edges only:
    # transitively, a BODIES row could satisfy "has a seals predecessor"
    # through ANOTHER unit's seals while its own unit's seals never existed.
    for role, wanted in (
        (Role.SEALS, (Role.SCAFFOLD,)),
        (Role.BODIES, (Role.SEALS,)),
        (Role.ADJUDICATE, MANDATORY_PHASE_ORDER),
    ):
        for task in tasks:
            if roles.get(task.key) is not role:
                continue
            roots = _dedup(
                [
                    root
                    for dep in _deps_with_role(task.key, wanted)
                    for root in (unit_of.get(dep),)
                    if root is not None
                ]
            )
            candidates[task.key] = roots
            if len(roots) == 1:
                unit_of[task.key] = roots[0]
    return unit_of, candidates


@dataclass(frozen=True)
class RoleValidation:
    """The single result object for plan-time role validation.

    ``errors`` refuse the worklist; ``warnings`` never do. ``specs`` and
    ``units`` are the derived facts, exposed so that consumers compose over
    this result rather than re-deriving it (invariant 1's corollary: one
    entrypoint plus pure accessors over its result).
    """

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    specs: tuple[TaskRoleSpec, ...] = ()
    units: tuple[UnitView, ...] = ()

    @property
    def ok(self) -> bool:
        """True iff there are no errors. Warnings do not affect it."""
        return not self.errors


def validate(tasks: Sequence[plan_mod.Task]) -> RoleValidation:
    """THE plan-time role check. Pure function of the task list.

    One entrypoint, because two callables that both decide "is this worklist
    protocol-legal" would diverge (invariant 1). `plan.load_tasks` raises
    `ValidationError` when ``.errors`` is non-empty — before it returns, so a
    failing worklist never partially plans. Warning consumers call this same
    function and read ``.warnings``; they must not re-implement any rule.

    ERRORS (worklist refused):

      * any per-row failure from :func:`parse_task_role_spec`, collected for
        ALL rows rather than raising on the first, so one run reports every
        broken row. The first row that raises does not mask the rest.
      * PO-1: a SEALS task with no SCAFFOLD task in its direct ``blockedBy``.
      * PO-2: a BODIES task with no SEALS task in its direct ``blockedBy``.
        This is the rule that makes "bodies may not start until seals is
        Done" enforceable: without the edge there is nothing to gate on, and
        an absent edge must be a refusal, not an empty unit that passes.
      * PO-3: an ADJUDICATE task with no SCAFFOLD/SEALS/BODIES task in its
        direct ``blockedBy``.
      * PO-4: a role-carrying task whose direct role-carrying predecessors
        resolve to more than one unit root (ambiguous membership).
      * PO-5: a SEALS or BODIES task that names, in its direct ``blockedBy``,
        a task of a LATER mandatory phase from its own unit (a phase
        inversion inside one unit that is not a cycle — e.g. seals blocked by
        a sibling bodies task of the same unit).
      * OVERRIDE: a row whose ``immutable_paths:`` narrows its role's
        protected set, via :func:`validate_override` against
        :func:`built_in_policy`. Collected per row like the rest.

    Note what is NOT an error, and why: a BODIES task cannot be refused here
    for "touching tests/**", because task rows do not declare the paths they
    will touch. The plan-time half of that seal row is the **declared**
    attempt — an override that narrows — refused by :func:`validate_override`.
    The diff-time half is :func:`check_branch`.

    WARNINGS (reported, never refusing):

      * a SCAFFOLD task with no SEALS dependent, or a SEALS task with no
        BODIES dependent: an incomplete unit. A warning because a worklist is
        legitimately authored and dispatched incrementally, and refusing
        would block the first commit of every unit.
      * an override entry already covered by the role's default (a redundant
        protection — invariant 5).
      * LEGACY and role-carrying tasks in the same file. Legal and expected
        during migration, worth seeing.

    Model-family correlation is NOT decided here: it needs the run-level
    implementer default, which is not a property of the file. See
    :func:`agent_correlation_warnings`.

    Determinism: errors and warnings are ordered by task key, then by rule id,
    so two runs over one file produce byte-identical output.
    """
    errors: list[tuple[str, str, str]] = []  # (task key, rule id, message)
    warnings: list[tuple[str, str, str]] = []

    roles, role_errors = _roles_of(tasks)
    specs: list[TaskRoleSpec] = []
    for task in tasks:
        if task.key in role_errors:
            errors.append((task.key, "ROLE", role_errors[task.key]))
            continue
        try:
            specs.append(parse_task_role_spec(task.raw or {}, task_key=task.key))
        except RoleProtocolError as exc:
            # Collected, never raised on the first: one run must report every
            # broken row, or fixing them costs one round per row.
            errors.append((task.key, "ROW", str(exc)))

    unit_of, candidates = _unit_roots(tasks, roles)
    units = units_of(tasks)
    by_key = {task.key: task for task in tasks}

    def _direct_roles(key: str, wanted: tuple[Role, ...]) -> list[str]:
        task = by_key.get(key)
        if task is None:
            return []
        return [dep for dep in task.blocked_by if roles.get(dep) in wanted]

    for task in tasks:
        role = roles.get(task.key)
        if role is None or role is Role.LEGACY:
            continue

        if role is Role.SEALS and not _direct_roles(task.key, (Role.SCAFFOLD,)):
            errors.append((
                task.key,
                "PO-1",
                f"PO-1: task {task.key} is role 'seals' and names no 'scaffold' "
                "task in its blockedBy. The edge IS the unit: without it there "
                "is nothing for the dispatcher to order by and no scaffold to "
                "seal against",
            ))
        if role is Role.BODIES and not _direct_roles(task.key, (Role.SEALS,)):
            errors.append((
                task.key,
                "PO-2",
                f"PO-2: task {task.key} is role 'bodies' and names no 'seals' "
                "task in its blockedBy. That edge is what makes 'bodies may not "
                "start until seals is done' enforceable; an absent edge is a "
                "refusal, never an empty unit that passes",
            ))
        if role is Role.ADJUDICATE and not _direct_roles(
            task.key, MANDATORY_PHASE_ORDER
        ):
            errors.append((
                task.key,
                "PO-3",
                f"PO-3: task {task.key} is role 'adjudicate' and names no "
                "scaffold/seals/bodies task in its blockedBy, so the dispute it "
                "rules on belongs to no unit",
            ))

        roots = candidates.get(task.key, ())
        if len(roots) > 1:
            errors.append((
                task.key,
                "PO-4",
                f"PO-4: task {task.key}'s role-carrying predecessors resolve to "
                f"{len(roots)} units ({', '.join(roots)}); ambiguous membership "
                "is a typed error, not a silent choice of one",
            ))

        if role in (Role.SEALS, Role.BODIES):
            own_root = unit_of.get(task.key)
            own_phase = MANDATORY_PHASE_ORDER.index(role)
            for dep in task.blocked_by:
                dep_role = roles.get(dep)
                if dep_role not in MANDATORY_PHASE_ORDER:
                    continue
                if own_root is None or unit_of.get(dep) != own_root:
                    continue
                if MANDATORY_PHASE_ORDER.index(dep_role) > own_phase:
                    errors.append((
                        task.key,
                        "PO-5",
                        f"PO-5: task {task.key} (role {role.value!r}) is blocked "
                        f"by {dep} (role {dep_role.value!r}) of its own unit "
                        f"{own_root} — a later phase cannot gate an earlier one. "
                        "This is a phase inversion, not a cycle, so cycle "
                        "detection cannot see it",
                    ))

    defaults = built_in_policy()

    # --- illegal (narrowing) overrides ------------------------------------ #
    # The declared half of the immutable-paths rule, and the only half plan
    # time can see: a row does not declare the paths it will touch, but it
    # does declare the ones it claims are no longer its role's to protect.
    # Held against the COMPILED-IN defaults, which is the only policy a pure
    # function of the task list has and also the right one — a repo `roles:`
    # section may itself only ADD, so an entry that narrows the built-in set
    # narrows every policy derived from it. Collected, never raised on the
    # first, for the same reason the per-row failures above are.
    for spec in specs:
        try:
            validate_override(spec, defaults)
        except RoleProtocolError as exc:
            errors.append((spec.task_key, "OVERRIDE", str(exc)))

    # --- warnings: reported, never refusing ------------------------------- #
    for spec in specs:
        if not spec.added_immutable_globs:
            continue
        try:
            role_globs = defaults.rule_for(spec.role).globs
        except RoleProtocolError:  # pragma: no cover - table covers every role
            continue
        for entry in spec.added_immutable_globs:
            if entry in role_globs:
                warnings.append((
                    spec.task_key,
                    "W-REDUNDANT",
                    f"task {spec.task_key} adds immutable path {entry!r}, which "
                    f"role {spec.role.value!r} already denies. A duplicated "
                    "protection is invariant 5's failure mode: two entries "
                    "covering one fact let a mutation delete half while the "
                    "suite stays green",
                ))

    for unit in units:
        if not unit.seals_keys:
            warnings.append((
                unit.scaffold_key,
                "W-NO-SEALS",
                f"unit {unit.unit_id}: scaffold task {unit.scaffold_key} has no "
                "'seals' task depending on it — an incomplete unit. Legal "
                "(worklists are authored incrementally) and worth seeing",
            ))
        for seals_key in unit.seals_keys:
            if not any(
                seals_key in by_key[bodies_key].blocked_by
                for bodies_key in unit.bodies_keys
            ):
                warnings.append((
                    seals_key,
                    "W-NO-BODIES",
                    f"unit {unit.unit_id}: seals task {seals_key} has no "
                    "'bodies' task depending on it — an incomplete unit",
                ))

    legacy_keys = sorted(k for k, r in roles.items() if r is Role.LEGACY)
    role_keys = sorted(k for k, r in roles.items() if r is not Role.LEGACY)
    if legacy_keys and role_keys:
        warnings.append((
            "",
            "W-MIXED",
            "this file mixes role-less (legacy) rows with role-carrying rows: "
            f"legacy {', '.join(legacy_keys)}; roles {', '.join(role_keys)}. "
            "Legal and expected during migration, worth seeing",
        ))

    return RoleValidation(
        errors=tuple(msg for _k, _r, msg in sorted(errors, key=lambda e: e[:2])),
        warnings=tuple(
            msg for _k, _r, msg in sorted(warnings, key=lambda w: w[:2])
        ),
        specs=tuple(sorted(specs, key=lambda s: s.task_key)),
        units=units,
    )


def agent_correlation_warnings(
    validation: RoleValidation, *, default_agent: str
) -> tuple[str, ...]:
    """Warn when a unit's SEALS and BODIES tasks share a model family.

    Composes over :func:`validate`'s result; derives no unit membership of its
    own. ``default_agent`` is REQUIRED and has no default value: the effective
    family of a row with no ``agent:`` is the run-level implementer (which
    under ``--no-claude`` is grok, not claude), so a module-level guess would
    make two identical rows compare unequal and the warning would silently
    never fire. A caller that cannot supply it must not call this.

    The comparison is on the effective family — ``spec.declared_agent`` or
    ``default_agent`` — so an absent ``agent:`` and an explicit
    ``agent: claude`` are correctly seen as the same family. A differing
    ``model:`` tier (opus vs sonnet) does NOT clear the warning: same family
    means correlated failure modes, which is what the warning is about.

    Never an error. Per the plan's correction, cross-family sealing is a
    recommendation; refusing on model identity would be theatre, since the
    dispatcher already spawns a fresh session per task and the real property
    (the seal author cannot see the scaffold author's reasoning) already
    holds.

    One warning per (unit, shared family), sorted by unit id.
    """
    if isinstance(default_agent, bool) or not isinstance(default_agent, str):
        raise RoleProtocolError(
            f"default_agent must be the run-level implementer name, got "
            f"{default_agent!r}. There is no module-level guess: under "
            "--no-claude the effective implementer is grok, not claude"
        )
    if not default_agent.strip():
        raise RoleProtocolError(
            "default_agent is blank; the effective family of a row with no "
            "agent: is the run-level implementer, and a blank one would make "
            "every row correlate with every other"
        )

    spec_by_key = {spec.task_key: spec for spec in validation.specs}
    fallback = _agent_family(default_agent)

    def _families(keys: Sequence[str]) -> set[str]:
        out: set[str] = set()
        for key in keys:
            spec = spec_by_key.get(key)
            declared = spec.declared_agent if spec is not None else None
            # The EFFECTIVE family: an absent `agent:` is the run default, so
            # an unstated row and an explicit `agent: claude` are one family.
            # A differing `model:` tier is deliberately not consulted — opus
            # and sonnet share their failure modes, which is the whole point.
            out.add(_agent_family(declared) if declared else fallback)
        return out

    warnings: list[str] = []
    for unit in sorted(validation.units, key=lambda u: u.unit_id):
        shared = sorted(_families(unit.seals_keys) & _families(unit.bodies_keys))
        for family in shared:
            warnings.append(
                f"unit {unit.unit_id}: seals "
                f"({', '.join(unit.seals_keys)}) and bodies "
                f"({', '.join(unit.bodies_keys)}) share model family "
                f"{family!r}. Cross-family sealing is a recommendation, not a "
                "rule — a shared family is a correlated-failure risk, never a "
                "refusal (plan §3, Stream D correction)"
            )
    return tuple(warnings)


def _agent_family(agent: str) -> str:
    """The model family an ``agent:`` name belongs to.

    Case and surrounding whitespace are not part of the identity; the model
    *tier* is not consulted at all (that is ``model:``, a separate field).
    """
    return agent.strip().lower()


def dispatch_satisfied_statuses(
    dependent_role: Role, dependency_role: Role, *, integration: str
) -> frozenset[str]:
    """Which dependency statuses let ``dependent_role`` dispatch (DISPATCH
    ordering), for one ``blockedBy`` edge.

    Replaces ``plan._DISPATCH_SATISFIED_BRANCH`` / ``_DISPATCH_SATISFIED_PR``
    at the single call site that reads them (``plan.runnable_now``). Total
    dispatch over both roles' :class:`Role` values and over ``integration``
    (``"branch"`` | ``"pr"``, anything else raises — an unknown integration
    mode must not pick a default set).

    The rules:

      * every edge NOT into a SEALS dependency keeps today's behaviour
        exactly — ``{Done}`` in branch mode, ``{Done, Awaiting Review,
        Merged}`` in pr mode. LEGACY↔LEGACY therefore behaves byte-identically
        to today, which is the compatibility requirement.
      * a SEALS → BODIES edge in ``pr`` mode narrows to ``{Merged}``. This is
        a deliberate divergence from the pr-mode widening and it needs to be
        said plainly: the widening exists because an Awaiting-Review
        dependency's *commits* already exist and reach the dependent's
        worktree. But the seals gate is not a code-availability gate, it is a
        review gate — §2a's P2 is done when the seals are committed RED **and
        reviewed**, and a seals PR can still be rejected. Letting bodies start
        against unreviewed seals would rebuild the honour system one level up.
        In ``branch`` mode the same edge stays ``{Done}``, which is already
        terminal there.

    Consequence P3 must not paper over: in ``pr`` mode a unit's bodies wait
    for the seals PR to *land*, so a unit serialises across two PR merges.
    That is the intended cost of the phase gate.

    **2026-08-04 P2 ruling, widening what P1 wrote.** The narrowing is keyed on
    the *dependency* being a SEALS task, not on the (BODIES ← SEALS) pair. P1's
    prose left (dependency=SEALS, dependent ∈ {SCAFFOLD, SEALS, ADJUDICATE,
    LEGACY}) unstated and the seals cover those pairs for totality only. The
    reason to answer them the same way is that the property belongs to the
    dependency: seals are done when they are committed RED **and reviewed**, so
    an Awaiting-Review seals task has not finished its phase no matter who is
    waiting on it. Answering those pairs with the wide pr-mode set would make
    the gate depend on the waiter's role, which is not where the fact lives.
    """
    from . import plan as plan_mod

    # Total over `integration` FIRST: an unknown mode must not be answered at
    # all, for any pair. Membership, not a truthiness test, so "" / "PR" /
    # "pr " / "auto" are all refusals rather than a silent branch-mode default.
    if isinstance(integration, bool) or not isinstance(integration, str):
        raise RoleProtocolError(
            f"integration must be 'branch' or 'pr', got {integration!r} "
            f"({type(integration).__name__})"
        )
    if integration not in ("branch", "pr"):
        raise RoleProtocolError(
            f"unknown integration mode {integration!r}; legal values are "
            "'branch' and 'pr'. An unrecognised mode must not silently pick "
            "one of the two status sets"
        )

    # Total over both roles, with `else: raise` (invariant 3): a Role member
    # added without updating this dispatch must redden, never fall through to
    # whichever set happens to be last.
    for name, role in (("dependent", dependent_role), ("dependency", dependency_role)):
        if role not in (
            Role.SCAFFOLD,
            Role.SEALS,
            Role.BODIES,
            Role.ADJUDICATE,
            Role.LEGACY,
        ):
            raise RoleProtocolError(
                f"{name}_role {role!r} is not a Role member this dispatch "
                "handles; a new role must be added here explicitly, because "
                "falling through would order its edges by someone else's rule"
            )

    if dependency_role is Role.SEALS:
        if integration == "pr":
            # The divergence from the pr-mode widening, stated in the contract
            # above: a review gate, not a code-availability gate.
            return frozenset({plan_mod.MERGED})
        # branch mode: Done is already terminal, so the edge does not narrow —
        # and it is byte-identically plan's own set, not a hand-written twin.
        return plan_mod._DISPATCH_SATISFIED_BRANCH

    # Every edge NOT into a SEALS dependency keeps today's behaviour exactly,
    # read off plan's own sets so a change there cannot pass unnoticed here.
    if integration == "pr":
        return plan_mod._DISPATCH_SATISFIED_PR
    return plan_mod._DISPATCH_SATISFIED_BRANCH


# --------------------------------------------------------------------------- #
# Policy loading (base-pinned — invariant 6)
# --------------------------------------------------------------------------- #


def built_in_policy() -> RolePolicy:
    """:data:`DEFAULT_ROLE_RULES` as a :class:`RolePolicy`.

    Source :data:`PolicySource.BUILT_IN_DEFAULTS`, ``base_ref`` None. Runs
    :func:`validate_rule` over every entry, so a malformed compiled-in table
    fails loudly at first use instead of silently under-protecting.

    Adds one thing the tuple does not carry: :data:`SEAL_VERIFY_TEST_PATHS` is
    appended to the deny set of every role in
    :data:`TEST_PATH_DELEGATED_ROLES`. It lives here rather than in
    :data:`DEFAULT_ROLE_RULES` because that tuple is the glob table — every
    entry in it is a pattern with a fixture path pinning it — and the
    delegation marker is not a pattern at all. Appended LAST so a glob-matched
    violation always reports the specific glob.
    """
    rules: list[RoleRule] = []
    for rule in DEFAULT_ROLE_RULES:
        if rule.role in TEST_PATH_DELEGATED_ROLES:
            rule = dataclasses.replace(
                rule, globs=_dedup((*rule.globs, SEAL_VERIFY_TEST_PATHS))
            )
        validate_rule(rule)
        rules.append(rule)
    return RolePolicy(
        rules=tuple(rules),
        source=PolicySource.BUILT_IN_DEFAULTS,
        base_ref=None,
    )


def role_policy_from_mapping(section: object) -> RolePolicy:
    """Build a policy from a ``roles:`` mapping out of ``.dispatcher.yaml``.

    Shape::

        roles:
          bodies:
            immutable_paths: ["**/fixtures/**"]   # ADD-only
          seals:
            immutable_paths: ["**/cmd/**"]

    Rules, all strict (the precedent is ``repo_config``'s handling of
    ``test:``: a policy-bearing value that is not the shape the author thought
    it was must fail, never be coerced):

      * ``section`` None / absent → :func:`built_in_policy` unchanged, source
        :data:`PolicySource.BUILT_IN_DEFAULTS`. An absent section has exactly
        one meaning and it is the strict one.
      * ``section`` present but not a mapping → :class:`RoleProtocolError`.
      * a key that is not a member of :data:`AUTHORABLE_ROLES` → error
        (including ``legacy``: a repo may not grant the legacy escape hatch a
        policy, and may certainly not restrict it, because that would change
        pre-protocol tasks' behaviour).
      * a per-role value that is not a mapping, or carries a key other than
        ``immutable_paths`` → error. Tolerating unknown nested keys here
        (as ``repo_config`` does at the top level) would silently drop a
        protection the repo asked for.
      * ``immutable_paths`` on ADJUDICATE or on a non-DENY_GLOBS role → error.
      * additions are unioned onto the compiled-in globs. Removal is not
        expressible; an entry shaped like a negation is an error, exactly as
        in :func:`validate_override`.

    Pure function of ``section``. The git read is
    :func:`load_role_policy_from_base`.

    A parsed mapping is stamped :data:`PolicySource.CONFIG_MAPPING`, not
    BASE_PINNED_CONFIG: this function cannot know where its input came from,
    and the function that pinned it is the one entitled to say so.
    """
    if section is None:
        return built_in_policy()
    if isinstance(section, bool) or not isinstance(section, Mapping):
        raise RoleProtocolError(
            f"the {CONFIG_SECTION!r} section must be a mapping of role -> "
            f"options, got {type(section).__name__}: {section!r}"
        )

    additions: dict[Role, tuple[str, ...]] = {}
    for raw_key, raw_value in section.items():
        key = str(raw_key).strip().lower() if isinstance(raw_key, str) else raw_key
        role = next(
            (r for r in AUTHORABLE_ROLES if r.value == key), None
        )
        if role is None:
            raise RoleProtocolError(
                f"{CONFIG_SECTION}: has key {raw_key!r}, which is not an "
                f"authorable role ({_authorable_values()}). A typo must not "
                "silently drop the protection the repo asked for, and "
                "'legacy' may not be given a policy at all — that would "
                "change pre-protocol tasks' behaviour"
            )
        if isinstance(raw_value, bool) or not isinstance(raw_value, Mapping):
            raise RoleProtocolError(
                f"{CONFIG_SECTION}.{key} must be a mapping with an "
                f"{IMMUTABLE_OVERRIDE_FIELD!r} key, got "
                f"{type(raw_value).__name__}: {raw_value!r}"
            )
        unknown = sorted(
            str(k) for k in raw_value if str(k) != IMMUTABLE_OVERRIDE_FIELD
        )
        if unknown:
            raise RoleProtocolError(
                f"{CONFIG_SECTION}.{key} has unknown key(s) "
                f"{', '.join(unknown)}; the only key is "
                f"{IMMUTABLE_OVERRIDE_FIELD!r}. Tolerating unknown keys here "
                "would silently drop a protection the repo asked for"
            )
        if IMMUTABLE_OVERRIDE_FIELD not in raw_value:
            continue
        if _default_kind(role) is not RuleKind.DENY_GLOBS:
            raise RoleProtocolError(
                f"{CONFIG_SECTION}.{key} sets {IMMUTABLE_OVERRIDE_FIELD}:, "
                f"which has no meaning for a "
                f"{_default_kind(role).value} role"
            )
        entries = _string_list(
            raw_value[IMMUTABLE_OVERRIDE_FIELD],
            task_key=f"{CONFIG_SECTION}.{key}",
            field_name=IMMUTABLE_OVERRIDE_FIELD,
        )
        for entry in entries:
            _reject_negation_shape(
                entry, where=f"{CONFIG_SECTION}.{key}.{IMMUTABLE_OVERRIDE_FIELD}"
            )
        additions[role] = entries

    defaults = built_in_policy()
    rules: list[RoleRule] = []
    for rule in defaults.rules:
        extra = additions.get(rule.role, ())
        if extra:
            rule = dataclasses.replace(
                rule, globs=_dedup((*rule.globs, *extra))
            )
        validate_rule(rule)
        rules.append(rule)
    return RolePolicy(
        rules=tuple(rules),
        source=PolicySource.CONFIG_MAPPING,
        base_ref=None,
    )


def load_role_policy_from_base(
    repo_root: str | Path, base_ref: str
) -> RolePolicy:
    """Load the policy from ``base_ref``'s object store — never a working tree.

    Invariant 6: nothing on the gating path reads its parameters from the
    branch under review. A branch that edits its own ``roles:`` section is
    judged under the section already on the protected base.

    Delegates the blob read to :func:`repo_config.load_text_at_base` and
    parses with :func:`role_policy_from_mapping`. Outcomes: absent file or
    absent section → :func:`built_in_policy`; a readable section → its
    additions merged, source :data:`PolicySource.BASE_PINNED_CONFIG`,
    ``base_ref`` recorded. Anything else — the ref does not resolve, the entry
    is a symlink or submodule, the blob will not read or decode, the YAML is
    malformed, the section is invalid — raises. There is deliberately no
    fallback to the head copy and none to the defaults: "I could not read the
    policy" must not read as "the policy permits this", and a *silent* fall
    back to defaults would also hide that the repo's additions were dropped.

    Callers turn the raise into :data:`DiffVerdict.UNDETERMINED`
    (:func:`check_branch`) or a plan-time refusal.

    **P3 composition note.** ``risk.load_risk_config_from_base`` on the
    unmerged ``fix/authority-doc-carveout`` branch already contains exactly
    this git read for the ``risk:`` section of the same file. Do NOT write a
    second copy: implement :func:`repo_config.load_text_at_base` as the one
    reader, and if that branch has already merged when this body is written,
    refactor ``risk.py`` to delegate to it in the same commit. Two readers of
    one file's gate policy is invariant 5's failure mode, and they would
    diverge on exactly the interesting cases (symlink, submodule, non-UTF-8).

    **P3 note on that composition.** ``fix/authority-doc-carveout`` has NOT
    merged into `main` as of this implementation, so
    ``risk.load_risk_config_from_base`` does not exist on this branch and there
    is nothing to refactor yet; ``risk.py`` is left untouched.
    ``repo_config.blob_text_at`` is the one git blob reader and
    ``repo_config.load_text_at_base`` is its config-shaped face (this
    function's and, after the carveout merges, the ``risk:`` loader's).
    """
    from ruamel.yaml.error import YAMLError

    from . import repo_config as repo_config_mod
    from . import yaml_io

    # Attribute lookup on the module, never a from-import: the ONE reader must
    # be substitutable at its own name, which is what lets a seal prove this
    # function contains no second private git read.
    text = repo_config_mod.load_text_at_base(repo_root, base_ref)
    if text is None or not text.strip():
        return built_in_policy()

    try:
        doc = yaml_io.loads(text)
    except YAMLError as exc:
        raise repo_config_mod.RepoConfigError(
            f"malformed YAML in {repo_config_mod.CONFIG_FILENAME} at "
            f"{base_ref}: {exc}"
        ) from exc
    if doc is None:
        return built_in_policy()
    if not isinstance(doc, Mapping):
        raise repo_config_mod.RepoConfigError(
            f"root of {repo_config_mod.CONFIG_FILENAME} at {base_ref} must be "
            f"a mapping, got {type(doc).__name__}"
        )
    if CONFIG_SECTION not in doc or doc.get(CONFIG_SECTION) is None:
        return built_in_policy()

    policy = role_policy_from_mapping(doc.get(CONFIG_SECTION))
    return dataclasses.replace(
        policy, source=PolicySource.BASE_PINNED_CONFIG, base_ref=base_ref
    )


# --------------------------------------------------------------------------- #
# Diff-time enforcement
# --------------------------------------------------------------------------- #


class DiffVerdict(Enum):
    """Outcome of one branch check. Three states, not two-plus-null.

    CLEAN
        The diff was computed and every changed path is writable by the role.
    VIOLATION
        The diff was computed and at least one changed path (or one changed
        scaffolded signature) is not the role's to touch.
    UNDETERMINED
        The diff could not be computed, the policy could not be read, or the
        role could not be resolved. **Fails closed**: callers must treat it as
        a refusal, not a pass. An empty changed-path list from a git command
        that errored is indistinguishable from a genuinely empty diff, so a
        failed read is UNDETERMINED and a *successful* read with zero paths is
        also UNDETERMINED — a role task that changed nothing has not done its
        phase, and "did nothing" must not look like "succeeded"
        (`skills/explicit-state.md`).
    """

    CLEAN = "clean"
    VIOLATION = "violation"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class PathViolation:
    """One changed path the role may not touch, and the glob that says so.

    ``matched_glob`` is the first glob that matched, or
    :data:`SEAL_VERIFY_TEST_PATHS` when the path was denied by the delegated
    test-path predicate, or :data:`ALLOWLIST_MISS` when the rule is
    allow-only and the path matched nothing — a named state in every case,
    never None and never a magic literal.

    ``rationale`` is the violated rule's own rationale, copied in here at
    construction time (2026-08-04 P2 ruling). ``main`` is required to print
    *why* a path is not the role's to touch, and it has only the
    :class:`RoleDiffResult` to print from; making a caller re-derive the rule
    would put a second policy read on the reporting path, which is how the two
    reads drift apart. It defaults to empty so a caller that constructs a
    violation for a test or a report is not forced to invent policy text.
    """

    path: str
    matched_glob: str
    rule_kind: RuleKind
    rationale: str = ""


class SignatureCheckStatus(Enum):
    """Whether the scaffolded-signature comparison actually ran.

    CHECKED
        Both revisions of every candidate file parsed; ``changes`` is
        authoritative.
    UNCHECKED_UNSUPPORTED_LANGUAGE
        At least one changed source file is not Python **and at least one
        was** — a PARTIAL check. This module cannot compare the first kind.
        Named, not silent: an unchecked file must not report as an unchanged
        signature. Callers surface it; the plan's Go side needs its own
        comparator. On BODIES this **does not block** (2026-08-09 operator
        ruling, the per-file verdict): the files this gate could read were
        compared and they decide, and the ones it could not are named instead
        — see :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES`. It keeps the
        ``UNCHECKED_`` prefix because part of the diff genuinely went unread,
        and the naming, not the verdict, is what makes that honest.
    UNCHECKED_UNPARSEABLE
        A revision of a file this gate CAN read would not parse as Python.
        The check started on a file this module is responsible for and could
        not finish, so on BODIES this still refuses (D1-inputs I5) — "I can
        read this language and this file is broken" is not "I cannot read
        this language", and the per-file ruling touches only the second.
    UNCHECKED_COMPARATOR_UNAVAILABLE
        A comparator this gate HAS could not RUN: the ``go`` binary is missing
        or unusable, the packaged helper is absent, died, timed out, or
        answered with a document this protocol does not recognise. Every
        member of :class:`ComparatorFault` maps here and nowhere else — see
        :func:`signature_status_for_fault`, which owns that mapping.

        A fact about the MACHINE, and the third distinct kind of "not
        compared" this enum now carries. Its two neighbours are a fact about
        the LANGUAGE (permanent, nobody can fix it by committing) and a fact
        about the FILE (the branch author fixes it). This one is fixed by
        whoever owns the image, and neither of the other two names them.

        BLOCKING on BODIES, and this is the member's whole reason for
        existing rather than reusing UNCHECKED_UNSUPPORTED_LANGUAGE: that
        status is promoted to UNCHECKED_NO_SUPPORTED_FILE on a diff with
        nothing readable in it, and UNCHECKED_NO_SUPPORTED_FILE is CLEAN. Give
        a missing ``go`` binary the language answer and a broken CI image
        silently clears every Go branch it builds, for as long as the image
        stays broken — the loudly-wrong refusal the 2026-08-09 ruling removed,
        replaced by a quietly-wrong pass, which is the trade that ruling was
        careful NOT to make. It is therefore in
        :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES`, and ranked FIRST in
        :data:`_SIGNATURE_STATUS_PRECEDENCE` so no neighbour's clearing status
        can outrank it on a mixed diff (P4, 2026-08-09 — the rank's own
        rationale is at the precedence tuple).
    UNCHECKED_NO_SUPPORTED_FILE
        **Nothing** in the diff is a file this gate has a comparator for — a
        Go-only, TypeScript-only or docs-only branch. Distinct from both of
        its neighbours, by the 2026-08-09 operator ruling (see the I6 section
        of ``tests/test_role_protocol_inputs.py``):

          * not UNCHECKED_UNSUPPORTED_LANGUAGE. Under I6 the ruled VERDICTS
            differed; under the per-file ruling that replaced it (2026-08-09)
            both are CLEAN, so the verdict no longer separates them and the
            STATUS is the only place the difference can live: "this gate
            examined NOTHING" versus "this gate examined something and skipped
            the rest". Collapsing them would also force :func:`check_branch`
            to re-derive the difference from the path list, i.e. spell the
            supported-language rule a second time outside
            :func:`_supported_language_refusal`, which owns it. Two copies of
            "which languages can this gate read" fail towards a silent CLEAN
            the day a Go comparator lands.
          * not NOT_APPLICABLE, which is a fact about the ROLE ("no signature
            duty"). This is a fact about the LANGUAGE: the role HAS the duty
            and this gate cannot discharge it. The two diverge the moment a
            comparator exists.

        The ``UNCHECKED_`` prefix is deliberate even though the verdict is
        CLEAN: the comparison genuinely did not run, and a name that hid that
        would reintroduce the I5 lie one level up. What makes the CLEAN
        honest is :attr:`SignatureComparison.unsupported_paths` and the
        detail, not the state's name.
    NOT_APPLICABLE
        The role has no signature obligation (every role except BODIES).
    """

    CHECKED = "checked"
    UNCHECKED_UNSUPPORTED_LANGUAGE = "unchecked_unsupported_language"
    UNCHECKED_UNPARSEABLE = "unchecked_unparseable"
    UNCHECKED_COMPARATOR_UNAVAILABLE = "unchecked_comparator_unavailable"
    UNCHECKED_NO_SUPPORTED_FILE = "unchecked_no_supported_file"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SignatureChange:
    """One scaffolded signature that the branch altered or removed.

    ``before``/``after`` are normalised fingerprints (see
    :func:`compare_signatures`), so a reformat is not a change and a renamed
    parameter is. ``after`` is None when the symbol was removed.
    """

    path: str
    symbol: str
    before: str
    after: str | None


@dataclass(frozen=True)
class SignatureComparison:
    """Result of comparing one file's signatures across two revisions.

    ``unsupported_paths`` is the changed paths this gate has NO comparator
    for, in diff order — the machine-readable half of "which files did nobody
    read". A field and not only prose, because prose is the claim and the
    field is the mechanism: for a wholly-unreadable diff every path is
    unsupported, so a report that dumps the whole path list is
    indistinguishable from an honest one. They differ only on a MIXED diff,
    where this field names the skipped file alone (2026-08-09 ruling).

    An unparseable ``*.py`` is NOT in it. That file was opened and read; the
    gate failed ON it rather than skipping it, and its reason is not language
    support — naming it would send the reader off to write a comparator that
    already exists.
    """

    status: SignatureCheckStatus
    changes: tuple[SignatureChange, ...] = ()
    detail: str = ""
    unsupported_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleDiffResult:
    """The verdict of one :func:`check_branch` call.

    ``checked_paths`` is the exact path list the verdict was computed over, so
    a CLEAN verdict can be audited for having actually examined something —
    the A-stream's coverage lesson applied to this gate.
    """

    verdict: DiffVerdict
    role: Role
    base_ref: str
    branch_ref: str
    violations: tuple[PathViolation, ...] = ()
    signature: SignatureComparison | None = None
    checked_paths: tuple[str, ...] = ()
    policy_source: PolicySource | None = None
    detail: str = ""
    #: D7's answer, or ``None`` when :func:`check_branch` did not ask — which
    #: was the state at the P1 scaffold and is NO LONGER REACHABLE through
    #: :func:`check_branch`: since the D7 wiring (P4, 2026-08-12) every return
    #: from this function that gets past the diff read carries a record, and
    #: the arms that return before it return through ``_undetermined`` and are
    #: UNDETERMINED, never CLEAN. It stays ``None``-able because a caller may
    #: build a :class:`RoleDiffResult` itself, and because that is the state
    #: the field's whole warning is about. **``None`` is not "clean"**, exactly as
    #: ``signature=None`` is not "unchanged": the sub-record carries its own
    #: :class:`~claude_dispatcher.branch_reachability.ReachabilitySweepStatus`
    #: for every way of not having run, and ``None`` means the question was
    #: never put. A caller that treats ``None`` as a pass has invented the one
    #: reading this whole unit exists to refuse.
    reachability: BranchReachability | None = None


def first_matching_glob(path: str, patterns: Sequence[str]) -> str | None:
    """The first pattern in ``patterns`` matching ``path``, else None.

    Delegates to ``risk.matches_any_glob`` one pattern at a time so this
    module owns no second glob translation (invariant 5): the gate's glob
    semantics — anchored, ``**/`` matching zero or more segments — are defined
    once, in ``risk.py``, and both gates must agree. ``path`` is posix form,
    as git emits.

    Purely a glob question: the non-glob markers a rule may carry
    (:data:`SEAL_VERIFY_TEST_PATHS`) are passed to ``risk.matches_any_glob``
    like any other pattern and match nothing, because they contain no
    wildcard. Their meaning is applied by :func:`evaluate_changed_paths`, so
    this function stays the one place glob semantics live and nothing else.
    """
    from . import risk as risk_mod

    for pattern in patterns:
        if risk_mod.matches_any_glob(path, (pattern,)):
            return pattern
    return None


def evaluate_changed_paths(
    rule: RoleRule, changed_paths: Sequence[str]
) -> tuple[PathViolation, ...]:
    """Every path in ``changed_paths`` that ``rule`` forbids.

    Total over :class:`RuleKind`: DENY_GLOBS → paths that match a glob;
    ALLOW_ONLY_GLOBS → paths that match NO glob; UNRESTRICTED → empty tuple.
    Any other kind raises.

    ``changed_paths`` must be produced with rename detection OFF (see
    :func:`changed_paths_between`) so a file moved out of a protected
    directory appears as a deletion of the protected path. Deletions and
    additions count as touching: a body agent that deletes a seal has
    defeated it as thoroughly as one that edits it.

    Pure. Order follows ``changed_paths``; one violation per path, carrying
    the FIRST matching glob so a mutation that removes a single glob reddens
    exactly one seal.

    One addition the P1 contract does not state and the 2026-08-04 P2 ruling
    does: when the rule carries :data:`SEAL_VERIFY_TEST_PATHS`, a path no glob
    matched is put to ``seal_verify.is_test_path`` — the repo's ONE matcher for
    "is this a test file" — and denied if it answers yes, with
    :data:`SEAL_VERIFY_TEST_PATHS` as the ``matched_glob``. Globs are tried
    first so a violation names the specific pattern when there is one.

    **Both kinds read the marker (2026-08-10).** It used to be read in the
    DENY_GLOBS branch only, so an ALLOW_ONLY rule whose writable set was "this
    repo's test files" fell through to :func:`first_matching_glob`, which
    matches nothing on a marker that carries no wildcard — the rule silently
    meant "the writable set is empty" and refused every path in the repository,
    seals included. The marker names a FACT ("this repo's test files"); the
    rule's KIND is what turns that fact into a denial or a grant. One marker,
    one meaning, two verdicts — which is exactly what
    :data:`Role.SEALS`'s inverted row needs, and the reason the split is done
    once in :func:`_split_delegation_marker` rather than twice by hand.

    An allow-only violation still carries :data:`ALLOWLIST_MISS`, never the
    marker: on the allow side the marker is the reason a path was PERMITTED, and
    there is no pattern that "says so" for a path outside the writable set.
    """
    if rule.kind is RuleKind.UNRESTRICTED:
        return ()

    if rule.kind is RuleKind.DENY_GLOBS:
        patterns, delegate = _split_delegation_marker(rule.globs)
        violations: list[PathViolation] = []
        for path in changed_paths:
            matched = first_matching_glob(path, patterns)
            if matched is None and delegate and _is_test_path(path):
                matched = SEAL_VERIFY_TEST_PATHS
            if matched is not None:
                violations.append(
                    PathViolation(
                        path=path,
                        matched_glob=matched,
                        rule_kind=rule.kind,
                        rationale=rule.rationale,
                    )
                )
        return tuple(violations)

    if rule.kind is RuleKind.ALLOW_ONLY_GLOBS:
        patterns, delegate = _split_delegation_marker(rule.globs)
        return tuple(
            PathViolation(
                path=path,
                matched_glob=ALLOWLIST_MISS,
                rule_kind=rule.kind,
                rationale=rule.rationale,
            )
            for path in changed_paths
            if first_matching_glob(path, patterns) is None
            and not (delegate and _is_test_path(path))
        )

    raise RoleProtocolError(
        f"cannot evaluate changed paths for unknown rule kind {rule.kind!r}; a "
        "kind that falls out of the bottom would report every diff as clean"
    )


def _split_delegation_marker(
    globs: Sequence[str],
) -> tuple[tuple[str, ...], bool]:
    """Split a rule's ``globs`` into real patterns and the delegation flag.

    :data:`SEAL_VERIFY_TEST_PATHS` is not a glob — it names a fact that
    ``seal_verify.is_test_path`` answers — so it must never reach
    :func:`first_matching_glob`, where it would match nothing and quietly
    disappear. Both :class:`RuleKind` branches of
    :func:`evaluate_changed_paths` need the same split, and doing it here is
    what keeps the marker's meaning from being written down twice and drifting
    apart, which is the defect this function was extracted to close.
    """
    return (
        tuple(glob for glob in globs if glob != SEAL_VERIFY_TEST_PATHS),
        SEAL_VERIFY_TEST_PATHS in globs,
    )


def _is_test_path(path: str) -> bool:
    """``seal_verify``'s test-path predicate, imported at the call site.

    Function-local import: ``seal_verify`` pulls in ``mechanical_verify`` and
    subprocess machinery this module otherwise has no need of, and the gate
    path must not grow imports it does not use.
    """
    from . import seal_verify as seal_verify_mod

    return seal_verify_mod.is_test_path(path)


# --------------------------------------------------------------------------- #
# Unit D2 — the comparator registry
#
# **P1 SCAFFOLD. Contracts only.** Everything in this section is a typed
# signature plus a normative docstring; the bodies that are present are either
# (a) the existing Python comparator MOVED behind the new interface, unchanged
# in behaviour, or (b) one of the two small pure helpers a seal must import to
# express itself, named as such at their definitions
# (:func:`validate_registry`, :func:`support_for_path`). Everything Go-side
# raises ``NotImplementedError``.
#
# WHY A REGISTRY AND NOT AN ``elif``
# ----------------------------------
# The signature half of this gate protects **zero files in the target repo**:
# `compare_signatures` dispatched on ``endswith(".py")`` and evenplay-mono holds
# 2,288 Go files, 996 TS/TSX, 781 SQL, 316 Java and 0 Python. The next target
# (awevana) is 231 Go / 75 TS / 8 Python. Both target families are
# Go-then-TypeScript, so a per-language ``elif`` chain in
# :func:`compare_signatures` would be the two-copies problem returning by
# another door: the language rule was DELIBERATELY collapsed to exactly one
# spelling on 2026-08-09 (one ``endswith`` in the whole module, proved by a
# mutation that moves 41 rows), and an ``elif`` chain re-scatters it.
#
# HOW THE ONE-SPELLING PROPERTY IS PRESERVED
# ------------------------------------------
# Two questions, one answer site each, and no third site may ask either:
#
#   * **"what language is this path?"** — :func:`support_for_path`, reading
#     :data:`COMPARATORS` and nothing else. The ``".py"`` literal moved OUT of
#     :func:`_supported_language_refusal` and INTO the Python row's
#     ``extensions``; that function now calls this one. There is still exactly
#     one place in this module where a file extension decides anything.
#   * **"who can read that language?"** — the row's ``fingerprinter``. Adding
#     TypeScript is one new row in :data:`COMPARATORS` plus one class; no
#     dispatch site changes, because there is no dispatch site to change —
#     :func:`compare_signatures` asks the registry and calls what it is handed.
#
# The registry is a TABLE, not a chain. A mutation that deletes a row removes
# a language's coverage and can be measured; a mutation that adds one cannot
# quietly widen what the gate claims, because :func:`validate_registry` runs at
# import and :func:`enrolled_languages` is the public, sealable answer to "what
# does this build actually cover today".
#
# WHAT THIS REGISTRY DOES **NOT** COVER, STATED SO ITS EXISTENCE IMPLIES NOTHING
# -----------------------------------------------------------------------------
# SQL (781 files in the target repo) and Java (316) are real contract surface —
# a changed column type or a changed method signature is a contract change in
# exactly the sense §2a means — and this unit does not read either. Their
# extensions appear in NO table here, on
# purpose: a "languages we know about but cannot read" table would be a second
# place answering "what language is this path", which is the property this
# section exists to protect. They are reported the way every unreadable file has
# been reported since the 2026-08-09 ruling — by PATH, in
# :attr:`SignatureComparison.unsupported_paths` and in the verdict's own detail
# — so a diff containing them says which files nobody opened, without this
# module having to hold an opinion about what SQL is.
#
# TypeScript (996 files) is also unread, and since D4 (2026-08-10) it is unread
# for a DIFFERENT and nameable reason: it has a row
# (:data:`TYPESCRIPT_SUPPORT`) and that row is in :data:`PENDING_COMPARATORS`,
# where nothing dispatches on it. "Written but not enrolled" is a state with a
# mechanism; "we have not written it" is a state with none. A `.ts` path is
# answered today exactly as a `.sql` path is — by PATH, unsupported — and
# :func:`support_for_path` reads :data:`COMPARATORS` alone, so the pending row
# cannot make the gate claim coverage it does not have.
#
# The consequence, written down rather than left to be discovered: on a diff of
# nothing but SQL and Java, the BODIES verdict is CLEAN
# (UNCHECKED_NO_SUPPORTED_FILE) and no signature was compared. That is the
# 2026-08-09 ruling applied to languages the ruling did not name, and it is the
# correct application of it — but it is coverage this gate does not have, and
# nobody should read the existence of a registry as coverage.
#
# NOTES FOR THE SEAL AUTHOR (P2)
# ------------------------------
# The docstrings in this section are the specification; where one is vague, say
# so and get a ruling rather than guessing — the last three units each had a
# seal author derive a ruling from prose and a P4 adjudicate the guess.
# Specifically:
#
#   * **The one-spelling property is sealable and should be sealed.** There is
#     exactly one ``endswith`` over a file extension in this module and it is in
#     :func:`support_for_path`. A seal that greps this module's source for a
#     second extension literal is legitimate and precedented (the provenance
#     seals already read source). The stronger seal is behavioural: monkeypatch
#     :data:`COMPARATORS` to a registry with a fake language and assert that
#     :func:`compare_signatures`, :func:`_supported_language_refusal` and
#     :func:`check_branch` ALL change their answer — a second copy of the rule
#     somewhere else shows up as one of the three not moving.
#   * **The vacuity trap here is a registry seal that asserts on the table.**
#     ``COMPARATORS == (PYTHON_SUPPORT,)`` proves nothing about dispatch. Assert
#     through :func:`support_for_path` and through
#     :func:`compare_signatures`, and include a row for a language NOT in the
#     table (``.sql``, ``.java``) that asserts the refusal names the path.
#   * **What counts as a change** is unchanged by this unit and is stated once,
#     in :func:`compare_signatures`: added symbol → not a change; removed →
#     change with ``after`` None; differing fingerprint → change; comment or
#     docstring edit → not a change; reformat → not a change. A language row
#     may not re-decide any of those, and a seal that pins them should pin them
#     against the DRIVER, not against a fingerprinter.
#   * **What counts as honest body work** on the Go side, so the seal author
#     does not have to infer it: adding a top-level declaration, editing any
#     function body, editing doc comments, renaming a receiver variable,
#     reformatting. NOT honest: changing a struct tag, adding or reordering a
#     struct field, renaming a parameter, changing a named result to unnamed,
#     making a variadic non-variadic, changing a type alias to a definition.
#     See :class:`GoSignatureFingerprinter`, which rules each of those and says
#     why the receiver-name exception is the one place Go does not follow
#     Python.
#   * **Which states are terminal.** None of the UNDETERMINED signature states
#     is terminal for a branch: unparseable → fix the source; a fault → fix the
#     environment; unsupported-language-in-a-mixed-diff → write the comparator
#     (or split the branch). UNCHECKED_NO_SUPPORTED_FILE is the only state
#     nothing a branch can commit will change, which is precisely why the
#     2026-08-09 ruling made it CLEAN. The full status → verdict table is in
#     :func:`check_branch`.
#   * **Seals written against faults will be RED until a P4 commit exists** —
#     :func:`signature_status_for_fault` names a status member that P1 may not
#     create. Write them anyway and say so in the docstring, as this project's
#     seals already do ("Red now: the member does not exist"); a seal deferred
#     until the member lands is a seal written by the author of the code.
# --------------------------------------------------------------------------- #


class Language(Enum):
    """A language this gate has, or is being given, a signature comparator for.

    A closed set, and deliberately SMALL: membership here is a claim that the
    repo intends to read the language, not that it can today. What it can read
    today is :func:`enrolled_languages`, which is derived from
    :data:`COMPARATORS` and cannot disagree with the dispatch.

    SQL and Java are absent. See this section's header: naming them here would
    create a second table that answers a language question, and the honest
    report of an unread SQL file is its PATH in
    :attr:`SignatureComparison.unsupported_paths`, not a language label.

    **TypeScript joined this enum in D4 (2026-08-10) and is NOT enrolled.** It
    is here for the same reason Go was: it has a written row
    (:data:`TYPESCRIPT_SUPPORT`) sitting in :data:`PENDING_COMPARATORS`, and a
    row needs a member. Membership is a claim of intent, never of coverage;
    :func:`enrolled_languages` is the coverage claim and it reads
    :data:`COMPARATORS` alone.
    """

    PYTHON = "python"
    GO = "go"
    TYPESCRIPT = "typescript"


class ComparatorFault(Enum):
    """Why a comparator that EXISTS could not run. A closed, exhaustive set.

    The gate acquires a **toolchain dependency** with the Go comparator: a
    subprocess, a ``go`` binary, a helper program, a JSON document. Every way
    that can fail is named here, and none of them resolves to a silent CLEAN.

    **A fault is not an unsupported language, and the difference is the whole
    reason this enum exists.** A language nobody can read is a permanent fact
    about the gate; a missing binary is a fact about the machine the gate ran
    on. Conflating them is not a naming preference — it is a live fail-open:
    after the 2026-08-09 ruling a diff whose every path is *unsupported* is
    promoted to :attr:`SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE` and
    the branch is **CLEAN**. So a Go-only branch built in a CI image with no
    ``go`` on PATH would, under the conflated reading, be handed a clean bill of
    health by the broken image — every Go branch, silently, for as long as the
    image stayed broken. Faults therefore map to their own status and NEVER
    into ``unsupported_paths``; see :func:`signature_status_for_fault`.

    A fault is also not an unparseable source file. Unparseable Go is
    :class:`SourceUnparseable`: the gate opened the file, read it, and the file
    is bad. The remediation differs (fix the branch vs fix the environment) and
    so does the party who can act.

    TOOLCHAIN_MISSING
        The external program the comparator needs (``go``) is not on PATH.
    TOOLCHAIN_UNUSABLE
        It is on PATH and did not answer: a version probe that fails or exits
        non-zero, a version older than the helper's language version, a
        ``GOCACHE``/``HOME`` the process cannot write. On PATH is not the same
        as working, and a gate that assumes it is fails open the first time a
        container drops ``$HOME``.
    HELPER_MISSING
        The helper program's source is not where
        :func:`go_helper_source_dir` looked. An install that dropped the
        non-Python asset (the failure mode ``tests/test_packaging.py`` exists
        for, hit live twice on 2026-07-13) must not read as "no Go here".
    HELPER_FAILED
        The helper ran and exited non-zero: a compile error, a panic, a write
        to stderr with no document on stdout.
    HELPER_TIMEOUT
        The helper exceeded :data:`_HELPER_TIMEOUT_SECONDS`. A gate that hangs
        is a gate that is not enforcing anything, and CI would report the hang
        as infrastructure rather than as an unchecked branch — the same
        reasoning as :data:`_GIT_TIMEOUT_SECONDS`.
    HELPER_OUTPUT_INVALID
        The helper exited 0 and stdout is not a well-formed response document
        of the expected schema: not JSON, the wrong ``schema`` string, a missing
        field, a duplicate symbol key. **Including an EMPTY document** where a
        symbol list was expected — "the helper returned no symbols" and "the
        helper returned nothing" must not be the same answer, because the first
        clears a branch and the second is a broken helper clearing every branch.
        The schema string is checked rather than assumed: a helper from a
        different version of this protocol is a fault, not a best-effort read.
    """

    TOOLCHAIN_MISSING = "toolchain_missing"
    TOOLCHAIN_UNUSABLE = "toolchain_unusable"
    HELPER_MISSING = "helper_missing"
    HELPER_FAILED = "helper_failed"
    HELPER_TIMEOUT = "helper_timeout"
    HELPER_OUTPUT_INVALID = "helper_output_invalid"


class ComparatorError(Exception):
    """Base for the two things a fingerprinter may raise.

    Deliberately NOT a subclass of :class:`RoleDiffError`. ``RoleDiffError`` is
    caught in four places on the gate path and mapped to UNDETERMINED with a
    message about git; a comparator failure that inherited it would be swept
    into those handlers and reported as a diff-read failure, losing both the
    fault and the path. Two different failures with one name is invariant 5's
    shape.
    """


class SourceUnparseable(ComparatorError):
    """One revision of one file is not valid source in its own language.

    A fact about the FILE. The comparator opened it, read it, and the text is
    not parseable; ``path`` and ``message`` say which and why.
    :func:`compare_signatures` maps this to
    :attr:`SignatureCheckStatus.UNCHECKED_UNPARSEABLE` and — as it already does
    for Python — leaves ``unsupported_paths`` EMPTY: that file was read, not
    skipped, and naming it as unread would send a reader off to write a
    comparator that already exists.
    """

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


class ComparatorUnavailable(ComparatorError):
    """A comparator that exists could not run. Carries the named fault.

    A fact about the ENVIRONMENT, never about the file or the language. See
    :class:`ComparatorFault` for why that distinction is load-bearing and not
    cosmetic.
    """

    def __init__(self, fault: ComparatorFault, message: str) -> None:
        super().__init__(f"{fault.value}: {message}")
        self.fault = fault
        self.message = message


#: How long the Go helper may take for ONE file revision. Mirrors
#: :data:`_GIT_TIMEOUT_SECONDS` and exists for the same reason: a gate that
#: hangs enforces nothing, and the hang must surface as
#: :attr:`ComparatorFault.HELPER_TIMEOUT` — a named, blocking state — rather
#: than as a CI job somebody cancels.
_HELPER_TIMEOUT_SECONDS = 30


#: Fault -> reportable status, one row per :class:`ComparatorFault` member,
#: written out rather than defaulted. Every row is the same answer today and
#: that is the point of writing them: see :func:`signature_status_for_fault`
#: for why a single ``return`` is refused here, and
#: ``test_every_comparator_fault_has_a_row_and_a_new_one_raises`` for the seal.
_FAULT_SIGNATURE_STATUS: dict[ComparatorFault, SignatureCheckStatus] = {
    ComparatorFault.TOOLCHAIN_MISSING: (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    ),
    ComparatorFault.TOOLCHAIN_UNUSABLE: (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    ),
    ComparatorFault.HELPER_MISSING: (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    ),
    ComparatorFault.HELPER_FAILED: (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    ),
    ComparatorFault.HELPER_TIMEOUT: (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    ),
    ComparatorFault.HELPER_OUTPUT_INVALID: (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    ),
}


def signature_status_for_fault(fault: ComparatorFault) -> SignatureCheckStatus:
    """The ONE mapping from a comparator fault to a reportable status.

    Normative table. Every member of :class:`ComparatorFault` maps to:

      ``SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE``

    There is no second row: every fault in that enum is an environment fault,
    they share a verdict and they share a remediation (fix the machine, not the
    branch), so splitting them across statuses would put a distinction in the
    status that the FAULT already carries. The fault travels in the detail; the
    status carries the verdict.

    **Totality, and why it is spelled as a TABLE and not as one ``return``**
    (P4, 2026-08-09). Every row of that table says the same thing today, so an
    unconditional ``return UNCHECKED_COMPARATOR_UNAVAILABLE`` would be shorter
    and would pass every test written against today's six faults. It is refused
    for one reason: a function with no rows has no row that can be MISSING, so
    the seventh :class:`ComparatorFault` — added by whoever writes the
    TypeScript comparator, in a unit that has not read this docstring — would
    be absorbed silently at whatever the single return happens to say. Today
    that absorption is harmless because there is only one answer; the day a
    fault appears that should NOT block (a comparator legitimately skipping a
    generated file, say) the silent absorption is a fail-open with nobody's
    name on it. The table makes the seventh fault a loud
    :class:`RoleProtocolError` on the first call, which is a decision somebody
    has to make rather than one the code makes for them. This is the same
    discipline :func:`_worst_signature_status` applies to statuses.

    A fault that fell out of the bottom into ``UNCHECKED_UNSUPPORTED_LANGUAGE``
    would be promoted to UNCHECKED_NO_SUPPORTED_FILE on a Go-only diff and
    clear the branch — the broken-CI-image fail-open in one line. There is no
    permissive default here and there must never be one.

    **The BODIES verdict.** UNCHECKED_COMPARATOR_UNAVAILABLE is BLOCKING: it
    belongs in both :data:`_UNCHECKED_SIGNATURE_STATUSES` (the comparison did
    not run) and :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES` (and the branch is
    therefore not cleared) ⇒ :attr:`DiffVerdict.UNDETERMINED` on BODIES,
    ignored on every other role, which has no signature duty. It must NOT be
    promotable to UNCHECKED_NO_SUPPORTED_FILE, which is what makes it different
    from an unsupported language in the only way that shows up in a verdict.

    **The bookkeeping that makes the non-promotion true.**
    :func:`_compare_branch_signatures` promotes when it examined NOTHING and
    skipped at least one path for its language. A path whose comparator exists
    and faulted counts as **examined** — the gate tried to read it — so a
    Go-only diff on a machine with no ``go`` has ``examined == 1``, no
    promotion, and UNDETERMINED. The same path contributes NOTHING to
    ``unsupported_paths``, so the two mechanisms agree: it was not skipped for
    its language and it is not reported as such.

    **P4, 2026-08-09: the above is CORRECT as a conclusion and WRONG about
    which half does the work.** It was checked by breaking each half in a clone
    and reading the verdict, rather than by reading the argument. Both halves
    are also already true and cost nothing: ``examined`` is incremented for
    every path a registry row CLAIMED, before ``compare_signatures`` is called
    and whatever it answers; and the aggregate extends ``unsupported_paths``
    only from ``_supported_language_refusal``'s refusal document, never from a
    comparison's, so a faulted path has no route into that list at all. What
    needed adding was not code but SEALS, because both properties are
    structural and a P3 refactor can undo either without touching a line that
    looks like a gate.

    Measured (BODIES; the ``.go`` row's comparator raises TOOLCHAIN_MISSING)::

        broken           go-only faulted   .go faulted + .sql unreadable
        ---------------- ----------------  ----------------------------
        nothing          undetermined      undetermined
        (a) unsup_paths  undetermined      undetermined
        (b) examined     undetermined      CLEAN  <- fail-open
        (a) and (b)      CLEAN  <- open    CLEAN  <- fail-open
        rank demoted     undetermined      CLEAN  <- fail-open

    Three corrections fall out:

      * **(a) alone is not a verdict property.** A fault filed in
        ``unsupported_paths`` does not clear anything on its own; it produces a
        report that calls a broken toolchain "a language this gate has no
        comparator for", which is a lie with a future in it, but the branch is
        still refused. It is sealed as an honesty requirement, not as the
        fail-open.
      * **(b) alone IS the fail-open, and not on the diff the scaffold cited.**
        The Go-only diff survives (b) being broken, because with nothing in
        ``unsupported_paths`` the promotion's second half cannot fire either.
        The diff that falls over is the MIXED one, where an innocent ``.sql``
        supplies ``unsupported_paths`` and the miscounted fault supplies
        ``examined == 0``. A seal written only against the Go-only case — the
        case the scaffold argued from — would have been green with (b) broken.
      * **The RANK is a third, independent mechanism**, and the one the
        scaffold could not have known about: it predates the ranked fold. With
        both halves correct, demoting this status below
        UNCHECKED_UNSUPPORTED_LANGUAGE clears the same mixed diff by a
        different route. See :data:`_SIGNATURE_STATUS_PRECEDENCE`.

    All five rows are sealed in ``tests/test_role_protocol_faults.py``.

    **The P4 amendment this required.** Adding the member reddens
    ``test_every_signature_check_status_is_reachable``
    (``tests/test_role_protocol_diff.py``), which pins
    :class:`SignatureCheckStatus` by VALUE-SET EQUALITY — deliberately, so that
    a sixth member cannot land without a ruling, exactly as the fifth could not.
    P1 may not amend a seal and P3 may not either, so the member, the seal
    amendment (a sixth literal in the written value set plus a PRODUCING call
    that reaches the new state — never ``produced.add(...)``, never ``>=`` on
    the set) and this body landed in ONE P4-authored commit. They did; this is
    it.

    No fault is reachable in this build through an enrolled row: the only
    fingerprinter that can raise one is :class:`GoSignatureFingerprinter`,
    which is not implemented and not enrolled. It is reachable through the
    registry seam, which is how it is sealed and how the status is produced.
    """
    status = _FAULT_SIGNATURE_STATUS.get(fault)
    if status is None:
        raise RoleProtocolError(
            f"comparator fault {fault!r} has no row in the fault -> signature "
            "status table; a fault absorbed into whatever the previous row "
            "said is a verdict nobody chose, and the one it would most likely "
            "be absorbed into (UNCHECKED_UNSUPPORTED_LANGUAGE) is promoted to "
            "CLEAN on a diff this gate can read nothing in. Classify it here"
        )
    return status


class SignatureFingerprinter(Protocol):
    """One language's answer to "what are this file's declared signatures?".

    The ONLY thing a language contributes. Everything else about the comparison
    — what counts as a change, what an added symbol means, what a removed one
    means, how a deletion is reported — is language-independent, lives once in
    :func:`compare_signatures`, and is NOT re-decided per language. That split
    is deliberate: a registry of whole comparators would let the Go entry
    quietly rule that an added symbol is a violation, or that a removed one is
    not, and the two languages' answers to the same protocol question would
    drift. A registry of fingerprinters cannot.

    ``fingerprints`` returns ``{qualified symbol: fingerprint string}`` for ONE
    revision of ONE file, in **declaration order** (dicts preserve it, and
    :func:`_scaffolded_signatures` already relies on that so a report reads
    top-to-bottom). The strings are opaque to everything above: they are
    compared for equality and printed, never parsed. Two revisions that mean
    the same thing must fingerprint identically — that is what makes a reformat
    not a change — and two revisions that differ in the contract must not.

    Raises :class:`SourceUnparseable` when the text is not valid source, and
    :class:`ComparatorUnavailable` when the comparator itself could not run.
    It must raise ONE of those rather than return an empty mapping for either:
    an empty mapping is a legitimate answer ("this file declares nothing"), and
    a comparator that answers it for a failure hands the caller a CHECKED
    comparison with no changes — a pass bought by having read nothing, which is
    the exact defect class this protocol exists to close.

    Must be a pure function of ``(path, text)`` in the sense that matters:
    same inputs, same fingerprints, whatever else is on the machine. ``path``
    is passed for MESSAGES and for language-dialect decisions a suffix implies;
    a fingerprinter must not read the file off disk — at the revisions this gate
    compares, the file is not on disk at all (see :func:`file_text_at`, which
    reads blobs out of git's object store).
    """

    def fingerprints(self, path: str, text: str) -> dict[str, str]:
        ...


@dataclass(frozen=True)
class LanguageSupport:
    """One row of the comparator registry: a language, its extensions, its
    reader.

    ``extensions`` is **the** spelling of what that language's files look like
    — lowercase, dot-prefixed, matched as a case-sensitive suffix by
    :func:`support_for_path` (which is exactly what ``endswith(".py")`` did, so
    the move changes no behaviour). Case sensitivity is inherited rather than
    chosen: ``FOO.PY`` was unsupported before this unit and still is. It is a
    known gap, not a decision, and neither target repo contains one.

    ``fingerprinter`` is the row's reader. One row per language, one reader per
    row: :func:`validate_registry` refuses a registry where two rows claim the
    same language or the same extension, because "who can read Go" having two
    answers is how a mutation deletes coverage without deleting a row.
    """

    language: Language
    extensions: tuple[str, ...]
    fingerprinter: SignatureFingerprinter


class PythonSignatureFingerprinter:
    """Python, moved behind the interface unchanged.

    The definition of a Python signature is :func:`compare_signatures`'
    contract and :func:`_scaffolded_signatures`' implementation, both
    pre-existing and both untouched by this unit. This class is the adapter: it
    translates ``ast``'s two refusals into :class:`SourceUnparseable` so the
    driver above it never handles a language-specific exception type.

    That translation is the whole of the change, and it is why the Python side
    is a moved body rather than a scaffold: a language the registry cannot
    already serve would make the registry's first entry unexercised, and an
    unexercised interface is a guess about what the second entry needs.
    """

    def fingerprints(self, path: str, text: str) -> dict[str, str]:
        """:func:`_scaffolded_signatures`, with ``ast``'s refusals renamed."""
        try:
            return _scaffolded_signatures(text)
        except SyntaxError as exc:
            raise SourceUnparseable(path, f"python: {exc}") from exc
        except ValueError as exc:  # null bytes and similar ast.parse refusals
            raise SourceUnparseable(path, f"python: {exc}") from exc


# --------------------------------------------------------------------------- #
# Go — the second entry, contract only
# --------------------------------------------------------------------------- #

#: The helper's protocol version, on every request and every response. Checked
#: rather than assumed: a helper source that a branch, an install or a partial
#: upgrade left at a different version is :attr:`ComparatorFault.
#: HELPER_OUTPUT_INVALID`, never a best-effort read of whatever came back.
#: Bump it whenever the fingerprint GRAMMAR changes, because a fingerprint is
#: compared for equality across two invocations of the helper and a grammar
#: change would otherwise read as every symbol having changed.
#: v2 (2026-08-10) closed two false NEGATIVES the P2 seals reproduced: a struct
#: embed renders as ``embedded:T`` rather than ``embedded T`` (the old marker
#: sat in the column a field name occupies, and ``embedded`` is a legal
#: identifier), and an interface literal's element list carries each method's
#: signature wherever no ``Iface.Method`` sub-symbol will. Both change the
#: grammar, so both require this bump; ``main.go`` carries the same constant and
#: the same note.
GO_HELPER_SCHEMA = "claude-dispatcher/go-signature-fingerprint/v2"

#: Where the helper's source lives, relative to this package. Inside
#: ``src/claude_dispatcher/`` and NOT in ``tools/`` for one reason: the gate
#: judges branches in OTHER repositories (evenplay-mono, awevana), so the helper
#: must travel with the dispatcher, not with the tree under judgement — a helper
#: read out of the judged repo would be supplied by the branch it is judging.
#: It is a non-``.py`` asset under the package, so ``pyproject.toml`` must ship
#: it (``tests/test_packaging.py`` is the seal, and the failure it exists for —
#: a pipx install missing an asset — is precisely
#: :attr:`ComparatorFault.HELPER_MISSING`).
GO_HELPER_PACKAGE_DIR = "go_signature_fingerprint"


@dataclass(frozen=True)
class GoHelperRequest:
    """What the Python side sends the helper: ONE revision of ONE file.

    Serialised as a single JSON object on the helper's **stdin**, which is then
    closed. Source travels as TEXT, never as a filename: the revisions this
    gate compares are a merge-base blob and a branch blob, and neither is on
    disk. A helper that took a path would force the caller to materialise
    temporary files and would make the comparison depend on the working tree —
    the working tree being exactly what the branch controls.

    One file per invocation, not a batch. A batch would be faster and would
    make one bad file's fault ambiguous across the set; per-file keeps
    "which file" answerable, and the timeout per-file rather than per-diff.
    """

    schema: str
    path: str
    source: str


@dataclass(frozen=True)
class GoHelperSymbol:
    """One declared symbol and its fingerprint, as the helper reports it.

    ``symbol`` is the qualified key :func:`compare_signatures` matches across
    revisions; ``fingerprint`` is the opaque string it compares. ``kind`` is
    reportage only — ``"func"``, ``"method"``, ``"type"``, ``"interface_method"``
    — and is never part of the comparison: a symbol that changed kind changed
    its fingerprint too, and a second comparison surface is a second thing to
    keep in agreement.
    """

    symbol: str
    fingerprint: str
    kind: str


@dataclass(frozen=True)
class GoHelperResponse:
    """What the helper writes to **stdout**: exactly one JSON object, always.

    Exit status and document are two different channels and mean two different
    things:

      * **exit 0** ⇒ stdout holds a valid response document. That includes the
        document reporting a PARSE ERROR: unparseable Go is a successful run of
        the helper and a fact about the file
        (:class:`SourceUnparseable` ⇒ UNCHECKED_UNPARSEABLE), not a helper
        malfunction.
      * **non-zero** ⇒ :attr:`ComparatorFault.HELPER_FAILED`, whatever is on
        stdout. Diagnostics go to stderr and are folded into the fault message;
        stdout is never partially parsed on a non-zero exit.

    ``parse_error`` and ``symbols`` are mutually exclusive: a document carrying
    both, or neither, is :attr:`ComparatorFault.HELPER_OUTPUT_INVALID`. So is a
    document whose ``schema`` is not :data:`GO_HELPER_SCHEMA`, or whose
    ``symbols`` repeat a key. ``symbols`` may be empty **only** when the file
    genuinely declares nothing; the helper distinguishes that from "I produced
    no output" by always emitting the object, which is why an empty stdout is a
    fault and an empty ``symbols`` list is an answer.

    Order is DECLARATION order, as the Python side's is, so a report reads
    top-to-bottom and two runs of the helper over identical text produce
    identical documents. Determinism is part of the contract: a map iteration
    that reorders symbols would make every diff look like a change.
    """

    schema: str
    symbols: tuple[GoHelperSymbol, ...] = ()
    parse_error: str | None = None


def encode_go_helper_request(path: str, source: str) -> str:
    """The JSON document for one file revision, ready for the helper's stdin.

    Contract: a single JSON object with exactly the fields of
    :class:`GoHelperRequest`, ``schema`` set to :data:`GO_HELPER_SCHEMA`, UTF-8,
    no trailing newline required. ``source`` is passed through verbatim —
    including a BOM, CRLF line endings, or invalid UTF-8 the git read already
    accepted — because normalising here would make the Python and Go sides
    disagree about what the file says.
    """
    return json.dumps(
        {"schema": GO_HELPER_SCHEMA, "path": path, "source": source},
        # ASCII on purpose, and not a style choice. `source` is whatever the
        # git read accepted, which can include lone surrogates from a blob that
        # is not valid UTF-8; `ensure_ascii=False` would raise on encoding
        # those and turn a bad FILE into an environment fault. Escaped, the
        # payload is pure ASCII and always encodable.
        ensure_ascii=True,
        # Deterministic separators, so two runs over one file produce one
        # request byte for byte.
        separators=(",", ":"),
    )


def _decode_helper_response(
    stdout: str,
    schema: str,
    response_type: type,
    symbol_type: type,
) -> object:
    """Validate one helper's stdout and build its response. **One implementation.**

    THE SHARED VALIDATOR, extracted by unit D4's P3 body under the ruling at
    :func:`decode_ts_helper_response` and forced by
    ``test_one_decoder_serves_both_languages_and_neither_is_a_copy``. Every
    line below is language-independent; the only Go- or TypeScript-shaped
    things in it are the four arguments.

    It exists because two decoders would be two implementations of one wire
    protocol, and the copy that forgets the duplicate-key check clears branches
    the original refuses — a divergence in the exact place where being wrong
    fails OPEN.

    The signature is normative and is stated at
    :func:`decode_ts_helper_response`:

      * ``stdout`` and ``schema`` are the first two POSITIONALS, in that order,
        so a seal can observe that each wrapper fixes its OWN schema;
      * ``response_type`` and ``symbol_type`` are constructed by KEYWORD, which
        is what makes four arguments sufficient — the two dataclass pairs are
        field-for-field identical in name by contract, not by coincidence;
      * the return is the caller's ``response_type``, and neither wrapper
        re-validates or reshapes it.

    Raises :class:`ComparatorUnavailable` with
    :attr:`ComparatorFault.HELPER_OUTPUT_INVALID` for every way the document
    can be wrong — not JSON, not an object, wrong or missing ``schema``, empty
    string, missing fields, wrong types, both ``symbols`` and ``parse_error``,
    neither, duplicate symbol keys. Every one of those is a fault and not a
    partial result: a response this function half-understood would produce a
    fingerprint set missing a symbol, and a MISSING symbol is reported by
    :func:`compare_signatures` as a REMOVED one — a bad parse would manufacture
    violations, and a bad parse that dropped everything would manufacture a
    pass.

    Does **not** decide anything about the comparison: a document carrying
    ``parse_error`` is returned intact, and it is the fingerprinter that turns
    it into :class:`SourceUnparseable`. One place per decision.
    """

    def invalid(reason: str) -> ComparatorUnavailable:
        return ComparatorUnavailable(
            ComparatorFault.HELPER_OUTPUT_INVALID,
            f"{reason}; a response this function half-understood would drop "
            "symbols, and a dropped symbol reads as a REMOVED one",
        )

    if not stdout.strip():
        raise invalid(
            "the helper wrote nothing to stdout. 'no symbols' and 'no output' "
            "are not the same answer: the first clears one file and the "
            "second would clear every branch"
        )
    try:
        document = json.loads(stdout)
    except ValueError as exc:
        raise invalid(f"stdout is not JSON ({exc})") from exc
    if not isinstance(document, dict):
        raise invalid(
            f"stdout is a JSON {type(document).__name__}, not the response object"
        )

    declared = document.get("schema")
    if declared != schema:
        raise invalid(
            f"the response schema is {declared!r}, not {schema!r}. A "
            "helper from a different version of this protocol is a fault, "
            "never a best-effort read: fingerprints are compared for equality "
            "across two runs and a grammar change would read as a rewrite"
        )

    raw_parse_error = document.get("parse_error")
    if raw_parse_error is not None and not isinstance(raw_parse_error, str):
        raise invalid(
            f"parse_error is a {type(raw_parse_error).__name__}, not a string"
        )
    parse_error = raw_parse_error or None

    raw_symbols = document.get("symbols")
    if raw_symbols is not None and not isinstance(raw_symbols, list):
        raise invalid(
            f"symbols is a {type(raw_symbols).__name__}, not a list. An empty "
            "LIST is the answer for a file that declares nothing; a missing "
            "one is not an answer at all"
        )

    if (raw_symbols is None) == (parse_error is None):
        raise invalid(
            "symbols and parse_error are mutually exclusive and this document "
            + ("carries both" if parse_error is not None else "carries neither")
        )

    if parse_error is not None:
        return response_type(schema=schema, parse_error=parse_error)

    symbols: list[object] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_symbols or ()):
        if not isinstance(entry, dict):
            raise invalid(f"symbols[{index}] is not an object")
        name = entry.get("symbol")
        fingerprint = entry.get("fingerprint")
        kind = entry.get("kind")
        for field, value in (
            ("symbol", name),
            ("fingerprint", fingerprint),
            ("kind", kind),
        ):
            if not isinstance(value, str) or not value:
                raise invalid(
                    f"symbols[{index}].{field} is {value!r}, not a non-empty "
                    "string"
                )
        assert isinstance(name, str)  # narrowed by the loop above
        if name in seen:
            raise invalid(
                f"symbols carries {name!r} twice. Two fingerprints for one key "
                "means one of them is unreachable, and which one is decided by "
                "dict insertion order rather than by this protocol"
            )
        seen.add(name)
        symbols.append(
            symbol_type(
                symbol=name,
                fingerprint=str(fingerprint),
                kind=str(kind),
            )
        )
    return response_type(schema=schema, symbols=tuple(symbols))


def decode_go_helper_response(stdout: str) -> GoHelperResponse:
    """Parse the Go helper's stdout, or raise the named fault.

    A thin wrapper that fixes :data:`GO_HELPER_SCHEMA` and the Go dataclass
    pair; the validation is :func:`_decode_helper_response` and lives in
    exactly one place. It does not re-validate and it does not reshape — a
    wrapper that did either would be the second copy of the wire protocol back
    again, in the place where a divergence fails OPEN.
    """
    response = _decode_helper_response(
        stdout, GO_HELPER_SCHEMA, GoHelperResponse, GoHelperSymbol
    )
    assert isinstance(response, GoHelperResponse)  # the type it was handed
    return response


def go_helper_source_dir() -> Path:
    """Where this build's Go helper source is, or the named fault.

    Resolves :data:`GO_HELPER_PACKAGE_DIR` **relative to this package** —
    ``Path(__file__).parent`` — never relative to ``repo_root`` and never
    relative to the CWD. The gate's normal job is judging a branch in another
    repository; resolving the helper against that repository would let the
    branch under judgement supply the program that judges it, which is the
    defect ``scripts/check_body_branch.sh`` closes for this module and must not
    be reopened for the helper.

    Raises :class:`ComparatorUnavailable` with
    :attr:`ComparatorFault.HELPER_MISSING` when the directory or its entry
    point is absent — an install that dropped the asset, which
    ``tests/test_packaging.py`` exists to prevent and which has happened twice
    live. Absence is a fault, never "no Go support here": the second reading
    would turn a broken wheel into a clean bill of health for every Go branch.

    **The self-judgement hole, flagged for P4 and NOT closed here.** When this
    repository judges ITSELF (the shape CI has, and the shape
    ``scripts/check_body_branch.sh`` already handles for the module and the
    policy), the helper source IS in the tree under judgement, and
    :data:`FLOOR_GLOBS` does not cover it. A bodies branch could rewrite the
    helper to emit an empty symbol list for every file and walk through the
    signature gate it just neutered — the 2026-08-08 measurement, one file to
    the left. Two things are required and neither is P1's to do:

      * :data:`FLOOR_GLOBS` must grow
        ``**/src/claude_dispatcher/go_signature_fingerprint/**``. That reddens
        ``test_the_floor_is_exactly_the_written_out_set_of_globs``
        (``tests/test_role_protocol_floor.py``), whose ``_FLOOR_ROWS`` table P4
        already ruled that P3 **may not edit** — so the glob and its literal
        rows are one P4 commit, like the module's own two globs were.
      * ``scripts/check_body_branch.sh`` must read the helper out of
        ``<base>``'s object store in the self-judging case, by the same rule it
        already applies to this module: "when its own ``src/`` lies inside the
        checkout under judgement, the branch supplied the library".

    Until both hold, :data:`GO_SUPPORT` must not be enrolled. Coverage a branch
    can switch off is not coverage, and enrolling first would trade a gate that
    protects zero Go files for one that appears to protect 2,288.

    **P3: ``go.mod`` is checked as well as ``main.go``.** Both are entry points
    in the sense that matters — ``go.mod`` fixes the language version the parse
    runs under and pins the module to stdlib-only, which is why
    :data:`FLOOR_GLOBS` covers the whole subtree rather than the one file. An
    install that dropped it would reach ``go build`` and fail there as
    HELPER_FAILED with a module error, which names the wrong party.
    """
    directory = Path(__file__).parent / GO_HELPER_PACKAGE_DIR
    if not directory.is_dir():
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_MISSING,
            f"the Go signature helper's source directory is not at "
            f"{directory}. An install that dropped the asset is a broken "
            "install, never 'this build has no Go support': the second "
            "reading hands every Go branch a clean bill of health",
        )
    missing = [
        name
        for name in ("main.go", "go.mod")
        if not (directory / name).is_file()
    ]
    if missing:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_MISSING,
            f"the Go signature helper at {directory} is missing "
            f"{', '.join(missing)}; it is a program that cannot be built, "
            "which is a broken install and not a language nobody can read",
        )
    return directory


#: How long the ONE-OFF ``go build`` of the helper may take. Separate from
#: :data:`_HELPER_TIMEOUT_SECONDS` because it bounds different work: that one is
#: a per-file budget paid once per revision, this one is paid once per process
#: and a cold Go build cache is a different order of magnitude. Measured
#: 2026-08-09 on the reference machine: 1.9s with an empty ``GOCACHE``, 0.04s
#: warm. Deliberately generous against those numbers — what this bounds is a
#: HUNG toolchain, not a slow one, and a build killed on a loaded CI box would
#: be a HELPER_TIMEOUT nobody can reproduce.
_HELPER_BUILD_TIMEOUT_SECONDS = 120

#: The helper this PROCESS prepared: ``(binary, None)`` or ``(None, fault)``,
#: whichever the first call produced, and None before there has been one.
#:
#: **Why the build is cached and the run is not** (P3, measured 2026-08-09).
#: The gate runs the helper TWICE per changed Go file — base revision and head
#: — so a 200-file Go branch is 400 invocations on the post-implementer hot
#: path. ``go run .`` compiles before each one: measured 59ms per invocation,
#: **24 seconds** added to every such gate run. Building once and executing the
#: binary is 0.7ms per invocation, **0.3s** for the same branch, which is why
#: this global exists. The wire contract is untouched — still one JSON request
#: per file on a fresh process's stdin, still a per-file timeout, still "which
#: file" answerable — so this is a cost fix and not a protocol change.
#:
#: Per PROCESS and never on disk between runs. A binary cached under ``/tmp``
#: across runs would be a file outside :data:`FLOOR_GLOBS` whose bytes decide
#: what a Go signature is, which is the self-judgement hole at
#: :func:`go_helper_source_dir` reopened somewhere the floor cannot reach.
#:
#: The FAULT is cached too, so a machine with no ``go`` pays one ``which`` and
#: not one per file, and so every file in the diff is refused with the same
#: message. A seal that needs a second preparation sets this back to None.
_GO_HELPER_PREPARED: (
    tuple[Path, None] | tuple[None, ComparatorUnavailable] | None
) = None


def _go_toolchain_environment() -> dict[str, str]:
    """The environment the ``go`` toolchain is invoked under.

    Isolated from the ambient one on the axes that would otherwise let the
    machine — or the repository under judgement — change what the helper is:

      * ``GOWORK=off``: the target repo is itself a Go module and may carry a
        ``go.work``. Inheriting it would pull the helper into the judged
        repository's workspace, which is the provenance defect
        :func:`go_helper_source_dir` exists to close, arriving by another door.
      * ``GOFLAGS=``: an inherited ``-mod=vendor`` from a shell profile fails a
        module that has no vendor directory, and the failure would read as
        HELPER_FAILED on a helper that is fine.
      * ``GOPROXY=off`` and ``GOTOOLCHAIN=local``: the helper is stdlib-only and
        must not consult the network. Both make that structural rather than
        true-by-inspection, and a build that suddenly needs a fetch fails
        loudly here instead of hanging into HELPER_TIMEOUT.
      * ``GOOS``/``GOARCH`` removed: a cross-compiling shell would produce a
        binary this process cannot exec.

    ``GOCACHE`` and ``HOME`` are deliberately INHERITED. Pointing the cache at
    a temporary directory would make every run a cold build; an unwritable one
    is a real fault with a name (:attr:`ComparatorFault.TOOLCHAIN_UNUSABLE`)
    and :func:`_probe_go_toolchain` reports it as one.
    """
    import os

    env = dict(os.environ)
    env.update(
        {
            "GOWORK": "off",
            "GOFLAGS": "",
            "GOPROXY": "off",
            "GOTOOLCHAIN": "local",
            "GO111MODULE": "on",
        }
    )
    env.pop("GOOS", None)
    env.pop("GOARCH", None)
    return env


def _go_module_language_version(go_mod: Path) -> tuple[int, ...] | None:
    """The ``go`` directive of the helper's ``go.mod``, or None if unreadable.

    None rather than a raise: the directive is used only to REFUSE a toolchain
    older than the helper needs, so a version this cannot read must not become
    a fault of its own — ``go build`` is still the authority and will say so.
    """
    try:
        text = go_mod.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[0] == "go":
            try:
                return tuple(int(part) for part in fields[1].split("."))
            except ValueError:
                return None
    return None


def _probe_go_toolchain(go: str, source: Path) -> None:
    """Refuse a ``go`` that is on PATH but cannot do the job.

    On PATH is not the same as working, and a gate that assumes it is fails
    open the first time a container drops ``$HOME``. Three refusals, all
    :attr:`ComparatorFault.TOOLCHAIN_UNUSABLE`:

      * the probe does not run, times out, or exits non-zero;
      * ``GOCACHE`` is unset or ``off`` — which is exactly what ``go env``
        reports when there is no writable ``HOME`` (measured), and a build
        under it cannot cache and will not run;
      * the installed version is older than the helper's ``go`` directive. A
        toolchain that predates the syntax the helper is written against
        reports a COMPILE error, and a compile error is HELPER_FAILED — which
        blames the helper for the machine's age.

    One subprocess, once per process: ``go env`` answers both questions.
    """
    import subprocess

    try:
        probe = subprocess.run(
            [go, "env", "GOVERSION", "GOCACHE"],
            capture_output=True,
            timeout=_HELPER_TIMEOUT_SECONDS,
            env=_go_toolchain_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env` did not answer within {_HELPER_TIMEOUT_SECONDS}s; a "
            "toolchain that hangs on its own version probe cannot be used to "
            "clear a branch",
        ) from exc
    except OSError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env` could not be run: {type(exc).__name__}: {exc}",
        ) from exc

    if probe.returncode != 0:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env` exited {probe.returncode}: "
            f"{_helper_diagnostic_text(probe.stderr)}",
        )

    lines = probe.stdout.decode("utf-8", "replace").splitlines()
    version_text = lines[0].strip() if lines else ""
    cache = lines[1].strip() if len(lines) > 1 else ""

    if not cache or cache == "off":
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env GOCACHE` reports {cache or 'nothing'!r}, which is what "
            "it says when there is no writable HOME. A build cannot run "
            "without a cache, and a container that dropped $HOME must not read "
            "as a repository with no Go in it",
        )

    installed = None
    if version_text.startswith("go"):
        try:
            installed = tuple(
                int(part) for part in version_text[2:].split("-")[0].split(".")
            )
        except ValueError:
            installed = None
    if installed is None:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`{go} env GOVERSION` answered {version_text!r}, which is not a "
            "version this gate can compare against the helper's own",
        )

    required = _go_module_language_version(source / "go.mod")
    if required is not None and installed < required:
        installed_text = ".".join(str(part) for part in installed)
        required_text = ".".join(str(part) for part in required)
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"the installed toolchain is go{installed_text} and the helper "
            f"declares go{required_text}. A toolchain older than the language "
            "the helper is written in fails as a COMPILE error, which would "
            "blame the helper for the age of the machine",
        )


def _helper_diagnostic_text(raw: bytes | None) -> str:
    """Helper stderr for a fault message. Lossy and bounded on purpose.

    A diagnostic that cannot be decoded must not mask the failure it describes,
    and a compile-error dump must not become the whole report.
    """
    if not raw:
        return "(nothing on stderr)"
    text = bytes(raw).decode("utf-8", "replace").strip()
    if len(text) > 2000:
        text = text[:2000] + " …(truncated)"
    return text or "(nothing on stderr)"


def _build_go_helper() -> Path:
    """Resolve, probe and compile the helper once. Returns the binary's path.

    Total: every failure leaves here as a :class:`ComparatorUnavailable`
    carrying the named fault, in the order
    :meth:`GoSignatureFingerprinter.fingerprints` documents — HELPER_MISSING,
    then TOOLCHAIN_MISSING, then TOOLCHAIN_UNUSABLE, then the build's own.
    """
    import atexit
    import shutil
    import subprocess
    import tempfile

    source = go_helper_source_dir()

    go = shutil.which("go")
    if go is None:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_MISSING,
            "no `go` on PATH, so the Go signature comparator could not run. "
            "This is a fact about this machine and not about the branch: a "
            "broken CI image must never clear a Go branch",
        )

    _probe_go_toolchain(go, source)

    workspace = Path(tempfile.mkdtemp(prefix="claude-dispatcher-go-helper-"))
    atexit.register(shutil.rmtree, workspace, ignore_errors=True)
    binary = workspace / "go-signature-fingerprint"

    try:
        built = subprocess.run(
            [go, "build", "-o", str(binary), "."],
            cwd=str(source),
            capture_output=True,
            timeout=_HELPER_BUILD_TIMEOUT_SECONDS,
            env=_go_toolchain_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_TIMEOUT,
            f"building the helper in {source} exceeded "
            f"{_HELPER_BUILD_TIMEOUT_SECONDS}s. A gate that hangs is a gate "
            "that is not enforcing anything",
        ) from exc
    except OSError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_FAILED,
            f"`{go} build` in {source} could not be run: "
            f"{type(exc).__name__}: {exc}",
        ) from exc

    if built.returncode != 0 or not binary.is_file():
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_FAILED,
            f"building the helper in {source} exited {built.returncode}: "
            f"{_helper_diagnostic_text(built.stderr)}",
        )
    return binary


def _go_helper_binary() -> Path:
    """The built helper for this process, or re-raise the fault that stopped it.

    See :data:`_GO_HELPER_PREPARED` for why this is cached and why the cache is
    per-process and in memory.
    """
    global _GO_HELPER_PREPARED

    if _GO_HELPER_PREPARED is None:
        try:
            _GO_HELPER_PREPARED = (_build_go_helper(), None)
        except ComparatorUnavailable as exc:
            _GO_HELPER_PREPARED = (None, exc)

    binary, failure = _GO_HELPER_PREPARED
    if failure is not None:
        raise failure
    assert binary is not None  # the two arms of the tuple are exclusive
    return binary


def _run_go_helper(binary: Path, path: str, text: str) -> str:
    """One request in, the helper's stdout out, or the named fault.

    Exit status and document are separate channels: a non-zero exit is
    HELPER_FAILED and stdout is **not read at all**, because a document from a
    run that failed is a partial answer and a partial answer manufactures
    removed symbols.
    """
    import subprocess

    request = encode_go_helper_request(path, text).encode("utf-8")
    try:
        finished = subprocess.run(
            [str(binary)],
            input=request,
            capture_output=True,
            timeout=_HELPER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_TIMEOUT,
            f"the helper took longer than {_HELPER_TIMEOUT_SECONDS}s on "
            f"{path}. There is no retry and no degraded mode: a fallback is "
            "how a gate ends up reporting a pass it did not earn",
        ) from exc
    except OSError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_FAILED,
            f"the helper binary at {binary} could not be executed: "
            f"{type(exc).__name__}: {exc}",
        ) from exc

    if finished.returncode != 0:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_FAILED,
            f"the helper exited {finished.returncode} on {path}: "
            f"{_helper_diagnostic_text(finished.stderr)}",
        )

    try:
        return finished.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_OUTPUT_INVALID,
            f"the helper's stdout for {path} is not valid UTF-8: {exc}",
        ) from exc


class GoSignatureFingerprinter:
    """Go signatures, via ``go/ast`` in a helper program. Contract only.

    **One parser, not two.** The fingerprints come from a small Go program
    built on ``go/ast``, never from a Go parser written in Python. A second
    parser would be a second definition of what a Go signature is, and the two
    would drift the first time the language gained syntax — generics being the
    worked example: a hand-rolled Python reader written before 1.18 would have
    silently dropped every type parameter, and dropping a type parameter is a
    contract change reported as no change.

    WHAT A GO SIGNATURE IS
    ----------------------
    By analogy with the Python contract in :func:`compare_signatures`, whose
    docstring is the model. Read off the FILE's top level and off type
    declarations only; function bodies are never descended into, so a helper a
    body agent defines inside a function is invisible here — which is the point.

    Symbol keys, in declaration order:

      * a top-level ``func`` → ``Name``
      * a method → ``Recv.Name``, where ``Recv`` is the receiver's base type
        name with any ``*`` and any type arguments stripped (``func (s *Svc[T])
        Do()`` → ``Svc.Do``). Pointer-ness is in the FINGERPRINT, not the key,
        so changing a value receiver to a pointer receiver is a change to a
        symbol rather than the removal of one and the addition of another.
      * a type declaration → ``Name``
      * an interface method → ``Iface.Method``

    Fingerprints, all rendered from the AST through ``go/printer`` so gofmt-able
    differences, comments and redundant parens are not changes:

      * ``func``/method: the keyword, the receiver (pointer-ness and base type
        with its type parameters), the name, the type parameter list (name and
        constraint), the parameter list (name, type, and ``...`` variadic
        marker) and the result list (names when named, types always).
      * ``struct`` type: the type parameter list, then every field in
        DECLARATION ORDER — name, type, **struct tag verbatim**, and whether
        the field is embedded. Embed-ness is marked as ``embedded:T``, with the
        colon load-bearing: a marker a field NAME can spell is not a marker, and
        ``embedded`` is a legal field name.
      * ``interface`` type: the type parameter list, its embedded interfaces,
        and its method names. **A top-level interface DEFINITION carries names
        only**, because each method is also its own ``Iface.Method`` symbol and
        repeating the signature would report one change twice — this mirrors the
        Python side, whose class fingerprint carries fields while methods are
        separate symbols. **Every other interface literal carries the full
        signature of each method**: an alias' right-hand side, a struct field,
        parameter, result or constraint type, and a literal embedded in another
        interface have no sub-symbols behind them, so a name-only element list
        would store the signature nowhere and retyping a method of such a
        literal — source-breaking for every implementation — would be reported
        as no change. The signature is rendered by the same normalising path as
        every parameter list, so grouping and line breaks are still spelling.
      * any other type declaration: whether it is an alias (``type A = B``) or a
        definition (``type A B``) — the ``=`` is semantic, not spelling — and
        the right-hand type expression.

    **Struct tags are part of the fingerprint, and this is not a detail.** A
    changed ``json:"amount"`` is a wire-contract change: it silently rewrites
    every payload the type serialises and every payload it accepts, with no
    compile error anywhere. It is the single most consequential edit a body
    agent can make to a Go type without touching a function signature, and a
    comparator that ignored tags would protect the shape of the contract while
    leaving its meaning writable. Tags are compared as the raw literal
    including quoting, because a tag is a string the runtime parses and the gate
    is not in the business of deciding which of two spellings a reflection
    library agrees with.

    IN SCOPE, INCLUDING UNEXPORTED
    ------------------------------
    **Every top-level declaration, exported or not**, and **every struct field,
    exported or not, in declaration order.** Both are parity decisions with the
    Python side and both are deliberate:

      * ``_scaffolded_signatures`` collects underscore-prefixed module symbols,
        so P2 can seal a private helper and P3 may not then change it. Go's
        equivalent is real and common: an in-package ``_test.go`` seal binds to
        unexported identifiers, so an unexported func IS sealable contract, and
        an export-only comparator would leave every one of those seals
        unenforced.
      * ``_class_fingerprint`` carries every annotated class field in order,
        with the explicit rationale that "frozen dataclass fields ARE the
        contract in this codebase, so a reordered or retyped field is a
        signature change". A Go struct is the same object. So inserting a field
        into a scaffolded struct — even an unexported one — IS a change here.

    That second one is the strictest thing in this contract and the seal author
    should treat it as ruled, not as an accident: **adding a field to a
    scaffolded struct is a signature change, adding a top-level declaration is
    not.** The asymmetry is inherited whole from Python, where an added symbol
    is explicitly allowed ("a body may add private helpers") and an added class
    field is explicitly not. A body agent that needs new state puts it in a new
    type, or gets a P4 ruling.

    DELIBERATELY EXCLUDED, each with its reason
    -------------------------------------------
      * **Function bodies, and anything declared inside one.** Body work is the
        thing this gate exists to permit.
      * **Doc comments and any other comment.** Parity: "a docstring edit → not
        a change; the docstring is P1's contract and P3 may extend it, and an
        over-strict rule here would make honest work fail."
      * **The receiver's variable NAME** (``func (s *Svc)`` ≡ ``func (svc
        *Svc)``). The one place this contract does NOT take parity with Python,
        which fingerprints ``self`` like any other parameter. The reason is that
        the analogy breaks: Python's ``self`` is a real entry in the parameter
        list and an unbound call can pass it positionally, so it is callable
        surface; a Go receiver cannot be named at any call site, does not
        participate in interface satisfaction, and is scoped to the body — it is
        the closest thing Go has to a local variable. Parameter names, by
        contrast, ARE fingerprinted: they are the scaffold's declared shape and
        they appear in godoc, and the Python side fingerprints them.
      * **Package-level ``const`` and ``var``.** Parity: the Python comparator
        reads ``def`` and ``class`` and ignores module-level assignments. This
        is a known gap and worth naming as one — an exported ``const
        MaxRetries`` is real API — but closing it on the Go side alone would
        make the two languages mean different things by "signature", and this
        unit's whole subject is two definitions of one thing drifting.
      * **Imports and import aliases as declarations.** But note the
        consequence, which is a real false positive: type expressions are
        compared AS WRITTEN, so renaming an import alias rewrites every
        ``pkg.T`` that mentions it and every one of those reads as a change.
        Python has the identical property (annotations are compared as
        ``ast.unparse`` source, so a renamed import changes them all). Same
        class of noise, same remedy — it is visible, it names the symbols, and
        it is a VIOLATION rather than a silent pass.
      * **Type identity and resolution.** The helper parses one file with
        ``go/parser``, without ``go/types`` and without the rest of the package,
        so ``T`` and ``mypkg.T`` are different fingerprints even when they
        denote the same type, and a type alias is not followed. Syntactic, like
        the Python side, and for the same reason: resolution needs a buildable
        package, and the revisions being compared are two blobs out of git that
        may not build in isolation.
      * **Build constraints.** ``//go:build`` lines are comments; a file
        excluded from the current platform is fingerprinted like any other. That
        is the conservative answer — the gate reads what the branch wrote, not
        what one GOOS would compile.
      * **``//go:generate`` output and vendored trees.** No special case. If
        they must be exempt, that is the path gate's job
        (:data:`DEFAULT_ROLE_RULES` already denies ``**/generated/**``), not the
        comparator's — one notion of "which paths are protected", in the table
        that owns it.

    FAILURE
    -------
    Raises :class:`SourceUnparseable` when the helper reports a parse error, and
    :class:`ComparatorUnavailable` carrying the named :class:`ComparatorFault`
    for every environment failure. It may return an empty mapping ONLY for a
    file that genuinely declares nothing (``package main`` and no more); it may
    never return one to signal a failure. See
    :func:`signature_status_for_fault` for what each of those is worth to the
    BODIES verdict.

    Not implemented, and not enrolled: see :data:`GO_SUPPORT`.
    """

    def fingerprints(self, path: str, text: str) -> dict[str, str]:
        """One revision of one Go file → symbol → fingerprint.

        The steps, so the seal author knows which fault belongs to which:
        probe the toolchain (:attr:`ComparatorFault.TOOLCHAIN_MISSING`,
        :attr:`ComparatorFault.TOOLCHAIN_UNUSABLE`), resolve the helper
        (:attr:`ComparatorFault.HELPER_MISSING` — :func:`go_helper_source_dir`),
        run it with :func:`encode_go_helper_request` on stdin under
        :data:`_HELPER_TIMEOUT_SECONDS`
        (:attr:`ComparatorFault.HELPER_TIMEOUT`,
        :attr:`ComparatorFault.HELPER_FAILED`), decode stdout
        (:attr:`ComparatorFault.HELPER_OUTPUT_INVALID` —
        :func:`decode_go_helper_response`), and finally turn a
        ``parse_error`` document into :class:`SourceUnparseable`.

        Every one of those is terminal for this file: there is no retry, no
        fallback comparator and no degraded mode. A fallback is how a gate ends
        up reporting a pass it did not earn.

        **P3: the first three steps happen once per PROCESS, not once per
        file.** The probe and the compile are cached in
        :data:`_GO_HELPER_PREPARED`; only the run and the decode are per-file.
        That is a cost decision with a measurement behind it — see that
        global — and it changes nothing the contract promises: the helper still
        receives one file per invocation on a fresh process's stdin, and the
        timeout is still per-file.
        """
        response = decode_go_helper_response(
            _run_go_helper(_go_helper_binary(), path, text)
        )
        if response.parse_error is not None:
            # A fact about the FILE, established by working apparatus — so it
            # is not a fault, and `compare_signatures` reports it as
            # UNCHECKED_UNPARSEABLE rather than as a broken machine.
            raise SourceUnparseable(path, f"go: {response.parse_error}")
        # Declaration order, which the helper guarantees and dicts preserve.
        return {
            symbol.symbol: symbol.fingerprint for symbol in response.symbols
        }


@dataclass(frozen=True)
class GoSignatureEditRuling:
    """One ruled edit: does it change a Go signature, or is it body work?

    A row of :data:`GO_SIGNATURE_EDIT_RULINGS`. The point of the dataclass is
    that a ruling stops being prose in a docstring — which the last three units
    each had a seal author derive a guess from — and becomes something P2 can
    assert against and P3 can implement to.

    ``before``/``after`` are complete, minimal Go files. ``is_a_change`` is the
    ruled answer. ``python_analogue`` carries the same edit transliterated to
    Python when the edit HAS an analogue, so the row can be checked against a
    live comparator today, years before the Go one exists; it is None for the
    rows where Go and Python genuinely differ, and that None is itself the
    claim that they differ.
    """

    name: str
    before: str
    after: str
    is_a_change: bool
    rationale: str
    python_analogue: tuple[str, str] | None = None


#: **P4 ruling, 2026-08-09: Go parameter NAMES are part of the fingerprint.**
#: The scaffold flagged this as the first question to send to P4 and it is
#: settled here, with the boundary rows that make the criterion checkable.
#:
#: THE SCAFFOLD'S TWO ARGUMENTS ARE BOTH WEAKER THAN THEY LOOK, and the ruling
#: does not rest on either.
#:
#:   * *For*: "parameter names are the scaffold's declared shape, they appear in
#:     godoc, and the Python side fingerprints them." Godoc is documentation,
#:     not contract. And bare parity is the argument this whole unit exists to
#:     distrust — :class:`GoSignatureFingerprinter` already BREAKS parity for
#:     the receiver name, so "Python does it" cannot be doing the work.
#:   * *Against*: "it is stricter than Go's own compatibility rules and will
#:     flag a rename that breaks no caller." True, and correct as far as it
#:     goes.
#:
#: WORSE, the scaffold is internally inconsistent. It excludes the receiver name
#: on the ground that a receiver "cannot be named at any call site" — a
#: CALLABLE-SURFACE test — and then includes parameter names two sentences
#: later, when a Go parameter cannot be named at a call site either. Applied
#: honestly, the scaffold's own stated criterion excludes parameter names. That
#: criterion is the one being replaced.
#:
#: THE CRITERION THIS RULING USES: **a fingerprint must distinguish two
#: declarations that mean different things to a caller.** Not "can the caller
#: type this name" — "can the caller be silently wrong if this changes".
#:
#: What forces the answer is the SAME-TYPE REORDER. ``func Move(src, dst
#: string)`` becoming ``func Move(dst, src string)`` is type-identical: a
#: fingerprint built from types alone sees nothing, every existing call site
#: compiles, and every one of them now means the opposite of what it says.
#: That is the struct-tag defect exactly — a semantic inversion with no compile
#: error anywhere — and names are the only thing that catches it.
#:
#: AND THE TWO CANNOT BE SEPARATED. ``(src, dst)`` -> ``(dst, src)`` is a
#: reorder and is equally two renames; a syntactic, single-file, no-``go/types``
#: comparator cannot tell them apart, because there is no fact in the text that
#: distinguishes them. So "catch reorders but not renames" is not a stricter
#: rule this unit declined to write — it is not implementable at all. The choice
#: is binary, and the rename false positive is the PRICE of the reorder catch,
#: not a design goal.
#:
#: WHY THAT PRICE IS ACCEPTABLE, given the against-argument is real:
#:
#:   * the severities are not comparable. A false VIOLATION is visible, names
#:     the symbol, and costs one round trip or one ruling — the same escape
#:     hatch the added-struct-field rule already relies on. A missed same-type
#:     reorder is silent, ships, and is the SMG-3966 shape.
#:   * this contract ALREADY accepts a strictly noisier false positive without
#:     complaint: renaming an import alias rewrites every ``pkg.T`` that
#:     mentions it and every one reads as a change. If that noise is tolerable,
#:     a parameter rename — one symbol, one line — is.
#:   * the noise is bounded by what a body agent is FOR. It fills bodies against
#:     a signature it was handed. Renaming a parameter of a function someone
#:     else declared is not the common case; it is a body agent editing the
#:     declaration, which is the thing being gated.
#:
#: THE RECEIVER EXCEPTION SURVIVES, and that is the check on the criterion
#: rather than a carve-out bolted onto it: a receiver cannot be silently swapped
#: with anything, because there is exactly one and it has no position. It
#: carries no ordering information, so renaming it cannot make a caller wrong.
#: Same criterion, opposite answer, which is how you tell a criterion from a
#: preference.
#:
#: The table is the acceptance criterion for :class:`GoSignatureFingerprinter`
#: (P3) and the thing P2 seals against. Rows with a ``python_analogue`` are
#: checked against the live Python comparator TODAY — see
#: ``tests/test_role_protocol_faults.py`` — so the parity claim is measured
#: rather than asserted, and the receiver row's None is the recorded claim that
#: Go and Python differ there on purpose.
GO_SIGNATURE_EDIT_RULINGS: tuple[GoSignatureEditRuling, ...] = (
    GoSignatureEditRuling(
        name="parameter renamed",
        before="package m\n\nfunc Move(src, dst string) error { return nil }\n",
        after="package m\n\nfunc Move(source, target string) error { return nil }\n",
        is_a_change=True,
        rationale=(
            "THE RULING. Indistinguishable, in a syntactic single-file "
            "comparison, from the same-type reorder below — so it is ruled "
            "the same way. Breaks no caller on its own; that is the accepted "
            "price of the row below, not an oversight"
        ),
        python_analogue=(
            "def move(src, dst):\n    pass\n",
            "def move(source, target):\n    pass\n",
        ),
    ),
    GoSignatureEditRuling(
        name="same-type parameters reordered",
        before="package m\n\nfunc Move(src, dst string) error { return nil }\n",
        after="package m\n\nfunc Move(dst, src string) error { return nil }\n",
        is_a_change=True,
        rationale=(
            "THE REASON FOR THE RULING. Type-identical, so a names-free "
            "fingerprint reports no change; every existing call site still "
            "compiles and every one now means the opposite. A silent semantic "
            "inversion with no compile error — the struct-tag defect in the "
            "parameter list"
        ),
        python_analogue=(
            "def move(src, dst):\n    pass\n",
            "def move(dst, src):\n    pass\n",
        ),
    ),
    GoSignatureEditRuling(
        name="receiver variable renamed",
        before="package m\n\ntype S struct{}\n\nfunc (s *S) Do() {}\n",
        after="package m\n\ntype S struct{}\n\nfunc (svc *S) Do() {}\n",
        is_a_change=False,
        rationale=(
            "THE BOUNDARY, and the check on the criterion. There is exactly "
            "one receiver and it has no position, so it carries no ordering "
            "information and no caller can be made silently wrong by renaming "
            "it. Same criterion as the two rows above, opposite answer. NO "
            "python_analogue: Python fingerprints `self` like any other "
            "parameter (measured), and this row is the recorded claim that the "
            "two languages differ here deliberately"
        ),
        python_analogue=None,
    ),
    GoSignatureEditRuling(
        name="body rewritten, declaration untouched",
        before="package m\n\nfunc Move(src, dst string) error { return nil }\n",
        after=(
            "package m\n\nfunc Move(src, dst string) error {\n"
            "\t_ = src\n\t_ = dst\n\treturn nil\n}\n"
        ),
        is_a_change=False,
        rationale=(
            "THE CONTROL, and the row without which this table proves "
            "nothing. Every other row here is a change, so a comparator that "
            "answered 'changed' to everything would satisfy them all. This is "
            "the work the gate EXISTS to permit, and it must stay silent"
        ),
        python_analogue=(
            "def move(src, dst):\n    pass\n",
            "def move(src, dst):\n    del src, dst\n    return None\n",
        ),
    ),
)


#: Python's row, and the whole of what this gate reads today.
PYTHON_SUPPORT = LanguageSupport(
    language=Language.PYTHON,
    extensions=(".py",),
    fingerprinter=PythonSignatureFingerprinter(),
)

#: Go's row, complete and **deliberately not enrolled** — it is not in
#: :data:`COMPARATORS`, so :func:`support_for_path` never returns it and a
#: ``.go`` path is answered exactly as it was before this unit
#: (UNCHECKED_UNSUPPORTED_LANGUAGE, promoted to UNCHECKED_NO_SUPPORTED_FILE on a
#: diff with nothing else in it, CLEAN on BODIES).
#:
#: Enrolment is a two-line MOVE — adding this row to :data:`COMPARATORS` **and
#: removing it from** :data:`PENDING_COMPARATORS` — and it may not happen until
#: all four of these hold. They are listed as a checklist because three of them
#: are somebody else's commit.
#:
#: **This paragraph said "ONE edit — adding this row to COMPARATORS" and that
#: was wrong; corrected by P4 on 2026-08-10 after measuring it.** Doing only the
#: documented edit leaves the row in BOTH tuples,
#: :func:`validate_registry` raises ``RoleProtocolError`` ("language 'go' has
#: two comparator rows") at import, and the entire suite fails collection. The
#: move is still one commit and one reviewable hunk; it is not one line.
#: :func:`test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees`
#: (``tests/test_go_comparator.py``) is the seal that states the invariant this
#: correction rests on:
#:
#:   1. :class:`GoSignatureFingerprinter` is implemented (P3), to the rulings
#:      in :data:`GO_SIGNATURE_EDIT_RULINGS` — which is the acceptance
#:      criterion, not a suggestion, and settles the parameter-name question
#:      the scaffold sent to P4. **DONE**, P3 2026-08-09. All four ruled edits
#:      are produced by the live comparator, and the helper was soaked over
#:      6,035 real ``.go`` files (GOROOT/src, 68,809 symbols) with no fault.
#:
#:      Two ordinary Go constructs had to be excluded to get there, both
#:      because a file may legally hold SEVERAL of each and duplicate symbol
#:      keys are :attr:`ComparatorFault.HELPER_OUTPUT_INVALID` at the caller —
#:      so emitting them would have blamed the machine for generated code.
#:      Neither is callable surface: ``func _()``/``type _`` cannot be referred
#:      to at all, and ``func init`` cannot either and has a signature the spec
#:      fixes, so its fingerprint could never report a change. See ``isBlank``
#:      and ``isPackageInit`` in the helper. A METHOD named ``init`` is kept.
#:
#:      **What is still NOT sealed, and it is the gap worth naming**
#:      (measured 2026-08-09): nothing in ``tests/`` exercises this
#:      implementation, before or after enrolment. Dropping parameter names
#:      from the Go fingerprint — the exact defect
#:      :data:`GO_SIGNATURE_EDIT_RULINGS` exists to forbid — leaves the suite
#:      at its usual 1630 passed unenrolled, and enrolled it produces the same
#:      eight failures as the unmutated tree and not one more. The eight seals
#:      in item 4 pin Go as UNREADABLE; none of them pins it as read
#:      CORRECTLY, and enrolment alone does not buy that. Seals against the
#:      rulings table are a P2 job that has not happened.
#:   2. ``SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE`` exists and is
#:      in both status sets, with the seal amendment that lets it exist (P4 —
#:      see :func:`signature_status_for_fault`). Enrolling first would make a
#:      missing ``go`` binary raise ``NotImplementedError`` out of
#:      :func:`check_branch`, which is documented never to raise. **DONE**, P4
#:      2026-08-09, and it also acquired a RANK, which the scaffold did not
#:      foresee because it predates the ranked fold: without one,
#:      :func:`_worst_signature_status` raises on it and every faulted diff is
#:      UNDETERMINED-by-exception rather than by classification.
#:   3. :data:`FLOOR_GLOBS` covers the helper source and
#:      ``scripts/check_body_branch.sh`` reads it from the protected base (P4 —
#:      see :func:`go_helper_source_dir`). **DONE**, P4 2026-08-09. The script
#:      needed no change: the helper lives under the ``src/`` prefix the
#:      base-pinned block already copies wholesale, which was MEASURED and then
#:      sealed, because it is true by location and a later move to ``tools/``
#:      would silently undo it.
#:   4. The seals that pin Go as unreadable are amended by P4, because
#:      enrolment reddens every one of them and P3 may not touch a seal.
#:      **DONE**, P4 2026-08-10. Every one of them is re-languaged, none is
#:      deleted, and enrolment now reddens NOTHING: measured by moving the row
#:      in a ``cp -a`` clone of this tree, clearing ``__pycache__`` and running
#:      the whole suite — 1989 collected, 13 skipped, 0 failed, the same as
#:      unenrolled. **This item does not say the comparator is correct** — see
#:      the gap named in item 1 and the seals in ``tests/test_go_comparator.py``
#:      that close it.
#:
#:      **The count has now been wrong four times: SEVEN, then EIGHT, and it is
#:      NINE.** The scaffold said seven. P4 measured eight on 2026-08-09 and
#:      added ``test_a_skipped_non_python_file_is_not_reported_as_a_checked_signature``
#:      (``tests/test_role_protocol_inputs.py``). P4 measured NINE on
#:      2026-08-10; the ninth is
#:      ``tests/test_go_comparator.py::test_go_is_still_not_enrolled``, which
#:      did not exist when either earlier count was taken. It is not a
#:      stale-probe seal — it is a deliberate tripwire asserting this row is
#:      unenrolled — and it is replaced by
#:      ``test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees``,
#:      which pins the registry/lookup relation instead of one transient state
#:      of it. A checklist that undercounts is worse than none, because the
#:      unit that works through it stops when the named ones are green; the
#:      lesson that keeps repeating is that the only trustworthy count is one
#:      taken by enrolling in a clone THAT DAY.
#:
#:      **The two that are NOT this class stay green, and must not be
#:      amended.** ``test_no_role_gets_a_clean_verdict_for_editing_the_gate``
#:      and
#:      ``test_the_gate_is_refused_under_the_policy_the_gate_actually_runs_with``
#:      (``tests/test_role_protocol_provenance.py``), whose probes include the
#:      Go helper's own path since it joined :data:`FLOOR_GLOBS`. They reddened
#:      only while an UNIMPLEMENTED :class:`GoSignatureFingerprinter` raised
#:      ``NotImplementedError`` out of :func:`check_branch` — item 1 of this
#:      list, not item 4. Item 1 is done, and both were re-measured GREEN with
#:      the row enrolled on 2026-08-10. They were not touched.
#:
#:      What each probe became, and why those languages. In
#:      ``tests/test_role_protocol_diff.py``:
#:      ``test_an_unchecked_comparison_is_named_never_reported_as_unchanged``
#:      (``cmd/classify/main.go`` -> ``db/migrate/001_bay.sql``, and its
#:      ``web/app.ts`` row -> ``svc/Handler.java``) and
#:      ``test_every_signature_check_status_is_reachable`` (its ``m.go`` probe
#:      and its Go-only BODIES probe both -> ``db/migrate/001_bay.sql``; those
#:      two are the only producers of UNCHECKED_UNSUPPORTED_LANGUAGE and
#:      UNCHECKED_NO_SUPPORTED_FILE, so deleting them would have destroyed a
#:      closed-set seal. Its faulting-row probe stays ``.go``: that row
#:      REPLACES the registry and :class:`Language` is a closed two-member
#:      set). In ``tests/test_role_protocol_inputs.py``:
#:      ``test_a_skipped_non_python_file_is_not_reported_as_a_checked_signature``,
#:      ``test_a_bodies_diff_this_gate_cannot_read_is_clean_and_names_what_it_missed``,
#:      ``test_cannot_read_this_language_and_no_duty_here_stay_two_different_states``,
#:      ``test_the_paths_named_unread_are_the_skipped_ones_not_the_whole_diff``,
#:      ``test_the_per_file_comparator_names_the_file_it_could_not_read`` and
#:      ``test_the_ci_face_clears_a_wholly_unreadable_branch_and_names_the_file_it_could_not_read``
#:      (RENAMED from ``...clears_a_go_only_branch...``: the name carried the
#:      probe rather than the property).
#:
#:      Those seals were CORRECT and state the ruled behaviour; what changed
#:      underneath them is which languages are unreadable, so each Go probe is
#:      REPLACED by one in a language this gate still cannot read — SQL (781
#:      files in the target repo) and Java (316), with no comparator planned
#:      and no scaffolded-stub discipline in a migration or a POJO to preserve
#:      — never deleted. ``.ts`` probes sitting in the same seals went too:
#:      TypeScript is 996 files and the obvious NEXT enrolment, so leaving them
#:      would have booked this same job a second time. A seal deleted because
#:      the fact it rested on moved is a seal the next unit does not have.
#:
#: The row exists now, unenrolled, rather than being written by P3, because the
#: extension belongs in the table that owns extensions and because a reader can
#: check what this build covers by reading one place. :func:`validate_registry`
#: checks the pending rows against the enrolled ones, so a pending row cannot
#: collide with a live one and cannot be enrolled twice.
GO_SUPPORT = LanguageSupport(
    language=Language.GO,
    extensions=(".go",),
    fingerprinter=GoSignatureFingerprinter(),
)


# --------------------------------------------------------------------------- #
# Unit D4 — TypeScript, the third entry. **P1 SCAFFOLD. Contracts only.**
#
# Everything below is a typed signature plus a normative docstring. Two things
# have bodies and both are named as such at their definitions:
# :func:`ts_symbol_key` (a seal cannot express the key-collision property
# without it) and :func:`ts_parser_home` (it IS this unit's answer to the
# central design problem, and an answer left as ``NotImplementedError`` is a
# note, not an answer). Everything else raises.
#
# THE CENTRAL PROBLEM: THE ONLY TYPESCRIPT PARSER ON THIS MACHINE LIVES INSIDE
# THE TREE UNDER JUDGEMENT
# ---------------------------------------------------------------------------
# Measured 2026-08-10::
#
#     require.resolve('typescript', {paths:['<target repo>']})
#       -> <target repo>/node_modules/typescript/lib/typescript.js   (5.9.3)
#     require.resolve('typescript', {paths:['<dispatcher>']})  -> MODULE_NOT_FOUND
#     require.resolve('typescript')                            -> MODULE_NOT_FOUND
#     npm root -g -> /usr/local/lib/node_modules  (no typescript in it)
#
# Go does not have this problem and the asymmetry is the whole of this unit's
# difficulty. Go's parser is ``go/ast``, which ships inside a ``go`` toolchain
# that lives outside every repository; the branch cannot reach it. TypeScript's
# parser is an npm package, and npm's canonical home is ``node_modules`` in the
# repository root — the directory the branch owns. A comparator that called
# Node's ordinary module resolution from anywhere inside the judged checkout
# would let a bodies branch supply the program that decides what a TypeScript
# signature is. That is *a gate writable by what it gates*, the class this
# project has closed at real cost twice (``FLOOR_GLOBS = ()`` appended to the
# branch's own ``role_protocol.py``, 2026-08-08; the Go helper subtree,
# 2026-08-09), and here it would be designed in from the start rather than
# discovered.
#
# THE RULE THIS UNIT ADOPTS, and it is one sentence:
#
#   **The parser's location is a pure function of the DISPATCHER's own
#   installed location, and of nothing else.**
#
# ``Path(__file__).parent`` and nothing else — not the CWD, not ``NODE_PATH``,
# not an ancestor-directory walk, not ``npm root -g``, not an environment
# variable, not ``.npmrc``, not ``tsconfig.json``. That is exactly the rule
# :func:`go_helper_source_dir` already states for the Go helper's source, and
# the reason to state it as a rule rather than as a habit is that it is the
# only predicate under which "can the branch write this?" has an answer that
# does not depend on where the gate happens to be run from.
#
# The consequence is that **no parser is configured today**, because nothing is
# vendored: :func:`ts_parser_home` raises
# :attr:`ComparatorFault.HELPER_MISSING` on every call, on every machine. That
# is the honest first answer and it is deliberately the shipped one. See
# :data:`TYPESCRIPT_SUPPORT` for the enrolment checklist that changes it.
#
# WHAT WAS REJECTED, AND WHY
# --------------------------
#   * **Resolve ``typescript`` from the target repo** (or from the CWD, or by
#     letting Node walk up from the source file's directory). Rejected: it is
#     the defect stated above in its purest form. A bodies branch that runs
#     ``npm i typescript@my-fork`` — or that edits one function inside the
#     existing ``node_modules/typescript/lib/typescript.js`` to drop a modifier
#     — gets every TypeScript file in its diff reported as unchanged. Note that
#     ``node_modules/`` is **gitignored** in the target, so the branch cannot
#     *commit* the poisoned parser and a diff-based gate would see nothing at
#     all; the gate would load it from disk anyway. A hole that leaves no trace
#     in the diff is worse than one that leaves a reviewable hunk.
#   * **``npx typescript`` at gate time.** Rejected on three counts. It fetches
#     from the network *during a judgement*, so whatever the registry serves
#     that minute becomes the definition of a TypeScript signature — the same
#     objection ``GOPROXY=off`` already encodes for Go. It caches into
#     ``~/.npm/_npx``, a mutable path outside :data:`FLOOR_GLOBS` whose bytes
#     decide a verdict, which is the objection :data:`_GO_HELPER_PREPARED`
#     already records against caching the built Go binary under ``/tmp``. And
#     an offline or air-gapped CI image would fail into a fault on every run,
#     making the gate's availability a function of the network.
#   * **A globally installed ``typescript``** (``npm i -g``). Not rejected on
#     the writability test — ``/usr/local/lib/node_modules`` is outside every
#     repository and passes it exactly as ``go`` does — but rejected because
#     "global" is not a location the dispatcher can name. ``npm root -g`` is
#     resolved through npm's config, and npm reads a **project-local
#     ``.npmrc``** from the CWD, so the branch influences which directory
#     "global" means. There is no probe that repairs that: the answer would be
#     trustworthy on the machine you tested and not on the next one. This is
#     the closest of the rejected options and a later ruling may take it with a
#     hard-coded, operator-owned absolute path; it is not taken here because a
#     path this module cannot derive is a path this module cannot defend.
#   * **An environment variable naming a trusted parser**
#     (``CLAUDE_DISPATCHER_TS_PARSER=/opt/...``). Rejected, and this is the
#     rejection worth arguing because it is the one that looks most reasonable.
#     Anything that redirects the gate's parser is part of the machinery that
#     computes the verdict, and this project's answer to "who may change the
#     machinery" is :data:`FLOOR_GLOBS` — a table of PATHS. **An environment
#     variable cannot be put on the floor.** It is not a path, it has no diff,
#     no base revision to pin it against, and ``scripts/check_body_branch.sh``
#     has nothing to read it from. Accepting one would move the trust boundary
#     from a reviewable file to the ambient process environment, where the
#     protocol has no vocabulary at all.
#   * **A dependency-free TypeScript parser written in the helper, or in
#     Python.** Rejected by :class:`GoSignatureFingerprinter`'s own ruling —
#     "one parser, not two" — applied to a language where it is strictly more
#     forceful. Go's grammar gained generics once in a decade; TypeScript's
#     gained ``satisfies``, ``const`` type parameters, ``accessor``, ``out``/
#     ``in`` variance annotations and a whole second decorator syntax inside
#     three years. A hand-rolled reader silently drops what it does not know,
#     and a dropped MODIFIER (``readonly``, ``?``, ``export``) reads as no
#     change — a silent pass. The measured argument is in the Go docstring and
#     it transfers unchanged.
#   * **Adding a seventh :class:`ComparatorFault`** — ``PARSER_UNTRUSTED``,
#     which :func:`signature_status_for_fault` explicitly predicts "whoever
#     writes the TypeScript comparator" will add. NOT added, and the reason is
#     not timidity: under the rule above, "the parser I found is inside the
#     tree under judgement" is **unreachable by construction**, because the
#     resolution never looks there. An enum member for an unreachable state is
#     the vacuity this codebase keeps paying for. (It would also have reddened
#     ``tests/test_role_protocol_faults.py``'s hard ``len(list(ComparatorFault))
#     == 6``, which P1 may not amend — but that is why it would have had to be
#     a P4 commit, not why it should not exist.) The six existing faults cover
#     every state this design can reach; the mapping is in
#     :class:`TypeScriptSignatureFingerprinter`.
#
# THE SELF-JUDGEMENT CASE, which is where the rule alone is not enough
# --------------------------------------------------------------------
# When this repository judges ITSELF, ``Path(__file__).parent`` IS inside the
# tree under judgement, so "dispatcher-owned" and "branch-writable" stop being
# opposites. This is not a new hole — it is precisely the one
# :func:`go_helper_source_dir` flagged and that P4 closed for Go on 2026-08-09
# by putting the helper subtree on :data:`FLOOR_GLOBS`. The same close is
# required here and it is a precondition of enrolment, not of this commit:
# ``**/src/claude_dispatcher/ts_signature_fingerprint/**`` must be on the floor
# BEFORE anything is vendored into it, for the reason the Go entry records —
# "a floor that arrives with enrolment is a floor that was absent for every
# commit that built the thing it protects".
#
# A SECOND, SMALLER INSTANCE OF THE SAME PROBLEM: ``tsconfig.json``
# ------------------------------------------------------------------
# The obvious way to parse a TypeScript file is to build a ``ts.Program`` from
# the repository's ``tsconfig.json``. That file is in the tree under judgement
# and it chooses ``jsx``, ``target``, ``experimentalDecorators``, path mappings
# and which files exist at all — so a branch that edits it edits how its own
# files are read. It is never consulted. Parse options are FIXED by this
# module (see :class:`TypeScriptSignatureFingerprinter`), which also keeps the
# comparator single-file and syntactic, exactly as the Go one is and for the
# same stated reason: the two revisions being compared are blobs out of git
# that may not resolve in isolation.
#
# WAS THIS ONE ROW? NO, AND HERE IS THE LIST
# ------------------------------------------
# The registry's claim is that "adding TypeScript is one new row in
# :data:`COMPARATORS` plus one class; no dispatch site changes". The DISPATCH
# half of that is true and was verified: :func:`support_for_path`,
# :func:`_supported_language_refusal`, :func:`compare_signatures` and
# :func:`check_branch` needed no edit, and the one ``endswith`` in this module
# is still the one in :func:`support_for_path`. What the claim omits, and what
# every future language will pay again:
#
#   * a :class:`Language` member and an amendment to that enum's docstring,
#     which asserted TypeScript's absence as a design property;
#   * an amendment to this section's own header, which asserted that no table
#     here names a ``.ts`` extension;
#   * a helper subtree under the package, a :data:`FLOOR_GLOBS` entry for it
#     (P4-only, because the floor's row table is a seal), and a
#     ``pyproject.toml`` package-data glob;
#   * a **third copy of the helper wire protocol** — request encoder, response
#     decoder, request/response dataclasses. :func:`decode_go_helper_response`
#     is ~110 lines of language-independent validation whose only Go-shaped
#     element is a schema string. This is the two-copies problem arriving in
#     the plumbing rather than in the dispatch, and it is named with its
#     required fix at :func:`decode_ts_helper_response`.
#
# The honest summary is that the registry made the *language question* one row
# and left the *toolchain question* unfactored. A fourth language should extract
# the subprocess-helper machinery before adding anything else.
#
# WHAT THIS DESIGN CANNOT DO
# --------------------------
# Stated here rather than left to be found, and each is a false NEGATIVE unless
# marked otherwise.
#
#   * **Cross-file declaration merging is invisible, and it is a real bypass.**
#     The gate compares one file at a time. TypeScript lets a second file widen
#     an existing interface (``interface Bet { newField: string }`` in any file
#     that imports it into scope) or augment another module outright (``declare
#     module './bet' { … }``). A NEW file has no base revision, so every symbol
#     in it is an ADDED symbol, and an added symbol is not a change. A body
#     agent can therefore widen a sealed type without editing the file it was
#     sealed in. Go has a weaker version of this (a new file adding methods to
#     an existing type); TypeScript's is a first-class language feature and is
#     the single largest hole in this contract. Closing it needs a whole-diff
#     comparison rather than a per-file one, which is a change to
#     :func:`_compare_branch_signatures`, not to a comparator.
#   * **Inferred types are not read.** ``export const config = { retries: 3 }``
#     has a public type this comparator cannot see; see the ruled row in
#     :data:`TS_SIGNATURE_EDIT_RULINGS`. Inference needs a checker and a
#     resolvable program, and a resolvable program needs the branch's own
#     ``tsconfig.json``.
#   * **No type identity.** Two different ``Foo``s fingerprint alike; an alias
#     is not followed; a barrel file's ``export * from './v2'`` swapped for
#     ``'./v1'`` changes the meaning of every downstream annotation and the
#     downstream files' fingerprints do not move.
#   * **``.mts``, ``.cts`` and all JavaScript are uncovered**, and ``.mts`` is
#     not reached by the ``.ts`` entry because matching is a suffix match.
#   * **Uppercase extensions are uncovered** (``FOO.TS``), inherited from
#     :class:`LanguageSupport`'s case-sensitive matching rather than chosen.
#   * **FALSE POSITIVES, accepted deliberately**: a renamed import alias moves
#     every annotation that mentions it; a reordered union or intersection
#     moves the type that contains it; a renamed parameter or type parameter is
#     a change even when no caller breaks; an edit to a class method is
#     reported twice, once as the member and once through the class; and
#     ADDING a class method — including a `private` or `#` one that breaks no
#     external caller — is a change, because the class fingerprint carries its
#     members in full (P4 adjudication 2026-08-10, at
#     :class:`TypeScriptSignatureFingerprinter`). Each is argued where it is
#     ruled.
#
# WHERE THIS DESIGN IS SILENT, named so nobody reads silence as a ruling:
# ``as const`` assertions outside a top-level binding; ``abstract`` constructor
# types; ``unique symbol``; ``asserts this is T`` predicates on class methods;
# the ``T[]`` / ``Array<T>`` and ``A|B`` / ``B|A`` normalisation pairs (ruled
# NOT normalised, but the reasoning is thinner than the rest); triple-slash
# directives (``/// <reference …>``), which are comments to the parser and
# module graph edges to the compiler; and whether a ``.d.ts`` should be held to
# a stricter standard than a ``.ts`` given that all of it is signature.
# --------------------------------------------------------------------------- #


#: The TS helper's protocol version, on every request and every response.
#: Same discipline as :data:`GO_HELPER_SCHEMA` and same reason: a fingerprint
#: is compared for equality across two invocations, so a grammar change would
#: read as every symbol having been rewritten. Bump it whenever the fingerprint
#: GRAMMAR changes — which, for this comparator, includes changing the vendored
#: parser's MAJOR/MINOR version, because the rendering is derived from the
#: parser's AST and TypeScript adds node shapes in minor releases.
TS_HELPER_SCHEMA = "claude-dispatcher/ts-signature-fingerprint/v1"

#: Where the TS helper and its vendored parser live, relative to this package.
#: Inside ``src/claude_dispatcher/`` for the reason
#: :data:`GO_HELPER_PACKAGE_DIR` records — the gate judges branches in OTHER
#: repositories, so its apparatus must travel with the dispatcher.
#:
#: **FLAT, and that is a measured constraint, not a preference.**
#: ``pyproject.toml``'s ``package-data`` glob for the Go helper is
#: ``go_signature_fingerprint/*``; setuptools package-data globs do not recurse,
#: so a vendored parser laid out as ``node_modules/typescript/lib/...`` would be
#: dropped from the wheel and every install would be
#: :attr:`ComparatorFault.HELPER_MISSING`. It happens that this costs nothing:
#: ``typescript/lib/typescript.js`` is a self-contained CommonJS bundle that
#: ``require``s nothing else (measured 2026-08-10 — copied alone into an empty
#: directory it parses ``.ts`` and ``.tsx`` and prints nodes), so the vendored
#: tree is three flat files: the helper, the parser, and the parser's LICENSE.
TS_HELPER_PACKAGE_DIR = "ts_signature_fingerprint"

#: The helper program Node executes. A ``.cjs`` suffix, not ``.js``, so that a
#: ``package.json`` with ``"type": "module"`` anywhere above the install cannot
#: change how the file is interpreted. The extension is the only way to state
#: "this is CommonJS" that no ancestor directory can override.
TS_HELPER_ENTRY_POINT = "main.cjs"

#: The vendored parser, beside the helper and loaded by absolute path.
TS_VENDORED_PARSER = "typescript.js"

#: The parser's license text. Vendoring third-party source into this package is
#: new for this repository and the license travels with it; it is also the
#: cheapest available evidence that what was vendored is what it claims to be.
TS_VENDORED_PARSER_LICENSE = "LICENSE.typescript.txt"

# --------------------------------------------------------------------------- #
# THE PARSER IS A SEPARATELY-VERSIONED ARTIFACT, AND THE DIGEST IS THE ONLY
# THING THAT MAKES THAT SURVIVABLE. Operator ruling, 2026-08-10; landed by the
# D4 vendoring commit.
#
# THE RULING. The 9.1 MB parser is **not a blob in this repository's history**.
# It is a pinned artifact fetched at INSTALL time into the dispatcher-owned
# path :func:`ts_parser_home` names, and the pin is verified **at USE**, not
# merely at fetch. `src/claude_dispatcher/ts_parser_vendor.py` is the fetcher;
# `.gitignore` names the two fetched files so they cannot be committed by
# accident, and names them individually so that ``main.cjs`` — the reviewable
# helper — is still tracked.
#
# WHY "AT USE" IS THE WHOLE OF IT, and not a belt-and-braces extra. The
# section header above rejected ``npx`` partly because it caches into
# ``~/.npm/_npx``, "a mutable path outside :data:`FLOOR_GLOBS` whose bytes
# decide a verdict". An install-time fetch lands bytes in exactly that kind of
# path: outside the repository on a wheel install, gitignored inside it on an
# editable one, and unreadable by ``scripts/check_body_branch.sh`` either way.
# So a fetch-time-only check — a boolean recorded after downloading, or a stamp
# file written beside the artifact — leaves a window in which anyone who can
# write the installed path defeats the entire scheme, and leaves no diff.
# Recomputing the digest from the bytes the process is about to load closes it:
# the mutable path's bytes stop deciding the verdict the moment they stop
# matching the immutable, floored constant. :func:`_ts_prepared_parser` is
# where that happens and it is on the path that produces every TS verdict.
#
# WHY THE EXPECTATION LIVES HERE. A digest read from a manifest beside the
# artifact is not a check, it is a formality: whoever wrote the parser wrote
# the manifest. The expectation has to sit in a file the branch cannot edit
# without a floor violation, and this module is the third entry on
# :data:`FLOOR_GLOBS`. **There is deliberately no SHA256SUMS, no stamp file and
# no lockfile beside the artifact**, and adding one would not be an
# improvement — it would be a second authority, and the weaker of the two would
# be the one an attacker chooses.
#
# WHAT CHANGED FROM THE P4 FLOOR RULING, recorded rather than left to be
# discovered. That ruling described the protection as "a floor violation on the
# BYTES and a second one on the EXPECTATION, in two different files". Under the
# operator's separately-versioned ruling the bytes are never committed, so a
# branch has **no reviewable path to them at all** — it can only tamper the
# on-disk copy, which the floor cannot see and which this digest catches. The
# subtree glob is not thereby vacuous: ``main.cjs`` is a parser input, it IS
# committed, and it is what the glob protects today.
#
# THE FETCH IS NOT PART OF THE TRUST BOUNDARY, which is the pleasant corollary.
# `ts_parser_vendor.py` is NOT on :data:`FLOOR_GLOBS` and does not need to be:
# a branch that rewrote it to fetch a poisoned parser, or to skip its own
# checks entirely, would produce bytes that fail the check below and a gate
# that faults. The fetcher can only decide whether the gate RUNS, never what it
# answers.
#
# THE RESIDUAL WINDOW, recorded and deliberately not closed: the preparation is
# cached once per PROCESS (:data:`_TS_HELPER_PREPARED`), so a tamper landing
# after a given process has prepared its parser is not caught by that process.
# The gate runs a fresh process per judgement, so per-process is per-verdict.
# --------------------------------------------------------------------------- #

#: The exact TypeScript release this build vouches for. Bumping it is bumping
#: :data:`TS_HELPER_SCHEMA` too — see that constant: the fingerprint grammar is
#: derived from the parser's AST, so a parser change is a grammar change and a
#: grammar change reads as every symbol having been rewritten.
TS_VENDORED_PARSER_VERSION = "5.9.3"

#: **The floored expectation. This constant is the authority over the bytes on
#: disk, and nothing else is.** sha256 of ``package/lib/typescript.js`` from the
#: npm tarball below, measured 2026-08-10 and independently confirmed three
#: times: against the tarball this repository fetches, against the extracted
#: artifact, and against the primary target's own
#: ``node_modules/typescript/lib/typescript.js`` (which is where the measurement
#: started and is the one copy nothing here may ever RESOLVE to).
TS_VENDORED_PARSER_SHA256 = (
    "3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675"
)

#: The parser's size, pinned beside the hash because it is the cheap half: a
#: truncated, swapped or ballooned file is refused by a ``stat`` that reads no
#: content. It is not a substitute for the hash and it is checked FIRST only to
#: bound the work — :func:`_ts_prepared_parser` hashes whenever the size agrees,
#: which is the case a size check cannot decide.
TS_VENDORED_PARSER_BYTES = 9_112_572

#: Where the artifact comes from, pinned to one immutable URL rather than to a
#: package name. ``npm view typescript@5.9.3 dist.tarball``, 2026-08-10. A
#: registry name resolved through npm's config would be a location a
#: project-local ``.npmrc`` can move, which is the argument that rejected
#: ``npm root -g`` two hundred lines above; the fetcher therefore speaks HTTPS
#: to this URL directly and never invokes ``npm`` or ``npx`` at all.
TS_VENDORED_PARSER_TARBALL_URL = (
    "https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz"
)

#: npm's own integrity string for that tarball, in npm's ``sha512-<base64>``
#: spelling so it can be compared against a lockfile by eye. Verified before the
#: archive is opened, which is what makes a hostile or corrupted download a
#: refusal rather than a ``tarfile`` parse of attacker-chosen bytes.
#:
#: It does NOT replace :data:`TS_VENDORED_PARSER_SHA256`: this one is checked
#: once, at fetch, on a machine that had network; that one is checked on every
#: process that renders a TypeScript signature. Two different questions.
TS_VENDORED_PARSER_TARBALL_INTEGRITY = (
    "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4"
    "bXlb1RHhLpp8wtm6M5TgSw=="
)

#: The two members lifted out of the tarball, and the flat names they land under
#: (:data:`TS_HELPER_PACKAGE_DIR` is FLAT by contract, so the paths are
#: rewritten rather than preserved). Nothing else is extracted: the tarball
#: holds a full npm package including ``tsc``, ``tsserver`` and a ``bin/``, none
#: of which this gate runs, and an archive member this build does not need is an
#: archive member this build should not write.
TS_VENDORED_PARSER_TARBALL_MEMBERS: tuple[tuple[str, str], ...] = (
    ("package/LICENSE.txt", TS_VENDORED_PARSER_LICENSE),
    ("package/lib/typescript.js", TS_VENDORED_PARSER),
)

#: sha256 of the license text, checked at FETCH and deliberately NOT at use.
#:
#: The split is the point. The at-use check covers exactly the bytes that decide
#: a verdict, and the license decides nothing — verifying it on the verdict path
#: would turn a benign edit to a text file into a gate outage, which is how a
#: check acquires the reputation that gets it disabled. At fetch it is worth
#: having: it is the cheapest evidence that what was extracted is the package it
#: claims to be, which is the role :data:`TS_VENDORED_PARSER_LICENSE` was given.
TS_VENDORED_PARSER_LICENSE_SHA256 = (
    "a7d00bfd54525bc694b6e32f64c7ebcf5e6b7ae3657be5cc12767bce74654a47"
)

#: The lowest ``ts.version`` this grammar is defined against. A parser older
#: than this does not know syntax the target repo contains (``satisfies``,
#: ``const`` type parameters, ``in``/``out`` variance) and would either
#: parse-error on it — which is survivable, it reads as UNPARSEABLE — or, for
#: modifiers it predates, drop it silently, which is not. Checked, not assumed:
#: :attr:`ComparatorFault.TOOLCHAIN_UNUSABLE` when the vendored parser reports
#: less, by the same argument :func:`_probe_go_toolchain` uses for a ``go``
#: older than the helper's language version.
TS_PARSER_MINIMUM_VERSION = (5, 5)

#: The lowest Node this helper is defined against. Node is to this comparator
#: what ``go`` is to the Go one: a RUNTIME found on PATH, and a fact about the
#: machine. It is not the parser — the vendored ``typescript.js`` is — and the
#: split matters for which fault a failure gets: no ``node`` is
#: TOOLCHAIN_MISSING, no vendored parser is HELPER_MISSING.
TS_NODE_MINIMUM_VERSION = (18,)


def ts_parser_home() -> Path:
    """Where this build's trusted TypeScript parser is, or the named fault.

    **This function IS this unit's answer to the untrusted-parser problem**, and
    it is implemented rather than stubbed for that reason: an answer expressed
    only in prose is a note. It is also, today, a refusal — nothing is vendored,
    so every call raises :attr:`ComparatorFault.HELPER_MISSING`. That is the
    designed first state, not an omission.

    THE RULE, and the whole of it: the directory is
    :data:`TS_HELPER_PACKAGE_DIR` resolved against ``Path(__file__).parent``.
    Never against ``repo_root``, never against the CWD, never against an
    environment variable, and never by asking Node to resolve ``typescript``.
    The section header above argues each rejection; the code here is the
    argument's only enforceable form.

    Three refusals, all :attr:`ComparatorFault.HELPER_MISSING`, because all
    three are the same fact — *the trusted parser this build claims to ship is
    not there*:

      * the directory is absent (the shipped state today, and the state of any
        install that dropped the asset);
      * :data:`TS_HELPER_ENTRY_POINT`, :data:`TS_VENDORED_PARSER` or
        :data:`TS_VENDORED_PARSER_LICENSE` is missing from it;
      * any of those three resolves, after following symlinks, to a path
        OUTSIDE this package directory. A symlink from the vendored parser to
        ``<target>/node_modules/typescript/lib/typescript.js`` would satisfy
        every existence check while restoring the exact defect this unit
        exists to prevent, and it would do so with a one-byte artifact. The
        containment check is the one place where "is the parser trusted" is
        decided by measurement rather than by construction, and it is deliberate
        belt-and-braces: under the resolution rule the escape should be
        impossible, and a check that never fires costs one ``resolve()`` per
        process.

    Absence is a FAULT and never "this build has no TypeScript support". The
    second reading is the broken-wheel fail-open
    :class:`ComparatorFault` exists to name: it would hand every TypeScript
    branch a clean bill of health for as long as the install stayed broken.

    **Not implemented here, and not P1's to do — the enrolment preconditions.**
    See :data:`TYPESCRIPT_SUPPORT` for the full checklist. The two that belong
    with this function:

      * :data:`FLOOR_GLOBS` must grow
        ``**/src/claude_dispatcher/ts_signature_fingerprint/**`` BEFORE
        anything is vendored into it, and that reddens
        ``test_the_floor_is_exactly_the_written_out_set_of_globs``
        (``tests/test_role_protocol_floor.py``), whose ``_FLOOR_ROWS`` table P4
        already ruled P3 may not edit — so the glob and its rows are one P4
        commit, as the Go subtree's were.
      * ``pyproject.toml`` must ship ``ts_signature_fingerprint/*``. It is a
        FLAT glob and the vendored layout must stay flat to match; see
        :data:`TS_HELPER_PACKAGE_DIR`.
    """
    package = Path(__file__).parent.resolve()
    directory = package / TS_HELPER_PACKAGE_DIR
    if not directory.is_dir():
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_MISSING,
            f"no trusted TypeScript parser is installed at {directory}. This "
            "gate resolves its parser ONLY from its own package directory, "
            "never from the repository under judgement — the only TypeScript "
            "parser on a typical machine lives in that repository's "
            "node_modules, which the branch owns. Until one is vendored here, "
            "TypeScript is UNCHECKED and blocking, never clean",
        )
    for name in (
        TS_HELPER_ENTRY_POINT,
        TS_VENDORED_PARSER,
        TS_VENDORED_PARSER_LICENSE,
    ):
        candidate = directory / name
        if not candidate.is_file():
            raise ComparatorUnavailable(
                ComparatorFault.HELPER_MISSING,
                f"the TypeScript helper at {directory} is missing {name}; it "
                "is an apparatus that cannot run, which is a broken install "
                "and not a language nobody can read",
            )
        if not str(candidate.resolve()).startswith(f"{package}/"):
            raise ComparatorUnavailable(
                ComparatorFault.HELPER_MISSING,
                f"{candidate} resolves to {candidate.resolve()}, outside "
                f"{package}. A parser reached by a link out of this package is "
                "a parser this gate cannot vouch for, and the destination is "
                "very likely the judged repository's own node_modules",
            )
    return directory


#: What this PROCESS prepared: ``(directory, None)`` or ``(None, fault)``,
#: whichever the first call produced, and ``None`` before there has been one.
#:
#: **The name is CONTRACT** (P4 adjudication, 2026-08-10) — see
#: :meth:`TypeScriptSignatureFingerprinter.fingerprints`. It is the exact
#: analogue of :data:`_GO_HELPER_PREPARED`, it starts as ``None``, and rebinding
#: it to ``None`` makes the next call re-resolve, re-probe and **re-verify** the
#: digest from scratch. That last word is why a seal reaches for this name: "the
#: digest is verified at USE" has no falsifiable form without a way to say *this
#: is a new use*, and inside one process the only way to say it is to clear this.
#:
#: Per PROCESS and never on disk between runs, for :data:`_GO_HELPER_PREPARED`'s
#: reason with one turn of the screw added: a cached *verification result* on
#: disk would be a stamp file, and a stamp file is the fetch-time check this
#: unit's whole design refuses.
#:
#: The FAULT is cached too, so a machine with no vendored parser pays one
#: ``stat`` rather than one per file, and every file in the diff is refused with
#: the same message.
_TS_HELPER_PREPARED: (
    tuple[Path, None] | tuple[None, ComparatorUnavailable] | None
) = None


def _verify_vendored_parser(directory: Path) -> None:
    """Recompute the parser's digest from disk and compare it to the floor.

    **The at-use half of the operator's ruling**, and the only place the
    comparison happens. Called from :func:`_ts_prepared_parser` on the path that
    produces every TypeScript verdict, never from the fetcher's success path.

    Two comparisons, in this order:

      * size against :data:`TS_VENDORED_PARSER_BYTES`, from ``stat``, so a
        truncated or ballooned file is refused without reading it. It is a bound
        on work, not a check that stands alone;
      * sha256 of the whole file against :data:`TS_VENDORED_PARSER_SHA256`.
        Reached whenever the size agrees, which is exactly the case the size
        check cannot decide — a same-length substitution is the interesting
        tamper and it is the one the hash exists for.

    The license is NOT hashed here; see
    :data:`TS_VENDORED_PARSER_LICENSE_SHA256` for that split and its argument.

    The fault is :attr:`ComparatorFault.HELPER_MISSING` and not a seventh
    member. A parser whose bytes are not the floored ones is *the trusted parser
    this build claims to ship is not there* — the same fact
    :func:`ts_parser_home`'s three refusals name, arrived at by measurement
    instead of by ``is_file()``. It is emphatically not TOOLCHAIN_UNUSABLE,
    which blames the machine for something this build got wrong, and it is not
    ``PARSER_UNTRUSTED``, which the scaffold refused as a member for a state
    that the resolution rule makes unreachable.
    """
    import hashlib

    parser = directory / TS_VENDORED_PARSER
    try:
        size = parser.stat().st_size
    except OSError as exc:  # pragma: no cover - ts_parser_home checked is_file
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_MISSING,
            f"the vendored parser at {parser} could not be read: {exc}",
        ) from exc

    if size != TS_VENDORED_PARSER_BYTES:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_MISSING,
            f"the vendored parser at {parser} is {size} bytes; this build "
            f"vouches for TypeScript {TS_VENDORED_PARSER_VERSION} at "
            f"{TS_VENDORED_PARSER_BYTES} bytes. Re-fetch it with `python3 -m "
            "claude_dispatcher.ts_parser_vendor`; do NOT edit the expectation "
            "to match the file, which is a floor violation and a seal",
        )

    digest = hashlib.sha256(parser.read_bytes()).hexdigest()
    if digest != TS_VENDORED_PARSER_SHA256:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_MISSING,
            f"the vendored parser at {parser} hashes to {digest}, not the "
            f"floored {TS_VENDORED_PARSER_SHA256}. These bytes live in a "
            "mutable path that `scripts/check_body_branch.sh` cannot read, so "
            "this comparison is the only thing standing between them and every "
            "TypeScript verdict this gate issues. TypeScript is UNCHECKED and "
            "BLOCKING until the artifact matches the floored digest",
        )


def _ts_prepared_parser() -> Path:
    """The verified parser directory for this process, or re-raise its fault.

    Resolution (:func:`ts_parser_home`) and verification
    (:func:`_verify_vendored_parser`) together, cached in
    :data:`_TS_HELPER_PREPARED` — see that constant for why the cache is
    per-process, in memory, and never a file.

    Both halves are inside the cached region on purpose. Caching the resolution
    but re-verifying, or the reverse, would be a preparation that is half fresh
    and half stale, and "which half decided this verdict" is a question nobody
    should have to ask of a gate.
    """
    global _TS_HELPER_PREPARED

    if _TS_HELPER_PREPARED is None:
        try:
            directory = ts_parser_home()
            _verify_vendored_parser(directory)
            _TS_HELPER_PREPARED = (directory, None)
        except ComparatorUnavailable as exc:
            _TS_HELPER_PREPARED = (None, exc)

    directory, failure = _TS_HELPER_PREPARED
    if failure is not None:
        raise failure
    assert directory is not None  # the two arms of the tuple are exclusive
    return directory


def _node_toolchain_environment() -> dict[str, str]:
    """The environment the helper's ``node`` process is invoked under. Contract.

    :func:`_go_toolchain_environment`'s counterpart, and it carries more weight
    than that one does, because Node's default behaviour is to load code from
    directories it discovers at run time. Every entry below closes one route by
    which the tree under judgement could inject a module into the process that
    decides what its signatures are. Normative:

      * ``NODE_OPTIONS`` **removed**. It can carry ``--require`` /
        ``--import``, which executes arbitrary code before the helper's first
        line. An operator shell that sets it for an unrelated project would
        silently join the trusted base.
      * ``NODE_PATH`` **removed**. It is a module search root taken from the
        environment; the whole of this unit's rule is that search roots come
        from ``__file__``.
      * ``NODE_REPL_EXTERNAL_MODULE``, ``NODE_EXTRA_CA_CERTS`` and any other
        ``NODE_*`` **removed**. Enumerating what is dangerous is the wrong
        shape: the helper needs NO ``NODE_*`` variable to do its job, so the
        contract is *strip them all* and a future one is closed in advance.
      * ``NPM_CONFIG_*`` **removed**. The helper never invokes npm; a variable
        that only npm reads can only redirect something.
      * ``cwd`` set to :func:`ts_parser_home`. Not cosmetic: Node resolves
        ``require`` by walking UP from the requiring file and, for some
        lookups, from the CWD, and it reads ``package.json`` from ancestor
        directories to decide CommonJS-vs-ESM. Left at the judged checkout, the
        ancestor chain is the branch's.

    ``PATH`` and ``HOME`` are INHERITED, as the Go side inherits ``GOCACHE`` and
    ``HOME``: ``node`` is found on ``PATH`` like ``go`` is, and an unusable
    ``HOME`` is a real fault with a name rather than something to paper over.

    The helper itself must also ``require`` the parser by ABSOLUTE PATH — not
    ``require('typescript')`` — so that even a process whose environment was
    scrubbed incorrectly still cannot reach an ancestor ``node_modules``. Two
    independent mechanisms for one property, on purpose: the environment can be
    got wrong by a caller, the absolute path cannot.

    **P3:** the ``NODE_*`` strip is written as *remove every variable whose
    name starts with* ``NODE_``, not as a list of the dangerous ones, because
    the contract above rules the enumeration to be the wrong shape — the helper
    needs none of them, so a future one is closed in advance rather than
    discovered. ``NPM_CONFIG_*`` goes the same way.
    """
    import os

    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("NODE_") and not name.startswith("NPM_CONFIG_")
    }


@dataclass(frozen=True)
class TsHelperRequest:
    """What the Python side sends the TS helper: ONE revision of ONE file.

    Field-for-field :class:`GoHelperRequest`, with :data:`TS_HELPER_SCHEMA` in
    ``schema``, and for the same reasons: source travels as TEXT because the
    revisions compared are git blobs that are not on disk, and one file per
    invocation because a batch makes "which file faulted" unanswerable.

    ``path`` is load-bearing here in a way it is not for Go: it selects the
    parse DIALECT. ``.tsx`` and ``.ts`` are different grammars for the same
    bytes — measured 2026-08-10, ``const x = <T>(y);`` parses clean as ``.ts``
    and produces two diagnostics as ``.tsx``, where ``<T>`` opens a JSX element
    — so a helper that guessed, or that used one setting for both, would
    manufacture parse errors on half the target repo.
    """

    schema: str
    path: str
    source: str


@dataclass(frozen=True)
class TsHelperSymbol:
    """One declared symbol and its fingerprint, as the TS helper reports it.

    ``symbol`` is the key :func:`compare_signatures` matches across revisions
    and it is built by :func:`ts_symbol_key`, never by string concatenation in
    the helper. ``kind`` (``"function"``, ``"class"``, ``"interface"``,
    ``"type"``, ``"enum"``, ``"variable"``, ``"member"``, ``"export"``,
    ``"module"``) is reportage only and is never compared, for the reason
    :class:`GoHelperSymbol` gives: a second comparison surface is a second
    thing to keep in agreement.
    """

    symbol: str
    fingerprint: str
    kind: str


@dataclass(frozen=True)
class TsHelperResponse:
    """What the TS helper writes to stdout: exactly one JSON object, always.

    The contract is :class:`GoHelperResponse`'s, unchanged: exit 0 means the
    document is valid *including* when it reports a parse error; non-zero is
    :attr:`ComparatorFault.HELPER_FAILED` and stdout is not read at all;
    ``symbols`` and ``parse_error`` are mutually exclusive; an empty
    ``symbols`` LIST is an answer and an empty stdout is a fault.

    **One TypeScript-specific rule, and it is the most important sentence in
    this class.** ``ts.createSourceFile`` is an ERROR-RECOVERING parser: given
    ``export function ok(a: string): void {}\\nexport class`` it returns one
    diagnostic *and a syntax tree containing two statements* (measured
    2026-08-10). Go's parser recovers too, but TypeScript's is designed for an
    editor and recovers aggressively. So the helper must report
    ``parse_error`` whenever the parse produced **any** diagnostic, and must
    never return the symbols it recovered alongside it. The reason is a silent
    pass, not a noisy failure: if the BASE revision parses partially and drops
    a declaration, that declaration is *added* at head, an added symbol is not a
    change, and a body agent's widening walks through. A recovered tree is not a
    conservative answer — it is a smaller one, and smaller is the direction that
    clears branches.

    A corollary the helper author must not miss: the diagnostics channel is
    load-bearing, so a helper that cannot read it (a parser build that does not
    expose it) must **exit non-zero** — HELPER_FAILED — rather than proceed
    assuming the parse was clean.
    """

    schema: str
    symbols: tuple[TsHelperSymbol, ...] = ()
    parse_error: str | None = None


def encode_ts_helper_request(path: str, source: str) -> str:
    """The JSON document for one file revision, ready for the helper's stdin.

    Byte-for-byte the contract of :func:`encode_go_helper_request` with
    :data:`TS_HELPER_SCHEMA` substituted: exactly the fields of
    :class:`TsHelperRequest`, ``ensure_ascii=True`` (a blob that is not valid
    UTF-8 must not turn a bad FILE into an environment fault), deterministic
    separators, and ``source`` passed through verbatim including BOM and CRLF.

    **P3 must not copy** :func:`encode_go_helper_request`. See
    :func:`decode_ts_helper_response` for the ruling and the refactor it names;
    the same applies here, where the duplication is smaller and therefore more
    tempting.

    **P3:** the shared piece here is one ``json.dumps`` call with three
    keyword arguments, so the extraction the decoder needed would be a wrapper
    longer than the thing it wraps. What is shared instead is the ARGUMENT —
    the reasons for ``ensure_ascii`` and for the separators are recorded once,
    at :func:`encode_go_helper_request`, and are not restated. The schema and
    the field set are what differ, and they are the whole body.
    """
    return json.dumps(
        {"schema": TS_HELPER_SCHEMA, "path": path, "source": source},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def decode_ts_helper_response(stdout: str) -> TsHelperResponse:
    """Parse the TS helper's stdout, or raise the named fault.

    The contract is :func:`decode_go_helper_response`'s, entirely: every way the
    document can be wrong — not JSON, not an object, wrong or missing
    ``schema``, empty string, missing fields, wrong types, both ``symbols`` and
    ``parse_error``, neither, duplicate symbol keys — is
    :attr:`ComparatorFault.HELPER_OUTPUT_INVALID` and never a partial result,
    because a dropped symbol is reported as a REMOVED one and a wholly dropped
    document manufactures a pass.

    **THE DUPLICATION RULING, and it is this unit's clearest evidence that the
    registry did not make TypeScript one row.** :func:`decode_go_helper_response`
    is ~110 lines of pure, language-independent validation whose only Go-shaped
    element is the schema string it compares against. Copying it here would
    create two implementations of one protocol, which is the two-copies problem
    this whole section was built to refuse — and it would do so in the exact
    place where a divergence is a fail-open, since the copy that forgets the
    duplicate-key check clears branches the original refuses.

    P3 **may not copy it and may not implement it independently.** The required
    shape is a P4-authored extraction: one shared validator with
    :func:`decode_go_helper_response` and this function as thin wrappers that
    fix its arguments. That is a change to shipped Go code and to seals that
    name it, so it is neither P1's nor P3's; it is named here so the seal author
    can write the seal that FORCES it — assert that both decoders reject the
    same malformed documents with the same fault, over one shared table of bad
    inputs, so a divergent second copy reddens.

    **P4 ADJUDICATION, 2026-08-10 — the named signature was wrong and is
    corrected here.** The scaffold wrote ``_decode_helper_response(stdout,
    schema)``. Two arguments cannot be met: the validator does not merely
    VALIDATE, it BUILDS the result, and there are two response/symbol dataclass
    pairs — :class:`GoHelperResponse`/:class:`GoHelperSymbol` and
    :class:`TsHelperResponse`/:class:`TsHelperSymbol` — which are distinct
    types by deliberate design (each carries its own schema and its own
    docstring's rules). A two-argument validator would have to pick one pair,
    and the language whose pair it did not pick would need its own construction
    step — which is the second implementation this ruling exists to forbid,
    reintroduced one level down. The seal author reported the arity mismatch
    rather than writing a seal against a signature that cannot be met, and
    wrote the spy to accept extras. The signature P3 implements is::

        _decode_helper_response(
            stdout: str,
            schema: str,
            response_type: type,
            symbol_type: type,
        )

    Normative, and each clause is load-bearing:

      * ``stdout`` and ``schema`` are the first two POSITIONAL parameters, in
        that order. The seal observes the schema each wrapper passes, which is
        how "each decoder fixes its OWN schema" is checkable at all; a
        keyword-only or reordered spelling makes it unobservable.
      * ``response_type`` and ``symbol_type`` are the constructors, passed in.
        Four arguments is the smallest number that lets ONE body of validation
        serve two type pairs, and the two type arguments are what stops the
        extraction degenerating into a shared parser plus two private builders.
      * Both are constructed by KEYWORD — ``symbol_type(symbol=…,
        fingerprint=…, kind=…)`` and ``response_type(schema=…, symbols=…)`` or
        ``response_type(schema=…, parse_error=…)``. This is what makes four
        arguments sufficient rather than five: the two pairs are already
        field-for-field identical in name and order, and that identity is a
        contract of :class:`TsHelperRequest`/:class:`TsHelperResponse` ("field
        for field :class:`GoHelperRequest`"), not a coincidence to be
        rediscovered. A future language that needs a different field set needs
        a ruling, not a fifth argument.
      * The return is the caller's ``response_type``. Neither wrapper
        re-validates and neither wrapper reshapes; a wrapper that did would be
        the divergence back again.

    The duplication is real and it is not an artifact of the wire format being
    poorly chosen. Both helpers are subprocesses that speak one JSON object; a
    third language would make it three copies. That is worth writing down as
    the answer to "was this one row": the *dispatch* was one row, the
    *plumbing* was not.

    **P3, 2026-08-10: the extraction is done and this is the wrapper.** The
    validation is :func:`_decode_helper_response`, called with the corrected
    four-argument signature above; there is no second implementation and no
    copy. :func:`decode_go_helper_response` is now the same shape, which is the
    half of the ruling that could not have been met by writing only this
    function.
    """
    response = _decode_helper_response(
        stdout, TS_HELPER_SCHEMA, TsHelperResponse, TsHelperSymbol
    )
    assert isinstance(response, TsHelperResponse)  # the type it was handed
    return response


#: The tag vocabulary for one segment of a TypeScript symbol key. A closed set;
#: :func:`ts_symbol_key` refuses anything else.
#:
#: ``i``  an identifier-named declaration or member (``foo``, ``#secret``)
#: ``s``  a string-literal member name, or a module specifier
#: ``c``  a computed member name (``[Symbol.iterator]``), rendered as source
#: ``k``  a KEYWORD SLOT — a position the language has but no identifier names:
#:        ``default`` (an anonymous default export), ``global`` (``declare
#:        global``), ``call`` / ``new`` / ``index`` (call, construct and index
#:        signatures), ``ctor`` (a class constructor), ``export`` (the module's
#:        export-surface subtree, and — alone, as a whole key — ``export = X``;
#:        see :class:`TypeScriptSignatureFingerprinter`), ``star``
#:        (``export * from``), ``empty`` (a name that is the EMPTY STRING).
#:
#: **``empty`` — P4 ruling, 2026-08-10, and the tag set is untouched by it.**
#: ``interface I { "": number }``, ``declare module "" {}`` and
#: ``export * from ""`` are all legal, all compile, and were all found in the
#: soak corpus rather than by reading. Each produces an empty segment text,
#: which :func:`ts_symbol_key` refuses — correctly, since a key built from a
#: helper bug matches nothing across revisions — so before the guard the helper
#: exited non-zero and the gate reported HELPER_FAILED on ordinary compiling
#: code. That is the worse of the two ways to be wrong: a fault is not a
#: lenient answer, it is NO answer, over the whole file.
#:
#: It belongs on ``k`` because it satisfies that tag's own definition exactly —
#: a position the language has and no identifier names — and because it cannot
#: be forged: a member named ``empty`` keys ``i:empty``, a string-literal member
#: ``"empty"`` normalises to ``i:empty`` too, and a string-literal member
#: spelled ``k:empty`` keys ``s:k:empty``, since the LEADING tag is what is
#: read. What this ruling adds is a WORD to the list above. **The TAG SET
#: remains closed at ``{i, s, c, k}``** and adding to it would be a different
#: ruling with a different argument; the word list has always been open, which
#: is what a keyword slot is for.
TS_KEY_TAGS: frozenset[str] = frozenset({"i", "s", "c", "k"})


def ts_symbol_key(segments: Sequence[tuple[str, str]]) -> str:
    """Build one TypeScript symbol key from ``(tag, text)`` segments. Pure.

    One of the two things this scaffold implements rather than stubs, because a
    seal cannot express the property below without calling it, and because it is
    a total function of its arguments that either always works or always does
    not.

    **THE COLLISION PROPERTY, which is trap 1 from the Go unit restated for a
    language that makes it much easier to hit.** Go's embed marker was defeated
    by a struct field literally named ``embedded``: a marker a name can spell is
    not a marker. TypeScript is worse, because a member name is not required to
    be an identifier at all —

        interface I { "a/b": string; "i:x": number; [Symbol.iterator](): void }

    — so ``/`` and ``:`` and every other separator are spellable *in the member
    position*. The grammar here is therefore:

      * a key is its segments joined by ``/``;
      * each segment is ``<tag>:<text>`` with ``tag`` from :data:`TS_KEY_TAGS`;
      * inside ``text``, ``\\`` becomes ``\\\\`` and ``/`` becomes ``\\/``.

    Both markers are then unspellable **in the position they occupy**, which is
    the property Go's fix established and the only one that counts. A tag is
    one character followed by ``:`` at offset 0 of a segment, and no TypeScript
    identifier may contain ``:`` — so ``i:``, ``s:``, ``c:`` and ``k:`` cannot
    be produced by a name. An unescaped ``/`` cannot be produced by a name
    either, because every ``/`` a name contains is escaped here. A member
    literally named ``i:x`` keys as ``i:I/s:i:x`` — the LEADING tag is what is
    read, and the rest of the segment is data.

    The ``k`` tag is the piece that has no Go analogue and it is the reason
    tags exist at all rather than a bare escape. TypeScript has declaration
    positions with no name: an anonymous ``export default class {}``, a call
    signature, an index signature. Those need keys, the obvious keys
    (``default``, ``index``) are ordinary spellable identifiers, and
    ``k:default`` is not.

    Raises :class:`RoleProtocolError` on an empty segment list, an unknown tag,
    or an empty ``text``. All three are helper bugs rather than facts about a
    file, and a key built from a bug is a key that matches nothing across
    revisions — which reports every symbol in the file as removed and added.
    """
    if not segments:
        raise RoleProtocolError(
            "a TypeScript symbol key needs at least one segment; an empty key "
            "matches nothing across revisions, which reports every symbol in "
            "the file as removed"
        )
    parts: list[str] = []
    for tag, text in segments:
        if tag not in TS_KEY_TAGS:
            raise RoleProtocolError(
                f"unknown TypeScript symbol key tag {tag!r}; the tag set is "
                f"closed ({', '.join(sorted(TS_KEY_TAGS))}) so that no member "
                "name can spell one"
            )
        if not text:
            raise RoleProtocolError(
                f"empty text for a {tag!r} segment of a TypeScript symbol key"
            )
        escaped = text.replace("\\", "\\\\").replace("/", "\\/")
        parts.append(f"{tag}:{escaped}")
    return "/".join(parts)


#: What this PROCESS probed, keyed by the parser directory the probe loaded.
#:
#: Keyed rather than a bare pair because the directory is not a constant: the
#: digest seals repoint :data:`TS_HELPER_PACKAGE_DIR` at a copy, and a probe
#: result cached from the shipped directory would then be answering about bytes
#: nobody loaded. The key makes "this is a different parser" say so.
#:
#: Per PROCESS and never on disk, for :data:`_TS_HELPER_PREPARED`'s reason.
#: This cache carries no verification result — the digest is re-checked by
#: :func:`_ts_prepared_parser` on every call, ahead of this one — so it cannot
#: become the stamp file the design refuses.
_TS_NODE_PREPARED: dict[
    str, tuple[str, None] | tuple[None, ComparatorUnavailable]
] = {}


def _parse_dotted_version(text: str) -> tuple[int, ...] | None:
    """``"v20.19.4"`` or ``"5.9.3"`` → ``(20, 19, 4)``, or None if unreadable."""
    cleaned = text.strip().lstrip("v").split("-")[0].split("+")[0]
    parts = cleaned.split(".")
    try:
        return tuple(int(part) for part in parts if part != "")
    except ValueError:
        return None


def _probe_node_and_parser(directory: Path) -> str:
    """Refuse a ``node`` or a vendored parser that cannot do the job.

    Two faults, and the split is the one :data:`TS_NODE_MINIMUM_VERSION`
    records: ``node`` is a RUNTIME found on PATH and a fact about the machine,
    so its absence is :attr:`ComparatorFault.TOOLCHAIN_MISSING`; everything
    else here is :attr:`ComparatorFault.TOOLCHAIN_UNUSABLE`, by
    :func:`_probe_go_toolchain`'s argument — a toolchain that is present but
    cannot run would otherwise fail later as a parse error and blame the branch
    for the age of the install.

    ONE subprocess answers both questions, and it is the helper itself under
    ``--probe`` rather than ``node --version``. That is deliberate: it also
    proves that this Node can actually load this 9.1 MB parser, which is the
    failure a version comparison would sail past.

    The parser version check is belt-and-braces after
    :func:`_verify_vendored_parser` has matched the bytes exactly, and it is
    kept because the contract names it and because it costs nothing here — the
    subprocess is already being run for Node's version.

    **AND THE THIRD CHECK IS THE ONE THAT MATTERS: THE LOADED PARSER IS
    IDENTIFIED, NOT ASSUMED.** P4 ruling, 2026-08-10, task #15. Everything
    above verifies BYTES ON DISK and a VERSION; neither says which file the
    helper process actually loaded. ``main.cjs`` loads the parser by absolute
    path and never as ``require('typescript')``, and that is the central
    security property of this unit — but it was, until this ruling, sealed by
    nothing. A mutation to ``require('typescript')`` reddens only where no
    ambient TypeScript resolves; on a laptop with a global install, a CI image
    with hoisted ``node_modules``, or the primary target checkout — which
    vendors TypeScript — the mutant resolves, runs, and answers. **And it
    answers with the same version string**, because the ambient copy is
    routinely the same release: measured on a manufactured hostile machine,
    both report ``5.9.3``. A version is equally true of the untrusted copy, so
    a version check cannot separate them and never could.

    ``--probe`` therefore also reports ``parser``: the filename Node resolved
    for the module object the helper is holding, read out of the loader's own
    ``module.children`` rather than recomputed from the specifier. This
    function compares it against the vendored file by IDENTITY — resolved
    paths, so a symlinked checkout compares equal — and refuses anything else.
    A helper that cannot say, or does not say, is refused too: a missing
    ``parser`` key is the check being deleted from the helper side, and the
    default for "which parser ran is unknown" is a fault, not a pass.

    The fault is TOOLCHAIN_UNUSABLE and not a seventh one. The trusted parser
    is present and its digest matched — that is what
    :func:`_ts_prepared_parser` already established — so this is not
    HELPER_MISSING; what has gone wrong is that the runtime loaded something
    else, which is a toolchain that is present and cannot be used to clear a
    branch. No new fault is added, by :class:`TypeScriptSignatureFingerprinter`'s
    rule that this design adds none.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_MISSING,
            "`node` is not on PATH. The vendored parser is this build's own "
            "apparatus and it is present; the RUNTIME that executes it is a "
            "fact about the machine, which is why this is a toolchain fault "
            "and not HELPER_MISSING",
        )

    entry = directory / TS_HELPER_ENTRY_POINT
    try:
        probe = subprocess.run(
            [node, str(entry), "--probe"],
            capture_output=True,
            timeout=_HELPER_TIMEOUT_SECONDS,
            env=_node_toolchain_environment(),
            cwd=str(directory),
        )
    except subprocess.TimeoutExpired as exc:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`node {entry} --probe` did not answer within "
            f"{_HELPER_TIMEOUT_SECONDS}s; a runtime that hangs loading the "
            "parser cannot be used to clear a branch",
        ) from exc
    except OSError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`node {entry} --probe` could not be run: "
            f"{type(exc).__name__}: {exc}",
        ) from exc

    if probe.returncode != 0:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"`node {entry} --probe` exited {probe.returncode}: "
            f"{_helper_diagnostic_text(probe.stderr)}",
        )

    try:
        reported = json.loads(probe.stdout.decode("utf-8", "replace"))
    except ValueError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"the probe answered {probe.stdout!r}, which is not the "
            "`{node, typescript, parser}` document this helper promises",
        ) from exc
    if not isinstance(reported, dict):
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"the probe answered a JSON {type(reported).__name__}, not an object",
        )

    for label, key, minimum in (
        ("node", "node", TS_NODE_MINIMUM_VERSION),
        ("the vendored parser", "typescript", TS_PARSER_MINIMUM_VERSION),
    ):
        raw = reported.get(key)
        version = _parse_dotted_version(raw) if isinstance(raw, str) else None
        if version is None:
            raise ComparatorUnavailable(
                ComparatorFault.TOOLCHAIN_UNUSABLE,
                f"the probe reported {label} as {raw!r}, which is not a "
                "version this gate can compare against its own minimum",
            )
        if version < minimum:
            wanted = ".".join(str(part) for part in minimum)
            raise ComparatorUnavailable(
                ComparatorFault.TOOLCHAIN_UNUSABLE,
                f"{label} is {raw}, older than the {wanted} this grammar is "
                "defined against. A parser that predates syntax the target "
                "repository contains either parse-errors on it — survivable, "
                "it reads as UNPARSEABLE — or, for a modifier it predates, "
                "drops it SILENTLY, which is not",
            )

    # THE IDENTITY CHECK. See the docstring: this is the only one of the three
    # that answers "which parser RAN", and it is the only one a machine with an
    # ambient TypeScript cannot defeat.
    expected = (directory / TS_VENDORED_PARSER).resolve()
    raw_parser = reported.get("parser")
    if not isinstance(raw_parser, str) or not raw_parser:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"the probe reported the loaded parser as {raw_parser!r}. A helper "
            "that does not say which parser it loaded cannot be trusted to have "
            "loaded the vendored one, and 'unknown' is a fault here rather than "
            "a pass: `require('typescript')` resolves on any machine with a "
            "global install or a hoisted node_modules — including the target "
            "checkout, which vendors TypeScript — and reports the same version",
        )
    try:
        loaded = Path(raw_parser).resolve()
    except OSError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"the probe reported the loaded parser as {raw_parser!r}, which "
            f"could not be resolved to a path: {type(exc).__name__}: {exc}",
        ) from exc
    if loaded != expected:
        raise ComparatorUnavailable(
            ComparatorFault.TOOLCHAIN_UNUSABLE,
            f"the helper loaded {str(loaded)!r}, not the vendored parser at "
            f"{str(expected)!r}. That is the untrusted-parser failure this unit "
            "exists to prevent: a branch that edits its own "
            "`node_modules/typescript/lib/typescript.js` to drop a modifier "
            "would be choosing the program that decides what its signatures "
            "are. The digest above vouched for bytes NOBODY LOADED, and the "
            "version matched because an ambient copy is routinely the same "
            "release",
        )
    return node


def _ts_prepared_node(directory: Path) -> str:
    """The probed ``node`` for this process and this parser, or its fault.

    Caches both arms in :data:`_TS_NODE_PREPARED`, so a machine with no
    ``node`` pays one ``which`` rather than one per file and every file in the
    diff is refused with the same message.
    """
    key = str(directory)
    if key not in _TS_NODE_PREPARED:
        try:
            _TS_NODE_PREPARED[key] = (_probe_node_and_parser(directory), None)
        except ComparatorUnavailable as exc:
            _TS_NODE_PREPARED[key] = (None, exc)

    node, failure = _TS_NODE_PREPARED[key]
    if failure is not None:
        raise failure
    assert node is not None  # the two arms of the tuple are exclusive
    return node


def _run_ts_helper(node: str, directory: Path, path: str, text: str) -> str:
    """One request in, the helper's stdout out, or the named fault.

    :func:`_run_go_helper`'s contract, unchanged: exit status and document are
    separate channels, so a non-zero exit is
    :attr:`ComparatorFault.HELPER_FAILED` and stdout is **not read at all** — a
    document from a run that failed is a partial answer, and a partial answer
    manufactures removed symbols.

    The ``cwd`` is the parser's own directory, per
    :func:`_node_toolchain_environment`: Node reads ``package.json`` from
    ancestor directories to decide CommonJS-versus-ESM, and left at the judged
    checkout the ancestor chain would be the branch's.
    """
    import subprocess

    entry = directory / TS_HELPER_ENTRY_POINT
    request = encode_ts_helper_request(path, text).encode("utf-8")
    try:
        finished = subprocess.run(
            [node, str(entry)],
            input=request,
            capture_output=True,
            timeout=_HELPER_TIMEOUT_SECONDS,
            env=_node_toolchain_environment(),
            cwd=str(directory),
        )
    except subprocess.TimeoutExpired as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_TIMEOUT,
            f"the TypeScript helper took longer than "
            f"{_HELPER_TIMEOUT_SECONDS}s on {path}. There is no retry and no "
            "degraded mode: a fallback is how a gate ends up reporting a pass "
            "it did not earn",
        ) from exc
    except OSError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_FAILED,
            f"the TypeScript helper at {entry} could not be executed: "
            f"{type(exc).__name__}: {exc}",
        ) from exc

    if finished.returncode != 0:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_FAILED,
            f"the TypeScript helper exited {finished.returncode} on {path}: "
            f"{_helper_diagnostic_text(finished.stderr)}",
        )

    try:
        return finished.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ComparatorUnavailable(
            ComparatorFault.HELPER_OUTPUT_INVALID,
            f"the TypeScript helper's stdout for {path} is not valid UTF-8: "
            f"{exc}",
        ) from exc


class TypeScriptSignatureFingerprinter:
    """TypeScript signatures, via a vendored parser in a Node helper. Contract.

    **One parser, not two**, as :class:`GoSignatureFingerprinter` rules for Go —
    and the parser is ``typescript.js`` itself, vendored into this package. The
    section header above says why it is vendored rather than resolved, and what
    was rejected.

    Syntactic and single-file. ``ts.createSourceFile`` with
    ``ScriptTarget.Latest``, ``setParentNodes=true``, and ``ScriptKind`` taken
    from the path: ``.tsx`` → ``ScriptKind.TSX``, ``.ts`` → ``ScriptKind.TS``.
    **No ``ts.Program``, no type checker, no ``tsconfig.json``, no file
    system.** The reason is the Go one — the revisions compared are two blobs
    out of git that may not resolve in isolation — plus a second one specific
    to this language: ``tsconfig.json`` lives in the tree under judgement and
    choosing parse options from it would let a branch decide how its own files
    are read.

    WHAT A TYPESCRIPT SIGNATURE IS
    ------------------------------
    Read off the file's top level, off the members of declared types and
    classes, and off the module's export statements. Function and method bodies
    and all other expression positions are never descended into.

    **Symbol keys** are built by :func:`ts_symbol_key`; see it for the escaping
    and for why ``/`` and a tag prefix are the separators. In declaration
    order:

      * a top-level declaration named ``f`` → ``i:f``, whatever its kind
        (function, class, interface, type alias, enum, namespace, variable);
      * a member ``m`` of a top-level declaration ``C`` → ``i:C/i:m``, and a
        namespace's exported declarations nest the same way to any depth;
      * a call, construct or index signature of a type → ``i:I/k:call``,
        ``i:I/k:new``, ``i:I/k:index``; a class constructor → ``i:C/k:ctor``;
      * ``declare module "foo"`` → ``s:foo``; ``declare global`` → ``k:global``;
      * an anonymous ``export default …`` → ``k:default``;
      * ``export = X`` → ``k:export``, the bare keyword slot with nothing under
        it (below, and it is a P4 ruling of 2026-08-10 rather than an omission);
      * the module's export surface → ``k:export/…`` (below);
      * **a name that is the EMPTY STRING → ``k:empty`` in the segment that name
        occupies.** ``interface I { "": number }``, ``declare module "" {}`` and
        ``export * from ""`` are legal and were all found in the soak corpus, so
        this is a position the grammar must have; :data:`TS_KEY_TAGS` carries the
        ruling and the argument for why the slot is ``k`` and cannot be forged.

    **ONE KEY PER NAME, and every declaration of that name folds into it.**
    This is the ruling that makes the scheme total, and it answers three
    TypeScript shapes at once that would otherwise each need their own rule and
    would each otherwise produce a DUPLICATE KEY — which
    :func:`decode_ts_helper_response` refuses as
    :attr:`ComparatorFault.HELPER_OUTPUT_INVALID`, i.e. the gate would fault on
    ordinary, legal, compiling code:

      * **Function overloads.** ``function f(x: string): string; function f(x:
        number): number; function f(x: any): any {…}`` is three
        ``FunctionDeclaration`` nodes named ``f`` (measured). One symbol
        ``i:f``; its fingerprint is the ORDERED list of all three signatures,
        each marked as an overload declaration or as the implementation.
      * **Declaration merging.** ``interface I {…}`` twice, ``class C`` plus
        ``interface C``, ``namespace N`` twice, ``enum E`` twice. One symbol,
        fingerprint is the ordered list of each contributing declaration's
        rendering, each prefixed by its kind.
      * **A name in both declaration spaces.** ``interface Foo {}`` beside
        ``const Foo = 1`` is legal and common. Folding them into one key means
        the scheme never has to model TypeScript's type/value split — which is
        a real simplification and also, honestly, a real loss of precision: a
        change to either is reported against the one name, and the fingerprint
        text is what says which.

    ORDER, and where it is and is not semantic
    ------------------------------------------
    Go rules struct fields in declaration order because that order is memory
    and wire layout. TypeScript is not uniform and each position is ruled:

      * **Parameters: ordered.** The Go ruling transfers with its argument
        intact — ``move(src, dst)`` → ``move(dst, src)`` is type-identical,
        compiles everywhere, inverts every call, and is indistinguishable in a
        syntactic comparison from two renames. So **parameter NAMES are IN**,
        for the reason the Go table records: the choice is binary and the
        rename false positive is the price of the reorder catch.
      * **Type parameters: ordered, and their NAMES are IN**, by the identical
        argument one level up. ``<K, V>`` → ``<V, K>`` silently inverts every
        ``Map<A, B>`` in the codebase. Their constraints (``extends``),
        defaults (``=``) and variance annotations (``in`` / ``out`` /
        ``const``) are all IN.
      * **Overload signatures: ordered.** TypeScript resolves an overload set
        in declaration order, so swapping two overloads changes which one a
        call selects, with no error. Same shape as the parameter reorder.
      * **Enum members: ordered, with their explicit initialisers.** ``enum E {
        X, Y }`` gives ``X = 0, Y = 1``; reordering rewrites both values, and a
        ``const enum``'s values are INLINED into consumers, so this is a wire
        change of the struct-tag kind.
      * **Tuple type elements: ordered** — ``[string, number]`` is not
        ``[number, string]``.
      * **Members of interfaces, type literals and classes: SORTED by rendered
        key, not declaration order.** A deliberate parity break with the Go
        struct-field rule, and the criterion is the one the Go table used
        rather than the habit: object member order carries no information a
        caller can be made wrong by — ``{a: string; b: number}`` and ``{b:
        number; a: string}`` are the same type to every consumer — so ordering
        them buys no reorder catch and costs a false positive on every
        alphabetise-the-interface edit. Where the criterion says order matters
        it is kept; where it says order is spelling it is normalised. That
        asymmetry is the check on the criterion, exactly as the receiver row is
        in the Go table.
      * **Union and intersection constituents: as written.** The honest answer
        rather than the tidy one. ``A | B`` and ``B | A`` are the same type, so
        sorting them would be a legitimate normalisation — but intersection
        order can affect which overload of a merged callable is selected, and
        this comparator has no type checker with which to tell a union from an
        intersection of callables in every position. Rendering both as written
        costs a false positive on a reorder; sorting one and not the other
        would be a rule nobody can state. The false positive is the same class
        as the import-alias noise the Go contract already accepts.

    IN, each with its reason
    ------------------------
      * **Modifiers**, all of them: ``export``, ``declare``, ``abstract``,
        ``static``, ``readonly``, ``public``/``private``/``protected``,
        ``override``, ``async``, ``accessor``, the optional marker ``?`` and
        the definite-assignment marker ``!``. ``export`` is the one to argue:
        removing it deletes a declaration from the module's public API with **no
        error anywhere in the file**, which is the archetypal silent narrowing
        and precisely what a P3 body agent tidying "unused exports" would do.
      * **The export surface**, as symbols under ``k:export``. ``export { a as
        b }`` renames a public name without touching a declaration; ``export
        type { T }`` versus ``export { T }`` changes what survives
        ``verbatimModuleSyntax``; ``export * from './m'`` republishes another
        module's surface. All three are contract changes that a
        declaration-only reader cannot see. Keys: ``k:export/i:b`` for a named
        export, ``k:export/k:star/s:.\\/m`` for a star re-export of ``./m``;
        the fingerprint carries the local name, the source specifier and the
        type-only flag.

        **``export = X`` is the BARE ``k:export`` key — P4 ruling, 2026-08-10,
        and the position list above now names it.** The seal author found the
        behaviour shipped and unruled: it is distinct from ``k:default`` and
        from ``k:export/i:<name>`` by construction, but no contract sentence
        required it, so the row pinned an accident. It is ruled IN, because it
        is the only key that is true of it. ``export = X`` does not export a
        NAME out of the module's surface, it replaces the surface — the module
        *is* ``X`` — so the symbol is the export-surface subtree root itself,
        with nothing under it. That is also why it may not share ``k:default``:
        ``export = X`` is the CommonJS-shaped export consumed by
        ``import X = require('m')`` and ``import * as X``, ``export default X``
        is the ES one, and swapping them breaks every importer — at build time
        for some and at run time for the rest, depending on
        ``esModuleInterop``. Sharing a key would report that swap as one symbol
        whose fingerprint moved, rather than as one promise withdrawn and a
        different one made. An ambient module NAMED ``"export"`` keys
        ``s:export`` and cannot reach the slot, by the tag rule.

        **P4 correction, 2026-08-10.** This example was written
        ``k:export/k:star/s:./m``, which is not the key :func:`ts_symbol_key`
        builds — the ``/`` inside a module specifier is escaped, exactly as the
        ``/`` inside a member name is, and for the same reason: unescaped it
        spells the segment separator and ``./m`` would key as two segments.
        Corrected rather than left, under this repository's standing ruling
        against a citation that sends a reader to something they cannot
        reproduce: the earlier spelling is unreachable from any input, so
        anyone checking it against the function would have concluded the
        function was wrong.
      * **Ambient declarations.** ``declare module "foo"``, ``declare global``,
        and everything in a ``.d.ts``. A ``.d.ts`` file is nothing but
        signature; it is read through the ``.ts`` row (``.d.ts`` cannot be its
        own registry row — :func:`validate_registry` refuses an extension that
        is a suffix of another, and ``.d.ts`` ends with ``.ts``) and needs no
        special case.
      * **Decorators, rendered in full including their arguments.** A parity
        break with Python, which fingerprints decorator NAMES only, and the
        reason is the struct-tag reason verbatim: ``@Column({ name: 'amount'
        })`` → ``@Column({ name: 'amt' })`` renames a database column, rewrites
        every row this type reads and writes, and produces no error anywhere.
        The Go contract calls tags "the single most consequential edit a body
        agent can make to a type without touching a function signature"; in a
        TypeScript codebase with an ORM or a validation decorator, this is that
        edit. Class, method, property, accessor and parameter decorators alike.
      * **Parameter properties.** ``constructor(private readonly x: string)``
        declares a class property and a parameter at once; it appears in both
        renderings.
      * **``this`` parameters.** ``function f(this: HTMLElement, x: string)``.
        The TYPE is contract; the name is fixed by the grammar and cannot be
        renamed, so the receiver question the Go table settles does not arise.
      * **Getters and setters**, folded into ONE member key with a marker for
        which accessors exist. Deleting a setter makes a property read-only to
        every consumer, with no error in this file.
      * **Top-level ``const`` / ``let`` / ``var``**, which is the largest
        deliberate departure from both the Python and the Go contracts, both of
        which ignore module-level and package-level bindings. It is departed
        from because bare parity is the argument this section exists to
        distrust, and here the analogy breaks outright: in TypeScript —
        overwhelmingly so in the 475 ``.tsx`` files of the primary target —
        ``export const Button: React.FC<Props> = props => …`` **is** how a
        function is declared. ``function f() {}`` and ``const f = () => {}``
        are two spellings of one declaration, and a comparator that reads the
        first and ignores the second is not a parity decision, it is a hole
        with a syntax key. Every top-level binding is a symbol; the fingerprint
        is:

          1. the declared type annotation, if there is one; else
          2. the type of a ``satisfies`` expression, if the initialiser is one
             (``const config = {…} satisfies Config`` is the author declaring
             the contract in the only place TypeScript lets them declare it
             without widening — the brief's ``satisfies`` question, ruled in);
             else
          3. the signature — type parameters, parameters, return annotation —
             of the initialiser when it is an arrow function or a function
             expression; else
          4. the marker meaning **no declared type**.

        In no case is the initialiser's VALUE fingerprinted; that is a body
        concern, exactly as the Python contract rules a parameter default's
        value to be. Rendering ``no declared type`` as a marker rather than
        omitting the symbol is what keeps the rule total: adding or removing an
        annotation is then a fingerprint change on a stable key rather than the
        addition or removal of a symbol, and "added symbol" would have meant
        "not a change".

        A destructuring binding (``const { a, b } = obj``) yields one symbol
        per bound identifier, all carrying the declaration's annotation if it
        has one and the ``no declared type`` marker otherwise. That is a coarse
        answer and it is named as one.

    THE POSITIONS WHERE A TYPE HAS NO SUB-SYMBOL — trap 2, and the rule that
    retires the whole class
    -----------------------------------------------------------------------
    The Go unit lost interface-literal signatures in six positions because the
    name/signature split was right for the one shape that has sub-symbols and
    wrong everywhere else. TypeScript has far more such positions, because an
    anonymous object type, function type, mapped type or conditional type may
    appear anywhere a type may appear. Enumerated, so the enumeration can be
    checked rather than trusted — a structural type with no sub-symbol behind
    it occurs in:

      1. a type alias' right-hand side, at any depth
         (``type A = { m(): void } | ((a: string) => void)``);
      2. a parameter's type; 3. a return type; 4. a property's type;
      5. a type parameter's ``extends`` constraint; 6. its default;
      7. an index signature's key or value type;
      8. a type argument anywhere (``Promise<{ m(): void }>``);
      9. a ``extends`` / ``implements`` clause's type arguments;
      10. a variable, parameter-property or class-property annotation;
      11. the body of a mapped type (``{ [K in keyof T]: () => T[K] }``);
      12. either branch of a conditional type, and its ``infer`` positions;
      13. a tuple element, including labelled and optional ones;
      14. a ``typeof`` / ``keyof`` / indexed-access operand;
      15. a template-literal type's placeholders;
      16. an overload signature's parameter and return types;
      17. a rest parameter's element type;
      18. a type predicate's asserted type (``x is { m(): void }``);
      19. a ``satisfies`` operand under the ``const`` rule above.

    Rather than rule on nineteen positions, this contract adopts the rule that
    makes the list moot and states it as an invariant P2 should seal directly:

      **No rendering position in this grammar is name-only. Every type
      expression renders its full structure wherever it appears, and
      sub-symbols are ADDITIONAL reporting granularity, never the sole storage
      of a signature.**

    That is strictly stronger than the Go contract, which renders a top-level
    interface definition's methods by name only *because* each has an
    ``Iface.Method`` sub-symbol — the split that produced the defect. The price
    is paid in exactly one place and it is small: a member of an interface is
    stored in the interface's own fingerprint, which is why interface members
    are NOT emitted as separate symbols here. A class's methods ARE separate
    symbols **as well**, and there the price is real — an edit to ``C.m``
    changes both ``i:C/i:m`` and, through the class rendering, ``i:C`` — so a
    report may carry two rows for one edit. That redundancy is accepted
    deliberately: the Go unit took the other trade and it cost six lost
    positions, and this project's stated stance is that a visible duplicate row
    is cheaper than a silent pass.

    **P4 ADJUDICATION, 2026-08-10 — the class-method contradiction, ruled.**
    Two sentences of this contract could not both hold. One said a method's
    rendering is inside the class fingerprint (the paragraph above, and the
    header's accepted false positive "an edit to a class method is reported
    twice"); the other said adding a method to a class is NOT a change, which is
    true only if the class fingerprint does not carry the method. The seal
    author's reference implementation had to choose, chose sub-symbols-only to
    satisfy the ruled row, and flagged it rather than choosing quietly. The
    ruling goes the other way, and the reason is the invariant immediately
    above rather than a preference between two costs:

      *sub-symbols are ADDITIONAL reporting, never the sole storage of a
      signature.* Rendering a class's members by name in ``i:C`` and storing
      the signature only under ``i:C/i:m`` is a name-only rendering position,
      which this grammar does not have. It is also, precisely, the Go split:
      Go's interface elements were name-only, the signature lived in the
      sub-symbol, and that arrangement lost signatures in **six** positions. It
      lost them where no sub-symbol existed; the answer here is not "a class
      method always has a sub-symbol, so this instance is safe" but that a
      contract with one name-only position has to be checked position by
      position, which is the enumeration this section retired.

    The transfer from Python that the old ruling rested on was invalid, and
    that is worth naming rather than overruling silently. Python's "a body may
    add private helpers" is a CONSEQUENCE of Python's mechanism —
    :func:`_class_fingerprint` carries bases, decorators and annotated fields
    and does not carry methods — not a principle standing above it. This
    grammar adopted a different mechanism on purpose. Transferring Python's
    conclusion while rejecting Python's mechanism is how two sentences came to
    contradict each other.

    So, exhaustively, for every containing declaration this grammar has:

      * **adding a member to an interface, type literal or enum IS a change** —
        it is inside the containing type's fingerprint. This is correct on its
        own merits: an added required member breaks every implementor.
      * **adding a member to a class IS a change**, method and property alike,
        because both are rendered inside the class fingerprint. The property
        half is Python's rule for annotated class-level assignments transferred
        intact; the method half is this ruling.
      * the same edit also adds the sub-symbol ``i:C/i:m``, and an ADDED symbol
        is not a change — so the verdict comes from the class fingerprint
        moving, and the new sub-symbol is the report row that says which member
        did it.

    THE COST, stated rather than discovered. A body agent may no longer add a
    private helper METHOD to an existing class without the gate reporting a
    signature change; it must put the helper in a new type, at module level, or
    get a ruling. That is a false positive by the criterion this contract uses
    everywhere else — ``private`` and ``#`` members break no external caller —
    and it is accepted for the reason the decorator and struct-tag rows are
    accepted: this project's stance is that a visible false positive is cheaper
    than a silent pass, and the alternative here is not a smaller false
    positive but a name-only position in a grammar that has ruled it has none.
    Narrowing it later — excluding ``private``/``#`` members from the class
    rendering — is a coherent future ruling and is deliberately NOT taken now,
    because ``private`` is erased at compile time, still occupies a name a
    subclass must not collide with, and would reintroduce exactly one
    position that has to be argued on its own.

    JSX — 475 of the 996 target files, and the ruling is that it is out
    ------------------------------------------------------------------
    **No JSX syntax appears in any fingerprint, and this is not a gap.** A JSX
    element is an EXPRESSION. Expressions occur in initialisers and in function
    bodies, and bodies are the work this gate exists to permit. There is no
    declaration form in TypeScript whose JSX content is part of a contract.

    What ``.tsx`` does change is the PARSE, and that is the whole of its effect
    on this comparator: the dialect must come from the path, because the same
    bytes mean different things (measured — ``const x = <T>(y);`` is a type
    assertion in ``.ts`` and an unterminated JSX element in ``.tsx``, and the
    ``<T,>`` trailing comma is the ``.tsx`` idiom for a generic arrow that
    would be a syntax oddity elsewhere). This is exactly the case
    :class:`SignatureFingerprinter` means when it says ``path`` is passed "for
    language-dialect decisions a suffix implies".

    A consequence worth stating so nobody reads the JSX exclusion as
    ``.tsx`` coverage being thin: a React component's contract is its **props
    type** and its **declared signature**, both of which are fingerprinted in
    full by the ``const`` rule and the interface rule above. What is not read is
    the markup it returns, which is its body.

    JSX *type* declarations are a different thing and are IN by the ordinary
    path: ``declare global { namespace JSX { interface IntrinsicElements {…} } }``
    is a namespace and an interface, and is read as such.

    DELIBERATELY EXCLUDED, each with its reason
    -------------------------------------------
      * **Function and method bodies, and anything declared inside one.** The
        work the gate exists to permit.
      * **Comments and JSDoc.** Parity with both other contracts: a docstring
        is P1's and P3 may extend it.
      * **``import`` declarations, including ``import type``.** Parity with the
        Go contract, and for its reason: imports are not this module's
        declarations. The same recorded consequence follows — type expressions
        are compared AS WRITTEN, so renaming an import alias rewrites every
        annotation mentioning it and every one reads as a change. Visible,
        named, and a violation rather than a silent pass. Note the asymmetry
        with the export surface, which IS read: an import is what this module
        consumes, an export is what it promises.
      * **Type identity and resolution.** ``Foo`` from two different modules
        fingerprints identically; an alias is not followed; a type is not
        expanded. Syntactic, like both other contracts, and for the same
        reason.
      * **Initialiser values, default values, and every other expression.**
      * **``.mts``, ``.cts``, ``.js``, ``.jsx``, ``.mjs``, ``.cjs``.** Not in
        :data:`TYPESCRIPT_SUPPORT`'s ``extensions``. The primary target contains
        zero of the first two (measured) and this contract has no opinion about
        JavaScript. Named as a gap so its absence is a state rather than an
        oversight; note that ``.mts`` would NOT be picked up by the ``.ts``
        entry, since matching is a suffix match and ``".mts".endswith(".ts")``
        is false.

    NORMALISATION, and the one measurement P3 must not skip
    -------------------------------------------------------
    Two revisions that mean the same thing must fingerprint identically. The
    Go side gets this from ``go/printer``. **TypeScript's printer does not
    provide it**, and this was measured on 2026-08-10 rather than assumed:
    ``ts.createPrinter().printNode(…, sourceFile)`` reuses the original source
    text for many nodes, so ``type A = 'x'`` and ``type B = "x"`` print with
    their original quotes. A fingerprint built naively on ``printNode`` would
    report a signature change for every string-literal type in the repository
    the day someone changes a Prettier setting.

    So the renderer is this unit's own, and it must not depend on original
    source text. At minimum it must normalise: string-literal quoting; numeric
    literal spelling (``1``, ``1.0``, ``0x1``, ``1_000``); redundant
    parenthesisation; ``;`` versus ``,`` versus newline as an object-type member
    separator; trailing commas; line breaks and indentation inside parameter
    and type-parameter lists; and the ``T[]`` / ``Array<T>`` pair is
    deliberately NOT normalised, because they differ under ``readonly`` and
    this comparator has no checker with which to know when they do not.

    FAILURE
    -------
    Raises :class:`SourceUnparseable` when the helper reports a parse error —
    which, per :class:`TsHelperResponse`, means **any** parse diagnostic — and
    :class:`ComparatorUnavailable` carrying the named fault otherwise. The
    mapping uses the existing six and adds none:

      * ``node`` not on PATH → :attr:`ComparatorFault.TOOLCHAIN_MISSING`;
      * ``node`` present but its version probe fails, times out, exits
        non-zero, or reports less than :data:`TS_NODE_MINIMUM_VERSION`; or the
        vendored parser loads and reports a ``ts.version`` below
        :data:`TS_PARSER_MINIMUM_VERSION` →
        :attr:`ComparatorFault.TOOLCHAIN_UNUSABLE`. A parser present but too
        old is the direct analogue of :func:`_probe_go_toolchain`'s
        language-version refusal: it would fail as a parse error and blame the
        branch for the age of the install;
      * **the probe does not report the loaded parser, or reports one that is
        not the vendored file** → :attr:`ComparatorFault.TOOLCHAIN_UNUSABLE`.
        P4 ruling, 2026-08-10, task #15. The digest verifies BYTES ON DISK and
        the version verifies a STRING; neither says which file the helper
        process loaded, and a version is equally true of an ambient copy — the
        target checkout vendors TypeScript 5.9.3, the same release this build
        pins. ``--probe`` therefore reports ``parser``, the filename Node
        resolved for the module the helper is holding, and
        :func:`_probe_node_and_parser` compares it against the vendored file by
        identity. Without it, "the parser is loaded by absolute path" was a
        property no seal on any machine could falsify;
      * the helper directory, entry point, vendored parser or license is
        missing, or escapes the package by symlink →
        :attr:`ComparatorFault.HELPER_MISSING` (:func:`ts_parser_home`);
      * the helper exits non-zero → :attr:`ComparatorFault.HELPER_FAILED`;
      * it exceeds :data:`_HELPER_TIMEOUT_SECONDS` →
        :attr:`ComparatorFault.HELPER_TIMEOUT`;
      * its stdout is not a well-formed document of :data:`TS_HELPER_SCHEMA` →
        :attr:`ComparatorFault.HELPER_OUTPUT_INVALID`
        (:func:`decode_ts_helper_response`).

    Every one is terminal for the file: no retry, no fallback parser, no
    degraded mode. **And the load-bearing consequence of the whole design: a
    parser the branch can write never produces a CHECKED verdict, because a
    parser the branch can write is never reached.** The reachable states are "a
    trusted parser answered" and "a fault", and every fault maps through
    :func:`signature_status_for_fault` to
    ``UNCHECKED_COMPARATOR_UNAVAILABLE``, which is blocking on BODIES.

    Not implemented, and not enrolled: see :data:`TYPESCRIPT_SUPPORT`.
    """

    def fingerprints(self, path: str, text: str) -> dict[str, str]:
        """One revision of one TypeScript file → symbol → fingerprint.

        The steps, so the seal author knows which fault belongs to which:
        resolve the trusted parser (:func:`ts_parser_home` →
        :attr:`ComparatorFault.HELPER_MISSING`), find and probe ``node``
        (:attr:`ComparatorFault.TOOLCHAIN_MISSING`,
        :attr:`ComparatorFault.TOOLCHAIN_UNUSABLE`), run the helper under
        :func:`_node_toolchain_environment` with
        :func:`encode_ts_helper_request` on stdin and
        :data:`_HELPER_TIMEOUT_SECONDS` as the budget
        (:attr:`ComparatorFault.HELPER_TIMEOUT`,
        :attr:`ComparatorFault.HELPER_FAILED`), decode stdout
        (:attr:`ComparatorFault.HELPER_OUTPUT_INVALID`), and turn a
        ``parse_error`` document into :class:`SourceUnparseable`.

        Ordering the parser resolution FIRST is deliberate and differs from the
        Go helper's order, which probes the toolchain before the helper source.
        Here the parser is the thing whose provenance is in question, so the
        first message an operator sees on an unconfigured machine names it:
        "no trusted TypeScript parser is installed", not "no node on PATH".

        The resolution, the probe and any warm-up are once per PROCESS, cached
        in memory and never on disk between runs — see
        :data:`_GO_HELPER_PREPARED` for the argument, which transfers whole: a
        cache under ``/tmp`` would be a file outside :data:`FLOOR_GLOBS` whose
        bytes decide what a signature is. Unlike Go there is no compile step,
        so the cached object is the resolved directory and the probe result.

        **The cache is a module global named ``_TS_HELPER_PREPARED``, and the
        name is CONTRACT (P4 adjudication, 2026-08-10).** It is the exact
        analogue of :data:`_GO_HELPER_PREPARED`, it starts as ``None``, and
        rebinding it to ``None`` must make the next call re-resolve, re-probe
        and re-verify from scratch — a fresh gate process, simulated.

        This is written into the contract because a seal already requires it.
        The digest is verified AT USE rather than at fetch, and "at use" has no
        falsifiable form without a way for a seal to say *this is a new use*;
        inside one pytest process the only way to say it is to clear the cache.
        The coupling was reported by the seal author as a private name a seal
        reaches for, and it is RULED ACCEPTABLE — but a private name a seal
        depends on is a contract whether or not anyone writes it down, and an
        unwritten contract is the thing this unit exists to refuse. So it is
        written down here, where P3 reads it, rather than left in a fixture.

        What is NOT added, and the refusal is the substance of the ruling: no
        public reset entry point, and no supported way to make a running
        process re-prepare. The cache is per-process BY CONTRACT and a gate
        runs a fresh process per verdict, so there is no production caller with
        a reason to reset it; a public reset would be machinery whose only user
        is a test, and machinery on the verdict path that exists for a test is
        exactly how a fail-open arrives. The corollary is recorded rather than
        sealed, as the seal author had it: a tamper landing AFTER a process has
        prepared its parser is not caught by that process. Sealing against that
        would be sealing against this paragraph.

        May return an empty mapping ONLY for a file that genuinely declares
        nothing. Never to signal a failure: an empty mapping is a CHECKED
        comparison with no changes, which is a pass bought by having read
        nothing.

        **THE DIGEST STEP, added by the D4 vendoring commit (operator ruling,
        2026-08-10), and it is IMPLEMENTED rather than contracted.** The
        resolution step above is now :func:`_ts_prepared_parser`, which resolves
        AND recomputes the parser's sha256 against
        :data:`TS_VENDORED_PARSER_SHA256` before returning a directory. It is
        the first statement of this method and it runs before every other step,
        which is what "verified at use" means operationally: no path through
        this method reaches ``node`` with bytes that were not hashed by the
        process that is about to load them.

        It is written here, and not left with the rest of the body, because the
        parser is a separately-versioned artifact fetched into a mutable path
        (see the ruling recorded at :data:`TS_VENDORED_PARSER_SHA256`). A fetch
        whose product is only checked at fetch time is the design the scaffold
        rejected ``npx`` for. So the check lands with the fetch mechanism, in
        the same commit, and the body that follows inherits a parser it can
        trust rather than a promise that one will be checked later.

        Until that body exists this method raises ``NotImplementedError`` — but
        it raises it AFTER the preparation, so on a machine whose parser has
        been tampered with the answer is already the fault rather than "not
        implemented". Ordering it the other way would have left the digest
        untestable until P3 landed, which is the shape of a check nobody ever
        measures.
        """
        directory = _ts_prepared_parser()
        response = decode_ts_helper_response(
            _run_ts_helper(_ts_prepared_node(directory), directory, path, text)
        )
        if response.parse_error is not None:
            # A fact about the FILE, established by working apparatus — so it
            # is not a fault, and `compare_signatures` reports it as
            # UNCHECKED_UNPARSEABLE rather than as a broken machine. Any
            # diagnostic at all reaches here: see `TsHelperResponse`.
            raise SourceUnparseable(path, f"typescript: {response.parse_error}")
        # Declaration order, which the helper guarantees and dicts preserve.
        return {symbol.symbol: symbol.fingerprint for symbol in response.symbols}


@dataclass(frozen=True)
class TsSignatureEditRuling:
    """One ruled edit: does it change a TypeScript signature, or is it body work?

    A row of :data:`TS_SIGNATURE_EDIT_RULINGS`, and the same instrument as
    :class:`GoSignatureEditRuling` — a ruling that is a table row is something
    P2 asserts against and P3 implements to, where a ruling that is a paragraph
    is something a seal author guesses at and a P4 adjudicates.

    ``path`` is part of the row because it selects the parse dialect, and the
    ``.tsx`` rows would parse differently without it. ``python_analogue``
    carries the same edit transliterated to Python where the edit HAS one, so
    the row is checkable against a live comparator today; None is the recorded
    claim that the languages differ there, or that Python has no such shape.
    """

    name: str
    path: str
    before: str
    after: str
    is_a_change: bool
    rationale: str
    python_analogue: tuple[str, str] | None = None


#: The acceptance criterion for :class:`TypeScriptSignatureFingerprinter` and
#: the thing P2 seals against. Rows with a ``python_analogue`` are checkable
#: against the live Python comparator today, as the Go table's are, so the
#: parity claims are measured rather than asserted.
#:
#: Every row is a complete file. The CONTROL rows (a body rewritten, JSX
#: rewritten, a string requoted, an un-annotated initialiser changed) are not
#: filler: without them a comparator that answered "changed" to everything
#: would satisfy the table, which is the failure mode the Go table names.
TS_SIGNATURE_EDIT_RULINGS: tuple[TsSignatureEditRuling, ...] = (
    TsSignatureEditRuling(
        name="parameter renamed",
        path="m.ts",
        before="export function move(src: string, dst: string): void {}\n",
        after="export function move(source: string, target: string): void {}\n",
        is_a_change=True,
        rationale=(
            "THE TRANSFERRED RULING. Checked rather than assumed: the Go "
            "argument holds unchanged in TypeScript, because a syntactic "
            "single-file comparison cannot distinguish this from the same-type "
            "reorder below. Breaks no caller on its own; that is the accepted "
            "price of the next row"
        ),
        python_analogue=(
            "def move(src, dst):\n    pass\n",
            "def move(source, target):\n    pass\n",
        ),
    ),
    TsSignatureEditRuling(
        name="same-type parameters reordered",
        path="m.ts",
        before="export function move(src: string, dst: string): void {}\n",
        after="export function move(dst: string, src: string): void {}\n",
        is_a_change=True,
        rationale=(
            "THE REASON FOR THE RULING ABOVE. Type-identical, every call site "
            "compiles, every one now means the opposite. TypeScript has no "
            "named arguments, so there is no compiler check anywhere"
        ),
        python_analogue=(
            "def move(src, dst):\n    pass\n",
            "def move(dst, src):\n    pass\n",
        ),
    ),
    TsSignatureEditRuling(
        name="type parameters reordered",
        path="m.ts",
        before="export type Pair<K, V> = { key: K; value: V };\n",
        after="export type Pair<V, K> = { key: K; value: V };\n",
        is_a_change=True,
        rationale=(
            "The parameter-reorder argument one level up the type system. "
            "Every `Pair<A, B>` in the codebase silently swaps meaning and "
            "most will still typecheck when A and B are structurally similar"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="destructured parameter's bindings reordered",
        path="m.ts",
        before=(
            "export function draw({ x, y }: { x: number; y: number }): void {}\n"
        ),
        after=(
            "export function draw({ y, x }: { x: number; y: number }): void {}\n"
        ),
        is_a_change=False,
        rationale=(
            "THE BOUNDARY, and the check on the criterion — the receiver row "
            "of this table. Destructuring binds BY NAME, so the pattern "
            "carries no ordering information and no caller can be made "
            "silently wrong by permuting it. The binding names are body-local "
            "and are not fingerprinted; the parameter's TYPE is. Same "
            "criterion as the two rows above, opposite answer"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="body rewritten, declaration untouched",
        path="m.ts",
        before="export function move(src: string, dst: string): void {}\n",
        after=(
            "export function move(src: string, dst: string): void {\n"
            "  const from = src;\n  const to = dst;\n  void from;\n  void to;\n"
            "}\n"
        ),
        is_a_change=False,
        rationale=(
            "THE CONTROL. This is the work the gate EXISTS to permit and it "
            "must stay silent. Without this row a comparator that answered "
            "'changed' to every other row here would pass the table"
        ),
        python_analogue=(
            "def move(src, dst):\n    pass\n",
            "def move(src, dst):\n    _ = src\n    _ = dst\n    return None\n",
        ),
    ),
    TsSignatureEditRuling(
        name="JSX markup rewritten in a component body",
        path="Button.tsx",
        before=(
            "export interface Props { label: string }\n"
            "export const Button = (p: Props) => <button>{p.label}</button>;\n"
        ),
        after=(
            "export interface Props { label: string }\n"
            "export const Button = (p: Props) => (\n"
            "  <button className=\"primary\" onClick={() => undefined}>\n"
            "    <span>{p.label}</span>\n  </button>\n);\n"
        ),
        is_a_change=False,
        rationale=(
            "THE JSX RULING, as a control. A JSX element is an EXPRESSION and "
            "expressions live in bodies. 475 of the target's 996 TypeScript "
            "files are .tsx and none of them has JSX in a declaration "
            "position. What .tsx changes is the PARSE DIALECT, nothing else — "
            "which is why `path` is on the row and on "
            "`SignatureFingerprinter.fingerprints`"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="a component's props type gains a required member",
        path="Button.tsx",
        before=(
            "export interface Props { label: string }\n"
            "export const Button = (p: Props) => <button>{p.label}</button>;\n"
        ),
        after=(
            "export interface Props { label: string; onClick: () => void }\n"
            "export const Button = (p: Props) => <button>{p.label}</button>;\n"
        ),
        is_a_change=True,
        rationale=(
            "The other half of the JSX ruling: .tsx coverage is real. An "
            "interface member is inside the interface's own fingerprint (no "
            "sub-symbols for interface members — see the trap-2 rule), so "
            "adding one is a change, and it should be: every existing "
            "`<Button label=…/>` call site now fails to compile, which is the "
            "contract break a body agent is not allowed to make unilaterally"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="an overload added",
        path="m.ts",
        before=(
            "export function f(x: string): string;\n"
            "export function f(x: any): any { return x; }\n"
        ),
        after=(
            "export function f(x: string): string;\n"
            "export function f(x: number): number;\n"
            "export function f(x: any): any { return x; }\n"
        ),
        is_a_change=True,
        rationale=(
            "Widening, which is the half of the build protocol this gate "
            "enforces, and it hides here better than anywhere else: no "
            "existing signature changed. It is a change because an overload "
            "set folds into ONE symbol whose fingerprint is the ordered list "
            "of its signatures — so 'an added symbol is not a change' does not "
            "apply, and must not"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="two overloads reordered",
        path="m.ts",
        before=(
            "export function f(x: string): string;\n"
            "export function f(x: unknown): number;\n"
            "export function f(x: any): any { return x; }\n"
        ),
        after=(
            "export function f(x: unknown): number;\n"
            "export function f(x: string): string;\n"
            "export function f(x: any): any { return x; }\n"
        ),
        is_a_change=True,
        rationale=(
            "TypeScript resolves an overload set in DECLARATION ORDER. After "
            "this edit `f('a')` returns number rather than string, at every "
            "call site, with no error. The parameter-reorder inversion moved "
            "up to the overload set"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="export removed from a declaration",
        path="m.ts",
        before="export function helper(a: string): void {}\n",
        after="function helper(a: string): void {}\n",
        is_a_change=True,
        rationale=(
            "Silent narrowing with no error in this file: the declaration is "
            "unchanged and the module's API lost a member. `export` is a "
            "modifier and modifiers are IN. This is what 'tidy up unused "
            "exports' looks like from inside a body task"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="a public name re-exported under a different alias",
        path="m.ts",
        before="function h(): void {}\nexport { h as handle };\n",
        after="function h(): void {}\nexport { h as run };\n",
        is_a_change=True,
        rationale=(
            "No declaration changed at all — a declaration-only comparator "
            "sees nothing — and every importer breaks. The export surface is "
            "read as symbols under `k:export` for exactly this row"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="a required property made optional",
        path="m.ts",
        before="export interface Bet { amountCents: number }\n",
        after="export interface Bet { amountCents?: number }\n",
        is_a_change=True,
        rationale=(
            "`?` is a modifier and modifiers are IN. It widens the type for "
            "producers and narrows every consumer that reads the field, and "
            "on a money field it is the difference between a required amount "
            "and undefined"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="a decorator's argument changed",
        path="m.ts",
        before=(
            "export class Bet {\n"
            "  @Column({ name: 'amount_cents' })\n"
            "  amountCents!: number;\n}\n"
        ),
        after=(
            "export class Bet {\n"
            "  @Column({ name: 'amount' })\n"
            "  amountCents!: number;\n}\n"
        ),
        is_a_change=True,
        rationale=(
            "THE STRUCT-TAG ROW. The declared shape is identical and the "
            "storage contract is not: every read and write of this type now "
            "names a different column, with no error anywhere. Decorators are "
            "rendered in FULL including arguments — a parity break with "
            "Python, which fingerprints decorator names only, for the reason "
            "the Go contract gives for tags"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="enum members reordered",
        path="m.ts",
        before="export enum Stage { Draft, Live, Settled }\n",
        after="export enum Stage { Live, Draft, Settled }\n",
        is_a_change=True,
        rationale=(
            "Implicit numeric values follow declaration order, so this "
            "rewrites Draft from 0 to 1 and Live from 1 to 0. Anything "
            "persisted, transmitted or compared numerically inverts. The one "
            "member list in this contract that is ordered rather than sorted, "
            "and the boundary that shows the sorting rule is a criterion "
            "rather than a convenience"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="interface members reordered",
        path="m.ts",
        before="export interface Bet { amountCents: number; id: string }\n",
        after="export interface Bet { id: string; amountCents: number }\n",
        is_a_change=False,
        rationale=(
            "CONTROL for the sorting rule, and a deliberate parity break with "
            "the Go struct-field rule. A Go struct's field order is memory and "
            "wire layout; an object type's member order is visible to nobody. "
            "No caller can be made silently wrong, so ordering buys no reorder "
            "catch and costs a false positive on every alphabetise edit"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="a class method added",
        path="m.ts",
        before="export class Svc {\n  do(a: string): void {}\n}\n",
        after=(
            "export class Svc {\n  do(a: string): void {}\n"
            "  private helper(b: number): void {}\n}\n"
        ),
        is_a_change=True,
        rationale=(
            "P4 ADJUDICATION 2026-08-10, and this row was RULED THE OTHER WAY "
            "in the P1 scaffold. It read 'Python's a body may add private "
            "helpers, transferred', which contradicted the same contract's "
            "statement that a method's rendering is inside the class "
            "fingerprint; both could not hold and the seal author's reference "
            "implementation had to pick one to satisfy this row. The class "
            "fingerprint carries its members in full, because the trap-2 "
            "invariant is that no rendering position in this grammar is "
            "name-only and sub-symbols are never the sole storage of a "
            "signature — the split that lost the Go unit six positions. So "
            "adding a member to a class moves `i:C`, method and property "
            "alike, and the added `i:C/i:m` sub-symbol is the report row that "
            "says which member did it. The cost is a real false positive on a "
            "private helper and it is accepted, for the reason the decorator "
            "row is accepted. The Python parity claim is DROPPED rather than "
            "quietly kept: Python answers NOT a change here, which makes this "
            "a deliberate parity BREAK like top-level `const`, and it is "
            "measured as a break by "
            "`test_the_class_method_parity_break_is_measured_and_not_a_drift`"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="a class property added",
        path="m.ts",
        before="export class Svc {\n  do(a: string): void {}\n}\n",
        after=(
            "export class Svc {\n  private cache: Map<string, number> "
            "= new Map();\n  do(a: string): void {}\n}\n"
        ),
        is_a_change=True,
        rationale=(
            "The strictest row here, inherited whole from Python, where class "
            "field lists ARE the contract. A body agent that needs new state "
            "puts it in a new type or gets a ruling. Named as ruled rather "
            "than accidental, exactly as the Go struct-field row is"
        ),
        python_analogue=(
            "class Svc:\n    def do(self, a):\n        pass\n",
            "class Svc:\n    cache: dict\n    def do(self, a):\n        pass\n",
        ),
    ),
    TsSignatureEditRuling(
        name="a string-literal type requoted",
        path="m.ts",
        before="export type Mode = 'live' | 'draft';\n",
        after='export type Mode = "live" | "draft";\n',
        is_a_change=False,
        rationale=(
            "CONTROL, and the one P3 is most likely to fail. Measured "
            "2026-08-10: `ts.createPrinter().printNode(node, sourceFile)` "
            "reuses ORIGINAL SOURCE TEXT and prints these two differently, so "
            "a fingerprint built on the TypeScript printer reports a signature "
            "change for every string-literal type in the repository the day a "
            "Prettier setting changes. The renderer must not depend on source "
            "text; see the normalisation list on the fingerprinter"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="an un-annotated const's initialiser changed",
        path="m.ts",
        before="export const config = { retries: 3 };\n",
        after="export const config = { retries: '3' };\n",
        is_a_change=False,
        rationale=(
            "THE BLIND SPOT, ruled rather than left to be discovered. The "
            "public type of `config` changed from { retries: number } to "
            "{ retries: string } and this comparator reports nothing, because "
            "the type is INFERRED and inference is exactly what a syntactic "
            "single-file reader cannot do. The remedy is a project convention "
            "(annotate or `satisfies` on exported constants), not a comparator "
            "change — a comparator that guessed here would need a type checker "
            "and a resolvable program, and would then be reading the branch's "
            "own tsconfig"
        ),
        python_analogue=None,
    ),
    TsSignatureEditRuling(
        name="an arrow const's declared signature changed",
        path="m.ts",
        before="export const parse = (raw: string): number => Number(raw);\n",
        after="export const parse = (raw: string, radix: number): number =>\n"
        "  parseInt(raw, radix);\n",
        is_a_change=True,
        rationale=(
            "THE DEPARTURE FROM PARITY, as a row. Python and Go both ignore "
            "module- and package-level bindings; this contract does not, "
            "because in TypeScript — and overwhelmingly in the target's 475 "
            ".tsx files — `const f = () => {}` IS how a function is declared. "
            "Ignoring one spelling of 'declare a function' while reading the "
            "other is not parity, it is a hole with a syntax key"
        ),
        python_analogue=None,
    ),
)


#: TypeScript's row: **ENROLLED, 2026-08-10, and this is what changed.** It is
#: in :data:`COMPARATORS`, so :func:`support_for_path` returns it and a ``.ts``
#: or ``.tsx`` path is READ. Until that commit it was in
#: :data:`PENDING_COMPARATORS` and such a path was answered exactly as it was
#: before this unit — UNCHECKED_UNSUPPORTED_LANGUAGE, promoted to
#: UNCHECKED_NO_SUPPORTED_FILE on a diff with nothing else in it, CLEAN on
#: BODIES. **That abstention is now a positive claim**, and the sign change was
#: measured in both directions through :func:`check_branch` on a real repository
#: rather than inferred from a green suite; the enrolment commit carries the
#: numbers.
#:
#: **AND IT NEWLY BLOCKS ONE CLASS OF BRANCH**, recorded here because the Go
#: enrolment found :func:`check_branch`'s "can never newly block" claim false
#: and this row is the second witness: a ``.ts`` file that does not parse is
#: UNCHECKED_UNPARSEABLE, which refuses a BODIES branch, and the identical
#: branch was CLEAN before enrolment (measured: UNDETERMINED /
#: UNCHECKED_UNPARSEABLE). The class is empty on the primary target today — the
#: soak below read 39,781 files with zero parse failures — so nothing regresses
#: now, but it is a real change in what this gate refuses and not a no-op.
#:
#: ``.d.ts`` is NOT a separate entry and cannot be one:
#: :func:`validate_registry` refuses an extension that is a suffix of another,
#: and ``.d.ts`` ends with ``.ts``. It needs none — a declaration file is
#: nothing but signature and the ``.ts`` row reads it. ``.mts`` and ``.cts`` are
#: absent and are NOT covered by ``.ts`` either, since matching is a suffix
#: match; the primary target contains zero of them.
#:
#: **ENROLMENT IS A TWO-LINE MOVE** — adding this row to :data:`COMPARATORS`
#: **and removing it from** :data:`PENDING_COMPARATORS`. Doing only the first
#: leaves the row in both tuples, :func:`validate_registry` raises at import and
#: the whole suite fails collection. That correction cost the Go row a P4
#: amendment on 2026-08-10; it is written here so this row does not repeat it,
#: and it did not.
#:
#: It could not happen until all of these held. Three of them were somebody
#: else's commit, and the first was the one that might have sunk the approach.
#: **All five are now met** and each carries the evidence that met it:
#:
#:   1. **A pinned TypeScript parser is vendored** into
#:      ``src/claude_dispatcher/ts_signature_fingerprint/`` as a flat trio —
#:      ``main.cjs``, ``typescript.js``, ``LICENSE.typescript.txt`` — and
#:      ``pyproject.toml`` ships ``ts_signature_fingerprint/*``. **NOT DONE, and
#:      not P1's to do.** State the cost honestly rather than let it be
#:      discovered at review: ``typescript.js`` is **9.1 MB** (measured, 5.9.3),
#:      it is third-party code, and this repository has never carried a
#:      vendored dependency. A 9 MB blob entering the git history of the module
#:      that decides every verdict is a review nobody has yet agreed to do, and
#:      it recurs at every parser upgrade. If that is refused, the honest
#:      outcome is that this row stays pending forever and TypeScript stays
#:      UNCHECKED — which is the state this scaffold ships and is why the
#:      refusal is designed to be survivable rather than to be a stopgap.
#:
#:      **PARTLY DONE, and the blob review the scaffold feared was REFUSED —
#:      operator ruling, 2026-08-10.** The parser does not enter this
#:      repository's history at all. It is a separately-versioned artifact:
#:      pinned by :data:`TS_VENDORED_PARSER_SHA256` and
#:      :data:`TS_VENDORED_PARSER_TARBALL_INTEGRITY`, fetched at install time by
#:      ``python3 -m claude_dispatcher.ts_parser_vendor`` into the path
#:      :func:`ts_parser_home` names, gitignored so it cannot be committed by
#:      accident, and — the part that makes it survivable — **verified at USE**
#:      by :func:`_ts_prepared_parser` rather than at fetch. So the largest file
#:      this repository tracks is unchanged, and the parser's review is a
#:      64-character constant on the floor instead of 9.1 MB nobody reads.
#:      What is still outstanding under this item is ``main.cjs``, which is P3's
#:      and is a few hundred reviewable lines like the Go helper's; until it
#:      lands :func:`ts_parser_home` still refuses, with the entry point named.
#:
#:      **DONE (P3, 2026-08-10):** ``main.cjs`` has landed. It is the first
#:      file the subtree glob on :data:`FLOOR_GLOBS` actually covers, it loads
#:      the parser by the path :func:`ts_parser_home` gives it and never by
#:      ``require('typescript')``, and its own header records the rendering
#:      grammar — the one thing about this unit that is stated nowhere else.
#:      ``pyproject.toml`` ships ``ts_signature_fingerprint/*`` as of the same
#:      commit, so a wheel built on a machine that ran the fetcher carries the
#:      parser and one built on a machine that did not is HELPER_MISSING — a
#:      named, blocking state, which is the correct answer for a broken install.
#:   2. :data:`FLOOR_GLOBS` covers
#:      ``**/src/claude_dispatcher/ts_signature_fingerprint/**`` **before**
#:      anything is vendored into it, and ``scripts/check_body_branch.sh`` reads
#:      it from the protected base. P4's commit, because the floor's
#:      ``_FLOOR_ROWS`` table is a seal P3 may not edit. **DONE (P4,
#:      2026-08-10):** the glob is on the floor above with four rows in
#:      ``_FLOOR_ROWS``, and the script needed no change — MEASURED rather than
#:      inherited from the Go entry, in a clone with a real repo: a self-judging
#:      checkout whose base carried
#:      ``src/claude_dispatcher/ts_signature_fingerprint/main.cjs`` and whose
#:      branch replaced it was run with a ``$PYTHON`` that dumps the file it was
#:      handed, and it was handed the BASE's line while the working tree still
#:      held the branch's. The negative was measured too: narrowing the
#:      base-pinned ``ls-tree`` to the one named library file makes the subtree
#:      stop travelling, so the probe measures the property rather than reading
#:      an untampered tree. Nothing is vendored yet and that is still the
#:      point — the floor is in place for the commit that does it.
#:   3. :class:`TypeScriptSignatureFingerprinter` is implemented (P3) to
#:      :data:`TS_SIGNATURE_EDIT_RULINGS`, which is the acceptance criterion
#:      and not a suggestion, and the helper's decoder is the shared extraction
#:      :func:`decode_ts_helper_response` names rather than a copy of the Go
#:      one. **DONE (P3, 2026-08-10):** all twenty rulings are measured green
#:      against the live comparator, and :func:`_decode_helper_response` is the
#:      one validator with both public decoders as wrappers — the Go one moved
#:      too, which is the half of the ruling that could not be met by writing
#:      only the TypeScript side.
#:
#:      Soaked the day it landed, as :data:`GO_SUPPORT`'s row was against
#:      GOROOT: 39,781 files and 240,643 symbols across the vendored parser
#:      itself, the primary target's own TypeScript and its ``node_modules``,
#:      with **zero parse failures, zero symbol keys moved and zero
#:      fingerprints moved** under a re-run and under a wholesale reformat
#:      through TypeScript's own printer. Two defects were found by that soak
#:      and by nothing else: an empty-string member name (legal, and it made
#:      the helper exit non-zero — the gate faulting on ordinary code), and a
#:      one-constituent union, which is what the leading-bar spelling parses
#:      as and which rendered differently from the same type without the bar.
#:
#:      Cost, measured rather than assumed, because the Go row's was: **169 ms
#:      per file on the gate path**, one ``node`` process per revision per file,
#:      almost all of it loading the 9.1 MB parser. The Go helper answered this
#:      by caching the BUILD; there is no build here, and the equivalent fix —
#:      a persistent process — is refused by :class:`TsHelperRequest`'s
#:      one-file-per-invocation rule, which exists so "which file faulted" is
#:      answerable. A 200-file TypeScript branch is therefore about 68 seconds
#:      of gate time, and that is the ruled price rather than an oversight.
#:
#:      **TASK #14, and P4 RECORDED IT RATHER THAN FIXING IT (2026-08-10).** It
#:      is not an enrolment blocker: 68 seconds is a cost, and every other item
#:      on this list is a correctness question. It is written down as an open
#:      task so that the day somebody proposes the persistent process, the
#:      argument against it is already here to be argued WITH rather than
#:      rediscovered — and so that a future measurement can be compared against
#:      a number that was actually taken.
#:   4. Seals exist that pin the comparator as CORRECT, not merely as present.
#:      The Go row's checklist records that enrolment alone bought nothing:
#:      dropping parameter names from the Go fingerprint left the suite green
#:      before and after enrolment. Do not repeat it. The seals that matter are
#:      the rulings table, the key-collision property
#:      (:func:`ts_symbol_key`), the parse-diagnostic strictness
#:      (:class:`TsHelperResponse`) and the resolution rule
#:      (:func:`ts_parser_home`).
#:
#:      **DONE (P2 in two passes, then P4, 2026-08-10), and the last piece was
#:      TASK #15 because it was the only one that could not be sealed at all.**
#:      `tests/test_ts_comparator.py` carries all four, plus a section on the
#:      RENDERING grammar's forgeability that the body author disclosed against
#:      its own interest. The piece that was missing until P4: **which parser
#:      actually ran.** Everything above verified the parser's LOCATION, its
#:      BYTES and its VERSION, and none of those says which file the helper
#:      process loaded — a mutation to ``require('typescript')`` reddened only
#:      on a machine with nothing ambient installed, and would have gone green
#:      with the defect present on the target checkout, which vendors
#:      TypeScript at the same release. ``--probe`` now reports the loaded
#:      parser's resolved path and :func:`_probe_node_and_parser` checks it by
#:      identity; the seal manufactures the hostile machine rather than waiting
#:      for one. Without that, the central security property of this unit would
#:      have been enrolled unsealed.
#:   5. The count of seals that redden on enrolment is taken **that day, by
#:      enrolling in a clone**. The Go row's count was wrong four times —
#:      seven, then eight, then nine — and the recorded lesson is that the only
#:      trustworthy count is a measured one. A first measurement for this row,
#:      taken 2026-08-10 on the D2 P4 tree: the ``.ts`` probes that would have
#:      reddened were already replaced with ``.sql`` and ``.java`` during the Go
#:      enrolment pass, precisely so this job would not be booked twice, and no
#:      test in the suite enumerates :class:`Language` or pins
#:      :data:`PENDING_COMPARATORS`'s contents. That is a reason to expect a
#:      small number, not a reason to skip the count.
#:
#:      **DONE, and the count is ZERO** — taken on the enrolment day, on this
#:      tree, by running the suite with the move applied: 2,197 collected, 0
#:      failed, 13 skipped (the pre-existing EPA-* rows), byte-identical to the
#:      unenrolled run. The prediction held. **Zero is not evidence that the
#:      comparator is right**, and that is the Go row's own lesson stated
#:      against this row: dropping parameter names from the Go fingerprint left
#:      the suite green before AND after enrolment. The evidence that this
#:      comparator READS is the two-direction :func:`check_branch` measurement,
#:      not the count.
#:
#: The row exists now, unenrolled, rather than being written by P3, for the
#: reason :data:`GO_SUPPORT` gives: the extensions belong in the table that owns
#: extensions, and a reader can check what this build covers by reading one
#: place. :func:`validate_registry` checks pending rows against enrolled ones,
#: so this row cannot collide with a live one and cannot be enrolled twice.
TYPESCRIPT_SUPPORT = LanguageSupport(
    language=Language.TYPESCRIPT,
    extensions=(".ts", ".tsx"),
    fingerprinter=TypeScriptSignatureFingerprinter(),
)


#: **THE registry.** The one table that says what this gate can read, and the
#: only input to :func:`support_for_path`. Adding a language is adding a row;
#: no dispatch site changes, because there is no dispatch site.
COMPARATORS: tuple[LanguageSupport, ...] = (
    PYTHON_SUPPORT,
    GO_SUPPORT,
    TYPESCRIPT_SUPPORT,
)

#: Rows that are written but not live. Nothing dispatches on this tuple — it
#: exists so that "scaffolded but not enrolled" is a NAMED state with a
#: mechanism (`skills/explicit-state.md`: absence is a state and must be
#: nameable) rather than a row someone forgot, and so
#: :func:`validate_registry` can refuse a pending row that collides with a live
#: one before anybody tries to enrol it.
#:
#: **Empty as of the D2+D4 integration, 2026-08-10, and empty is a claim.** It
#: does not mean "nobody wrote a pending row"; it means every row that has been
#: written is live. Go and TypeScript both sat here — simultaneously, on their
#: own branches — and that is the evidence this is a table rather than a place
#: to park one thing: while both were pending, ``.go`` and ``.ts``/``.tsx`` were
#: validated against each other and against the live ``.py`` row at import, so
#: an extension collision between two pending languages would have been refused
#: before either was enrolled. Nothing exercised that path until there were two.
PENDING_COMPARATORS: tuple[LanguageSupport, ...] = ()


def validate_registry(
    enrolled: Sequence[LanguageSupport],
    pending: Sequence[LanguageSupport] = (),
) -> None:
    """Refuse a registry that could give one language two answers. Pure.

    One of the two small helpers this scaffold implements rather than stubs
    (the other is :func:`support_for_path`), because a seal cannot express
    "the registry is well formed" without calling it, and because it runs at
    import over a literal: it either always passes or always fails, and a
    failure is visible on the first test collection rather than on the first Go
    branch.

    Raises :class:`RoleProtocolError` when, across ``enrolled`` and ``pending``
    together:

      * a :class:`Language` appears in more than one row — two readers for one
        language is the drift this unit removes;
      * an extension appears in more than one row, or one extension is a SUFFIX
        of another (``.go`` and ``.cgo`` would both match ``x.cgo``). Suffix
        matching is what :func:`support_for_path` does, so an ambiguity there is
        a silent first-row-wins and the second language quietly loses coverage;
      * an extension is empty, does not start with ``.``, or is not lowercase —
        matching is a case-sensitive suffix, so an uppercase entry would match
        nothing and read as coverage that does not exist;
      * a row's ``extensions`` is empty — a language nothing can select;
      * a row does not satisfy :class:`SignatureFingerprinter`.

    Never raises for a row being unimplemented: ``NotImplementedError`` is a
    runtime fact and this is a shape check. That is why the Go row can sit in
    ``pending`` and be validated.
    """
    seen_languages: dict[Language, str] = {}
    seen_extensions: dict[str, Language] = {}
    for row in tuple(enrolled) + tuple(pending):
        if not isinstance(row.language, Language):
            raise RoleProtocolError(
                f"comparator row {row!r} does not carry a Language member; a "
                "registry keyed by anything else has no closed set to be "
                "exhaustive over"
            )
        if row.language in seen_languages:
            raise RoleProtocolError(
                f"language {row.language.value!r} has two comparator rows; "
                "two readers for one language is exactly the drift this "
                "registry exists to prevent"
            )
        seen_languages[row.language] = row.language.value
        if not row.extensions:
            raise RoleProtocolError(
                f"comparator row for {row.language.value!r} declares no "
                "extensions, so no path can ever select it — coverage that "
                "reads as coverage and is not"
            )
        if not hasattr(row.fingerprinter, "fingerprints"):
            raise RoleProtocolError(
                f"comparator row for {row.language.value!r} has no "
                "`fingerprints` method and cannot satisfy "
                "SignatureFingerprinter"
            )
        for extension in row.extensions:
            if (
                not extension
                or not extension.startswith(".")
                or extension != extension.lower()
            ):
                raise RoleProtocolError(
                    f"comparator extension {extension!r} for "
                    f"{row.language.value!r} must be a lowercase, "
                    "dot-prefixed suffix; matching is a case-sensitive "
                    "`endswith`, so anything else silently matches nothing"
                )
            for other, owner in seen_extensions.items():
                if extension.endswith(other) or other.endswith(extension):
                    raise RoleProtocolError(
                        f"comparator extension {extension!r} "
                        f"({row.language.value!r}) is ambiguous with "
                        f"{other!r} ({owner.value!r}): suffix matching would "
                        "give the first row silently and the second none"
                    )
            seen_extensions[extension] = row.language


validate_registry(COMPARATORS, PENDING_COMPARATORS)


def support_for_path(path: str) -> LanguageSupport | None:
    """The registry row that can read ``path``, or None. **The one place that
    decides what language a file is.**

    The second of the two helpers this scaffold implements rather than stubs:
    it is the move of the pre-existing ``endswith(".py")``, not new behaviour,
    and :func:`_supported_language_refusal` — which used to hold that literal —
    is now its only caller inside this module. A case-sensitive suffix match
    against each row's ``extensions``, rows in registry order, first match
    wins; :func:`validate_registry` has already refused a registry in which
    "first" could be ambiguous.

    Reads :data:`COMPARATORS` — the enrolled table — and never
    :data:`PENDING_COMPARATORS`. A scaffolded-but-unenrolled row is not
    coverage, and a lookup that consulted it would report Go as readable while
    the reader raises.

    ``path`` is posix form, as git emits. Directory structure is irrelevant: a
    language is a property of the file, and any path-shaped exemption belongs to
    the path gate, which owns that question.
    """
    for row in COMPARATORS:
        for extension in row.extensions:
            if path.endswith(extension):
                return row
    return None


def enrolled_languages() -> tuple[Language, ...]:
    """What this build actually reads, in registry order.

    Derived from :data:`COMPARATORS`, so it cannot disagree with the dispatch —
    which is the point of it existing at all. The claim "the signature half of
    the protocol covers Go" is falsifiable by calling this, and a report or a
    doctor check that wants to state coverage must state it from here rather
    than from prose that ages.
    """
    return tuple(row.language for row in COMPARATORS)


def _supported_language_refusal(path: str) -> SignatureComparison | None:
    """None when this gate can read ``path``; otherwise the refusal, complete.

    **THE one place that answers "which languages can this gate read".** It was
    spelled twice — once here in :func:`compare_signatures`, once again in
    :func:`_compare_branch_signatures`'s loop — and the two 2026-08-09 rulings
    each made a third copy tempting. Under I6 it was that
    :func:`check_branch`'s verdict differed between a Go-only diff and a
    Go-plus-Python one; under the per-file ruling that replaced it both are
    CLEAN and it is the STATUS that differs (see
    :attr:`SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE`). Either way the
    distinction is carried in the state and :func:`check_branch` reads the
    state, never the suffix. The two pre-existing copies were collapsed here
    rather than joined by a third, so the day a Go comparator lands there is
    exactly one ``endswith`` to update and no copy left behind to fail towards
    a silent CLEAN.

    MEASURED, and the reason the aggregate below ranks reasons instead of
    re-deriving them: an implementation that recovers the right verdict in both
    path orders while re-deriving the refusal in :func:`check_branch` from the
    path list or from the prose — the second copy — passes every test in the
    suite except the status pin in
    ``test_a_broken_python_file_still_refuses_even_beside_an_unreadable_one``.
    ONE suffix test in this module is the invariant — the grep is one hit, and
    it is the ``if`` below. A mutation flipping it from ``.py`` to ``.go``
    moves 50 rows: the 41 measured on 2026-08-09 plus all nine of the per-file
    ones, across the diff, inputs and per-file suites. That is what proves one
    predicate governs both call sites.

    Returns the whole :class:`SignatureComparison` rather than a bool so the
    status, the prose and ``unsupported_paths`` are written once and cannot
    drift from each other: the aggregate unions what this returns instead of
    re-deriving any part of it.

    **D2:** the ``endswith`` this function used to hold moved into the Python
    row of :data:`COMPARATORS`, and the question is now asked of
    :func:`support_for_path`. The property is unchanged and so is the answer for
    every input: one place decides what a language is, and this is still the one
    place that turns "no comparator" into a refusal document. What this function
    does NOT report is a comparator that exists and failed — that is a
    :class:`ComparatorFault`, it is not a language fact, and it must never reach
    ``unsupported_paths``.
    """
    if support_for_path(path) is not None:
        return None
    readable = ", ".join(language.value for language in enrolled_languages())
    return SignatureComparison(
        status=SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE,
        detail=(
            f"{path} is not in a language this gate has a comparator for "
            f"(it reads: {readable}), so this file's signatures were compared "
            "by nothing and will not be reported as unchanged — the languages "
            "this repo has no comparator for still need one"
        ),
        unsupported_paths=(path,),
    )


def compare_signatures(
    path: str, base_text: str | None, head_text: str | None
) -> SignatureComparison:
    """Compare the *scaffolded signatures* of one file across two revisions.

    §2a's P3 gate is "no diff under tests/ schema/ **/generated/** **and no
    changed signature**". A body agent that widens a parameter list has
    changed the contract P2 sealed, without touching a protected path.

    The fingerprint of a symbol, all AST-derived so formatting is not a
    change:

      * for a ``def``/``async def`` (module level or in a class): qualified
        name, parameter names in order with their kinds
        (positional-only/keyword-only/var-positional/var-keyword), each
        parameter's annotation source, whether each parameter has a default
        (the default's *value* is a body concern and is NOT part of the
        fingerprint), the return annotation, and the decorator names.
      * for a class: its name, its base names, its decorator names, and its
        class-level annotated assignments (name, annotation, has-default).
        Frozen dataclass fields ARE the contract in this codebase, so a
        reordered or retyped field is a signature change.

    Rules: a symbol present at base and absent at head → change with ``after``
    None. A symbol whose fingerprint differs → change. A symbol added at head
    → NOT a change (a body may add private helpers). A docstring edit → not a
    change; the docstring is P1's contract and P3 may extend it, and an
    over-strict rule here would make honest work fail.

    **D2 — the language-specific half moved out.** The fingerprint above is
    Python's, and it is now produced by :class:`PythonSignatureFingerprinter`
    behind :class:`SignatureFingerprinter`; this function selects the row with
    :func:`support_for_path` and applies the rules below to whatever
    fingerprints it is handed. What is language-specific is the fingerprint of
    a symbol and nothing else. What is NOT — added is not a change, removed is,
    a differing fingerprint is, a new file has nothing to preserve, both
    revisions absent is a caller bug — is decided HERE, once, for every
    language, so a second entry in the registry cannot answer a protocol
    question differently from the first. See :class:`GoSignatureFingerprinter`
    for what a Go signature is; that docstring is the Go-side contract and this
    one stays the protocol.

    Statuses: both texts parse → CHECKED. ``path`` is in no registered
    language → UNCHECKED_UNSUPPORTED_LANGUAGE with the path in ``detail`` **and
    in ``unsupported_paths``** — this is the one function that knows a file was
    skipped for its language, so it is where that fact is recorded, and
    :func:`_compare_branch_signatures` unions rather than re-deriving. Either
    text fails to parse → UNCHECKED_UNPARSEABLE, and ``unsupported_paths``
    stays empty: that file was read, not skipped. The comparator for a
    registered language could not RUN (D2) → the status
    :func:`signature_status_for_fault` gives the fault, ``unsupported_paths``
    empty for the same reason and one more: an environment fault is not a
    language this gate cannot read, and letting it look like one clears the
    branch (:func:`_comparator_unavailable_comparison`). ``base_text`` None **and
    ``head_text`` not None** (the file is new on the branch) → CHECKED with no
    changes: a file that did not exist at base has no scaffolded signature to
    preserve. ``head_text`` None (the file was deleted) → every base symbol is
    a change with ``after`` None. **Both texts None → raises
    :class:`RoleDiffError`**: the file exists at neither revision, so it is
    neither "new on the branch" nor "deleted", the caller has a bug, and the
    one answer that must never be given is CHECKED-with-no-changes — a pass
    bought by having nothing to look at (2026-08-04 P2 ruling; the earlier text
    said flatly "``base_text`` None → CHECKED", which read literally made the
    both-absent case a silent pass). :func:`check_branch` turns the raise into
    UNDETERMINED.

    Pure function of ``(path, base_text, head_text)`` in the sense the gate
    needs: same inputs, same verdict, no reads of the working tree, no
    dependence on ``repo_root`` or on any ref. **Not** free of the environment
    once a language needs a toolchain (D2): the Go comparator runs a
    subprocess, so the same inputs on a machine without ``go`` produce a FAULT
    rather than a different answer. That is the distinction the fault states
    exist to keep — the function never returns a different comparison because
    of the environment, it returns "I could not compare", which is not a pass.

    Implementation notes (P3), none of which change what the contract above
    promises:

      * "Signature" is read off the module body and class bodies only.
        Function bodies are never descended into, so a nested helper a body
        agent adds is invisible here — which is the point. Moving a
        scaffolded ``def`` inside an ``if`` is likewise not an escape: the
        symbol simply disappears from head and is reported as removed.
      * A decorator's fingerprint is its unparsed *expression*, not its bare
        name: ``@dataclass(frozen=True)`` → ``@dataclass`` is a contract
        change in this codebase, and a name-only reading would miss it.
      * The both-texts-None refusal is stated in the contract above rather
        than here, because it IS the contract and not an implementation
        choice: UNDETERMINED is the honest verdict for a path git named but
        neither tree holds.
    """
    support = support_for_path(path)
    if support is None:
        return _supported_language_refusal(path)

    if base_text is None and head_text is None:
        raise RoleDiffError(
            f"{path} has no content at either revision; there is nothing to "
            "compare, and reporting a clean check for a path the diff named "
            "would be a pass bought by doing nothing"
        )

    if base_text is None:
        return SignatureComparison(
            status=SignatureCheckStatus.CHECKED,
            detail=f"{path} is new on the branch; no base signature to preserve",
        )

    try:
        base_symbols = support.fingerprinter.fingerprints(path, base_text)
    except SourceUnparseable as exc:
        return SignatureComparison(
            status=SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
            detail=f"{path} does not parse at base: {exc.message}",
        )
    except ComparatorUnavailable as exc:
        return _comparator_unavailable_comparison(path, "base", exc)

    if head_text is None:
        head_symbols: dict[str, str] = {}
        detail = f"{path} was deleted on the branch"
    else:
        try:
            head_symbols = support.fingerprinter.fingerprints(path, head_text)
        except SourceUnparseable as exc:
            return SignatureComparison(
                status=SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
                detail=f"{path} does not parse at head: {exc.message}",
            )
        except ComparatorUnavailable as exc:
            return _comparator_unavailable_comparison(path, "head", exc)
        detail = ""

    changes = tuple(
        SignatureChange(
            path=path,
            symbol=symbol,
            before=before,
            after=head_symbols.get(symbol),
        )
        for symbol, before in base_symbols.items()
        if head_symbols.get(symbol) != before
    )
    return SignatureComparison(
        status=SignatureCheckStatus.CHECKED, changes=changes, detail=detail
    )


def _comparator_unavailable_comparison(
    path: str, revision: str, exc: ComparatorUnavailable
) -> SignatureComparison:
    """The ONE place a :class:`ComparatorFault` becomes a comparison result.

    Assembly only: the status comes from :func:`signature_status_for_fault`,
    which owns that decision, and the fault's own name and message go into the
    detail so the report says which environment failure happened and on which
    revision of which file.

    ``unsupported_paths`` stays EMPTY, and that is the load-bearing line. The
    file was not skipped for its language — a reader for it exists and the
    machine could not run it — so it must not join the list of paths nobody can
    read. If it did, a diff of nothing but Go on a box with no ``go`` binary
    would satisfy :func:`_compare_branch_signatures`' promotion condition
    (nothing examined, something skipped for its language), become
    UNCHECKED_NO_SUPPORTED_FILE, and be reported CLEAN. The companion half of
    that invariant lives in the aggregate: a path whose comparator faulted
    counts as EXAMINED.
    """
    return SignatureComparison(
        status=signature_status_for_fault(exc.fault),
        detail=(
            f"{path}: the {revision} revision could not be compared — "
            f"{exc.fault.value}: {exc.message}. This is an environment fault, "
            "not a language this gate cannot read and not a bad source file, "
            "so it clears nothing"
        ),
    )


_HAS_DEFAULT = " = <default>"


def _annotation_source(node: ast.expr | None) -> str:
    """The normalised source of an annotation, or ``""`` when unannotated.

    ``ast.unparse`` rather than the raw slice, so a reflowed or requoted
    annotation is not a change.
    """
    return "" if node is None else ast.unparse(node)


def _parameter_fingerprint(
    kind: str, arg: ast.arg, *, has_default: bool
) -> str:
    """One parameter: kind, name, annotation, and whether a default exists.

    The default's VALUE is deliberately absent — that is a body concern.
    """
    return (
        f"{kind} {arg.arg}: {_annotation_source(arg.annotation)}"
        f"{_HAS_DEFAULT if has_default else ''}"
    )


def _parameter_fingerprints(args: ast.arguments) -> tuple[str, ...]:
    """Every parameter in declaration order, carrying its kind.

    The kind is part of the contract: making a keyword-only parameter
    positional widens what callers may do, so ``f(a, *, b)`` and ``f(a, b)``
    must not fingerprint alike.
    """
    positional = list(args.posonlyargs) + list(args.args)
    first_default = len(positional) - len(args.defaults)
    fingerprints = [
        _parameter_fingerprint(
            "positional_only" if index < len(args.posonlyargs)
            else "positional_or_keyword",
            arg,
            has_default=index >= first_default,
        )
        for index, arg in enumerate(positional)
    ]
    if args.vararg is not None:
        fingerprints.append(
            _parameter_fingerprint("var_positional", args.vararg, has_default=False)
        )
    fingerprints.extend(
        _parameter_fingerprint("keyword_only", arg, has_default=default is not None)
        for arg, default in zip(args.kwonlyargs, args.kw_defaults)
    )
    if args.kwarg is not None:
        fingerprints.append(
            _parameter_fingerprint("var_keyword", args.kwarg, has_default=False)
        )
    return tuple(fingerprints)


def _decorator_fingerprints(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> str:
    """The decorators, unparsed whole.

    ``@dataclass(frozen=True)`` is not ``@dataclass``: in this codebase
    frozen-ness IS the contract, so the arguments belong to the fingerprint.
    """
    return " ".join(f"@{ast.unparse(dec)}" for dec in node.decorator_list)


def _function_fingerprint(
    qualname: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> str:
    """A ``def``/``async def``'s fingerprint. Body and docstring excluded."""
    keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    params = ", ".join(_parameter_fingerprints(node.args))
    return (
        f"{keyword} {qualname}({params}) -> {_annotation_source(node.returns)}"
        f" [{_decorator_fingerprints(node)}]"
    )


def _class_fingerprint(qualname: str, node: ast.ClassDef) -> str:
    """A class's fingerprint: bases, decorators, and annotated class fields.

    Frozen dataclass fields are the contract here, so field order, name,
    annotation and has-default all count; the default's value does not.
    """
    bases = [ast.unparse(base) for base in node.bases]
    bases += [
        f"{'**' if kw.arg is None else kw.arg}={ast.unparse(kw.value)}"
        for kw in node.keywords
    ]
    fields = [
        f"{stmt.target.id}: {_annotation_source(stmt.annotation)}"
        f"{_HAS_DEFAULT if stmt.value is not None else ''}"
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    ]
    return (
        f"class {qualname}({', '.join(bases)})"
        f" [{_decorator_fingerprints(node)}]"
        f" {{{'; '.join(fields)}}}"
    )


def _collect_signatures(
    body: Sequence[ast.stmt], prefix: str, into: dict[str, str]
) -> None:
    """Fingerprint every ``def``/``class`` in ``body``, qualified by ``prefix``.

    Function bodies are not descended into: a helper defined inside a function
    is body work, not a scaffolded signature.
    """
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{prefix}{stmt.name}"
            into[qualname] = _function_fingerprint(qualname, stmt)
        elif isinstance(stmt, ast.ClassDef):
            qualname = f"{prefix}{stmt.name}"
            into[qualname] = _class_fingerprint(qualname, stmt)
            _collect_signatures(stmt.body, f"{qualname}.", into)


def _scaffolded_signatures(text: str) -> dict[str, str]:
    """Qualified symbol → fingerprint for one revision of one Python file.

    Declaration order is preserved so a report reads top-to-bottom. Raises
    ``SyntaxError``/``ValueError`` from :func:`ast.parse`; the caller names
    that UNCHECKED_UNPARSEABLE rather than swallowing it.
    """
    signatures: dict[str, str] = {}
    _collect_signatures(ast.parse(text).body, "", signatures)
    return signatures


def changed_paths_between(
    repo_root: str | Path,
    base_ref: str,
    branch_ref: str,
    *,
    run: Callable[..., object] | None = None,
) -> tuple[str, ...]:
    """The branch's own changed paths, as git reports them.

    ``git diff --name-only --no-renames base_ref...branch_ref`` — three-dot,
    so only the branch's own commits count and a base that advanced
    underneath does not read as the branch's work (``risk.collect_diff``'s
    two-dot fallback and its reasoning apply here too). ``--no-renames`` so
    each side of a move is its own path.

    ``run`` is an injectable subprocess seam, as in ``push_verify``, so the
    seals need no repository fixture. Raises :class:`RoleDiffError` on any git
    failure, timeout or unparseable output; the caller maps that to
    :data:`DiffVerdict.UNDETERMINED`. It must never return an empty tuple to
    mean failure.

    **P3 implementation notes.** The argv carries ``-c core.quotePath=false``:
    with quoting on, git renders a non-ASCII path as ``\\NNN`` escapes, and a
    path this function mis-renders is a path :func:`evaluate_changed_paths`
    cannot glob-match — a silent hole in the gate, which is the one failure
    mode this module exists to prevent. Output is split on newlines rather
    than read with ``-z`` because git still C-quotes (and therefore never
    emits a raw newline inside) a path containing a control character.

    **Every quoted line is DECODED (D1-inputs I1).** ``core.quotePath=false``
    buys one thing and only one: it stops git octal-escaping non-ASCII bytes.
    Git C-quotes a path containing ``"``, ``\\`` or a control character
    *whatever that setting says*, because the setting governs the high bytes
    and those three classes are ASCII. Measured against a real repo, the raw
    output of this very argv is::

        tests/plain.py                <- matched by `**/tests/**`
        tests/tést.py                 <- matched; this is what quotePath=false bought
        "tests/a\\tb.py"               <- matched NOTHING
        "tests/back\\\\slash.py"         <- matched NOTHING
        "tests/say\\"hi\\".py"           <- matched NOTHING

    A quoted rendering is not a path: it matches no glob, so three of those
    five bypassed the BODIES deny table, and a parent directory with a quote
    in its name (``sub"x/.dispatcher.yaml``) bypassed the non-overridable
    FLOOR — a branch could rewrite the file configuring every role's
    permissions by choosing where to put it. So each line goes through
    :func:`_unquote_git_path`, which reverses git's ``quote_c_style``
    (surrounding quotes, ``\\`` escapes, ``\\NNN`` octal bytes) rather than
    merely stripping the quotes: stripping alone leaves ``tests/back\\\\slash.py``
    and ``tests/say\\"hi\\".py``, which are neither glob-matchable nor readable
    by :func:`file_text_at`. The decoded name is the one git would accept
    back, so the path this reports is also the path the signature half can
    read. A line that will not decode raises rather than being passed on
    half-rendered: a path the gate cannot match is a hole that reports as a
    pass.

    Duplicate lines are collapsed AFTER decoding, order preserved: the diff of
    a merge-shaped range can name a path twice, and a doubled violation report
    would read as two offences. (Dedup must follow the decode, or one
    rendering of a name would not be recognised as the other.)
    """
    argv = [
        "git",
        "-c",
        "core.quotePath=false",
        "diff",
        "--name-only",
        "--no-renames",
        f"{base_ref}...{branch_ref}",
    ]
    rc, out, err = _run_git_capture(argv, str(repo_root), run)
    if rc != 0:
        raise RoleDiffError(
            f"git diff {base_ref}...{branch_ref} in {repo_root} exited {rc}: "
            f"{err.strip() or '(no stderr)'}; an empty path list from a failed "
            "command is indistinguishable from an empty diff, so this raises"
        )

    paths: list[str] = []
    seen: set[str] = set()
    for line in out.split("\n"):
        if not line:
            continue
        if not line.strip():
            raise RoleDiffError(
                f"git diff {base_ref}...{branch_ref} in {repo_root} emitted a "
                f"blank path {line!r}; unparseable output is not an empty diff"
            )
        try:
            path = _unquote_git_path(line)
        except ValueError as exc:
            raise RoleDiffError(
                f"git diff {base_ref}...{branch_ref} in {repo_root} emitted "
                f"{line!r}, which is not a decodable C-quoted path: {exc}; a "
                "path the gate cannot render is a path it cannot match, and an "
                "unmatchable path reports as a pass"
            ) from exc
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return tuple(paths)


#: git's ``quote_c_style`` escapes, inverted. The keys are the characters that
#: may follow a backslash inside a C-quoted path; an octal ``\\NNN`` run is
#: handled separately because it carries a raw BYTE, not a character.
_C_QUOTE_ESCAPES: Mapping[str, bytes] = {
    "a": b"\a",
    "b": b"\b",
    "f": b"\f",
    "n": b"\n",
    "r": b"\r",
    "t": b"\t",
    "v": b"\v",
    "\\": b"\\",
    '"': b'"',
}


def _unquote_git_path(line: str) -> str:
    """One ``git diff --name-only`` line as the real path it names.

    Git prints a path verbatim unless it must quote it; when it must, it wraps
    the whole thing in ``"`` and applies C-style escaping. ``core.quotePath``
    governs only whether high bytes become ``\\NNN``: a path containing ``"``,
    ``\\`` or a control character is quoted either way. A quoted rendering is
    not a path — it matches no glob and no object-store read resolves it — so
    this reverses the rendering.

    An unquoted line is returned unchanged, and that test is safe in both
    directions: git quotes any path containing a ``"``, so a line that starts
    with one was quoted by git and never merely happens to begin with a quote
    character.

    Octal escapes are accumulated as BYTES and the whole result decoded as
    UTF-8 once, so a multi-byte character split across two ``\\NNN`` runs
    survives; a byte string that is not UTF-8, an unterminated backslash, a
    short octal run and an escape git never emits all raise
    :class:`ValueError`. Half-decoding is the one outcome that must not
    happen: the caller reports what this returns to the glob engine AND to the
    blob reader, and a name only one of them accepts is a hole.
    """
    if len(line) < 2 or not line.startswith('"') or not line.endswith('"'):
        return line

    body = line[1:-1]
    out = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.extend(char.encode("utf-8"))
            index += 1
            continue
        index += 1
        if index >= len(body):
            raise ValueError("a trailing backslash escapes nothing")
        escape = body[index]
        if escape in _C_QUOTE_ESCAPES:
            out.extend(_C_QUOTE_ESCAPES[escape])
            index += 1
            continue
        if escape in "01234567":
            digits = body[index : index + 3]
            if len(digits) != 3 or any(d not in "01234567" for d in digits):
                raise ValueError(
                    f"\\{digits} is not a three-digit octal byte escape"
                )
            out.append(int(digits, 8))
            index += 3
            continue
        raise ValueError(f"\\{escape} is not an escape git emits")

    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"the decoded path is not valid UTF-8: {exc}") from exc


def file_text_at(
    repo_root: str | Path,
    ref: str,
    path: str,
    *,
    run: Callable[..., object] | None = None,
) -> str | None:
    """One file's UTF-8 text at ``ref``, or None when absent from that tree.

    ``git show ref:path`` via the same injectable seam. None means "the tree
    does not contain it" and nothing else: a read error, a non-UTF-8 blob, or
    a non-regular-file entry raises :class:`RoleDiffError` rather than
    returning None, so an unreadable base can never be mistaken for a
    newly-added file (which would suppress every signature change in it).

    **P3 implementation note.** Spelled ``git show ref:path`` in the contract,
    implemented as a delegation to ``repo_config.blob_text_at`` — the ONE
    reader of any path out of a ref's object store (invariant 5, and that
    function's own docstring names this caller). A private second reader here
    would have to answer symlink, submodule, non-UTF-8 and unresolvable-ref
    for itself, and the two readers would diverge on exactly those cases. A
    bare ``git show`` is in fact *wrong* for two of them: it prints a
    symlink's target as if it were file content, and it cannot distinguish
    "absent" from "unreadable" without inspecting git's message.

    Looked up as an attribute on the module, never from-imported, so a seal
    can prove this function contains no second git read.
    """
    from . import repo_config as repo_config_mod

    try:
        return repo_config_mod.blob_text_at(repo_root, ref, path, run=run)
    except Exception as exc:
        raise RoleDiffError(
            f"cannot read {path} at {ref}: {exc}; an unreadable revision is "
            "never reported as 'the file is not there', which would suppress "
            "every signature change in it"
        ) from exc


class RoleDiffError(RuntimeError):
    """Raised when a branch's diff or a file's content cannot be read.

    Carried, not swallowed: :func:`check_branch` converts it to
    :data:`DiffVerdict.UNDETERMINED` with the message in ``detail``.
    """


def check_branch(
    repo_root: str | Path,
    base_ref: str,
    branch_ref: str,
    role: Role,
    *,
    spec: TaskRoleSpec | None = None,
    policy: RolePolicy | None = None,
    run: Callable[..., object] | None = None,
) -> RoleDiffResult:
    """THE diff-time role check — the single entrypoint for all three callers.

    Callers: ``scripts/check_body_branch.sh`` (PR time and CI) and the
    orchestrator's task loop (immediately after the implementer returns, which
    is the call that saves a build cycle). One callable, so a PR-time pass and
    a task-loop pass can never disagree (invariant 1).

    Sequence, validate-before-apply:

      1. resolve the policy — ``policy`` when given, else
         :func:`load_role_policy_from_base` at ``base_ref``. A policy that
         cannot be read ⇒ UNDETERMINED (never the built-in defaults: that
         would silently drop the repo's additions).
      2. resolve the effective rule via :func:`effective_rule` when ``spec``
         is given, else the policy's rule for ``role``. ``spec`` is REQUIRED
         when ``role`` is ADJUDICATE — its writable set lives on the row, and
         without it the answer is UNDETERMINED, never "may touch nothing"
         (which would be a wrong CLEAN for an empty diff) and never "may
         touch anything".
      3. :func:`changed_paths_between`. Zero paths ⇒ UNDETERMINED with a
         detail saying so.
      3b. :func:`_floor_violations` over those paths — the non-overridable
         floor, unioned into the decision HERE rather than merged into a
         :class:`RolePolicy`, so a caller-supplied or base-pinned policy that
         omits it still gets it, and matched against the paths git reported
         rather than against anything a task declared.
      4. :func:`evaluate_changed_paths`, unioned with 3b: a path on the floor
         is reported as a floor violation whatever the role's own rule said
         about it, and every other violation is the role rule's, unchanged.
      5. for BODIES only, :func:`compare_signatures` over every changed
         ``*.py`` path that exists at the **merge-base** of ``base_ref`` and
         ``branch_ref`` — the revision step 3's three-dot diff measured the
         branch's work from, not ``base_ref``'s tip (D1-inputs I4). Other
         roles get :data:`SignatureCheckStatus.NOT_APPLICABLE`. **The verdict
         is PER FILE** (2026-08-09 operator ruling, the ruling after I6): each
         changed path is judged by whether its language is supported;
         supported files are compared and their changes decide; a path in a
         language this gate has no comparator for is NAMED in
         :attr:`SignatureComparison.unsupported_paths` and does not block. What
         still refuses on BODIES is a check that STARTED on a supported file
         and could not finish —
         :data:`SignatureCheckStatus.UNCHECKED_UNPARSEABLE`, the sole member of
         :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES` (D1-inputs I5).
      5b. for BODIES only, :func:`changed_paths_between` again — the path gate
         ran against the revision step 3 read, and step 5 re-resolved
         ``branch_ref`` for every blob. A branch that advanced in between is
         UNDETERMINED rather than CLEAN in its own name (D1-inputs I3). No
         other role reads anything after step 3, so no other role has the
         window.
      6. **WIRED (D7 P4 ruling, 2026-08-12).**
         :func:`~claude_dispatcher.branch_reachability.
         check_branch_reachability` over ``changed``, the two refs and the
         role, its answer onto :attr:`RoleDiffResult.reachability`, and
         :func:`~claude_dispatcher.branch_reachability.verdict_of` unioned into
         the verdict block below at
         :data:`~claude_dispatcher.branch_reachability._VERDICT_PRECEDENCE`
         (VIOLATION over UNDETERMINED over CLEAN — the order this block already
         applies). Placed HERE, last, so a branch that is already VIOLATION
         does not pay for it; that skip is a named state and not a silence, and
         the boolean that carries it is the verdict block's OWN VIOLATION
         condition rather than a second derivation of it.

         **What the wiring cost, and why it was P4's.** This module is on
         :data:`FLOOR_GLOBS`, and the call puts three modules into the floor's
         DERIVED delegation closure — ``branch_reachability`` by the
         function-local import itself, and ``call_site_reachability`` and
         ``call_site_contract`` transitively through that module's own
         module-level imports. So the commit that adds the call also adds one
         :data:`FLOOR_GLOBS` entry (the other two were already floored) and
         three rows to ``tests/test_floor_closure.py::_DELEGATION_TARGETS`` —
         a seal file BODIES may not touch. That is why the call is a P4
         amendment and not a P3 edit.

         **The call is SEALED as reached** (dispute D1, closed here):
         ``tests/test_floor_closure.py::
         test_check_branch_actually_calls_the_reachability_gate`` reddens if
         the call leaves this function, and
         ``tests/test_branch_reachability.py::
         test_the_wired_gate_refuses_a_bodies_branch_through_check_branch``
         reddens if the answer stops reaching the verdict. Neither reads this
         docstring; both re-derive the fact.

    Verdict: VIOLATION if any path violation or any signature change;
    UNDETERMINED on any :class:`RoleDiffError`, unreadable policy, missing
    required ``spec``, empty diff, a branch that moved mid-check, or a
    BLOCKING unchecked signature status **when the role is BODIES** — a
    signature check that started and could not finish, on the role whose gate
    that is, is not a pass; CLEAN otherwise, when the diff was read, was
    non-empty, still described the same branch when the reads finished, and
    produced no violation.

    The unchecked statuses that do NOT refuse a bodies branch, both by
    2026-08-09 operator rulings: UNCHECKED_NO_SUPPORTED_FILE — not one path in
    the diff is in a language this gate has a comparator for (D1 I6) — and
    UNCHECKED_UNSUPPORTED_LANGUAGE — some were and some were not, and the ones
    that were decided (the per-file ruling that closed the boundary I6 left
    open). Refusing either was a false refusal with no override: nothing the
    branch could commit would clear it, because a real branch on a tree of
    2,288 Go / 996 TS / 781 SQL / 316 Java / 0 Python files always carries a
    path nobody will ever write a comparator for. The consequence the ruling
    was chosen for: every comparator added later is a MONOTONIC improvement —
    enrolling a language can turn a CLEAN into a VIOLATION for a real finding,
    and can never newly block a class of branch.

    **Neither CLEAN is silent.** Whenever any path went unread, ``detail`` —
    the line :func:`_print_report` puts on stdout, and the only line a caller
    that logs the verdict keeps — carries those paths and the language reason,
    alongside :attr:`SignatureComparison.unsupported_paths`. It carries the
    SKIPPED paths and not the whole diff: a detail that lists everything is
    satisfied identically by an honest gate and by one that has lost track of
    what it skipped, and those two answers differ only on a mixed diff (P4
    dispute 1, 2026-08-09). The full path listing a reader may also want is
    already printed separately by :func:`_print_report`, under "changed paths
    examined:".

    **The whole signature-status → BODIES verdict table (D2), in one place,
    because a state whose verdict has to be inferred is a state somebody will
    infer wrongly.** Read it as the specification; the two frozensets below are
    its mechanism.

      ================================ ============= ================
      status                           BODIES        every other role
      ================================ ============= ================
      CHECKED (no changes)             CLEAN         n/a
      CHECKED (with changes)           VIOLATION     n/a
      UNCHECKED_UNPARSEABLE            UNDETERMINED  n/a
      UNCHECKED_COMPARATOR_UNAVAILABLE UNDETERMINED  n/a
      UNCHECKED_UNSUPPORTED_LANGUAGE   CLEAN [1]     n/a
      UNCHECKED_NO_SUPPORTED_FILE      CLEAN [1]     n/a
      NOT_APPLICABLE                   n/a           CLEAN
      ================================ ============= ================

      [1] and the paths it could not read are named — in
          ``signature.unsupported_paths`` AND on the verdict's own detail
          line. That naming is what the 2026-08-09 ruling bought the CLEAN
          with; a CLEAN on either of those rows that confesses nothing is the
          ruling misapplied.

    P4, 2026-08-09: the two CLEAN rows above were spelled UNDETERMINED when
    this table arrived with the D2 scaffold, which was branched before the
    per-file verdict landed. Corrected against
    :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES`, which is the mechanism, and
    sealed as DATA in ``tests/test_role_protocol_faults.py`` so the table and
    the frozenset cannot drift again — a specification table that disagrees
    with the code is worse than no table, because it is the thing a reader
    reaches for instead of the code.

    UNCHECKED_COMPARATOR_UNAVAILABLE is UNDETERMINED and not CLEAN because a
    toolchain that could not run is not a language nobody can read: the first
    is an environment fault somebody can fix and the second is a permanent fact
    about this gate. Give the fault the language answer and a CI image with no
    ``go`` binary clears every Go branch it builds — loudly wrong replaced by
    quietly wrong, which is the trade the 2026-08-09 ruling was careful NOT to
    make. See :func:`signature_status_for_fault`.

    Neither UNDETERMINED row is terminal for the branch: each names something
    an author or an operator can act on (fix the source, fix the image) and
    re-running clears it. UNCHECKED_NO_SUPPORTED_FILE is the one state nothing
    the branch commits can change, which is exactly why it is CLEAN — that was
    the ruling.

    LEGACY returns CLEAN when the diff read succeeded, was non-empty and
    touched no floor path: a pre-protocol task has no immutable paths, and this
    function must not become a new gate on legacy work. **The floor is the one
    exception** (2026-08-07 operator ruling, overriding this contract line as it
    was originally written — "LEGACY always returns CLEAN when the diff read
    succeeded and was non-empty"). The alternative is not a floor: LEGACY is not
    a role anyone is granted, it is what a row IS when the ``role:`` key is
    absent, so a floor LEGACY escapes is bypassed by deleting one line — and the
    deleted line would buy the right to rewrite the file that configures every
    role's permissions. The narrowing costs role-less rows nothing outside
    :data:`FLOOR_GLOBS`.

    **The reachability arm (D7), in one place, for the reason the signature
    table above gives — a state whose verdict has to be inferred is a state
    somebody will infer wrongly.** It is the same shape as the signature arm
    and deliberately so: on the ONE role whose gate it is, a check that could
    not finish is not a pass. It differs in one thing and the difference is the
    whole unit: :func:`~claude_dispatcher.call_site_reachability.check_tree`
    judges a TREE and this gate must judge a DIFF, so what refuses is a finding
    the BRANCH INTRODUCED — measured over the base tree and the head tree —
    and never the tree's standing BREACH set. Measured on this revision, that
    distinction is worth 12 findings on one vendored fixture with nothing
    edited at all, which is what a whole-tree arm would refuse every branch for
    forever. The tables are
    :data:`~claude_dispatcher.branch_reachability._ROLE_OBLIGATIONS` (BODIES
    blocks, ADJUDICATE is advisory, the other three do not run),
    :data:`~claude_dispatcher.branch_reachability._DISPOSITION_VERDICTS` (all
    five, raising on a sixth) and
    :data:`~claude_dispatcher.branch_reachability._BLOCKING_UNDECIDED_REASONS`
    — the counterpart of :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES`, ruled
    with THIS module's own 2026-08-09 discriminator: an abstention refuses when
    somebody can act on it and clears when nothing the branch could commit
    would.

    **P3 implementation notes**, each an addition the contract implies rather
    than states, and every one of them fails *closed*:

      * this function never raises. Every failure — an unreadable policy, an
        illegal override, a git explosion, a :class:`Role` member nothing here
        handles — becomes UNDETERMINED carrying the message in ``detail``,
        because :func:`main`'s callers need exit 3, not a traceback.
      * a ``spec`` whose ``role`` disagrees with the ``role`` argument is
        UNDETERMINED. The two are separate parameters and nothing reconciles
        them; picking either one would judge the branch under a rule its
        caller did not ask for.
      * ADJUDICATE with a ``spec`` whose ``disputed_paths`` is empty is
        UNDETERMINED for the same reason a missing ``spec`` is: the writable
        set, not the object carrying it, is what step 2 requires. An empty
        allow-only set makes every changed path a violation and loses the
        reason.
      * step 5's aggregate over several files reports the WORST reason any one
        file produced — :data:`_SIGNATURE_STATUS_PRECEDENCE` — and the union of
        the changes: one unparseable file must not be able to hide a changed
        signature in another, and a partial check is not a CHECKED one. Worst,
        and not first, because after the per-file ruling the reasons no longer
        agree on the verdict: first-wins would clear a branch whose Python does
        not parse whenever an unreadable file sorted ahead of it.
      * :func:`changed_paths_between`, :func:`file_text_at` and
        :func:`compare_signatures` are called through module globals, so the
        one entrypoint is the one place a caller can substitute the git seam.
    """

    def _undetermined(
        detail: str,
        *,
        policy_source: PolicySource | None = None,
        checked_paths: Sequence[str] = (),
        signature: SignatureComparison | None = None,
    ) -> RoleDiffResult:
        return RoleDiffResult(
            verdict=DiffVerdict.UNDETERMINED,
            role=role,
            base_ref=base_ref,
            branch_ref=branch_ref,
            signature=signature,
            checked_paths=tuple(checked_paths),
            policy_source=policy_source,
            detail=detail,
        )

    # 1. The policy. `policy` given wins verbatim — a PR-time pass and a
    #    task-loop pass cannot disagree if they can be handed the same one.
    if policy is None:
        try:
            policy = load_role_policy_from_base(repo_root, base_ref)
        except Exception as exc:
            return _undetermined(
                f"cannot read the role policy at {base_ref}: {exc}; "
                "'I could not read the policy' must not be answered with a "
                "policy, and the built-in defaults would silently drop the "
                "repo's additions"
            )
    source = policy.source

    # 2. The effective rule, resolved before anything is applied to a diff.
    if spec is not None and spec.role is not role:
        return _undetermined(
            f"task {spec.task_key} carries role {spec.role.value!r} but this "
            f"check was asked for {role.value!r}; judging the branch under "
            "either one would be a guess about which the caller meant",
            policy_source=source,
        )
    if role is Role.ADJUDICATE and (spec is None or not spec.disputed_paths):
        return _undetermined(
            "role 'adjudicate' has no writable set without the task row's "
            f"{DISPUTED_PATHS_FIELD!r}; an absent list is never 'may touch "
            "nothing' (a wrong CLEAN for an empty diff) and never 'may touch "
            "anything'",
            policy_source=source,
        )
    try:
        rule = (
            effective_rule(spec, policy)
            if spec is not None
            else policy.rule_for(role)
        )
    except RoleProtocolError as exc:
        return _undetermined(
            f"cannot resolve the effective rule for role {role.value!r}: "
            f"{exc}; an override that will not validate is never applied and "
            "never ignored",
            policy_source=source,
        )

    # 3. The diff.
    try:
        changed = changed_paths_between(repo_root, base_ref, branch_ref, run=run)
    except RoleDiffError as exc:
        return _undetermined(
            f"cannot read the branch diff {base_ref}...{branch_ref}: {exc}",
            policy_source=source,
        )
    if not changed:
        return _undetermined(
            f"git reported no changed paths for {base_ref}...{branch_ref}; a "
            f"role task that changed nothing has not done its {role.value!r} "
            "phase, and 'did nothing' must not look like 'succeeded'",
            policy_source=source,
        )

    # 3b. The floor, unioned into the DECISION rather than into any policy, and
    #     matched against the paths git just reported. Computed before the
    #     LEGACY short-circuit because LEGACY is subject to it too.
    floor_violations = _floor_violations(changed)

    if role is Role.LEGACY:
        if floor_violations:
            return RoleDiffResult(
                verdict=DiffVerdict.VIOLATION,
                role=role,
                base_ref=base_ref,
                branch_ref=branch_ref,
                violations=floor_violations,
                signature=_not_applicable_signature(role),
                checked_paths=changed,
                policy_source=source,
                detail=(
                    f"{len(floor_violations)} path(s) on the non-overridable "
                    "floor; a row with no `role:` key is exempt from the deny "
                    "table, not from the floor"
                ),
            )
        return RoleDiffResult(
            verdict=DiffVerdict.CLEAN,
            role=role,
            base_ref=base_ref,
            branch_ref=branch_ref,
            signature=_not_applicable_signature(role),
            checked_paths=changed,
            policy_source=source,
            detail=(
                "legacy: a pre-protocol single-role task has no immutable "
                "paths outside the floor, and this check must not become a "
                "new gate on it"
            ),
        )

    # 4. The paths: the role's own rule, then the floor unioned over it.
    try:
        violations = _drop_commons(
            _union_with_floor(
                evaluate_changed_paths(rule, changed), floor_violations, changed
            ),
            floor_violations,
        )
    except RoleProtocolError as exc:
        return _undetermined(
            f"cannot evaluate the changed paths for role {role.value!r}: "
            f"{exc}",
            policy_source=source,
            checked_paths=changed,
        )

    # 5. The scaffolded signatures — the half of the gate no path glob sees.
    if role is Role.BODIES:
        try:
            signature = _compare_branch_signatures(
                repo_root, base_ref, branch_ref, changed, run=run
            )
        except (RoleDiffError, RoleProtocolError) as exc:
            # RoleProtocolError too, because the aggregate is exhaustive over
            # the per-file statuses and RAISES on one it was never taught to
            # rank (invariant: no implicit state at a decision boundary). This
            # function never raises, so that refusal has to land here, as
            # UNDETERMINED — which is what "I do not know how bad this is" is
            # worth on the one role whose gate this is.
            return _undetermined(
                f"cannot compare scaffolded signatures across "
                f"{base_ref}...{branch_ref}: {exc}",
                policy_source=source,
                checked_paths=changed,
            )

        # 5b. Time of check, time of use (D1-inputs I3). Step 3 resolved
        #     `branch_ref` for the diff and step 5 resolved it again, once per
        #     blob, and the orchestrator makes this call the instant the
        #     implementer returns — while the implementer's own session still
        #     holds the worktree. A branch that advanced in between got its
        #     paths judged at the old commit and its blobs read at the new one,
        #     so a branch that gutted its own seal in that window was told
        #     CLEAN, in the name `feat/x`, on a path list that predated the
        #     edit. The diff is re-read AFTER the last ref-dependent read and
        #     the two lists must agree; a branch that moved is UNDETERMINED,
        #     which is what "I do not know what I just judged" is worth.
        #
        #     BODIES only, because BODIES is the only role that reads anything
        #     after the diff: for every other role `changed_paths_between` is
        #     the single read and there is no window between it and itself.
        #     Comparing the path LISTS rather than resolving the commit is
        #     deliberate — the path list is the whole input to the path gate,
        #     so it is the thing whose staleness can change a verdict, and
        #     `git rev-parse` is a fourth read on the gate path that the seals
        #     covering this module do not model.
        try:
            recheck = changed_paths_between(
                repo_root, base_ref, branch_ref, run=run
            )
        except RoleDiffError as exc:
            return _undetermined(
                f"cannot re-read the branch diff {base_ref}...{branch_ref} to "
                f"confirm it did not move mid-check: {exc}",
                policy_source=source,
                checked_paths=changed,
            )
        if recheck != changed:
            return _undetermined(
                f"{branch_ref} moved while it was being checked: the path gate "
                f"judged {list(changed)!r} and the branch now reports "
                f"{list(recheck)!r}. A verdict in the branch's NAME would be a "
                "claim about a revision that no longer exists, and the paths "
                "the gate never saw are exactly the ones a branch would move "
                "to hide",
                policy_source=source,
                checked_paths=changed,
                signature=signature,
            )
    elif role in (Role.SCAFFOLD, Role.SEALS, Role.ADJUDICATE):
        signature = _not_applicable_signature(role)
    else:
        # Exhaustive by construction: LEGACY returned above and the other four
        # are named. A Role member added without updating this dispatch lands
        # here and is UNDETERMINED, never a silent NOT_APPLICABLE + CLEAN.
        return _undetermined(
            f"no signature obligation is defined for role {role!r}; a new "
            "Role member must be handled everywhere it is dispatched, not "
            "fall through to the permissive branch",
            policy_source=source,
            checked_paths=changed,
        )

    # 6. The reachability arm (D7). WIRED HERE, and this call is the whole
    #    content of the D7 P4 wiring amendment; everything it composes lives in
    #    `branch_reachability` and nothing about the answer is re-decided here.
    #
    #    The import is FUNCTION-LOCAL and must stay so: `branch_reachability`
    #    imports THIS module at its own module level for `Role` and
    #    `DiffVerdict`, so a module-level import here is a cycle. That is also
    #    the line that puts `branch_reachability` — and, transitively through
    #    its own module-level imports, `call_site_reachability` and
    #    `call_site_contract` — into the floor's DERIVED delegation closure, so
    #    this call cannot land without the `FLOOR_GLOBS` entry and the
    #    `_DELEGATION_TARGETS` rows that land with it.
    #
    #    `already_violation` is the verdict block's own VIOLATION condition,
    #    read one line before the block applies it, and not a re-derivation:
    #    the two must not be able to disagree about whether the branch is
    #    already refused, because that boolean is what decides whether a doomed
    #    branch pays for a whole-tree sweep.
    #    THE `try` IS NOT DEFENSIVE PADDING AND IT IS NOT A SECOND GUARD ON
    #    `check_branch_reachability`, WHICH IS CONTRACTED NEVER TO RAISE. It
    #    covers the two things on this arm that are NOT covered by that
    #    contract: the import itself, and `verdict_of`, which raises by design
    #    on an unmapped `ReachabilityObligation` and, through `worst_verdict`,
    #    on a `DiffVerdict` nothing ranked. Both are exactly the "a new member
    #    must be ruled on, not defaulted" refusals this lineage keeps, and
    #    `check_branch` is contracted never to raise — so they land as
    #    UNDETERMINED carrying the sentence, which is what "I do not know how
    #    bad this is" is worth. Swallowing them into CLEAN would give the
    #    permissive answer a new spelling, on the one arm whose whole unit is
    #    about refusing exactly that.
    try:
        from . import branch_reachability as branch_reachability_mod

        already_violation = bool(violations) or bool(signature.changes)
        reachability = branch_reachability_mod.check_branch_reachability(
            repo_root,
            base_ref,
            branch_ref,
            role,
            changed,
            already_violation=already_violation,
            run=run,
        )
        reachability_verdict = branch_reachability_mod.verdict_of(reachability)
    except Exception as exc:  # noqa: BLE001 - check_branch never raises
        return _undetermined(
            f"the reachability arm could not be composed into the verdict: "
            f"{type(exc).__name__}: {exc}. check_branch is contracted never to "
            "raise; a gate whose new arm turns a traceback into a CI mystery "
            "has replaced exit 3 with nothing",
            policy_source=source,
            checked_paths=changed,
            signature=signature,
        )

    if violations or signature.changes:
        verdict = DiffVerdict.VIOLATION
        detail = (
            f"{len(violations)} forbidden path(s) and "
            f"{len(signature.changes)} changed scaffolded signature(s)"
        )
    elif (
        role is Role.BODIES
        and signature.status in _BODIES_BLOCKING_SIGNATURE_STATUSES
    ):
        verdict = DiffVerdict.UNDETERMINED
        detail = (
            f"the scaffolded-signature comparison did not run "
            f"({signature.status.value}"
            f"{': ' + signature.detail if signature.detail else ''}); on "
            "'bodies' — the one role whose gate that is — an unchecked "
            "signature is not a pass"
        )
    else:
        verdict = DiffVerdict.CLEAN
        detail = (
            f"{len(changed)} changed path(s) checked against the "
            f"{rule.kind.value} rule for {role.value!r} and against the "
            f"{len(FLOOR_GLOBS)}-glob floor; signatures: "
            f"{signature.status.value}"
        )
        if signature.unsupported_paths:
            # The price of the two 2026-08-09 rulings, paid on the same line
            # that announces the pass. A CLEAN reached over files nobody opened
            # says so HERE, in the verdict's own detail — the line
            # `_print_report` puts on stdout and the only line a caller that
            # logs the verdict keeps — and not only in the signature sub-report
            # a caller may never reach for. The signature gate is Python-only,
            # so on a Go/TypeScript/SQL tree this is most branches: a quiet
            # CLEAN would be a downgrade from the loud-but-wrong refusal it
            # replaces.
            #
            # Keyed on `unsupported_paths` and not on the status, because after
            # the per-file ruling a MIXED diff clears too and it is the one
            # shape where "name the skipped paths" and "dump the whole diff"
            # give different answers. Only the skipped ones are listed: the
            # compared paths are already printed by `_print_report` under
            # "changed paths examined:", and a detail that listed everything
            # would be satisfied identically by a gate that had lost track of
            # what it skipped (P4 dispute 1, 2026-08-09). Scoped to the CLEAN
            # branch, where the compared files had nothing to report; a
            # VIOLATION detail naming the path of the changed symbol is the
            # report doing its job and is not touched here.
            if signature.status is (
                SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
            ):
                detail += (
                    "; NOTHING in this diff is in a language this gate can "
                    "read, so no scaffolded signature was compared and none "
                    "could have been caught — unread: "
                )
            else:
                detail += (
                    f"; {len(signature.unsupported_paths)} of the "
                    f"{len(changed)} changed path(s) are in a language this "
                    "gate has no comparator for, so their signatures were "
                    "compared by nothing and are not covered by this pass — "
                    "unread: "
                )
            detail += ", ".join(signature.unsupported_paths)

    # 6b. The union, at `_VERDICT_PRECEDENCE` — VIOLATION over UNDETERMINED
    #     over CLEAN, which is the order this block already applies. Done
    #     AFTER the block rather than inside it so that the three arms above
    #     keep computing exactly what they computed before this amendment, and
    #     the reachability arm can only ever make the verdict WORSE. It can
    #     never make it better: `worst_verdict` is monotone and CLEAN is its
    #     bottom, so an arm that answers CLEAN — which is every NOT_RUN and
    #     every ADVISORY role, always — changes nothing at all.
    #
    #     WHEN THE ARM MOVES THE VERDICT, IT SAYS SO ON `detail`. That is
    #     forced rather than chosen: `detail` is the line `_print_report` puts
    #     on stdout and the only line a caller that logs the verdict keeps, and
    #     a verdict whose stated reason is the signature arm's while the actual
    #     reason is the reachability arm's is a report that answers a question
    #     nobody asked. When the arm does NOT move the verdict its status is
    #     still printed, by `_print_report`, off `RoleDiffResult.reachability`
    #     — so "this gate did not ask about your branch" is legible on a pass
    #     without rewriting the three details above, which several seals in
    #     this suite pin verbatim.
    #
    #     `worst_verdict` raises on a `DiffVerdict` nothing ranked, for the
    #     same reason `verdict_of` does, so it is guarded the same way and for
    #     the same contract: this function never raises.
    try:
        unioned = branch_reachability_mod.worst_verdict(
            (verdict, reachability_verdict)
        )
    except Exception as exc:  # noqa: BLE001 - check_branch never raises
        return _undetermined(
            f"the reachability verdict {reachability_verdict!r} could not be "
            f"unioned with {verdict!r}: {type(exc).__name__}: {exc}",
            policy_source=source,
            checked_paths=changed,
            signature=signature,
        )
    if unioned is not verdict:
        detail = (
            f"{detail}; and the reachability gate answers "
            f"{reachability_verdict.value.upper()} "
            f"({reachability.status.value}"
            f"{': ' + reachability.detail if reachability.detail else ''})"
        )
        verdict = unioned

    return RoleDiffResult(
        verdict=verdict,
        role=role,
        base_ref=base_ref,
        branch_ref=branch_ref,
        violations=violations,
        signature=signature,
        checked_paths=changed,
        policy_source=source,
        detail=detail,
        reachability=reachability,
    )


# --------------------------------------------------------------------------- #
# Private helpers for the diff-time path (no decisions of their own — every
# rule they serve is stated in the public function that calls them)
# --------------------------------------------------------------------------- #

def _drop_commons(
    violations: Sequence[PathViolation],
    floor_violations: Sequence[PathViolation],
) -> tuple[PathViolation, ...]:
    """Forgive a violation whose only offence is the rulings commons (D-66).

    The mirror of :func:`_union_with_floor`: that one ADDS refusals no role may
    override, this one REMOVES refusals every role may ignore. Applied to the
    decision, never to a policy, for the same reason the floor is — ADJUDICATE's
    rule is ALLOW_ONLY and its globs must stay exactly the row's
    ``disputed_paths``.

    **THE FLOOR OUTRANKS THE COMMONS.** A path that is on both is refused: the
    forgiveness is keyed by path against ``floor_violations``, so no rulings
    spelling can buy a floored file. Today the two sets are disjoint by
    construction (``**/docs/rulings/**`` names no machinery), and this guard is
    what keeps that true if either list grows.
    """
    floored = {v.path for v in floor_violations}
    return tuple(
        v for v in violations
        if v.path in floored or not first_matching_glob(v.path, (RULINGS_GLOB,))
    )


def _floor_violations(changed_paths: Sequence[str]) -> tuple[PathViolation, ...]:
    """Every changed path on :data:`FLOOR_GLOBS`, with the floor's own reason.

    Read against the paths GIT REPORTED, never against a declaration, which is
    the whole content of the 2026-08-07 ruling: the floor cannot be spelled
    around because it never reads the spelling. A ``disputed_paths:`` of
    ``sub/**`` contains no trace of the config file and still cannot buy
    ``sub/project/.dispatcher.yaml``.

    The floor is a deny set and is therefore NOT expressible as a union into a
    :class:`RoleRule`'s ``globs``: :data:`Role.ADJUDICATE`'s rule is
    ALLOW_ONLY_GLOBS, where adding a glob *widens*. It is a second, separate
    pass — which is also why it can carry :data:`FLOOR_RATIONALE` instead of
    whatever text the rule it overrode happened to hold.

    ``rule_kind`` is DENY_GLOBS on every floor violation, because that is what
    the floor is, regardless of the kind of the role rule it overrode. Pure;
    order follows ``changed_paths``; one violation per matching path.
    """
    return tuple(
        PathViolation(
            path=path,
            matched_glob=matched,
            rule_kind=RuleKind.DENY_GLOBS,
            rationale=FLOOR_RATIONALE,
        )
        for path, matched in (
            (p, first_matching_glob(p, FLOOR_GLOBS)) for p in changed_paths
        )
        if matched is not None
    )


def _union_with_floor(
    rule_violations: Sequence[PathViolation],
    floor_violations: Sequence[PathViolation],
    changed_paths: Sequence[str],
) -> tuple[PathViolation, ...]:
    """The role's violations with the floor's laid over them, in diff order.

    Per path the floor WINS, so a path on the floor is reported once and with
    the floor's reason. It has to win rather than merely be appended: for a
    DENY role the table already denies the config file, so appending would
    report one path twice, and for ADJUDICATE the rule that "explains" the
    refusal would be the one saying the writable set is ``disputed_paths:`` —
    the sentence that cannot explain it.

    A path NOT on the floor keeps the role rule's own violation verbatim: a
    floor hit must not turn the innocent rest of the diff into violations and
    send an agent hunting for a rule that does not exist.
    """
    floor_by_path = {v.path: v for v in floor_violations}
    rule_by_path: dict[str, PathViolation] = {}
    for violation in rule_violations:
        rule_by_path.setdefault(violation.path, violation)

    ordered: list[PathViolation] = []
    reported: set[str] = set()
    for path in changed_paths:
        if path in reported:
            continue
        violation = floor_by_path.get(path) or rule_by_path.get(path)
        if violation is not None:
            ordered.append(violation)
            reported.add(path)
    return tuple(ordered)


#: How long any single git read on the gating path may take. A gate that hangs
#: is a gate that is not enforcing anything, and CI would report the hang as an
#: infrastructure failure rather than as an unchecked branch.
_GIT_TIMEOUT_SECONDS = 30

#: The statuses that mean the signature comparison did NOT run. Named as a set
#: rather than spelled `is not CHECKED` so NOT_APPLICABLE — a real answer for
#: a role with no signature duty — can never be swept in with them.
_UNCHECKED_SIGNATURE_STATUSES: frozenset[SignatureCheckStatus] = frozenset(
    {
        SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE,
        SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE,
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE,
    }
)

#: The subset of those that REFUSE a bodies branch. A second, separately named
#: notion, because after the 2026-08-09 rulings "the comparison did not run" and
#: "the branch is not cleared" stopped being the same question: a diff whose
#: unread files are unread for their LANGUAGE did not run the comparison over
#: them and is nonetheless CLEAN.
#:
#: What refuses is a check that started on a file this gate is responsible for
#: and could not finish; what does not is a file this gate was never able to
#: open in the first place — named instead, in
#: :attr:`SignatureComparison.unsupported_paths`, because no commit its author
#: can write would clear a refusal for it.
#:
#: Spelled as the blocking set rather than as `_UNCHECKED_SIGNATURE_STATUSES -
#: {the cleared ones}` so a future member has to be classified deliberately, and
#: so that the two sets can be read side by side and seen to differ by exactly
#: the states the rulings cleared.
#:
#: **Two members, since D2** (P4, 2026-08-09). It was one, and the second is
#: UNCHECKED_COMPARATOR_UNAVAILABLE, which reaches the same conclusion by a
#: different route: the check did not merely fail to finish, it never started,
#: because the machine could not run the reader. The test above — "did this gate
#: START on a file it is responsible for" — is the one that puts it here, and it
#: is worth stating that the OTHER plausible test would have got it wrong. "Can
#: the branch author fix it?" answers NO for a fault (the author cannot install
#: ``go`` on the runner) and NO for an unsupported language, which would have
#: grouped the fault with the CLEARING state and handed a broken image the
#: authority to clear every Go branch it built. Remediability is not the
#: criterion. Responsibility is: this gate CLAIMED the file, so silence about it
#: is a claim it did not earn.
_BODIES_BLOCKING_SIGNATURE_STATUSES: frozenset[SignatureCheckStatus] = frozenset(
    {
        SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE,
    }
)

#: How the aggregate ranks the reasons one FILE can come back with, worst
#: first. It replaces "the first non-CHECKED status wins", which was sound only
#: while every non-CHECKED status refused a bodies branch: once
#: UNCHECKED_UNSUPPORTED_LANGUAGE clears and UNCHECKED_UNPARSEABLE refuses,
#: first-wins makes the verdict a fact about git's path order. MEASURED, on the
#: shape of the cheapest per-file fix (2026-08-09):
#:
#:     ["src/app.py", "db/migrate/001_bay.sql"] -> undetermined  unparseable
#:     ["db/migrate/001_bay.sql", "src/app.py"] -> CLEAN         unsupported
#:
#: — a branch whose Python does not parse, cleared on nothing but where the
#: migration sorted. So the blocking reason outranks the language one and the
#: language one outranks CHECKED, per file rather than by position.
#:
#: Only the statuses a per-file comparison can PRODUCE are ranked.
#: UNCHECKED_NO_SUPPORTED_FILE is the aggregate's own conclusion about the whole
#: diff and NOT_APPLICABLE is a fact about the role; neither is ever handed to
#: :func:`_worst_signature_status`, which raises rather than guess a rank for a
#: state it was not taught — a new member must be classified here deliberately,
#: not absorbed at whatever end of the order it happens to land.
#:
#: **UNCHECKED_COMPARATOR_UNAVAILABLE ranks FIRST** (P4, 2026-08-09, D2). Two
#: separate questions, answered separately, because only the first has a forced
#: answer:
#:
#: 1. *Above UNCHECKED_UNSUPPORTED_LANGUAGE — forced, and the reason the member
#:    exists.* Below it, a mixed diff of one faulted ``.go`` and one unreadable
#:    ``.sql`` folds to the language status, which clears BODIES: the broken CI
#:    image gets its clean bill of health back through the fold instead of
#:    through the promotion. Neither the ``examined`` counter nor
#:    ``unsupported_paths`` reaches that case — measured — so this line is the
#:    only thing refusing it.
#: 2. *Above UNCHECKED_UNPARSEABLE — a judgement, since both block and the
#:    verdict is UNDETERMINED either way.* What the rank decides is which reason
#:    the report LEADS with, and the tie-break is which claim the reader can
#:    trust. UNPARSEABLE was produced by working apparatus: the gate read the
#:    file and established a fact. A fault says the apparatus itself did not
#:    run, so nothing about the faulted paths was established at all and the
#:    completeness of the whole run is in question — including, on a Go/Python
#:    diff, whether the Go files hid a real violation. Leading with the
#:    trustworthy sub-claim while the instrument is broken understates the
#:    situation. It is also the report that names the right owner: an author
#:    told only "your file does not parse" fixes it, re-pushes, and hits a wall
#:    nobody mentioned, whereas a broken image is a FLEET condition that wants
#:    finding on the first branch rather than on the first branch with clean
#:    Python. Both reasons still reach the reader — ``details`` accumulates
#:    every per-file line — so what the rank moves is the headline, and the
#:    headline should be the one nobody can act on from inside the diff.
#:
#: The two are recorded apart on purpose: a later unit may re-argue 2 (nothing
#: fails open if it flips) but must not re-argue 1 without reopening the whole
#: member.
_SIGNATURE_STATUS_PRECEDENCE: tuple[SignatureCheckStatus, ...] = (
    SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE,
    SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
    SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE,
    SignatureCheckStatus.CHECKED,
)


def _worst_signature_status(
    left: SignatureCheckStatus, right: SignatureCheckStatus
) -> SignatureCheckStatus:
    """Whichever of two per-file statuses ranks worse in
    :data:`_SIGNATURE_STATUS_PRECEDENCE`.

    Commutative and associative, so the aggregate folding it over the changed
    paths cannot depend on their order — which is the whole point (see
    ``test_the_verdict_does_not_depend_on_where_the_unreadable_files_sort``).

    BOTH arguments are checked against the precedence before either is
    returned, and an unranked one raises :class:`RoleProtocolError`. Checking
    only the winner would rank an unknown status LAST by omission — the loop
    would find the known one first and return it — which is precisely "clear
    the branch for a reason nobody classified". :func:`check_branch` turns the
    raise into UNDETERMINED.
    """
    for candidate in (left, right):
        if candidate not in _SIGNATURE_STATUS_PRECEDENCE:
            raise RoleProtocolError(
                f"{candidate!r} is not a per-file signature status this "
                "aggregate knows how to rank against "
                f"{[s.value for s in _SIGNATURE_STATUS_PRECEDENCE]}; a status "
                "ranked by accident decides a bodies branch by accident, so a "
                "new member is classified here or it is not ranked at all"
            )
    for status in _SIGNATURE_STATUS_PRECEDENCE:
        if left is status or right is status:
            return status
    raise AssertionError(  # pragma: no cover - both arguments are ranked above
        f"unreachable: {left!r} and {right!r} both rank"
    )


def _not_applicable_signature(role: Role) -> SignatureComparison:
    """The signature result for a role with no scaffolded-signature duty.

    A :class:`SignatureComparison` rather than None: NOT_APPLICABLE is a named
    state the result must be able to report, and a None here would make every
    consumer handle a nullable to learn the same fact.
    """
    return SignatureComparison(
        status=SignatureCheckStatus.NOT_APPLICABLE,
        detail=(
            f"role {role.value!r} has no scaffolded-signature obligation; "
            "only 'bodies' implements against sealed stubs"
        ),
    )


def _compare_branch_signatures(
    repo_root: str | Path,
    base_ref: str,
    branch_ref: str,
    changed_paths: Sequence[str],
    *,
    run: Callable[..., object] | None,
) -> SignatureComparison:
    """:func:`compare_signatures` over every changed ``*.py`` path at base.

    **The baseline is the MERGE-BASE, not ``base_ref``'s tip** (D1-inputs I4).
    :func:`changed_paths_between` takes a three-dot diff, so the path list is
    the branch's own work measured from the merge-base; reading the baseline
    text at ``base_ref`` itself made the two halves of one check describe two
    different revisions. A base that advanced since the branch forked is the
    ordinary case, not an exotic one, and when it advanced to carry the very
    signature the branch widened, the gate compared the branch against a tip
    that already agreed with it, found no change, and reported CLEAN on the
    change §2a's gate exists to catch. The merge-base is what the diff
    measured from, so it is what the blobs are read at.

    The merge-base is resolved LAZILY — on the first ``*.py`` path about to be
    compared, and once — so a diff with no Python in it runs no third git
    command at all, and the read happens only where its answer is used.

    A path absent at the merge-base is skipped: a file that did not exist
    there has no scaffolded signature to preserve. Absence comes from
    :func:`file_text_at` returning None, which that function guarantees means
    "not in that tree" and nothing else — a read error raises out of here and
    the caller maps it to UNDETERMINED, because "I could not read the base"
    reported as "newly added" would suppress every signature change in it.

    **A file this module did not compare is not reported as checked**
    (D1-inputs I5). Every non-``*.py`` path used to be ``continue``d past
    before a status could be produced, so the aggregate said CHECKED —
    "``changes`` is authoritative" — for a diff in which a Go file's parameter
    list could have been widened underneath it, and for a diff of nothing but
    Markdown in which zero files were opened. That contradicts the per-file
    contract, where :func:`compare_signatures` answers
    UNCHECKED_UNSUPPORTED_LANGUAGE for both of those paths. It is now the
    aggregate's answer too, so "checked", "not applicable" and "examined
    nothing" are three reports rather than one word. On BODIES the caller maps
    any UNCHECKED_\\* to UNDETERMINED, which is what an unchecked signature on
    the role whose gate that is has always been worth.

    The boundary that ruling stops at (P4, 2026-08-08): a ``*.py`` path absent
    at the merge-base still counts as EXAMINED, and a diff of nothing but new
    Python files is still CHECKED. The gate made a determination there — it
    read the base tree and established the file is not in it, so there was no
    scaffolded signature to preserve and none was broken — which is exactly
    what :func:`compare_signatures` answers for that input. The skipped Go
    file is ignorance wearing the same word; this is knowledge. Ruling
    otherwise would make a body branch whose Python work is all new files
    permanently UNDETERMINED, for work that could not have violated anything.

    **A diff with NO supported file in it is its own state** (P4, 2026-08-09).
    When the loop examined nothing and skipped at least one path for its
    language, the aggregate is UNCHECKED_NO_SUPPORTED_FILE rather than
    UNCHECKED_UNSUPPORTED_LANGUAGE. The distinction is exactly "did this gate
    examine anything": one `.go` beside one `.py` is the partial check and
    keeps the older status; one `.go` alone is a gate that never started. Both
    are CLEAN at :func:`check_branch` — the verdict stopped separating them
    when the per-file ruling landed, which is what makes the two STATES the
    only place the difference still lives. It is derived from this loop's own
    counters, not from a second reading of the path list — see
    :func:`_supported_language_refusal`, which is the only place the language
    rule is spelled.

    ``unsupported_paths`` collects, in diff order, every path skipped for its
    language — taken verbatim from the per-file refusal, so the aggregate and
    :func:`compare_signatures` cannot disagree about what went unread. On a
    mixed diff it holds the skipped file ALONE, which is what distinguishes an
    honest report from one that hands back the whole path list.

    **Aggregation: the WORST reason any one file produced wins** — ranked by
    :data:`_SIGNATURE_STATUS_PRECEDENCE` — and the changes of every file are
    unioned, so one unparseable file cannot hide a changed signature in
    another and a partial check never reports as CHECKED.

    Worst, not first. This paragraph used to say "the FIRST non-CHECKED status
    wins", and that was sound only while every non-CHECKED status refused a
    bodies branch: the aggregate reported a reason, and which reason it was did
    not change the verdict. The per-file ruling split the reasons —
    UNCHECKED_UNPARSEABLE refuses and UNCHECKED_UNSUPPORTED_LANGUAGE clears —
    so under first-wins a branch whose Python does not parse is CLEARED
    whenever an unreadable neighbour sorts ahead of it, which is git's path
    order deciding a gate. Ranking is also what keeps the reported state the
    reason the branch was REFUSED: "unsupported language" on a branch refused
    for a Python file that does not parse sends its author off to write a SQL
    comparator.

    **D2 — a path whose comparator FAULTED counts as EXAMINED, and contributes
    nothing to ``unsupported_paths``.** Normative, and the promotion above is
    why it has to be: the promotion fires when the loop examined NOTHING and
    skipped at least one path for its language. A registered language whose
    reader could not run (no ``go`` binary, a helper that died, a timeout) was
    not skipped for its language — the gate reached for it and the machine
    failed — so it must not satisfy either half of that condition. Get this
    wrong in either place and a Go-only diff built in a broken CI image is
    promoted to UNCHECKED_NO_SUPPORTED_FILE and reported CLEAN, which is a
    broken image handing out clean bills of health. The two halves must agree:
    ``examined`` counts every path a registry row claimed, whatever happened
    next, and ``unsupported_paths`` holds only what
    :func:`_supported_language_refusal` named. See
    :func:`_comparator_unavailable_comparison` for the other side of the same
    invariant.

    Unchanged by D2: SQL and Java have no row in :data:`COMPARATORS`, so their
    paths are skipped for their language exactly as before, are named in
    ``unsupported_paths``, and on a diff of nothing else are CLEAN. That is the
    2026-08-09 ruling applied to languages it did not name, and it is coverage
    this gate does not have rather than a decision it made.

    **How that meets the ranking (P4, 2026-08-09 — the merge of this unit onto
    the per-file verdict).** The scaffold was branched while this paragraph
    still read "the FIRST non-CHECKED status wins", so it described the
    examined/``unsupported_paths`` bookkeeping as the whole of what keeps a
    fault off the CLEAN path. Under ranking it is not. THREE mechanisms now
    stand between a comparator fault and a CLEAN, and the diff that exercises
    all three is the MIXED one — one faulted ``.go`` beside one unreadable
    ``.sql`` — not the Go-only diff the scaffold argued from:

      1. ``examined`` counts the faulted path, so the promotion to
         UNCHECKED_NO_SUPPORTED_FILE cannot fire (this loop). **Necessary for
         the mixed diff**: the ``.sql`` already supplies the promotion's other
         half, so a miscounted fault is enough to clear the branch on its own.
      2. The faulted path is absent from ``unsupported_paths``
         (:func:`_comparator_unavailable_comparison`, and this loop, which
         extends that list only from a language refusal). Necessary for the
         Go-only diff and for the honesty of the report; measured NOT to be
         sufficient or independently load-bearing for the verdict.
      3. The status is RANKED ABOVE UNCHECKED_UNSUPPORTED_LANGUAGE in
         :data:`_SIGNATURE_STATUS_PRECEDENCE`. Necessary for the mixed diff and
         reached only when 1 and 2 hold: with no promotion, the fold decides,
         and a demoted rank hands back the ``.sql``'s clearing status.

    The measured verdict for every one of those broken, singly and together, is
    tabulated at :func:`signature_status_for_fault` and sealed in
    ``tests/test_role_protocol_faults.py``. Note that OMITTING the rank
    entirely is fail-CLOSED — :func:`_worst_signature_status` raises on an
    unranked status and :func:`check_branch` maps the raise to UNDETERMINED —
    so the trap is not forgetting to rank a new status, which is loud, but
    ranking it wrongly, which is silent. That is why the rank is sealed against
    a mixed diff and not merely asserted as a tuple.

    Raises :class:`RoleProtocolError` on an empty ``changed_paths``.
    :func:`check_branch` refuses an empty diff at step 3, so no public call can
    reach it; the raise is here because there is no honest status for it. Every
    per-file state is a claim about a file, and this input has none — CHECKED
    would be "I compared them and they agree" about nothing at all, and the
    older answer of UNCHECKED_UNSUPPORTED_LANGUAGE was chosen to fail CLOSED
    and stopped doing so the moment that status started clearing branches. The
    caller maps the raise to UNDETERMINED, which is what the old choice bought
    and this one keeps.
    """
    if not changed_paths:
        raise RoleProtocolError(
            "the scaffolded-signature aggregate was asked about an empty path "
            "list; every state it can report is a claim about a file, and "
            "'checked' about nothing at all is the pass bought by doing "
            "nothing that this gate exists to refuse"
        )

    status = SignatureCheckStatus.CHECKED
    changes: list[SignatureChange] = []
    details: list[str] = []
    unsupported_paths: list[str] = []
    merge_base: str | None = None
    examined = 0

    for path in changed_paths:
        refusal = _supported_language_refusal(path)
        if refusal is not None:
            # NOT `continue` on its own: this module cannot compare this file,
            # nothing else did either, and an unchecked file must not report as
            # an unchanged signature. The state, the prose and the named path
            # all come from `compare_signatures`' own refusal, so the aggregate
            # and the per-file contract cannot disagree and the aggregate does
            # not spell the language rule a second time.
            status = _worst_signature_status(status, refusal.status)
            details.append(refusal.detail)
            unsupported_paths.extend(refusal.unsupported_paths)
            continue
        if merge_base is None:
            merge_base = _merge_base_of(
                repo_root, base_ref, branch_ref, run=run
            )
        examined += 1
        base_text = file_text_at(repo_root, merge_base, path, run=run)
        if base_text is None:
            continue
        head_text = file_text_at(repo_root, branch_ref, path, run=run)
        comparison = compare_signatures(path, base_text, head_text)
        changes.extend(comparison.changes)
        status = _worst_signature_status(status, comparison.status)
        if comparison.detail:
            details.append(comparison.detail)

    if not examined and unsupported_paths:
        # NOTHING in this diff is a file this gate has a comparator for. That
        # is not the partial check I5 refuses — it is its own state, and
        # `check_branch` clears it (2026-08-09 ruling). Derived from the
        # counters this loop already keeps, not from a second reading of the
        # path list: `examined` and `unsupported_paths` are both written by the
        # one branch that consults `_supported_language_refusal`, so "which
        # languages can this gate read" is still asked in exactly one place.
        #
        # The promotion is unconditional on the status because it cannot
        # collide: reaching here with `examined == 0` means no comparison ran,
        # so the only status the ranking can have settled on is the refusal's
        # own. It is deliberately NOT ranked against the others — this is not a
        # per-file reason at all but the aggregate's conclusion about the WHOLE
        # diff, which is why `_SIGNATURE_STATUS_PRECEDENCE` does not carry it.
        status = SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
        # The aggregate fact, on top of the per-path lines above, which have
        # already named every one of them — so this counts rather than
        # re-listing. The enumeration a reader needs on one line is in
        # `check_branch`'s own detail, which is the line that reaches stdout
        # and a caller's log.
        details.append(
            f"not one of the {len(unsupported_paths)} changed path(s) is in a "
            "language this gate can read, so no signature was compared at all"
        )
    # There is no third case. Every path either produced a language refusal
    # (and is in `unsupported_paths`) or was examined, so `examined == 0` with
    # nothing unsupported means an empty path list — refused at the top of this
    # function, because the older answer here, UNCHECKED_UNSUPPORTED_LANGUAGE,
    # was picked to fail CLOSED and stopped doing so when the per-file ruling
    # took it out of `_BODIES_BLOCKING_SIGNATURE_STATUSES`.

    return SignatureComparison(
        status=status,
        changes=tuple(changes),
        detail="; ".join(details),
        unsupported_paths=tuple(unsupported_paths),
    )


def _merge_base_of(
    repo_root: str | Path,
    base_ref: str,
    branch_ref: str,
    *,
    run: Callable[..., object] | None,
) -> str:
    """The commit ``base_ref...branch_ref`` measures the branch's work from.

    ``git merge-base base_ref branch_ref`` — the third and last git read on
    the gate path, and the one that makes the signature half of the check
    describe the same revision as the path half (D1-inputs I4). Spelled
    positionally with the base first, which is what the two ``_run_stub``
    helpers were extended to answer and nothing wider.

    Every failure raises :class:`RoleDiffError`, which :func:`check_branch`
    maps to UNDETERMINED: no merge-base (unrelated histories), several (a
    criss-cross merge, where picking one would be a guess about which history
    the branch forked from), an unreadable ref. A baseline this cannot
    establish is never silently replaced with ``base_ref``'s tip — that
    substitution IS the defect.
    """
    argv = ["git", "merge-base", base_ref, branch_ref]
    rc, out, err = _run_git_capture(argv, str(repo_root), run)
    if rc != 0:
        raise RoleDiffError(
            f"git merge-base {base_ref} {branch_ref} in {repo_root} exited "
            f"{rc}: {err.strip() or '(no stderr)'}; the signature baseline is "
            "the revision the diff measured from, and falling back to the "
            "base ref's tip is the defect this read exists to close"
        )
    candidates = [line for line in out.split("\n") if line.strip()]
    if len(candidates) != 1:
        raise RoleDiffError(
            f"git merge-base {base_ref} {branch_ref} in {repo_root} named "
            f"{len(candidates)} commits ({candidates!r}); a baseline that is "
            "not exactly one revision cannot be chosen here without guessing "
            "which history the branch forked from"
        )
    return candidates[0].strip()


def _run_git_capture(
    cmd: Sequence[str],
    cwd: str,
    run: Callable[..., object] | None,
) -> tuple[int, str, str]:
    """``(returncode, stdout, stderr)`` for one git command on the gate path.

    ``run`` is the injectable subprocess seam (``push_verify``'s convention).
    Its result may be a ``CompletedProcess`` or a ``(rc, out, err)`` triple:
    the annotation admits both and neither reading is more correct, so both
    are accepted rather than one being pinned here.

    Every way this can fail — the seam raising, a timeout, a result shape
    nothing can read, stdout that is not UTF-8 — becomes
    :class:`RoleDiffError`. Deliberately total: a git read that returns
    *something* on failure would hand the caller an empty path list, and an
    empty path list is the one answer this module may never derive from a
    failure.

    Not shared with ``repo_config._run_git``: that one is the blob reader's
    plumbing and hands back raw bytes for the object-store path. The one fact
    those two would be at risk of answering differently — what a git read of a
    *path* means — is not duplicated: :func:`file_text_at` delegates to
    ``repo_config.blob_text_at`` rather than running git itself.
    """
    import subprocess

    argv = [str(part) for part in cmd]
    try:
        if run is None:
            proc = subprocess.run(
                argv, cwd=cwd, capture_output=True, timeout=_GIT_TIMEOUT_SECONDS
            )
            rc: int = proc.returncode
            raw_out: object = proc.stdout or b""
            raw_err: object = proc.stderr or b""
        else:
            result = run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
            if hasattr(result, "returncode"):
                rc = int(getattr(result, "returncode"))
                raw_out = getattr(result, "stdout", "") or ""
                raw_err = getattr(result, "stderr", "") or ""
            elif isinstance(result, tuple) and len(result) >= 2:
                rc = int(result[0])
                raw_out = result[1] or ""
                raw_err = result[2] if len(result) > 2 and result[2] else ""
            else:
                raise RoleDiffError(
                    f"the injected git seam returned an unusable "
                    f"{type(result).__name__} for {' '.join(argv)}; a result "
                    "that cannot be read is not an empty diff"
                )
    except RoleDiffError:
        raise
    except Exception as exc:
        raise RoleDiffError(
            f"{' '.join(argv)} in {cwd} could not be run: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    return rc, _git_stdout_text(raw_out, argv), _git_stderr_text(raw_err)


def _git_stdout_text(raw: object, argv: Sequence[str]) -> str:
    """git stdout as text, STRICTLY decoded.

    A path this cannot decode raises rather than becoming mojibake: a
    mis-decoded path is one :func:`evaluate_changed_paths` cannot glob-match,
    which is a hole in the gate that reports as a pass.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RoleDiffError(
                f"{' '.join(argv)} emitted output that is not valid UTF-8: "
                f"{exc}; a path that cannot be decoded cannot be matched"
            ) from exc
    raise RoleDiffError(
        f"{' '.join(argv)} produced stdout of type {type(raw).__name__}, "
        "which is neither text nor bytes"
    )


def _git_stderr_text(raw: object) -> str:
    """git stderr as text for a message. Lossy on purpose — it is diagnostic
    only, and a diagnostic that cannot be decoded must not mask the failure it
    is describing."""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode("utf-8", "replace")
    return "" if raw is None else str(raw)


# --------------------------------------------------------------------------- #
# CLI face (used by scripts/check_body_branch.sh)
# --------------------------------------------------------------------------- #


class ExitCode(Enum):
    """Process exit codes for the script face. Distinct per outcome, because a
    CI job that cannot tell "violation" from "could not check" will treat the
    second as the first or, worse, as a pass.

    Mirrors ``BoundaryError``'s CLI convention (plan §0.2) in spirit: 0 ok,
    nonzero and *specific* otherwise.
    """

    OK = 0
    VIOLATION = 2
    UNDETERMINED = 3
    USAGE = 64
    NOT_IMPLEMENTED = 70


#: Stands in for a task key when the role word came from argv rather than from
#: a `tasks.yaml` row, so :func:`parse_role_field`'s messages stay diagnosable
#: from a CI log without this module owning a second copy of the closed set.
_CLI_ROLE_SUBJECT = "<the role argument>"

#: The script face's usage line. One string, so the shell wrapper never has to
#: restate the arity or the legal roles (which is how the two drift apart).
_USAGE = (
    "usage: check_body_branch <base> <branch> <role> "
    "[--tasks PATH --task-key KEY]"
)

#: The two options that name the task row whose :class:`TaskRoleSpec` is
#: applied. Given together or not at all — half a row reference names no row,
#: and honouring the half that was given is how a caller comes to believe a
#: spec was applied when none was.
_TASKS_OPTION = "--tasks"
_TASK_KEY_OPTION = "--task-key"

#: Verdict → exit code. A mapping rather than a chain of ifs so a new
#: :class:`DiffVerdict` member is an *unmapped* verdict — caught below and
#: failed closed — instead of falling through whichever branch happens to be
#: last.
_VERDICT_EXIT_CODES: Mapping[DiffVerdict, ExitCode] = {
    DiffVerdict.CLEAN: ExitCode.OK,
    DiffVerdict.VIOLATION: ExitCode.VIOLATION,
    DiffVerdict.UNDETERMINED: ExitCode.UNDETERMINED,
}


def parse_role_value(text: str) -> Role:
    """Parse a CLI/script role argument into a :class:`Role`.

    Accepts exactly the members of :data:`AUTHORABLE_ROLES`, case-insensitive
    after stripping. ``legacy`` is rejected here too: a checker invoked with
    ``legacy`` is a checker invoked with no role, and answering CLEAN for it
    would let a caller disable the gate by passing a word. Raises
    :class:`RoleProtocolError`.

    **P3 implementation note.** This is deliberately a *delegation* to
    :func:`parse_role_field` with a synthetic one-key row rather than a second
    closed-set match. The script face and the plan-time parser must accept
    exactly the same words: two membership tests over
    :data:`AUTHORABLE_ROLES` would be two facts in two places and would drift
    on precisely the interesting shapes (``legacy``, ``scaffold+seals``,
    blank), which are the ones a caller reaches for to disable the gate. The
    only difference is the diagnostic subject — there is no task key here, so
    :data:`_CLI_ROLE_SUBJECT` stands in for one.
    """
    return parse_role_field(
        {ROLE_FIELD_CANONICAL: text}, task_key=_CLI_ROLE_SUBJECT
    )


def _split_row_reference(
    argv: Sequence[str],
) -> tuple[list[str], str | None, str | None, str | None]:
    """``(positional, tasks_rel, task_key, usage error)`` over ``argv``.

    Hand-rolled rather than ``argparse``: :func:`main`'s contract is "exactly
    three positional arguments, anything else is USAGE", and argparse answers
    a wrong arity by printing its own message and raising ``SystemExit`` —
    which a CLI face that returns an exit code must not do.

    The two options are given TOGETHER or not at all. Honouring whichever half
    arrived is how a caller comes to believe a spec was applied when none was,
    so half a reference is a usage error and not a silent ``spec=None``.
    """
    values: dict[str, str] = {}
    positional: list[str] = []
    tokens = list(argv)
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token in (_TASKS_OPTION, _TASK_KEY_OPTION):
            if token in values:
                return positional, None, None, f"{token} given more than once"
            if idx + 1 >= len(tokens):
                return positional, None, None, f"{token} needs a value"
            values[token] = tokens[idx + 1]
            idx += 2
            continue
        positional.append(token)
        idx += 1

    tasks_rel = values.get(_TASKS_OPTION)
    task_key = values.get(_TASK_KEY_OPTION)
    if (tasks_rel is None) != (task_key is None):
        return (
            positional,
            None,
            None,
            f"{_TASKS_OPTION} PATH and {_TASK_KEY_OPTION} KEY are given "
            "together or not at all: half a row reference names no row",
        )
    return positional, tasks_rel, task_key, None


def _task_role_spec_at_base(
    repo_root: str | Path, base_ref: str, tasks_rel: str, task_key: str
) -> TaskRoleSpec:
    """One worklist row's :class:`TaskRoleSpec`, read out of ``base_ref``'s
    object store — never the working tree.

    Invariant 6 by the same route as :func:`load_role_policy_from_base`, and
    it bites hardest on the most privileged role: an ADJUDICATE row's
    ``disputed_paths:`` **is** its writable set, so a branch that supplied its
    own row would widen its own gate by editing one line — including the line
    that hands it the worklist file. ``tasks_rel`` is therefore repo-relative
    and resolved against the protected base, and a worklist the branch merely
    added is not one this gate will read.

    The blob read goes through :func:`file_text_at` — the module's one reader
    of a path out of a ref (invariant 5) — so a ref that will not resolve
    raises :class:`RoleDiffError`, which :func:`main` maps to UNDETERMINED.
    Everything else (an absent file, an unparseable worklist, a key that names
    no row, a row the protocol rejects) is a :class:`RoleProtocolError`: "I
    could not find the row" is never answered with "no spec, carry on", which
    is the fail-open shape a typo reaches.
    """
    from ruamel.yaml.error import YAMLError

    from . import yaml_io

    text = file_text_at(repo_root, base_ref, tasks_rel)
    if text is None:
        raise RoleProtocolError(
            f"{tasks_rel!r} is not in {base_ref!r}. The row is read from the "
            "protected base, never from the branch under judgement"
        )
    try:
        doc = yaml_io.loads(text)
    except YAMLError as exc:
        raise RoleProtocolError(
            f"malformed YAML in {tasks_rel} at {base_ref}: {exc}"
        ) from exc
    rows = doc.get("tasks") if isinstance(doc, Mapping) else None
    if rows is None:
        raise RoleProtocolError(
            f"{tasks_rel} at {base_ref} has no 'tasks:' sequence, so it names "
            "no rows at all"
        )
    for row in rows:
        if isinstance(row, Mapping) and str(row.get("key")) == task_key:
            return parse_task_role_spec(row, task_key=task_key)
    raise RoleProtocolError(
        f"no task {task_key!r} in {tasks_rel} at {base_ref}"
    )


def main(argv: Sequence[str]) -> int:
    """``check_body_branch <base> <branch> <role> [--tasks PATH --task-key
    KEY]`` — returns an :class:`ExitCode` value.

    Prints a human-readable report to stdout (every violated path with its
    matching glob and the rule's rationale, every changed signature) and
    diagnostics to stderr. Exactly three POSITIONAL arguments; anything else
    is :data:`ExitCode.USAGE`. Maps :func:`check_branch`'s verdict to OK /
    VIOLATION / UNDETERMINED, and never maps UNDETERMINED to OK.

    ``repo_root`` is the current working directory: the script runs inside the
    checkout being judged, as CI does.

    ``--tasks PATH --task-key KEY`` name the worklist row whose
    :class:`TaskRoleSpec` is applied. Without them there is no spec, and the
    branch is judged by its role's default rule alone — which is right for
    every role whose rule is STATIC (the two deny-based roles, and SEALS, whose
    allow set is static too since the 2026-08-10 inversion) and is *not* an
    answer for ADJUDICATE, whose
    writable set lives on the row (:func:`check_branch` returns UNDETERMINED
    rather than guessing). ``PATH`` is repo-relative and the row is read out
    of ``<base>``'s object store by :func:`_task_role_spec_at_base`; see there
    for why the working tree is not an option.

    **P3 implementation notes.**

    * An unparseable ``role`` is :data:`ExitCode.USAGE` (64), never a verdict
      code. 0/2/3 all tell CI "a gate ran and reached a conclusion"; when the
      role would not parse, nothing was checked at all, and 3 in particular
      would be a lie about *which* step failed. The P2 seal only pins "never
      OK" and names the choice as an open dispute; this is the resolution and
      the reason for it.
    * A ``--task-key`` that names no row takes that same resolution: USAGE,
      because nothing was checked and the argument is the thing that was
      wrong. What it must never be is OK — degrading a missing row to
      ``spec=None`` would let a typo turn the ADJUDICATE gate into the BODIES
      one, and turn a per-task ``immutable_paths:`` addition into a comment.
      An unreadable *ref* is different: git ran and could not answer, which
      is UNDETERMINED (3).
    * A ``spec`` whose role disagrees with the ``role`` argument is NOT
      reconciled here; :func:`check_branch` answers it (UNDETERMINED). Two
      places deciding which of the two names the rule is how they come to
      disagree.
    * The rationale printed for a violation is
      :attr:`PathViolation.rationale`, carried on the violation itself. It is
      deliberately not re-derived from the policy here: a second policy read
      on the reporting path is exactly how the report and the verdict come to
      disagree about which rule fired.
    * :func:`check_branch` is looked up as a module global at call time, not
      captured, so the one decision point stays substitutable.
    """
    import sys

    positional, tasks_rel, task_key, option_error = _split_row_reference(argv)
    if option_error is not None:
        print(f"check_body_branch: {option_error}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return ExitCode.USAGE.value

    if len(positional) != 3:
        print(_USAGE, file=sys.stderr)
        print(
            f"  roles: {_authorable_values()} "
            "('legacy' is not accepted: a role-less task has no immutable "
            "paths, and accepting the word here would disable the gate)",
            file=sys.stderr,
        )
        print(
            f"  got {len(positional)} positional argument(s): {positional!r}",
            file=sys.stderr,
        )
        return ExitCode.USAGE.value

    base_ref, branch_ref, role_text = positional
    try:
        role = parse_role_value(role_text)
    except RoleProtocolError as exc:
        print(f"check_body_branch: {exc}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return ExitCode.USAGE.value

    spec: TaskRoleSpec | None = None
    if tasks_rel is not None and task_key is not None:
        try:
            spec = _task_role_spec_at_base(
                Path.cwd(), base_ref, tasks_rel, task_key
            )
        except RoleProtocolError as exc:
            print(f"check_body_branch: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return ExitCode.USAGE.value
        except RoleDiffError as exc:
            # git ran and could not answer. That is 3, not 64: the invocation
            # was well-formed and the check did not conclude.
            print(f"check_body_branch: {exc}", file=sys.stderr)
            print(
                "check_body_branch: UNDETERMINED is not a pass — the branch "
                "was not cleared",
                file=sys.stderr,
            )
            return ExitCode.UNDETERMINED.value

    result = check_branch(Path.cwd(), base_ref, branch_ref, role, spec=spec)

    _print_report(result)

    exit_code = _VERDICT_EXIT_CODES.get(result.verdict)
    if exit_code is None:
        # A DiffVerdict member nobody mapped. Fail closed and say so: the one
        # thing this function must never do is report an unmapped verdict as
        # OK (`skills/explicit-state.md` — an unknown state is not a pass).
        print(
            f"check_body_branch: unmapped verdict {result.verdict!r}; "
            "refusing to report it as a pass",
            file=sys.stderr,
        )
        return ExitCode.UNDETERMINED.value
    return exit_code.value


def _print_report(result: RoleDiffResult) -> None:
    """The human-readable half of :func:`main`, on stdout.

    Everything an agent needs to understand why it was refused, from the run
    log alone: the verdict, what was actually examined (so a CLEAN verdict can
    be audited for having examined something), every forbidden path with the
    glob that forbade it and that rule's rationale, and every changed
    signature. Diagnostics that are not the verdict go to stderr in
    :func:`main`.
    """
    import sys

    print(
        f"check_body_branch: {result.verdict.value.upper()} "
        f"role={result.role.value} base={result.base_ref} "
        f"branch={result.branch_ref}"
    )
    source = result.policy_source.value if result.policy_source else "unresolved"
    print(f"  policy: {source}")
    print(f"  changed paths examined: {len(result.checked_paths)}")
    for path in result.checked_paths:
        print(f"    {path}")

    for violation in result.violations:
        print(f"  FORBIDDEN {violation.path}")
        print(
            f"    matched {violation.matched_glob} "
            f"({violation.rule_kind.value})"
        )
        if violation.rationale:
            print(f"    why: {violation.rationale}")

    signature = result.signature
    if signature is not None:
        print(f"  scaffolded signatures: {signature.status.value}")
        if signature.detail:
            print(f"    {signature.detail}")
        for change in signature.changes:
            after = "<removed>" if change.after is None else change.after
            print(f"  CHANGED SIGNATURE {change.path}::{change.symbol}")
            print(f"    before: {change.before}")
            print(f"    after:  {after}")

    # D7 escalation 4, ruled 2026-08-12 (P4). "A verdict a caller cannot read
    # the reason for is the vacuous half of this gate."
    #
    # PRINTED ON EVERY VERDICT, INCLUDING CLEAN, and that is the whole point of
    # the block rather than a formatting choice. `BranchReachability` contracts
    # it in as many words — "``status`` / ``obligation``: the two named states.
    # Both are printed, always, including on a CLEAN verdict" — because "this
    # gate cleared your branch" and "this gate did not ask about your branch"
    # are different sentences and only one of them is a pass. It is the same
    # sentence `role_protocol` bought its two CLEAN signature rows with.
    #
    # `None` IS A STATE AND IT IS PRINTED AS ONE. It means the question was
    # never put — the P1 scaffold's state, and now only reachable through a
    # `RoleDiffResult` some other caller built. Printing nothing for it would
    # make the one shape this unit exists to refuse the one shape the report is
    # silent about.
    reachability = result.reachability
    if reachability is None:
        print(
            "  reachability: NOT ASKED — this result carries no D7 record at "
            "all, which is not a pass and is not a clean sweep"
        )
    else:
        print(
            f"  reachability: {reachability.status.value} "
            f"(obligation: {reachability.obligation.value})"
        )
        # The non-vacuity pair, and the third figure that makes it readable —
        # but ONLY when both sweeps actually produced a report. A "seals
        # examined: head 0, base 0" line printed under NOT_THIS_ROLES_GATE
        # reads as a measurement and is a default, and this whole unit is about
        # not letting "nobody looked" wear the clothes of "nothing was there".
        #
        # The discriminator is DERIVED and not a written-out list of statuses:
        # `head_dispositions` is None on exactly the exits that never got a
        # report, because every arm that carries the counts carries the
        # dispositions with them. A list would be a second enumeration of
        # `ReachabilitySweepStatus` in a module that does not own that enum,
        # and it would go stale on the tenth member.
        if reachability.head_dispositions is None:
            print("    no sweep ran under this status, so there is nothing to count")
        else:
            print(
                f"    seals examined: head "
                f"{reachability.head_seals_examined}, base "
                f"{reachability.base_seals_examined}; production roots at "
                f"head: {reachability.head_production_roots}"
            )
            print(
                "    dispositions at head: "
                + ", ".join(
                    f"{disposition.value}={count}"
                    for disposition, count in sorted(
                        reachability.head_dispositions.items(),
                        key=lambda item: item[0].value,
                    )
                )
            )
        for finding in reachability.introduced:
            print(
                f"  INTRODUCED {finding.disposition.value.upper()} "
                f"{finding.subject_key}"
            )
            print(f"    seal: {finding.test_id}")
            if finding.detail:
                print(f"    {finding.detail}")
        # Reported, never blocking — a declaration goes stale exactly when the
        # wiring lands, so refusing the branch that retires it would punish the
        # good outcome. It still has to be deleted, and ADJUDICATE is the role
        # that owns the file and reads this.
        for stale in reachability.stale_declarations:
            print(
                f"  STALE DECLARATION {stale.subject_key} (seal "
                f"{stale.test_id}) answered no finding — delete the row"
            )
        if reachability.detail:
            print(f"    {reachability.detail}")

    if result.detail:
        print(f"  detail: {result.detail}")

    if result.verdict is DiffVerdict.UNDETERMINED:
        print(
            "check_body_branch: UNDETERMINED is not a pass — the branch was "
            "not cleared",
            file=sys.stderr,
        )


if __name__ == "__main__":  # pragma: no cover - script face
    import sys

    # NOT `main(...)`, AND THE DIFFERENCE IS A LIVE VERDICT (D7 P4, 2026-08-12).
    #
    # `scripts/check_body_branch.sh` runs `python -P -m
    # claude_dispatcher.role_protocol`, and `-m` on a MODULE loads that module
    # TWICE: once as `__main__`, and again as `claude_dispatcher.role_protocol`
    # the moment anything imports it under its real name. The two module
    # objects have two `Role` enums, two `DiffVerdict` enums and two of every
    # class here, and `A.Role.BODIES is not B.Role.BODIES`.
    #
    # That was INERT until step 6 was wired, because nothing on the diff-time
    # path had ever crossed into a sibling module holding a table KEYED BY a
    # type defined here. `branch_reachability._ROLE_OBLIGATIONS` is such a
    # table, and it is keyed by the PACKAGE's `Role`. Measured on this
    # revision, with the wiring in and this delegation out: every run through
    # the CI entrypoint answered
    #
    #     UNDETERMINED … unchecked_sweep_vacuous: no reachability obligation
    #     is defined for role <Role.BODIES: 'bodies'>
    #
    # — the gate refusing every legal bodies branch, from `obligation_for_role`
    # doing exactly its job on a `Role` member that genuinely was not a key of
    # the mapping it was handed. Eleven rows in this suite reddened, all of
    # them through the real `check_body_branch.sh`.
    #
    # So the ONE copy that runs is the package's. This is not a workaround for
    # the enum dispatch: the alternative — making the lookups tolerant of a
    # foreign `Role` by matching on `.value` — is the D5 defect this unit just
    # removed, wearing a different hat, and it would leave two live `Role`
    # classes in the process for every other table to trip over later.
    from claude_dispatcher.role_protocol import main as _packaged_main

    raise SystemExit(_packaged_main(sys.argv[1:]))
