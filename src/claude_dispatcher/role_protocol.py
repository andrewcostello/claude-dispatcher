"""The P1/P2/P3/P4 build-protocol: task roles, immutable paths, phase order.

**Unit D1. P1 wrote these signatures and their contract docstrings, P2 wrote
the seals against them, P3 (this pass) wrote the bodies and the wiring. The
docstrings remain the contract; where a 2026-08-04 operator ruling overrode
one, the ruling is named at that spot. See "Wiring, and what is enforced
today" for the call sites that exist and the ones that do not.**

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
remove one, which is also why this module needs no separate "floor" tier the
way `risk.py` does (`risk.FORBIDDEN_FLOOR_GLOBS` exists because a repo may
*replace* `risk:` lists wholesale; here nothing can be replaced, so every
default entry is already a floor). A narrowing override is a self-weakening
policy — the defect class this whole project exists to close — and is a typed
error, not a silently-ignored line.

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
  * `orchestrator.run` → :func:`agent_correlation_warnings` alongside the
    preflight warnings (printed and replayed into run.log).
  * `repo_config.load` → validates a `roles:` section via
    :func:`role_policy_from_mapping`, so an invalid or narrowing section is a
    load failure rather than a line dropped into `RepoConfig.unknown_keys`.
    It deliberately does not *use* the parsed policy: `load` reads the
    working tree, and the gating path takes its policy from the protected
    base (:func:`load_role_policy_from_base`, invariant 6).
  * `scripts/check_body_branch.sh` → execs :func:`main`, so CI, PR time and
    any hand invocation go through :func:`check_branch`.

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
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

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
    matches zero directories in that translation, so one pattern covers both
    the root and nested layouts and a root-anchored twin would be dead weight
    (the same one-pattern-one-fact reasoning as
    ``risk.AUTHORITY_FLOOR_GLOBS``).

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
#     for BODIES and SEALS: those are machine-read instructions that the review
#     gate executes, so editing them edits the reviewer that is about to judge
#     the change.
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
        ),
        rationale=(
            "P1 must not write the seals it will be judged by; a scaffold "
            "author who writes tests re-creates the circular oracle that "
            "produced 24 vacuous seals (plan §5)"
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
FORBIDDEN_DISPUTED_GLOBS: frozenset[str] = frozenset(
    {"*", "**", "**/*", "/", "./**", "."}
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
        strings and must not appear in :data:`FORBIDDEN_DISPUTED_GLOBS`.
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
            if entry.strip() in FORBIDDEN_DISPUTED_GLOBS:
                raise RoleProtocolError(
                    f"task {task_key} has {DISPUTED_PATHS_FIELD} entry "
                    f"{entry!r}; a wildcard adjudication is not an "
                    "adjudication — it converts allow-only into unrestricted "
                    "with extra steps"
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
            if glob.strip() in FORBIDDEN_DISPUTED_GLOBS:
                raise RoleProtocolError(
                    f"rule for {role_name} allows {glob!r}; a wildcard "
                    "allow-only set is an unrestricted rule with extra steps"
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
    produce a rule at all (validate before apply — invariant 2).
    """
    validate_override(spec, policy)
    rule = policy.rule_for(spec.role)

    if rule.kind is RuleKind.DENY_GLOBS:
        return dataclasses.replace(
            rule, globs=_dedup((*rule.globs, *spec.added_immutable_globs))
        )
    if rule.kind is RuleKind.ALLOW_ONLY_GLOBS:
        return dataclasses.replace(rule, globs=tuple(spec.disputed_paths))
    if rule.kind is RuleKind.UNRESTRICTED:
        return rule
    raise RoleProtocolError(
        f"task {spec.task_key}: cannot build an effective rule for unknown "
        f"kind {rule.kind!r}"
    )


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

    # --- warnings: reported, never refusing ------------------------------- #
    defaults = built_in_policy()
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
        At least one changed source file is not Python, so this module cannot
        compare its signatures. Named, not silent: an unchecked file must not
        report as an unchanged signature. Callers surface it; the plan's Go
        side needs its own comparator.
    UNCHECKED_UNPARSEABLE
        A revision would not parse as Python. Same reasoning.
    NOT_APPLICABLE
        The role has no signature obligation (every role except BODIES).
    """

    CHECKED = "checked"
    UNCHECKED_UNSUPPORTED_LANGUAGE = "unchecked_unsupported_language"
    UNCHECKED_UNPARSEABLE = "unchecked_unparseable"
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
    """Result of comparing one file's signatures across two revisions."""

    status: SignatureCheckStatus
    changes: tuple[SignatureChange, ...] = ()
    detail: str = ""


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

    Statuses: both texts parse → CHECKED. ``path`` is not ``*.py`` →
    UNCHECKED_UNSUPPORTED_LANGUAGE with the path in ``detail``. Either text
    fails to parse → UNCHECKED_UNPARSEABLE. ``base_text`` None (the file is
    new on the branch) → CHECKED with no changes: a file that did not exist at
    base has no scaffolded signature to preserve. ``head_text`` None (the file
    was deleted) → every base symbol is a change with ``after`` None.

    Pure function of the two texts.
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError


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
      4. :func:`evaluate_changed_paths`.
      5. for BODIES only, :func:`compare_signatures` over every changed
         ``*.py`` path that exists at ``base_ref``; other roles get
         :data:`SignatureCheckStatus.NOT_APPLICABLE`.

    Verdict: VIOLATION if any path violation or any signature change;
    UNDETERMINED on any :class:`RoleDiffError`, unreadable policy, missing
    required ``spec``, empty diff, or a signature status of
    UNCHECKED_\\* **when the role is BODIES** — an unchecked signature on the
    role whose gate that is, is not a pass; CLEAN only when the diff was read,
    was non-empty, produced no violation, and every applicable check ran.

    LEGACY always returns CLEAN when the diff read succeeded and was
    non-empty: a pre-protocol task has no immutable paths, and this function
    must not become a new gate on legacy work.
    """
    raise NotImplementedError


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


def parse_role_value(text: str) -> Role:
    """Parse a CLI/script role argument into a :class:`Role`.

    Accepts exactly the members of :data:`AUTHORABLE_ROLES`, case-insensitive
    after stripping. ``legacy`` is rejected here too: a checker invoked with
    ``legacy`` is a checker invoked with no role, and answering CLEAN for it
    would let a caller disable the gate by passing a word. Raises
    :class:`RoleProtocolError`.
    """
    raise NotImplementedError


def main(argv: Sequence[str]) -> int:
    """``check_body_branch <base> <branch> <role>`` — returns an
    :class:`ExitCode` value.

    Prints a human-readable report to stdout (every violated path with its
    matching glob and the rule's rationale, every changed signature) and
    diagnostics to stderr. Exactly three positional arguments; anything else
    is :data:`ExitCode.USAGE`. Maps :func:`check_branch`'s verdict to OK /
    VIOLATION / UNDETERMINED, and never maps UNDETERMINED to OK.

    ``repo_root`` is the current working directory: the script runs inside the
    checkout being judged, as CI does.
    """
    raise NotImplementedError


if __name__ == "__main__":  # pragma: no cover - script face
    import sys

    raise SystemExit(main(sys.argv[1:]))
