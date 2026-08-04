"""D1 seals (phase P2): the role → immutable-paths TABLE and its closed sets.

Everything here is red today because every function in `role_protocol` raises
NotImplementedError; each test names, in its own docstring, the mutation or the
unimplemented contract that keeps it red and what will make it green. The table
is asserted THROUGH the module's own lenses (`built_in_policy`, `rule_for`,
`first_matching_glob`, `evaluate_changed_paths`, `validate_rule`) rather than by
reading the tuple directly, so a seal cannot pass by re-implementing the
matching it is supposed to be checking.

Three seals here are structural rather than per-row, and they are the ones that
survive a table rewrite:

  * `test_every_table_glob_has_exactly_one_probe_and_one_cover` — one fixture
    path per (role, glob), each matched by exactly ONE glob of that role, so
    deleting any single glob from DEFAULT_ROLE_RULES reddens exactly one row.
  * `test_every_seal_verify_test_path_is_denied_to_bodies` — the required set is
    derived FROM `seal_verify._TEST_PATH`, the other notion of "is this a test
    file", so the two cannot drift (the pattern is
    `test_risk.test_go_table_critical_paths_are_all_authority_paths`).
  * the two operator-ruling seals (`.dispatcher.yaml` denied to all four roles;
    `**/generated/**` absent from the table entirely) — these encode the
    2026-08-04 D1 P1 rulings, which POSTDATE this scaffold, so they are red both
    for the stubs and because the table still disagrees. See the P2 report's
    dispute list; the table is not this author's to edit.
"""

from __future__ import annotations

from enum import Enum

import pytest

from claude_dispatcher import risk
from claude_dispatcher.role_protocol import (
    AUTHORABLE_ROLES,
    CONFIG_SECTION,
    DEFAULT_ROLE_RULES,
    FORBIDDEN_DISPUTED_GLOBS,
    MANDATORY_PHASE_ORDER,
    PolicySource,
    Role,
    RolePolicy,
    RoleProtocolError,
    RoleRule,
    RuleKind,
    built_in_policy,
    evaluate_changed_paths,
    first_matching_glob,
    validate_rule,
)
from claude_dispatcher.seal_verify import _TEST_PATH


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _BogusKind(Enum):
    """A RuleKind member that does not exist — the `else: raise` probe.

    `RoleRule` is a frozen dataclass with no runtime type check, so a rule
    carrying this kind is constructible and is exactly the "a fourth state
    arrived" case from skills/explicit-state.md.
    """

    NOPE = "nope"


def _table_rule(role: Role) -> RoleRule:
    """The compiled-in rule for ``role``, read through the module's own lens."""
    return built_in_policy().rule_for(role)


# path -> the single DEFAULT_ROLE_RULES glob that must be its only cover, per
# role. Keyed by glob (patterns are unique across the table) and verified
# exhaustive against the table by
# `test_every_table_glob_has_exactly_one_probe_and_one_cover`, which is the
# glob-level mutation-resistance seal.
_GLOB_PROBES: dict[str, str] = {
    "**/tests/**": "pkg/tests/helper.py",
    "**/test_*.py": "pkg/test_helper.py",
    "**/*_test.py": "pkg/helper_test.py",
    "**/*_test.go": "pkg/helper_test.go",
    "**/*.test.*": "web/app.test.ts",
    "**/*.spec.*": "web/app.spec.ts",
    "**/testdata/**": "pkg/testdata/golden.json",
    "**/conftest.py": "pkg/conftest.py",
    "**/src/**": "src/claude_dispatcher/plan.py",
    "**/schema/**": "schema/merge.yaml",
    "**/.dispatcher.yaml": ".dispatcher.yaml",
    "**/roles/*.md": "roles/reviewer.md",
    "**/reviewer_prompts/**": "pkg/reviewer_prompts/_shared.md",
    "**/verifier_prompts/**": "pkg/verifier_prompts/verifier.md",
}

_TABLE_PAIRS = sorted(
    (rule.role.value, glob) for rule in DEFAULT_ROLE_RULES for glob in rule.globs
)


# --------------------------------------------------------------------------- #
# Closed set 1 of 4: Role
# --------------------------------------------------------------------------- #


def test_role_set_is_closed_and_every_member_has_exactly_one_rule() -> None:
    """`Role` has five members and the table covers each exactly once.

    Adding a Role member without a table row must redden here rather than
    silently produce a role with no policy — `rule_for`'s contract is that a
    missing entry raises, never "unrestricted".

    Red now: `built_in_policy()` raises NotImplementedError.
    Green when: `built_in_policy` returns DEFAULT_ROLE_RULES as a policy whose
    `rules` hold one entry per Role member.
    Falsify: add a member to `Role`, or delete a rule from the table.
    """
    assert {r.value for r in Role} == {
        "scaffold",
        "seals",
        "bodies",
        "adjudicate",
        "legacy",
    }
    assert AUTHORABLE_ROLES == frozenset(Role) - {Role.LEGACY}
    assert MANDATORY_PHASE_ORDER == (Role.SCAFFOLD, Role.SEALS, Role.BODIES)
    assert Role.ADJUDICATE not in MANDATORY_PHASE_ORDER

    policy = built_in_policy()
    assert policy.source is PolicySource.BUILT_IN_DEFAULTS
    assert policy.base_ref is None
    covered = [rule.role for rule in policy.rules]
    assert sorted(r.value for r in covered) == sorted(r.value for r in Role)
    assert len(covered) == len(set(covered)), f"duplicate role rows: {covered}"
    for role in Role:
        assert policy.rule_for(role).role is role


def test_rule_for_a_role_absent_from_the_table_raises() -> None:
    """A missing table entry is a bug, never UNRESTRICTED.

    This is the fail-open this module's `rule_for` docstring names: a Role added
    later without a table row must not read as "no restrictions".

    Red now: `RolePolicy.rule_for` raises NotImplementedError, which is not a
    RoleProtocolError, so `pytest.raises(RoleProtocolError)` fails.
    Green when: `rule_for` raises RoleProtocolError for an uncovered role.
    """
    partial = RolePolicy(
        rules=(
            RoleRule(
                role=Role.SCAFFOLD,
                kind=RuleKind.DENY_GLOBS,
                globs=("**/tests/**",),
                rationale="only entry",
            ),
        ),
        source=PolicySource.BUILT_IN_DEFAULTS,
    )
    with pytest.raises(RoleProtocolError):
        partial.rule_for(Role.BODIES)


# --------------------------------------------------------------------------- #
# Closed set 2 of 4: RuleKind — each kind PRODUCES its documented answer
# --------------------------------------------------------------------------- #


def test_rule_kind_set_is_closed() -> None:
    """Three kinds, and UNRESTRICTED is not spelled as "deny nothing".

    Red now: `validate_rule` raises NotImplementedError on the last assertion.
    Green when: every compiled-in rule is well-formed per `validate_rule`.
    """
    assert {k.value for k in RuleKind} == {
        "deny_globs",
        "allow_only_globs",
        "unrestricted",
    }
    kinds = {rule.role: rule.kind for rule in DEFAULT_ROLE_RULES}
    assert kinds[Role.LEGACY] is RuleKind.UNRESTRICTED
    assert kinds[Role.ADJUDICATE] is RuleKind.ALLOW_ONLY_GLOBS
    for role in (Role.SCAFFOLD, Role.SEALS, Role.BODIES):
        assert kinds[role] is RuleKind.DENY_GLOBS
    for rule in DEFAULT_ROLE_RULES:
        validate_rule(rule)


@pytest.mark.parametrize(
    "kind, globs, changed, expect_violating",
    [
        # DENY_GLOBS: the matching path is the violation.
        (RuleKind.DENY_GLOBS, ("**/tests/**",), ["tests/a.py", "src/a.py"], ["tests/a.py"]),
        # ALLOW_ONLY_GLOBS: the NON-matching path is the violation.
        (
            RuleKind.ALLOW_ONLY_GLOBS,
            ("src/a.py",),
            ["src/a.py", "src/b.py"],
            ["src/b.py"],
        ),
        # UNRESTRICTED: nothing is ever a violation, however alarming.
        (RuleKind.UNRESTRICTED, (), ["tests/a.py", ".dispatcher.yaml"], []),
    ],
)
def test_evaluate_changed_paths_is_total_over_every_rule_kind(
    kind: RuleKind, globs: tuple[str, ...], changed: list[str], expect_violating: list[str]
) -> None:
    """Each of the three kinds is exercised and produces its documented answer.

    Red now: `evaluate_changed_paths` raises NotImplementedError.
    Green when: it dispatches over all three kinds as documented.
    Falsify: make ALLOW_ONLY_GLOBS share DENY_GLOBS' branch — the middle row
    inverts and goes red.
    """
    rule = RoleRule(role=Role.BODIES, kind=kind, globs=globs, rationale="probe")
    violations = evaluate_changed_paths(rule, changed)
    assert [v.path for v in violations] == expect_violating
    assert all(v.rule_kind is kind for v in violations)


def test_evaluate_changed_paths_raises_on_an_unknown_rule_kind() -> None:
    """A fourth RuleKind must not fall out of the bottom as "no violations".

    skills/explicit-state.md: "naming three states does nothing if a fourth can
    arrive and be silently treated as the permissive one".

    Red now: NotImplementedError is not the raise this asserts.
    Green when: the dispatch ends in `else: raise` (any explicit exception type
    other than NotImplementedError).
    """
    rogue = RoleRule(
        role=Role.BODIES,
        kind=_BogusKind.NOPE,  # type: ignore[arg-type]
        globs=("**/tests/**",),
        rationale="probe",
    )
    with pytest.raises(Exception) as exc:
        evaluate_changed_paths(rogue, ["tests/a.py"])
    assert not isinstance(exc.value, NotImplementedError), (
        "an unknown RuleKind must raise a real error, not be unimplemented"
    )


# --------------------------------------------------------------------------- #
# validate_rule: the well-formedness contract per kind
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kind, globs",
    [
        # DENY_GLOBS with no globs is an emptied deny list masquerading as a
        # policy — the exact "could this pass without doing anything?" case.
        (RuleKind.DENY_GLOBS, ()),
        (RuleKind.DENY_GLOBS, ("",)),
        (RuleKind.DENY_GLOBS, ("**/tests/**", "   ")),
        (RuleKind.ALLOW_ONLY_GLOBS, ("",)),
        # A wildcard adjudication is not an adjudication.
        (RuleKind.ALLOW_ONLY_GLOBS, ("**",)),
        (RuleKind.ALLOW_ONLY_GLOBS, ("src/a.py", "*")),
        # UNRESTRICTED carrying globs is a self-contradicting rule; honouring
        # either half would be a guess.
        (RuleKind.UNRESTRICTED, ("**/tests/**",)),
    ],
)
def test_validate_rule_rejects_malformed_rules(
    kind: RuleKind, globs: tuple[str, ...]
) -> None:
    """Red now: `validate_rule` raises NotImplementedError, not RoleProtocolError.
    Green when: it enforces the per-kind invariants in its docstring.
    """
    rule = RoleRule(role=Role.BODIES, kind=kind, globs=globs, rationale="probe")
    with pytest.raises(RoleProtocolError):
        validate_rule(rule)


@pytest.mark.parametrize(
    "kind, globs",
    [
        (RuleKind.DENY_GLOBS, ("**/tests/**",)),
        # Empty globs are legal ONLY for the static ALLOW_ONLY table entry: the
        # writable set arrives per task via `disputed_paths:`.
        (RuleKind.ALLOW_ONLY_GLOBS, ()),
        (RuleKind.ALLOW_ONLY_GLOBS, ("src/a.py",)),
        (RuleKind.UNRESTRICTED, ()),
    ],
)
def test_validate_rule_accepts_well_formed_rules(
    kind: RuleKind, globs: tuple[str, ...]
) -> None:
    """Red now: NotImplementedError propagates out of `validate_rule`.
    Green when: a well-formed rule validates silently.
    """
    validate_rule(RoleRule(role=Role.BODIES, kind=kind, globs=globs, rationale="r"))


def test_every_table_rule_carries_a_rationale_a_violated_row_can_print() -> None:
    """`rationale` is the disposition text, not decoration.

    Red now: `built_in_policy()` raises NotImplementedError.
    Green when: the policy is constructible; each rationale is real prose.
    Falsify: blank any rationale in DEFAULT_ROLE_RULES.
    """
    for role in Role:
        rationale = _table_rule(role).rationale
        assert rationale.strip(), f"{role.value} has no rationale to print"
        assert len(rationale.strip()) > 20, f"{role.value} rationale is a stub"


# --------------------------------------------------------------------------- #
# Glob-level mutation resistance: one probe per glob, exactly one cover
# --------------------------------------------------------------------------- #


def test_every_table_glob_has_exactly_one_probe_and_one_cover() -> None:
    """Every (role, glob) in the table is pinned by exactly one probe path.

    This is the coverage half of the mutation-resistance seal and it guards ONE
    direction on purpose: every table glob must have a probe. Adding a glob to
    DEFAULT_ROLE_RULES reddens here (and only here); REMOVING one reddens only
    that glob's parametrized row below, which is what "removing any one glob
    reddens exactly one seal" requires.

    Red now, for two reasons: `first_matching_glob` raises NotImplementedError,
    AND `**/generated/**` is still in the table while deliberately having no
    probe — the 2026-08-04 ruling removes that glob entirely (see
    `test_generated_paths_are_absent_from_the_deny_table_for_every_role`), so
    giving it a probe here would encode the pre-ruling table.
    Green when: `first_matching_glob` delegates to `risk.matches_any_glob` and
    `**/generated/**` is gone from DEFAULT_ROLE_RULES.
    """
    missing = sorted(
        {glob for _role, glob in _TABLE_PAIRS} - set(_GLOB_PROBES)
    )
    assert not missing, (
        "DEFAULT_ROLE_RULES globs with no probe path — add one to _GLOB_PROBES "
        f"so a deletion cannot go unnoticed: {missing}"
    )
    # Non-vacuity: the probe table must actually be exercised by the rows below.
    assert len(_TABLE_PAIRS) >= 15, _TABLE_PAIRS
    # And the lens must be the module's, not a re-implementation.
    assert first_matching_glob("pkg/tests/x.py", ("**/tests/**",)) == "**/tests/**"


@pytest.mark.parametrize("role_value, glob", _TABLE_PAIRS)
def test_each_glob_denies_its_probe_and_is_that_probe_s_only_cover(
    role_value: str, glob: str
) -> None:
    """One glob, one fact: a probe matched by two globs lets a mutation delete
    half the protection while the suite stays green (invariant 5).

    Red now: `built_in_policy` / `first_matching_glob` /
    `evaluate_changed_paths` all raise NotImplementedError.
    Green when: they are implemented and the table still contains this glob.
    Falsify: delete this glob from DEFAULT_ROLE_RULES — this row (and no other)
    goes red, because `first_matching_glob` then returns None.
    """
    role = Role(role_value)
    probe = _GLOB_PROBES.get(glob)
    assert probe is not None, (
        f"{role_value} carries {glob!r}, which has no probe path. Either add one "
        "to _GLOB_PROBES, or the glob does not belong in the table (this is what "
        "the **/generated/** rows say)."
    )
    rule = _table_rule(role)

    covers = [g for g in rule.globs if first_matching_glob(probe, (g,)) is not None]
    assert covers == [glob], (
        f"{probe!r} must be covered by exactly one {role_value} glob — matched "
        f"{covers}"
    )
    assert first_matching_glob(probe, rule.globs) == glob

    violations = evaluate_changed_paths(rule, [probe])
    assert [(v.path, v.matched_glob) for v in violations] == [(probe, glob)]
    assert violations[0].rule_kind is RuleKind.DENY_GLOBS


# --------------------------------------------------------------------------- #
# Test-path coherence: derived FROM seal_verify._TEST_PATH, not hand-listed
# --------------------------------------------------------------------------- #

# One or more concrete paths per alternative of `seal_verify._TEST_PATH`. The
# keys are checked against the live pattern below, so adding an alternative to
# `_TEST_PATH` without a probe here reddens rather than silently widening the
# gap between the two notions of "is this a test file".
_TEST_PATH_PROBES: dict[str, tuple[str, ...]] = {
    r"_test\.": ("src/app/handler_test.js",),
    r"\.test\.": ("web/app.test.ts",),
    r"\.spec\.": ("web/app.spec.ts",),
    r"^tests?/": ("tests/unit_one.py", "test/unit_one.py"),
    r"/tests?/": ("pkg/tests/unit.py", "pkg/test/unit.py"),
    r"/__tests__/": ("web/__tests__/app.js",),
    r"^spec/": ("spec/models.rb",),
    r"/spec/": ("pkg/spec/models.rb",),
    r"/testdata/": ("cmd/classify/testdata/golden.json",),
    r"/fixtures/": ("pkg/fixtures/sample.json",),
    r"conftest\.py$": ("pkg/conftest.py",),
}


def _test_path_alternatives() -> list[str]:
    """The alternatives of `seal_verify._TEST_PATH`, read off the live pattern."""
    pattern = _TEST_PATH.pattern
    inner = pattern[pattern.index("(") + 1 : pattern.rindex(")")]
    return inner.split("|")


@pytest.mark.parametrize(
    "alternative, probe",
    sorted(
        (alt, probe)
        for alt, probes in _TEST_PATH_PROBES.items()
        for probe in probes
    ),
)
def test_every_seal_verify_test_path_is_denied_to_bodies(
    alternative: str, probe: str
) -> None:
    """Two disagreeing notions of "is this a test file" is invariant 5's failure.

    `seal_verify` decides which changed files are "the tests" when it inverts a
    change; `DEFAULT_ROLE_RULES[BODIES]` decides which files a body agent may
    not touch. A path the first calls a test and the second permits is a body
    agent editing its own seal with the gate reporting CLEAN.

    The fixture exhibits the failure first: each probe is asserted to actually
    match `_TEST_PATH` (with seal_verify's own leading-slash normalisation)
    before its denial is required, so this can never pass on a path that is not
    a test to either notion.

    The probe table is checked against the LIVE pattern on every row, so adding
    an alternative to `seal_verify._TEST_PATH` reddens here until a probe for it
    exists — the derivation source is the other module's regex, never a copy.

    Red now: (a) `evaluate_changed_paths` raises NotImplementedError, and (b) 6
    of the 11 alternatives are genuinely uncovered by the BODIES deny set —
    singular `test/`, `__tests__/`, `spec/`, `fixtures/`, and `_test.` with a
    non-Python/Go extension. (b) is a scaffold/contract disagreement raised as a
    P2 dispute: role_protocol's own module docstring promises this coherence.
    Green when: `evaluate_changed_paths` is implemented AND the BODIES deny set
    covers every `_TEST_PATH` alternative.
    """
    alternatives = _test_path_alternatives()
    assert sorted(alternatives) == sorted(_TEST_PATH_PROBES), (
        "seal_verify._TEST_PATH changed shape; probe table is stale: "
        f"{sorted(set(alternatives) ^ set(_TEST_PATH_PROBES))}"
    )
    assert _TEST_PATH.search("/" + probe), (
        f"{probe!r} does not exhibit alternative {alternative!r} — the fixture, "
        "not the table, is wrong"
    )
    bodies = _table_rule(Role.BODIES)
    violations = evaluate_changed_paths(bodies, [probe])
    assert [v.path for v in violations] == [probe], (
        f"seal_verify calls {probe!r} a test file but BODIES may write it: "
        f"{alternative!r} is uncovered by {bodies.globs}"
    )
    assert violations[0].matched_glob in bodies.globs


# --------------------------------------------------------------------------- #
# Operator rulings of 2026-08-04 (they postdate the scaffold — see the report)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", sorted(AUTHORABLE_ROLES, key=lambda r: r.value))
def test_dispatcher_yaml_is_denied_to_all_four_authorable_roles(role: Role) -> None:
    """Ruling: `.dispatcher.yaml` is denied to all four roles, scaffold included.

    A role that can edit the file configuring its own permissions is the
    self-widening shape this unit exists to remove. A unit's per-task override
    lives in its task row, so no role needs to edit the policy file.

    Red now: (a) the stubs, and (b) the SCAFFOLD row deliberately omits
    `**/.dispatcher.yaml` (the scaffold's own comment flags this as a considered
    choice) — the 2026-08-04 ruling overrides that choice, and the SCAFFOLD row
    of this seal is the dispute.
    Green when: `**/.dispatcher.yaml` is in every authorable role's deny set.
    Falsify: delete `**/.dispatcher.yaml` from any role's globs — that role's
    row goes red.
    """
    rule = _table_rule(role)
    for path in (".dispatcher.yaml", "sub/project/.dispatcher.yaml"):
        violations = evaluate_changed_paths(rule, [path])
        assert [v.path for v in violations] == [path], (
            f"{role.value} may write {path}: the role can widen its own policy"
        )
    assert CONFIG_SECTION == "roles"


def test_generated_paths_are_absent_from_the_deny_table_for_every_role() -> None:
    """Ruling: `**/generated/**` leaves the deny table entirely.

    The property wanted is not "bodies never touch generated files" but
    "generated files equal generator output", which the regenerate-and-diff gate
    owns for EVERY role. Denying the path made generator units (A3/A4, whose
    bodies legitimately commit regenerated output) undrivable, and ADD-only
    overrides gave no escape.

    Red now: (a) the stubs, and (b) SEALS and BODIES still deny
    `**/generated/**` — a scaffold/ruling disagreement reported as a dispute.
    Green when: no rule denies a generated path.
    Falsify: re-add `**/generated/**` to any role.
    """
    for role in Role:
        rule = _table_rule(role)
        assert "**/generated/**" not in rule.globs, (
            f"{role.value} still denies **/generated/**; the 2026-08-04 ruling "
            "moves that property to the regenerate-and-diff gate"
        )
        if rule.kind is RuleKind.DENY_GLOBS:
            assert evaluate_changed_paths(rule, ["pkg/generated/types.py"]) == ()


def test_forbidden_disputed_globs_are_the_wildcards_that_void_adjudication() -> None:
    """A wildcard `disputed_paths:` turns ALLOW_ONLY into UNRESTRICTED.

    Red now: `validate_rule` raises NotImplementedError.
    Green when: every forbidden wildcard is refused as an ALLOW_ONLY glob.
    Falsify: drop an entry from FORBIDDEN_DISPUTED_GLOBS — its row goes red.
    """
    assert FORBIDDEN_DISPUTED_GLOBS, "an empty forbidden set would be vacuous"
    for glob in sorted(FORBIDDEN_DISPUTED_GLOBS):
        rule = RoleRule(
            role=Role.ADJUDICATE,
            kind=RuleKind.ALLOW_ONLY_GLOBS,
            globs=(glob,),
            rationale="probe",
        )
        with pytest.raises(RoleProtocolError):
            validate_rule(rule)


def test_the_glob_lens_is_risk_pys_and_not_a_second_translator() -> None:
    """`**/x/**` must match root and nested alike, per risk.py's translation.

    Two glob translators is invariant 5's failure mode; this pins
    `first_matching_glob` to `risk.matches_any_glob`'s semantics by asserting
    the two agree on the cases where a hand-rolled matcher differs (leading
    `**/` matching zero segments; anchored full-path matching).

    Red now: `first_matching_glob` raises NotImplementedError.
    Green when: it delegates to `risk.matches_any_glob` one pattern at a time.
    """
    cases = [
        ("tests/a.py", "**/tests/**"),
        ("a/b/tests/c.py", "**/tests/**"),
        (".dispatcher.yaml", "**/.dispatcher.yaml"),
        ("roles/reviewer.md", "**/roles/*.md"),
    ]
    for path, glob in cases:
        assert risk.matches_any_glob(path, (glob,)), f"fixture wrong: {path}"
        assert first_matching_glob(path, (glob,)) == glob
    assert first_matching_glob("src/app.py", ("**/tests/**",)) is None
