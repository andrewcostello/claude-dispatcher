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
argument covers only the three DENY_GLOBS roles: :data:`Role.ADJUDICATE` is
ALLOW_ONLY_GLOBS and :func:`effective_rule` builds its writable set out of the
task's own `disputed_paths:`, so an adjudicate row that declared
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

**NOT wired, stated rather than implied:** the post-implementer call the P1
rulings name as the point that actually saves a build cycle —
:func:`check_branch` inside the orchestrator's task loop, right after the
implementer returns and before verify — has no call site yet. Until it does,
a role's diff is checked at PR time and in CI only, which is one build cycle
later than the plan wants. That hook changes task-loop control flow and has
no seal in this unit; it is named here so nobody reads this module as
already providing it.

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
SEAL_VERIFY_TEST_PATHS = "<seal_verify.is_test_path: this repo's test files>"

#: The roles whose deny set includes ``seal_verify``'s test-path predicate.
#: D1 P2 ruling: the role gate does not keep its own notion of what a test
#: file is. Six of eleven ``seal_verify._TEST_PATH`` alternatives were
#: uncovered by the globs below — ``handler_test.js``, singular ``test/`` at
#: root and nested, ``__tests__/``, ``spec/``, ``fixtures/`` — so a body agent
#: could add a file `seal_verify` already treats as a seal and this gate said
#: CLEAN. One matcher, one fact.
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
#   * ``**/.dispatcher.yaml`` is denied to ALL FOUR authorable roles, scaffold
#     included (2026-08-04 P1 ruling, overriding P1's own contrary note here).
#     A unit's per-task override lives in its task row, so no role ever needs
#     to edit the policy file, and a role that can edit the file configuring
#     its own permissions is the self-widening shape this unit exists to
#     remove.
#   * ``**/generated/**`` appears NOWHERE (2026-08-04 P1 ruling, overriding
#     P1's SEALS/BODIES entries). The property wanted is not "bodies never
#     touch generated files" but "generated files equal generator output",
#     which the regenerate-and-diff gate owns for every role in every unit.
#     Denying the path made generator units (A3/A4's ``fsmgen``, whose bodies
#     legitimately commit regenerated output) undrivable, and ADD-only
#     overrides gave no escape. Any unit with generated output carries that
#     gate in its seals instead.
#   * ``**/roles/*.md`` + ``**/reviewer_prompts/**`` + ``**/verifier_prompts/**``
#     for all three DENY_GLOBS roles: those are machine-read instructions that
#     the review gate executes, so editing them edits the reviewer that is about
#     to judge the change. SCAFFOLD was added 2026-08-09 (S4): the rationale is
#     not role-specific, and `src/` — where both prompt directories live — is
#     the one tree SCAFFOLD exists to write in, so it was the role with the
#     easiest reach and the only one without the deny. `_shared.md` is
#     concatenated into EVERY reviewer seat's prompt by
#     `cross_family_reviewer._load_prompt`, which is why the directory glob is
#     the right grain and a list of family names would have missed it.
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
    RoleRule(
        role=Role.SEALS,
        kind=RuleKind.DENY_GLOBS,
        globs=(
            "**/src/**",
            "**/schema/**",
            "**/.dispatcher.yaml",
            "**/roles/*.md",
            "**/reviewer_prompts/**",
            "**/verifier_prompts/**",
        ),
        rationale=(
            "P2 commits its seals RED against P1's stubs; a seal author who "
            "may edit the implementation can make its own seal pass, which is "
            "the definition of a vacuous seal"
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
            "**/roles/*.md",
            "**/reviewer_prompts/**",
            "**/verifier_prompts/**",
        ),
        rationale=(
            "P3 makes the seals pass by implementing them, never by editing "
            "them (plan §2a); the schema is the sole source and the role "
            "policy is not the body agent's to widen"
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
#: overrides may not *remove* a deny entry — and that argument covers the three
#: DENY_GLOBS roles and nothing else. :data:`Role.ADJUDICATE` is
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
FLOOR_GLOBS: tuple[str, ...] = (
    "**/.dispatcher.yaml",
    "**/scripts/check_body_branch.sh",
    "**/src/claude_dispatcher/role_protocol.py",
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
    "the machinery that decides every role's permissions — the policy file, "
    "the module that implements the rules, or the entrypoint that runs them — "
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
      * ALLOW_ONLY_GLOBS → globs = ``spec.disputed_paths``. The policy's own
        (empty) globs are not unioned in: for ALLOW_ONLY a union would *widen*.
      * UNRESTRICTED → returned unchanged; an override on it was already
        rejected by :func:`parse_task_role_spec`.

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
        built = dataclasses.replace(rule, globs=tuple(spec.disputed_paths))
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
        comparator. On BODIES this blocks: the gate examined something and
        could not finish (D1-inputs I5).
    UNCHECKED_UNPARSEABLE
        A revision would not parse as Python. Same reasoning.
    UNCHECKED_NO_SUPPORTED_FILE
        **Nothing** in the diff is a file this gate has a comparator for — a
        Go-only, TypeScript-only or docs-only branch. Distinct from both of
        its neighbours, by the 2026-08-09 operator ruling (see the I6 section
        of ``tests/test_role_protocol_inputs.py``):

          * not UNCHECKED_UNSUPPORTED_LANGUAGE, because the ruled VERDICT
            differs — this one is CLEAN and the partial check is still
            UNDETERMINED. :func:`check_branch` decides from the status, so
            with one member it would have to re-derive the difference from the
            path list, i.e. spell the supported-language rule a second time
            outside :func:`_supported_language_refusal`, which owns it. Two
            copies of "which languages can this gate read" fail towards a
            silent CLEAN the day a Go comparator lands.
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
    """
    if rule.kind is RuleKind.UNRESTRICTED:
        return ()

    if rule.kind is RuleKind.DENY_GLOBS:
        patterns = tuple(
            glob for glob in rule.globs if glob != SEAL_VERIFY_TEST_PATHS
        )
        delegate = SEAL_VERIFY_TEST_PATHS in rule.globs
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
        return tuple(
            PathViolation(
                path=path,
                matched_glob=ALLOWLIST_MISS,
                rule_kind=rule.kind,
                rationale=rule.rationale,
            )
            for path in changed_paths
            if first_matching_glob(path, rule.globs) is None
        )

    raise RoleProtocolError(
        f"cannot evaluate changed paths for unknown rule kind {rule.kind!r}; a "
        "kind that falls out of the bottom would report every diff as clean"
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
# exactly the sense §2a means — and this unit does not read either. Neither does
# it read TypeScript (996). Those extensions appear in NO table here, on
# purpose: a "languages we know about but cannot read" table would be a second
# place answering "what language is this path", which is the property this
# section exists to protect. They are reported the way every unreadable file has
# been reported since the 2026-08-09 ruling — by PATH, in
# :attr:`SignatureComparison.unsupported_paths` and in the verdict's own detail
# — so a diff containing them says which files nobody opened, without this
# module having to hold an opinion about what SQL is.
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

    SQL, Java and TypeScript are absent. See this section's header: naming them
    here would create a second table that answers a language question, and the
    honest report of an unread SQL file is its PATH in
    :attr:`SignatureComparison.unsupported_paths`, not a language label.
    """

    PYTHON = "python"
    GO = "go"


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


def signature_status_for_fault(fault: ComparatorFault) -> SignatureCheckStatus:
    """The ONE mapping from a comparator fault to a reportable status.

    Normative table. Every member of :class:`ComparatorFault` maps to:

      ``SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE``

    — a status that **does not exist yet**, and cannot be added by P1. See "The
    P4 amendment this unit requires" below. There is no second row: every fault
    in that enum is an environment fault, they share a verdict and they share a
    remediation (fix the machine, not the branch), so splitting them across
    statuses would put a distinction in the status that the FAULT already
    carries. The fault travels in the detail; the status carries the verdict.

    **Totality.** A :class:`ComparatorFault` member with no row here raises
    rather than returning a default. A fault that fell out of the bottom into
    ``UNCHECKED_UNSUPPORTED_LANGUAGE`` would be promoted to
    UNCHECKED_NO_SUPPORTED_FILE on a Go-only diff and clear the branch — the
    broken-CI-image fail-open in one line. There is no permissive default here
    and there must never be one.

    **The BODIES verdict.** UNCHECKED_COMPARATOR_UNAVAILABLE is BLOCKING: it
    belongs in both :data:`_UNCHECKED_SIGNATURE_STATUSES` (the comparison did
    not run) and :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES` (and the branch is
    therefore not cleared) ⇒ :attr:`DiffVerdict.UNDETERMINED` on BODIES,
    ignored on every other role, which has no signature duty. It must NOT be
    promotable to UNCHECKED_NO_SUPPORTED_FILE, which is what makes it different
    from an unsupported language in the only way that shows up in a verdict.

    **The bookkeeping that makes the non-promotion true**, because it is not
    automatic — :func:`_compare_branch_signatures` promotes when it examined
    NOTHING and skipped at least one path for its language. A path whose
    comparator exists and faulted counts as **examined**: the gate tried to read
    it. So a Go-only diff on a machine with no ``go`` has ``examined == 1``, no
    promotion, and UNDETERMINED. The same path contributes NOTHING to
    ``unsupported_paths``, so the two mechanisms agree: it was not skipped for
    its language and it is not reported as such.

    **The P4 amendment this unit requires, flagged and NOT made here.** Adding
    the member reddens ``test_every_signature_check_status_is_reachable``
    (``tests/test_role_protocol_diff.py``), which pins
    :class:`SignatureCheckStatus` by VALUE-SET EQUALITY — deliberately, so that
    a sixth member cannot land without a ruling, exactly as the fifth could not.
    P1 may not amend a seal and P3 may not either. So this function is a
    contract with no body: the member, the amendment (a sixth literal in the
    written value set plus a PRODUCING call that reaches the new state — never
    ``produced.add(...)``, never ``>=`` on the set) and this body land in ONE
    P4-authored commit, or none of them do.

    Until then no fault is reachable: the only fingerprinter that can raise one
    is :class:`GoSignatureFingerprinter`, which is not implemented and not
    enrolled. The ``NotImplementedError`` is therefore dead code today and a
    hard error the moment it is not — which is the correct failure for "this
    build cannot even name what just happened".
    """
    raise NotImplementedError(
        "signature_status_for_fault: SignatureCheckStatus has no member for a "
        f"comparator fault ({fault.value}). Adding "
        "UNCHECKED_COMPARATOR_UNAVAILABLE requires the P4 amendment to "
        "test_every_signature_check_status_is_reachable described in this "
        "function's contract; a fault must never fall back to an existing "
        "member, because UNCHECKED_UNSUPPORTED_LANGUAGE is promoted to CLEAN "
        "on a diff this gate can read nothing in"
    )


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
GO_HELPER_SCHEMA = "claude-dispatcher/go-signature-fingerprint/v1"

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
    raise NotImplementedError("D2 P3: encode the helper request")


def decode_go_helper_response(stdout: str) -> GoHelperResponse:
    """Parse the helper's stdout, or raise the named fault.

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
    ``parse_error`` is returned intact, and it is
    :meth:`GoSignatureFingerprinter.fingerprints` that turns it into
    :class:`SourceUnparseable`. One place per decision.
    """
    raise NotImplementedError("D2 P3: decode and validate the helper response")


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
    """
    raise NotImplementedError("D2 P3: resolve the packaged helper source")


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
        the field is embedded.
      * ``interface`` type: the type parameter list, its embedded interfaces,
        and its method NAMES. The method signatures are not repeated here
        because each is its own ``Iface.Method`` symbol; repeating them would
        report one change twice. This mirrors the Python side, whose class
        fingerprint carries fields while methods are separate symbols.
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
        """
        raise NotImplementedError("D2 P3: fingerprint Go via the go/ast helper")


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
#: Enrolment is ONE edit — adding this row to :data:`COMPARATORS` — and it may
#: not happen until all four of these hold. They are listed as a checklist
#: because three of them are somebody else's commit:
#:
#:   1. :class:`GoSignatureFingerprinter` is implemented (P3).
#:   2. ``SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE`` exists and is
#:      in both status sets, with the seal amendment that lets it exist (P4 —
#:      see :func:`signature_status_for_fault`). Enrolling first would make a
#:      missing ``go`` binary raise ``NotImplementedError`` out of
#:      :func:`check_branch`, which is documented never to raise.
#:   3. :data:`FLOOR_GLOBS` covers the helper source and
#:      ``scripts/check_body_branch.sh`` reads it from the protected base (P4 —
#:      see :func:`go_helper_source_dir`).
#:   4. The SEVEN seals that pin Go as unreadable are amended by P4, because
#:      enrolment reddens every one of them and P3 may not touch a seal. In
#:      ``tests/test_role_protocol_diff.py``:
#:      ``test_an_unchecked_comparison_is_named_never_reported_as_unchanged``
#:      (its ``cmd/classify/main.go`` row) and
#:      ``test_every_signature_check_status_is_reachable`` (its ``m.go`` probe
#:      and its Go-only BODIES probe — the latter is how the fifth status is
#:      PRODUCED, so it needs a replacement language, not a deletion). In
#:      ``tests/test_role_protocol_inputs.py``:
#:      ``test_a_bodies_diff_this_gate_cannot_read_is_clean_and_names_what_it_missed``,
#:      ``test_cannot_read_this_language_and_no_duty_here_stay_two_different_states``,
#:      ``test_the_paths_named_unread_are_the_skipped_ones_not_the_whole_diff``,
#:      ``test_the_per_file_comparator_names_the_file_it_could_not_read`` and
#:      ``test_the_ci_face_clears_a_go_only_branch_and_names_the_file_it_could_not_read``.
#:      Those seals are CORRECT today and state the ruled behaviour; what
#:      changes underneath them is which languages are unreadable, so each needs
#:      its Go probe REPLACED by one in a language this gate still cannot read —
#:      SQL and Java are the honest choices, 1,097 files in the target repo and
#:      no comparator planned — never deleted. A seal deleted because the fact
#:      it rested on moved is a seal the next unit does not have.
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

#: **THE registry.** The one table that says what this gate can read, and the
#: only input to :func:`support_for_path`. Adding a language is adding a row;
#: no dispatch site changes, because there is no dispatch site.
COMPARATORS: tuple[LanguageSupport, ...] = (PYTHON_SUPPORT,)

#: Rows that are written but not live. Nothing dispatches on this tuple — it
#: exists so that "scaffolded but not enrolled" is a NAMED state with a
#: mechanism (`skills/explicit-state.md`: absence is a state and must be
#: nameable) rather than a row someone forgot, and so
#: :func:`validate_registry` can refuse a pending row that collides with a live
#: one before anybody tries to enrol it.
PENDING_COMPARATORS: tuple[LanguageSupport, ...] = (GO_SUPPORT,)


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
    :func:`_compare_branch_signatures`'s loop — and the 2026-08-09 ruling made
    a third copy tempting, because :func:`check_branch`'s verdict now differs
    between a Go-only diff and a Go-plus-Python one. That difference is
    carried by the STATUS instead (see
    :attr:`SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE`), and the two
    pre-existing copies were collapsed into this function rather than joined
    by a third, so the day a Go comparator lands there is exactly one
    ``endswith`` to update and no copy left behind to fail towards a silent
    CLEAN.

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
         roles get :data:`SignatureCheckStatus.NOT_APPLICABLE`. A changed path
         this module did not compare leaves the aggregate UNCHECKED_\\*, which
         on BODIES is UNDETERMINED (D1-inputs I5) — **except** when NO changed
         path is in a language this gate can read, which is
         :data:`SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE` and is CLEAN
         (2026-08-09 operator ruling, D1 I6). See
         :data:`_BODIES_BLOCKING_SIGNATURE_STATUSES`.
      5b. for BODIES only, :func:`changed_paths_between` again — the path gate
         ran against the revision step 3 read, and step 5 re-resolved
         ``branch_ref`` for every blob. A branch that advanced in between is
         UNDETERMINED rather than CLEAN in its own name (D1-inputs I3). No
         other role reads anything after step 3, so no other role has the
         window.

    Verdict: VIOLATION if any path violation or any signature change;
    UNDETERMINED on any :class:`RoleDiffError`, unreadable policy, missing
    required ``spec``, empty diff, a branch that moved mid-check, or a
    BLOCKING unchecked signature status **when the role is BODIES** — a
    signature check that started and could not finish, on the role whose gate
    that is, is not a pass; CLEAN otherwise, when the diff was read, was
    non-empty, still described the same branch when the reads finished, and
    produced no violation.

    The one unchecked status that does NOT refuse a bodies branch (2026-08-09
    operator ruling, D1 I6): UNCHECKED_NO_SUPPORTED_FILE — a diff in which not
    one path is in a language this gate has a comparator for. The check did not
    start, rather than failing partway, and refusing it was a false refusal
    with no override: nothing the branch could commit would clear it, because
    the whole of its work is in a language this module cannot read. **The CLEAN
    is not silent.** ``detail`` — the line :func:`_print_report` puts on stdout
    — carries the unread paths and the language reason, alongside
    :attr:`SignatureComparison.unsupported_paths`, because the signature gate
    is Python-only and on a Go/TypeScript tree this verdict means the gate
    opened no file at all.

    **The whole signature-status → BODIES verdict table (D2), in one place,
    because a state whose verdict has to be inferred is a state somebody will
    infer wrongly.** Read it as the specification; the two frozensets below are
    its mechanism.

      ============================== ============= ==================
      status                         BODIES        every other role
      ============================== ============= ==================
      CHECKED (no changes)           CLEAN         n/a
      CHECKED (with changes)         VIOLATION     n/a
      UNCHECKED_UNPARSEABLE          UNDETERMINED  n/a
      UNCHECKED_UNSUPPORTED_LANGUAGE UNDETERMINED  n/a
      UNCHECKED_NO_SUPPORTED_FILE    CLEAN         n/a
      UNCHECKED_COMPARATOR_UNAVAIL.  UNDETERMINED  n/a
      NOT_APPLICABLE                 n/a           CLEAN
      ============================== ============= ==================

    The last row of the unchecked group does not exist yet: see
    :func:`signature_status_for_fault` for the member it names, why every
    :class:`ComparatorFault` maps to it, and the P4 amendment that must land
    with it. It is UNDETERMINED and not CLEAN because a toolchain that could not
    run is not a language nobody can read: the first is an environment fault
    somebody can fix and the second is a permanent fact about this gate. Give
    the fault the language answer and a CI image with no ``go`` binary clears
    every Go branch it builds — loudly wrong replaced by quietly wrong, which is
    the trade the 2026-08-09 ruling was careful NOT to make.

    None of the four UNDETERMINED rows is terminal for the branch: each names
    something an author or an operator can act on (fix the source, fix the
    image, write the comparator) and re-running clears it. UNCHECKED_NO_SUPPORTED
    _FILE is the one state nothing the branch commits can change, which is
    exactly why it is CLEAN — that was the ruling.

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
      * step 5's aggregate over several files reports the FIRST non-CHECKED
        status and the union of the changes: one unparseable file must not be
        able to hide a changed signature in another, and a partial check is
        not a CHECKED one.
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
        violations = _union_with_floor(
            evaluate_changed_paths(rule, changed), floor_violations, changed
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
        except RoleDiffError as exc:
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
        if signature.status is SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE:
            # The price of the 2026-08-09 ruling, paid on the same line that
            # announces the pass. A CLEAN reached without opening a file says
            # so HERE, in the verdict's own detail — the line `_print_report`
            # puts on stdout and the only line a caller that logs the verdict
            # keeps — and not only in the signature sub-report a caller may
            # never reach for. The signature gate is Python-only, so on a
            # Go/TypeScript tree this is most branches: a quiet CLEAN would be
            # a downgrade from the loud-but-wrong refusal it replaces.
            detail += (
                "; NOTHING in this diff is in a language this gate can read, "
                "so no scaffolded signature was compared and none could have "
                "been caught — unread: "
                + ", ".join(signature.unsupported_paths)
            )

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
    )


# --------------------------------------------------------------------------- #
# Private helpers for the diff-time path (no decisions of their own — every
# rule they serve is stated in the public function that calls them)
# --------------------------------------------------------------------------- #

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
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE,
    }
)

#: The subset of those that REFUSE a bodies branch. A second, separately named
#: notion, because after the 2026-08-09 ruling "the comparison did not run" and
#: "the branch is not cleared" stopped being the same question: a diff with no
#: supported file in it did not run the comparison and is nonetheless CLEAN.
#: Spelled as the blocking set rather than as `_UNCHECKED_SIGNATURE_STATUSES -
#: {the new one}` so a future member has to be classified deliberately, and so
#: that the two sets can be read side by side and seen to differ by exactly the
#: state the ruling created.
_BODIES_BLOCKING_SIGNATURE_STATUSES: frozenset[SignatureCheckStatus] = frozenset(
    {
        SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE,
        SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
    }
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
    UNCHECKED_UNSUPPORTED_LANGUAGE, and :func:`check_branch` clears it. The
    distinction is exactly "did this gate examine anything": one `.go` beside
    one `.py` is the partial check I5 refuses and keeps the older status; one
    `.go` alone is a gate that never started. It is derived from this loop's
    own counters, not from a second reading of the path list — see
    :func:`_supported_language_refusal`, which is the only place the language
    rule is spelled.

    ``unsupported_paths`` collects, in diff order, every path skipped for its
    language — taken verbatim from the per-file refusal, so the aggregate and
    :func:`compare_signatures` cannot disagree about what went unread. On a
    mixed diff it holds the skipped file ALONE, which is what distinguishes an
    honest report from one that hands back the whole path list.

    Aggregation: the FIRST non-CHECKED status wins and the changes of every
    file are unioned, so one unparseable file cannot hide a changed signature
    in another and a partial check never reports as CHECKED.

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
    """
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
            if status is SignatureCheckStatus.CHECKED:
                status = refusal.status
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
        if (
            status is SignatureCheckStatus.CHECKED
            and comparison.status is not SignatureCheckStatus.CHECKED
        ):
            status = comparison.status
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
        # so the only status the loop can have set is the refusal's own.
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
    elif status is SignatureCheckStatus.CHECKED and not examined:
        # Only reachable for an EMPTY path list — a non-empty diff with no
        # Python in it is the branch above. `check_branch` refuses an empty
        # diff before it gets here, so this is the state named rather than
        # left to fall through to CHECKED, which would be "I compared them and
        # they agree" about nothing at all. It is deliberately NOT the new
        # 2026-08-09 state: an empty diff has no unsupported path to name, and
        # the blocking status is the one that fails closed if this ever
        # becomes reachable.
        status = SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE
        details.append(
            "no path was examined, so there is no comparison to report"
        )

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
    the three deny-based roles and is *not* an answer for ADJUDICATE, whose
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

    raise SystemExit(main(sys.argv[1:]))
