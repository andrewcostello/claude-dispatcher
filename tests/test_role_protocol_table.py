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

P4 amendments, 2026-08-07 (the adjudicator is the only role that may amend a
seal; each is justified in the seal's own docstring):

  * `test_dispatcher_yaml_is_denied_to_all_four_authorable_roles` was the sixth
    vacuous seal found in this unit — its ADJUDICATE row passed only because
    that role's STATIC entry is an empty allowlist, so every path was a miss and
    the row would have passed for `docs/anything.md`. Split into
    `test_dispatcher_yaml_is_denied_to_every_role_the_table_can_deny_it_to`
    (the three deny roles, now with a writable-path control and a matched-glob
    assertion) and
    `test_the_table_cannot_deny_dispatcher_yaml_to_adjudicate_and_this_says_so`
    (why the fourth role is not answerable here, and where it is sealed).
  * the UNRESTRICTED row of
    `test_evaluate_changed_paths_is_total_over_every_rule_kind` probed
    `.dispatcher.yaml` and expected no violation, which sealed the LEGACY escape
    the 2026-08-07 operator ruling closes. Probes changed and a guard added.
"""

from __future__ import annotations

from enum import Enum

import pytest

from claude_dispatcher import risk
from claude_dispatcher.role_protocol import (
    AUTHORABLE_ROLES,
    CONFIG_SECTION,
    DEFAULT_ROLE_RULES,
    FLOOR_GLOBS,
    FORBIDDEN_DISPUTED_GLOBS,
    MANDATORY_PHASE_ORDER,
    PolicySource,
    Role,
    RolePolicy,
    RoleProtocolError,
    RoleRule,
    RuleKind,
    TEST_PATH_DELEGATED_ROLES,
    TaskRoleSpec,
    built_in_policy,
    effective_rule,
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

# The (role, glob) pairs the table must contain, WRITTEN OUT rather than read
# off `DEFAULT_ROLE_RULES`.
#
# P4 (2026-08-07): this list used to be a comprehension over DEFAULT_ROLE_RULES,
# which made the mutation-resistance seal below a tautology — deleting a glob
# from the table deleted its parametrized row, so the row could not go red, it
# simply stopped existing. Measured: deleting each of the 28 (role, glob) pairs
# in turn and running all five D1 seal files, 18 of the 28 deletions were caught
# by NOTHING. Four of those are outright fail-opens with no backstop —
# BODIES/`**/reviewer_prompts/**`, BODIES/`**/verifier_prompts/**` (the sole
# cover of the machine-read prompts that judge the branch, since BODIES has no
# `**/src/**` deny), SEALS/`**/roles/*.md` and SEALS/`**/schema/**` (both live
# outside `src/`, so nothing else denies them). A seal that cannot fail reads as
# protection while providing none, which is the exact failure this unit exists
# to remove.
#
# Written out, the two directions split cleanly and each deletion still reddens
# exactly ONE seal, as the docstrings below promise:
#   * REMOVING a glob from DEFAULT_ROLE_RULES -> that pair's parametrized row
#     goes red (the row still exists, and `first_matching_glob` now returns None)
#   * ADDING one -> `test_every_table_glob_has_exactly_one_probe_and_one_cover`
#     goes red, because the live table carries a pair this list does not.
_EXPECTED_TABLE_PAIRS: tuple[tuple[str, str], ...] = (
    ("bodies", "**/*.spec.*"),
    ("bodies", "**/*.test.*"),
    ("bodies", "**/*_test.go"),
    ("bodies", "**/*_test.py"),
    ("bodies", "**/.dispatcher.yaml"),
    ("bodies", "**/conftest.py"),
    ("bodies", "**/reviewer_prompts/**"),
    ("bodies", "**/roles/*.md"),
    ("bodies", "**/schema/**"),
    ("bodies", "**/test_*.py"),
    ("bodies", "**/testdata/**"),
    ("bodies", "**/tests/**"),
    ("bodies", "**/verifier_prompts/**"),
    ("scaffold", "**/*.spec.*"),
    ("scaffold", "**/*.test.*"),
    ("scaffold", "**/*_test.go"),
    ("scaffold", "**/*_test.py"),
    ("scaffold", "**/.dispatcher.yaml"),
    ("scaffold", "**/conftest.py"),
    ("scaffold", "**/test_*.py"),
    ("scaffold", "**/testdata/**"),
    ("scaffold", "**/tests/**"),
    ("seals", "**/.dispatcher.yaml"),
    ("seals", "**/reviewer_prompts/**"),
    ("seals", "**/roles/*.md"),
    ("seals", "**/schema/**"),
    ("seals", "**/src/**"),
    ("seals", "**/verifier_prompts/**"),
)

_TABLE_PAIRS = _EXPECTED_TABLE_PAIRS

#: The same pairs as the live table reports them — used ONLY to detect additions.
_LIVE_TABLE_PAIRS = sorted(
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
        # UNRESTRICTED: nothing is ever a violation, however alarming — but see
        # the P4 amendment below for why the probes here are deliberately not
        # floor paths.
        (RuleKind.UNRESTRICTED, (), ["tests/a.py", "schema/merge.yaml"], []),
    ],
)
def test_evaluate_changed_paths_is_total_over_every_rule_kind(
    kind: RuleKind, globs: tuple[str, ...], changed: list[str], expect_violating: list[str]
) -> None:
    """Each of the three kinds is exercised and produces its documented answer.

    **AMENDED BY P4, 2026-08-07.** The UNRESTRICTED row read
    ``(RuleKind.UNRESTRICTED, (), ["tests/a.py", ".dispatcher.yaml"], [])`` — it
    asserted that the policy file produces no violation under the one kind
    LEGACY holds, which is precisely the escape the operator has ruled out (a
    floor LEGACY escapes is bypassed by omitting the `role:` key). The row was
    NOT simply relaxed: its probes were changed to two paths that are protected
    for other roles and are not on the floor, so it still asserts exactly `[]`,
    and the guard below stops the floor path being put back.

    Where the floor lives — inside `evaluate_changed_paths` or inside
    `check_branch` — is P3's to choose and is deliberately unsealed here; the
    floor is unioned into the DECISION, so it is not a property of a
    :class:`RuleKind`. The behaviour that is sealed, for every role including
    LEGACY, is in `tests/test_role_protocol_floor.py`.

    Red now: `evaluate_changed_paths` raises NotImplementedError.
    Green when: it dispatches over all three kinds as documented.
    Falsify: make ALLOW_ONLY_GLOBS share DENY_GLOBS' branch — the middle row
    inverts and goes red. Put a floor path back into an UNRESTRICTED row that
    expects no violation — the guard goes red.
    """
    if kind is RuleKind.UNRESTRICTED and not expect_violating:
        assert all(first_matching_glob(p, FLOOR_GLOBS) is None for p in changed), (
            "an UNRESTRICTED row must not probe a floor path and expect it to "
            "pass. UNRESTRICTED is held solely by LEGACY, and LEGACY's "
            "exemption from the deny table is not an exemption from the floor "
            f"(2026-08-07 operator ruling): {changed} vs {list(FLOOR_GLOBS)}"
        )
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
    Falsify: add any glob to any DEFAULT_ROLE_RULES row — this goes red (and
    only this), because the live table then carries a pair `_EXPECTED_TABLE_PAIRS`
    does not.
    """
    # Additions: a glob nobody wrote down here, and therefore a glob with no
    # probe and no parametrized row. Checked against the WRITTEN list, not
    # against itself — see the P4 note on `_EXPECTED_TABLE_PAIRS`.
    unexpected = sorted(set(_LIVE_TABLE_PAIRS) - set(_EXPECTED_TABLE_PAIRS))
    assert not unexpected, (
        "DEFAULT_ROLE_RULES carries (role, glob) pairs that are not pinned by a "
        "parametrized row below. Add them to _EXPECTED_TABLE_PAIRS (and give the "
        f"glob a probe in _GLOB_PROBES) or they are unsealed: {unexpected}"
    )
    missing = sorted(
        {glob for _role, glob in _EXPECTED_TABLE_PAIRS} - set(_GLOB_PROBES)
    )
    assert not missing, (
        "expected table globs with no probe path — add one to _GLOB_PROBES "
        f"so a deletion cannot go unnoticed: {missing}"
    )
    # Non-vacuity: the probe table must actually be exercised by the rows below.
    assert len(_EXPECTED_TABLE_PAIRS) >= 15, _EXPECTED_TABLE_PAIRS
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
    goes red, because `covers` is then empty and `first_matching_glob` returns
    None. This only holds because the parametrize list is WRITTEN OUT in
    `_EXPECTED_TABLE_PAIRS`; when it was derived from the table, deleting a glob
    deleted the row instead of reddening it and 18 of 28 deletions went
    undetected across all five D1 seal files (P4, 2026-08-07).
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


#: The roles whose deny set must include `seal_verify`'s predicate, WRITTEN OUT
#: rather than read off `TEST_PATH_DELEGATED_ROLES` — deriving it from the
#: constant under test is the tautology documented on `_EXPECTED_TABLE_PAIRS`.
#: P4 (2026-08-07): this seal read `Role.BODIES` only, so the mutation
#: `TEST_PATH_DELEGATED_ROLES = (Role.BODIES,)` left the whole suite green while
#: a SCAFFOLD agent could add `test/unit.py`, `web/__tests__/app.js`,
#: `spec/models.rb`, `pkg/fixtures/sample.json` or `src/app/handler_test.js` —
#: every one a file `seal_verify` calls a test — with the gate reporting CLEAN.
#: P1 must not write the seals it will be judged by any more than P3 may.
_DELEGATED_ROLES_EXPECTED: tuple[Role, ...] = (Role.SCAFFOLD, Role.BODIES)


@pytest.mark.parametrize(
    "role", _DELEGATED_ROLES_EXPECTED, ids=lambda r: r.value
)
@pytest.mark.parametrize(
    "alternative, probe",
    sorted(
        (alt, probe)
        for alt, probes in _TEST_PATH_PROBES.items()
        for probe in probes
    ),
)
def test_every_seal_verify_test_path_is_denied_to_every_delegated_role(
    alternative: str, probe: str, role: Role
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
    Green when: `evaluate_changed_paths` is implemented AND each delegated
    role's deny set covers every `_TEST_PATH` alternative.
    Falsify: drop either role from `TEST_PATH_DELEGATED_ROLES` — that role's
    rows go red (P4, 2026-08-07: previously only BODIES was checked, so dropping
    SCAFFOLD was invisible).
    """
    assert TEST_PATH_DELEGATED_ROLES == _DELEGATED_ROLES_EXPECTED, (
        "the delegated-role set changed; this seal's coverage is written out "
        "on purpose, so update _DELEGATED_ROLES_EXPECTED deliberately: "
        f"{TEST_PATH_DELEGATED_ROLES}"
    )
    alternatives = _test_path_alternatives()
    assert sorted(alternatives) == sorted(_TEST_PATH_PROBES), (
        "seal_verify._TEST_PATH changed shape; probe table is stale: "
        f"{sorted(set(alternatives) ^ set(_TEST_PATH_PROBES))}"
    )
    assert _TEST_PATH.search("/" + probe), (
        f"{probe!r} does not exhibit alternative {alternative!r} — the fixture, "
        "not the table, is wrong"
    )
    rule = _table_rule(role)
    violations = evaluate_changed_paths(rule, [probe])
    assert [v.path for v in violations] == [probe], (
        f"seal_verify calls {probe!r} a test file but {role.value} may write "
        f"it: {alternative!r} is uncovered by {rule.globs}"
    )
    assert violations[0].matched_glob in rule.globs


# --------------------------------------------------------------------------- #
# Operator rulings of 2026-08-04 (they postdate the scaffold — see the report)
# --------------------------------------------------------------------------- #


#: The real paths git emits for `**/.dispatcher.yaml` — a root config and a
#: nested one.
_CONFIG_FILE_PROBES: tuple[str, ...] = (
    ".dispatcher.yaml",
    "sub/project/.dispatcher.yaml",
)

#: A path NO deny-table role denies. This is the control that makes the seal
#: below able to fail: without it, "the config file is denied" and "every path
#: is denied" are the same passing test.
_A_PATH_NO_DENY_ROLE_DENIES = "docs/anything.md"

#: The roles whose TABLE ENTRY can answer "is `.dispatcher.yaml` denied?" —
#: written out, not derived from `AUTHORABLE_ROLES` or from the table. Same P4
#: lesson as `_EXPECTED_TABLE_PAIRS`: a parametrization comprehended over the
#: constant it pins deletes its rows instead of reddening them.
#:
#: ADJUDICATE is absent BY RULING and not by omission — see the seal below it.
_DENY_TABLE_ROLES_WRITTEN_OUT: tuple[str, ...] = ("bodies", "scaffold", "seals")


@pytest.mark.parametrize("role_value", _DENY_TABLE_ROLES_WRITTEN_OUT)
def test_dispatcher_yaml_is_denied_to_every_role_the_table_can_deny_it_to(
    role_value: str,
) -> None:
    """Ruling: `.dispatcher.yaml` is denied to all four roles, scaffold included.

    A role that can edit the file configuring its own permissions is the
    self-widening shape this unit exists to remove. A unit's per-task override
    lives in its task row, so no role needs to edit the policy file.

    **AMENDED BY P4, 2026-08-07** (was
    `test_dispatcher_yaml_is_denied_to_all_four_authorable_roles`, parametrized
    over `AUTHORABLE_ROLES`). Two defects, one of them the sixth vacuous seal
    found in this unit:

      * the ADJUDICATE row passed only because ADJUDICATE's STATIC table entry
        is an empty allowlist, under which every path is a miss. It would have
        passed identically for `docs/anything.md`, and it never saw a task row —
        the only way ADJUDICATE ever gets a writable set. A seal named after the
        hole is how the hole survived. It is now excluded by ruling, its absence
        is itself sealed by the next test, and the real question is sealed
        RED against a task row in `tests/test_role_protocol_floor.py`.
      * every row, ADJUDICATE's included, asserted only that the config paths
        were violations. `_A_PATH_NO_DENY_ROLE_DENIES` is now asserted writable
        in the same call, so a rule that denies everything cannot satisfy this,
        and the matched glob is asserted so a denial that came from some
        unrelated pattern cannot either.

    Green when: `**/.dispatcher.yaml` is in each deny role's set.
    Falsify: delete `**/.dispatcher.yaml` from any of the three roles' globs —
    that row goes red. Point `_CONFIG_FILE_PROBES` at `docs/anything.md` — every
    row goes red (under the pre-amendment seal the ADJUDICATE row went on
    passing, which is what "vacuous" meant here).
    """
    role = Role(role_value)
    assert role in AUTHORABLE_ROLES, role_value
    rule = _table_rule(role)
    assert rule.kind is RuleKind.DENY_GLOBS, (
        f"{role_value} is no longer a deny-table role; this seal cannot answer "
        "the question for it — see the ADJUDICATE seal below"
    )

    # The control, first: a rule that denies everything must not pass this.
    assert evaluate_changed_paths(rule, [_A_PATH_NO_DENY_ROLE_DENIES]) == (), (
        f"{role_value} may not write {_A_PATH_NO_DENY_ROLE_DENIES}; this seal "
        "would then pass for any path at all"
    )

    for path in _CONFIG_FILE_PROBES:
        violations = evaluate_changed_paths(rule, [path])
        assert [v.path for v in violations] == [path], (
            f"{role_value} may write {path}: the role can widen its own policy"
        )
        assert violations[0].matched_glob == "**/.dispatcher.yaml", (
            f"{path} was denied to {role_value} by "
            f"{violations[0].matched_glob!r} rather than by the config glob; "
            "the ruling is about the policy file, not a side effect"
        )
    assert CONFIG_SECTION == "roles"


def test_the_table_cannot_deny_dispatcher_yaml_to_adjudicate_and_this_says_so(
) -> None:
    """Why ADJUDICATE is not in the parametrization above — sealed, not assumed.

    ADJUDICATE is `ALLOW_ONLY_GLOBS` and its static entry carries no globs: the
    writable set arrives per task in `disputed_paths:`. So at the table level
    "`.dispatcher.yaml` is denied to ADJUDICATE" is indistinguishable from
    "every path is denied to ADJUDICATE", and the distinguishing case — a row
    that DECLARES the config file, which is the actual exploit — is granted by
    `effective_rule` and can only be refused by the floor, which is unioned into
    the decision rather than into the table. That question therefore belongs to
    `check_branch` and is sealed there:
    `tests/test_role_protocol_floor.py::test_an_adjudicate_task_cannot_declare_its_way_into_the_policy_file`
    plus the `adjudicate` rows of `_FLOOR_x_ROLE_ROWS`.

    This seal exists so that exclusion cannot silently rot back into a vacuous
    row: it pins the two facts the exclusion rests on.

    Green now, and it must stay green.
    Falsify: give ADJUDICATE's table entry a non-empty allowlist, or make an
    empty allow-only set stop meaning "everything is a miss" — either reddens
    this, and the first also means ADJUDICATE belongs in the parametrization
    above.
    """
    static = _table_rule(Role.ADJUDICATE)
    assert static.kind is RuleKind.ALLOW_ONLY_GLOBS
    assert static.globs == (), (
        "ADJUDICATE's static entry now carries an allowlist; the seal above can "
        "answer the config-file question for it and should cover it"
    )
    # Fact 1: under the static entry the config file and an innocuous doc are
    # violated identically — this is what made the old ADJUDICATE row vacuous.
    assert [v.path for v in evaluate_changed_paths(static, [".dispatcher.yaml"])] == [
        ".dispatcher.yaml"
    ]
    assert [
        v.path for v in evaluate_changed_paths(static, [_A_PATH_NO_DENY_ROLE_DENIES])
    ] == [_A_PATH_NO_DENY_ROLE_DENIES]

    # Fact 2: with a task row — the only way ADJUDICATE ever gets a writable set
    # — the declaration is what governs, and the table has no say. A row that
    # declares the config file therefore GETS it, which is the exploit the floor
    # closes elsewhere.
    granted = effective_rule(
        TaskRoleSpec(
            task_key="D1-P4",
            role=Role.ADJUDICATE,
            disputed_paths=("docs/adr/0007.md",),
        ),
        built_in_policy(),
    )
    assert granted.globs == ("docs/adr/0007.md",), (
        "the table's globs leaked into ADJUDICATE's effective rule; for an "
        "allow-only kind a union WIDENS"
    )
    assert evaluate_changed_paths(granted, ["docs/adr/0007.md"]) == ()
    assert [
        v.path for v in evaluate_changed_paths(granted, [".dispatcher.yaml"])
    ] == [".dispatcher.yaml"]


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


#: The members `FORBIDDEN_DISPUTED_GLOBS` must have, written out — see the P4
#: note in the seal below. `**/*` is the load-bearing one: it matches every path.
_FORBIDDEN_DISPUTED_EXPECTED: tuple[str, ...] = (
    "*",
    "**",
    "**/*",
    "/",
    "./**",
    ".",
)


def test_forbidden_disputed_globs_are_the_wildcards_that_void_adjudication() -> None:
    """A wildcard `disputed_paths:` turns ALLOW_ONLY into UNRESTRICTED.

    Red now: `validate_rule` raises NotImplementedError.
    Green when: every forbidden wildcard is refused as an ALLOW_ONLY glob.
    Falsify: drop an entry from FORBIDDEN_DISPUTED_GLOBS — its row goes red.

    P4 (2026-08-07): the loop used to iterate `FORBIDDEN_DISPUTED_GLOBS` itself,
    so dropping an entry dropped its iteration rather than reddening it — the
    tautology documented on `_EXPECTED_TABLE_PAIRS`. Dropping `**/*` was
    undetected by the whole suite, and `**/*` matches every path, so a task
    could declare `disputed_paths: ["**/*"]` and hand ADJUDICATE an unrestricted
    writable set: ALLOW_ONLY converted to UNRESTRICTED with extra steps, the one
    thing this constant exists to forbid. The expected members are now written
    out and the set is pinned by equality.
    """
    assert FORBIDDEN_DISPUTED_GLOBS == frozenset(_FORBIDDEN_DISPUTED_EXPECTED), (
        "FORBIDDEN_DISPUTED_GLOBS changed; it is written out here on purpose so "
        "a removal reddens instead of vanishing: "
        f"{sorted(FORBIDDEN_DISPUTED_GLOBS ^ frozenset(_FORBIDDEN_DISPUTED_EXPECTED))}"
    )
    for glob in _FORBIDDEN_DISPUTED_EXPECTED:
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
