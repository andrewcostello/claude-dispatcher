"""D1 seals (P2): per-row parsing — `role:`, `immutable_paths:`, `disputed_paths:`.

The rule these seals exist to enforce is the operator ruling of 2026-08-04 plus
the module's own contract: **LEGACY arises ONLY from a wholly-absent key**.
Every other shape — present-but-null, blank, unknown, a list, two aliases, a
separator-joined pair, the literal `legacy` — is a typed error, and each gets its
own row, because a single "it raises somehow" assertion would let a
`role: legacy` opt-out slip in behind a passing suite.

All rows are red today: the parsers raise NotImplementedError, which is not a
`RoleProtocolError`, so both the raises-rows and the returns-rows fail.
"""

from __future__ import annotations

import pytest

from claude_dispatcher.role_protocol import (
    AUTHORABLE_ROLES,
    DISPUTED_PATHS_FIELD,
    FORBIDDEN_DISPUTED_GLOBS,
    IMMUTABLE_OVERRIDE_FIELD,
    ROLE_FIELD_ALIASES,
    ROLE_FIELD_CANONICAL,
    PolicySource,
    Role,
    RolePolicy,
    RoleProtocolError,
    RoleRule,
    RuleKind,
    TaskRoleSpec,
    built_in_policy,
    effective_rule,
    parse_role_field,
    parse_role_value,
    parse_task_role_spec,
    validate_override,
)

TASK_KEY = "D1-P2"


# --------------------------------------------------------------------------- #
# LEGACY is derived from absence, and from nothing else
# --------------------------------------------------------------------------- #


def test_absent_role_key_is_the_only_path_to_legacy() -> None:
    """A row with no `role:` key at all is LEGACY — absence is a named state.

    Red now: `parse_role_field` raises NotImplementedError.
    Green when: it returns Role.LEGACY for a row carrying none of the aliases.
    Falsify: make an unknown value fall through to LEGACY — the rows below go
    red while this one stays green, which is the pairing that catches it.
    """
    assert parse_role_field({}, task_key=TASK_KEY) is Role.LEGACY
    # Other fields present, no role alias: still LEGACY.
    row = {"summary": "s", "status": "To Do", "blockedBy": ["X-1"]}
    assert parse_role_field(row, task_key=TASK_KEY) is Role.LEGACY
    assert Role.LEGACY not in AUTHORABLE_ROLES


@pytest.mark.parametrize(
    "row, case",
    [
        # `role:` with nothing after it. The author wrote the key and meant
        # something; presence-with-null must not default to the permissive value.
        ({"role": None}, "present-but-null"),
        ({"role": ""}, "blank"),
        ({"role": "   "}, "whitespace-only"),
        ({"role": "\t\n"}, "whitespace-only-tabs"),
        # An unknown word must not buy a task its way out of the gate.
        ({"role": "implementer"}, "unknown-word"),
        ({"role": "scaffolding"}, "near-miss-word"),
        # A list is a task carrying two roles — a typed error, not a coercion.
        ({"role": ["scaffold", "seals"]}, "list-two"),
        # A single-element list is still not the shape of the contract.
        ({"role": ["scaffold"]}, "list-one"),
        ({"role": ("scaffold",)}, "tuple-one"),
        ({"role": {"scaffold": True}}, "mapping"),
        # Separator-joined pairs: "scaffold+seals" is two roles.
        ({"role": "scaffold+seals"}, "plus-separated"),
        ({"role": "scaffold,seals"}, "comma-separated"),
        ({"role": "scaffold/seals"}, "slash-separated"),
        ({"role": "scaffold|seals"}, "pipe-separated"),
        ({"role": "scaffold seals"}, "space-separated"),
        # The literal `legacy` is derived-only; spelling it is an opt-out.
        ({"role": "legacy"}, "literal-legacy"),
        ({"role": "LEGACY"}, "literal-legacy-upper"),
        ({"role": " legacy "}, "literal-legacy-padded"),
        # Non-strings name the value and the legal set rather than coercing.
        ({"role": True}, "bool"),
        ({"role": 3}, "int"),
        # More than one alias present is an error even when the values AGREE:
        # one fact, one place (the `plan._dependency_list` precedent).
        ({"role": "scaffold", "roles": "scaffold"}, "two-aliases-agreeing"),
        ({"role": "scaffold", "roles": "seals"}, "two-aliases-disagreeing"),
        ({"role": "bodies", "task_role": "bodies"}, "two-aliases-task_role"),
        ({"roles": "seals", "task_role": "seals"}, "two-non-canonical-aliases"),
    ],
)
def test_every_non_absent_role_shape_is_a_typed_error(row: dict, case: str) -> None:
    """One row per case, so no single shape can pass unnoticed.

    Red now: `parse_role_field` raises NotImplementedError, not RoleProtocolError.
    Green when: each shape raises RoleProtocolError naming the task key.
    Falsify: replace any branch with `return Role.LEGACY` — that row goes red.
    """
    with pytest.raises(RoleProtocolError) as exc:
        parse_role_field(row, task_key=TASK_KEY)
    assert TASK_KEY in str(exc.value), (
        f"the {case} error is diagnosed from a run log and must name the task"
    )


@pytest.mark.parametrize(
    "row, expected",
    [
        ({"role": "scaffold"}, Role.SCAFFOLD),
        ({"role": "seals"}, Role.SEALS),
        ({"role": "bodies"}, Role.BODIES),
        ({"role": "adjudicate"}, Role.ADJUDICATE),
        # Case-insensitive after stripping.
        ({"role": "SCAFFOLD"}, Role.SCAFFOLD),
        ({"role": "  Seals  "}, Role.SEALS),
        # Each alias works on its own; only *multiple* aliases are an error.
        ({"roles": "bodies"}, Role.BODIES),
        ({"task_role": "adjudicate"}, Role.ADJUDICATE),
    ],
)
def test_every_authorable_spelling_parses(row: dict, expected: Role) -> None:
    """Red now: NotImplementedError.
    Green when: the four authorable roles parse from any single alias.
    """
    assert parse_role_field(row, task_key=TASK_KEY) is expected


def test_alias_set_is_the_near_misses_that_must_not_be_dropped() -> None:
    """A silently ignored `roles: bodies` would restore the honour system.

    Red now: `parse_role_field` raises NotImplementedError on the last line.
    Green when: every alias in ROLE_FIELD_ALIASES is recognised.
    Falsify: remove an alias from ROLE_FIELD_ALIASES — the alias is then an
    unknown key, the row reads as LEGACY, and this goes red.
    """
    assert ROLE_FIELD_CANONICAL == "role"
    assert ROLE_FIELD_CANONICAL in ROLE_FIELD_ALIASES
    for alias in ROLE_FIELD_ALIASES:
        assert parse_role_field({alias: "bodies"}, task_key=TASK_KEY) is Role.BODIES


# --------------------------------------------------------------------------- #
# parse_task_role_spec: overrides and disputed paths
# --------------------------------------------------------------------------- #


def test_spec_records_role_override_and_agent_verbatim() -> None:
    """Red now: `parse_task_role_spec` raises NotImplementedError.
    Green when: the row's protocol facts are parsed into a TaskRoleSpec.
    """
    row = {
        "role": "bodies",
        IMMUTABLE_OVERRIDE_FIELD: ["**/fixtures/**", "**/cmd/**"],
        "agent": "grok",
    }
    spec = parse_task_role_spec(row, task_key=TASK_KEY)
    assert spec == TaskRoleSpec(
        task_key=TASK_KEY,
        role=Role.BODIES,
        added_immutable_globs=("**/fixtures/**", "**/cmd/**"),
        disputed_paths=(),
        declared_agent="grok",
    )


def test_absent_optional_fields_are_empty_not_none() -> None:
    """Red now: NotImplementedError.
    Green when: an absent override is `()` and an absent agent is None (the
    effective family is resolved by `agent_correlation_warnings`, never guessed).
    """
    spec = parse_task_role_spec({"role": "seals"}, task_key=TASK_KEY)
    assert spec.added_immutable_globs == ()
    assert spec.disputed_paths == ()
    assert spec.declared_agent is None


def test_unknown_agent_is_not_re_validated_here() -> None:
    """One fact, one place: `agent:` is validated by `plan.load_tasks`.

    Red now: NotImplementedError.
    Green when: the value is recorded verbatim without a second KNOWN_AGENTS
    check (two validators would diverge).
    Falsify: add a KNOWN_AGENTS check to parse_task_role_spec — this goes red.
    """
    spec = parse_task_role_spec(
        {"role": "bodies", "agent": "not-a-known-agent"}, task_key=TASK_KEY
    )
    assert spec.declared_agent == "not-a-known-agent"


@pytest.mark.parametrize(
    "row, case",
    [
        # A bare string is how a policy line gets silently dropped.
        ({"role": "bodies", IMMUTABLE_OVERRIDE_FIELD: "**/fixtures/**"}, "bare-string"),
        ({"role": "bodies", IMMUTABLE_OVERRIDE_FIELD: [""]}, "blank-entry"),
        ({"role": "bodies", IMMUTABLE_OVERRIDE_FIELD: ["   "]}, "whitespace-entry"),
        ({"role": "bodies", IMMUTABLE_OVERRIDE_FIELD: ["ok/**", None]}, "none-entry"),
        ({"role": "bodies", IMMUTABLE_OVERRIDE_FIELD: ["ok/**", 7]}, "int-entry"),
        ({"role": "bodies", IMMUTABLE_OVERRIDE_FIELD: {"a": "b"}}, "mapping"),
        ({"role": "bodies", IMMUTABLE_OVERRIDE_FIELD: None}, "present-but-null"),
        # An addition has no meaning for ALLOW_ONLY / UNRESTRICTED roles.
        ({"role": "adjudicate", DISPUTED_PATHS_FIELD: ["src/a.py"],
          IMMUTABLE_OVERRIDE_FIELD: ["**/x/**"]}, "override-on-adjudicate"),
        ({IMMUTABLE_OVERRIDE_FIELD: ["**/x/**"]}, "override-on-legacy-row"),
    ],
)
def test_malformed_immutable_paths_override_is_a_typed_error(
    row: dict, case: str
) -> None:
    """Red now: NotImplementedError is not RoleProtocolError.
    Green when: each shape raises, naming the task key.
    """
    with pytest.raises(RoleProtocolError) as exc:
        parse_task_role_spec(row, task_key=TASK_KEY)
    assert TASK_KEY in str(exc.value), case


@pytest.mark.parametrize(
    "row, case",
    [
        # REQUIRED and non-empty for ADJUDICATE: an absent list means
        # "nothing", never "anything".
        ({"role": "adjudicate"}, "absent"),
        ({"role": "adjudicate", DISPUTED_PATHS_FIELD: []}, "empty-list"),
        ({"role": "adjudicate", DISPUTED_PATHS_FIELD: None}, "present-but-null"),
        ({"role": "adjudicate", DISPUTED_PATHS_FIELD: "src/a.py"}, "bare-string"),
        ({"role": "adjudicate", DISPUTED_PATHS_FIELD: [""]}, "blank-entry"),
        ({"role": "adjudicate", DISPUTED_PATHS_FIELD: ["src/a.py", 3]}, "int-entry"),
        # Forbidden on every other role, INCLUDING legacy.
        ({"role": "bodies", DISPUTED_PATHS_FIELD: ["src/a.py"]}, "on-bodies"),
        ({"role": "scaffold", DISPUTED_PATHS_FIELD: ["src/a.py"]}, "on-scaffold"),
        ({"role": "seals", DISPUTED_PATHS_FIELD: ["src/a.py"]}, "on-seals"),
        ({DISPUTED_PATHS_FIELD: ["src/a.py"]}, "on-legacy-row"),
    ],
)
def test_disputed_paths_contract_is_enforced_per_role(row: dict, case: str) -> None:
    """Red now: NotImplementedError.
    Green when: ADJUDICATE requires a non-empty list of real paths and every
    other role forbids the field.
    """
    with pytest.raises(RoleProtocolError) as exc:
        parse_task_role_spec(row, task_key=TASK_KEY)
    assert TASK_KEY in str(exc.value), case


@pytest.mark.parametrize("wildcard", sorted(FORBIDDEN_DISPUTED_GLOBS))
def test_wildcard_disputed_path_is_refused(wildcard: str) -> None:
    """A wildcard adjudication converts ALLOW_ONLY into UNRESTRICTED.

    The row set is DERIVED from FORBIDDEN_DISPUTED_GLOBS, so adding a wildcard
    to that frozenset adds its row automatically and removing one removes its
    protection visibly.

    Red now: NotImplementedError.
    Green when: each wildcard is refused as a `disputed_paths:` entry.
    """
    row = {"role": "adjudicate", DISPUTED_PATHS_FIELD: [wildcard]}
    with pytest.raises(RoleProtocolError):
        parse_task_role_spec(row, task_key=TASK_KEY)


def test_adjudicate_row_with_real_disputed_paths_parses() -> None:
    """Red now: NotImplementedError.
    Green when: a well-formed adjudicate row yields its writable set.
    """
    row = {
        "role": "adjudicate",
        DISPUTED_PATHS_FIELD: ["tests/test_role_protocol_diff.py"],
    }
    spec = parse_task_role_spec(row, task_key=TASK_KEY)
    assert spec.role is Role.ADJUDICATE
    assert spec.disputed_paths == ("tests/test_role_protocol_diff.py",)
    assert spec.added_immutable_globs == ()


# --------------------------------------------------------------------------- #
# validate_override: ADD-only, and a negation is an ERROR not a filename
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "entry",
    [
        "!tests/**",
        "-tests/**",
        "tests/**:allow",
        "!**/schema/**",
        "- **/tests/**",
    ],
)
def test_negation_shaped_override_entry_is_refused(entry: str) -> None:
    """`immutable_paths:` has no subtraction syntax, so the expressible failure
    is an entry SHAPED like a negation. Treating it as an odd filename would let
    an agent believe it had been granted an exemption.

    Red now: `validate_override` raises NotImplementedError.
    Green when: negation-shaped entries raise RoleProtocolError.
    Falsify: accept `!tests/**` as a literal path — every row here goes red.
    """
    spec = TaskRoleSpec(
        task_key=TASK_KEY, role=Role.BODIES, added_immutable_globs=(entry,)
    )
    with pytest.raises(RoleProtocolError):
        validate_override(spec, built_in_policy())


def test_pure_addition_is_legal() -> None:
    """Red now: NotImplementedError.
    Green when: an addition validates silently (ADD-only is the whole point).
    """
    spec = TaskRoleSpec(
        task_key=TASK_KEY,
        role=Role.BODIES,
        added_immutable_globs=("**/fixtures/**", "**/cmd/reviewer/**"),
    )
    validate_override(spec, built_in_policy())


def test_redundant_addition_is_legal_here_and_only_warned_by_validate() -> None:
    """An entry already covered by the default is redundant, not narrowing.

    Invariant 5 makes it worth reporting, but `validate` owns that warning;
    refusing it here would make the two decisions disagree.

    Red now: NotImplementedError.
    Green when: `validate_override` accepts a redundant entry.
    """
    spec = TaskRoleSpec(
        task_key=TASK_KEY, role=Role.BODIES, added_immutable_globs=("**/tests/**",)
    )
    validate_override(spec, built_in_policy())


def test_override_is_measured_against_the_protected_set_not_the_literal_list() -> None:
    """A policy whose deny set the override would shrink must be refused.

    Constructed policy: BODIES denies `**/tests/**`; the "override" replaces it
    with a strictly narrower `tests/unit/**`. Under an ADD-only reading the
    union still protects `**/tests/**`, so this must pass; under a
    replace-the-list reading it silently drops protection. The seal pins the
    additive reading by asserting the union is what `effective_rule` applies.

    Red now: `effective_rule` raises NotImplementedError.
    Green when: the effective globs are policy-first union, never a replacement.
    """
    policy = RolePolicy(
        rules=(
            RoleRule(
                role=Role.BODIES,
                kind=RuleKind.DENY_GLOBS,
                globs=("**/tests/**",),
                rationale="probe",
            ),
        ),
        source=PolicySource.BUILT_IN_DEFAULTS,
    )
    spec = TaskRoleSpec(
        task_key=TASK_KEY, role=Role.BODIES, added_immutable_globs=("tests/unit/**",)
    )
    rule = effective_rule(spec, policy)
    assert rule.globs == ("**/tests/**", "tests/unit/**")


# --------------------------------------------------------------------------- #
# effective_rule: total over RuleKind, order stable, ALLOW_ONLY not unioned
# --------------------------------------------------------------------------- #


def test_effective_rule_for_deny_globs_is_policy_first_and_deduplicated() -> None:
    """Order matters: the reported `matched_glob` must be stable, so policy
    globs come first and a duplicate addition is dropped rather than appended.

    Red now: `effective_rule` raises NotImplementedError.
    Green when: globs == policy globs + new additions, deduplicated, in order.
    """
    policy = built_in_policy()
    base_globs = policy.rule_for(Role.BODIES).globs
    spec = TaskRoleSpec(
        task_key=TASK_KEY,
        role=Role.BODIES,
        # The first entry duplicates a policy glob; the second is new.
        added_immutable_globs=(base_globs[0], "**/fixtures/**"),
    )
    rule = effective_rule(spec, policy)
    assert rule.role is Role.BODIES
    assert rule.kind is RuleKind.DENY_GLOBS
    assert rule.globs == (*base_globs, "**/fixtures/**")


def test_effective_rule_for_allow_only_is_exactly_the_disputed_paths() -> None:
    """For ALLOW_ONLY a union would WIDEN, so the policy globs are not merged in.

    Red now: NotImplementedError.
    Green when: globs == spec.disputed_paths exactly.
    Falsify: union the (empty) table globs in — assertion on identity of the
    tuple contents still holds, so the seal instead pins the ALLOW_ONLY kind and
    the exact tuple; adding any extra glob reddens it.
    """
    spec = TaskRoleSpec(
        task_key=TASK_KEY,
        role=Role.ADJUDICATE,
        disputed_paths=("tests/test_x.py", "src/x.py"),
    )
    rule = effective_rule(spec, built_in_policy())
    assert rule.kind is RuleKind.ALLOW_ONLY_GLOBS
    assert rule.globs == ("tests/test_x.py", "src/x.py")


def test_effective_rule_for_unrestricted_is_returned_unchanged() -> None:
    """LEGACY has no immutable paths and must not acquire any here.

    Red now: NotImplementedError.
    Green when: the LEGACY rule comes back as the table's own entry.
    """
    policy = built_in_policy()
    spec = TaskRoleSpec(task_key=TASK_KEY, role=Role.LEGACY)
    rule = effective_rule(spec, policy)
    assert rule == policy.rule_for(Role.LEGACY)
    assert rule.kind is RuleKind.UNRESTRICTED
    assert rule.globs == ()


def test_effective_rule_refuses_an_illegal_override_before_producing_a_rule() -> None:
    """Validate before apply (invariant 2): an illegal override yields no rule.

    Red now: NotImplementedError is not RoleProtocolError.
    Green when: `effective_rule` calls `validate_override` first and the raise
    propagates.
    """
    spec = TaskRoleSpec(
        task_key=TASK_KEY, role=Role.BODIES, added_immutable_globs=("!tests/**",)
    )
    with pytest.raises(RoleProtocolError):
        effective_rule(spec, built_in_policy())


# --------------------------------------------------------------------------- #
# parse_role_value — the CLI/script face of the same closed set
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text, expected",
    [
        ("scaffold", Role.SCAFFOLD),
        ("seals", Role.SEALS),
        ("bodies", Role.BODIES),
        ("adjudicate", Role.ADJUDICATE),
        ("  BODIES  ", Role.BODIES),
        ("Seals", Role.SEALS),
    ],
)
def test_parse_role_value_accepts_the_authorable_roles(text: str, expected: Role) -> None:
    """Red now: `parse_role_value` raises NotImplementedError.
    Green when: it parses exactly AUTHORABLE_ROLES, case-insensitively.
    """
    assert parse_role_value(text) is expected


@pytest.mark.parametrize(
    "text, case",
    [
        # A checker invoked with `legacy` is a checker invoked with no role;
        # answering CLEAN for it would disable the gate by passing a word.
        ("legacy", "literal-legacy"),
        ("LEGACY", "literal-legacy-upper"),
        ("", "empty"),
        ("   ", "whitespace"),
        ("scaffold+seals", "two-roles"),
        ("implementer", "unknown"),
        ("body", "near-miss"),
    ],
)
def test_parse_role_value_rejects_everything_else(text: str, case: str) -> None:
    """Red now: NotImplementedError is not RoleProtocolError.
    Green when: each of these raises RoleProtocolError.
    """
    with pytest.raises(RoleProtocolError):
        parse_role_value(text)


def test_parse_role_value_covers_every_authorable_role() -> None:
    """Derived from AUTHORABLE_ROLES, so a new authorable role cannot be
    unparseable by the script face while the plan-time parser accepts it.

    Red now: NotImplementedError.
    Green when: every AUTHORABLE_ROLES member round-trips through its value.
    """
    for role in sorted(AUTHORABLE_ROLES, key=lambda r: r.value):
        assert parse_role_value(role.value) is role
