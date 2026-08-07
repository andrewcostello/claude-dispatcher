"""D1 seals (P2, follow-on): the non-overridable floor.

The hole these seals close
--------------------------
`Role.ADJUDICATE` is gated by an ALLOWLIST (`RuleKind.ALLOW_ONLY_GLOBS`) whose
globs `effective_rule` takes verbatim from the task's own `disputed_paths:`. So
an adjudicate row that declares `.dispatcher.yaml` gets that path *allowed*, and
`check_branch` reports CLEAN while the most privileged role rewrites the file
that configures every role's permissions — its own included. That contradicts
the D1 P1 ruling ("`.dispatcher.yaml` is denied to all four roles") and it is
the self-widening shape this whole unit exists to remove.

`test_role_protocol_table.test_dispatcher_yaml_is_denied_to_all_four_authorable_roles`
already parametrizes over ADJUDICATE, and it passes today — but it passes
because the STATIC table entry's allowlist is empty, so every path is a miss.
It never sees a task row, and a task row is the only way ADJUDICATE ever gets a
writable set. That is why the hole survived it, and why nothing here is
expressed against the static table.

The 2026-08-07 operator ruling closes it at two INDEPENDENT points, and this
file seals both separately on purpose — either one alone must catch the exploit:

  1. **Decision time.** `role_protocol.FLOOR_GLOBS` is unioned into the decision
     inside `check_branch`, and matched against THE PATHS GIT REPORTS AS
     CHANGED — never against the strings the task declared. This is the crux
     and it is what makes the floor spelling-independent: the floor cannot be
     spelled around because it never reads the spelling.
  2. **Plan time.** A row that DECLARES a floor path in `disputed_paths:` is
     refused by `parse_task_role_spec` / `validate`, so the mistake surfaces at
     planning instead of after a build cycle.

Why the spelling matrix is the largest seal here
------------------------------------------------
The shallow implementation of point 1 is a literal string test on the
declaration (`if any(g in FLOOR_GLOBS for g in spec.disputed_paths)`). It would
turn `test_the_adjudicate_exploit_...` green while leaving the exploit live under
`.dispatcher.yaml` (not in FLOOR_GLOBS — the floor glob is `**/.dispatcher.yaml`),
`*.yaml`, `.dispatcher.*` and, most of all, `sub/**` — a declaration containing
no trace of the floor path at all. `_SPELLING_ROWS` is written so that
implementation stays RED on six of its eight rows. Each row also asserts, in the
test body, whether the declaration genuinely GRANTS the changed path, so a row
can never pass on an allowlist miss it was not testing.

What is deliberately NOT sealed here
------------------------------------
`Role.LEGACY`. `test_role_protocol_diff.test_legacy_is_clean_on_any_non_empty_diff`
pins LEGACY + `.dispatcher.yaml` to CLEAN, and the module contract is emphatic
that a pre-protocol row must behave exactly as it does today. "The floor applies
to every role" is therefore sealed here as "every AUTHORABLE role". Raised as a
P2 dispute — see the report.

Vacuity discipline
------------------
The P4 lesson from this unit is quoted where it applies: a seal parametrized
over a comprehension across the constant it pins is VACUOUS, because deleting an
entry from the constant deletes the test row instead of reddening it. Every
table below (`_FLOOR_ROWS`, `_FLOOR_x_ROLE_ROWS`, `_SPELLING_ROWS`,
`_DECLARATIONS_THAT_NAME_THE_FLOOR`) is written out literally, and the live
constant is checked AGAINST the written list, never derived from it.
"""

from __future__ import annotations

import pytest

from claude_dispatcher import plan
from claude_dispatcher.role_protocol import (
    FLOOR_GLOBS,
    DiffVerdict,
    PolicySource,
    Role,
    RolePolicy,
    RoleProtocolError,
    RoleRule,
    RuleKind,
    TaskRoleSpec,
    built_in_policy,
    check_branch,
    first_matching_glob,
    parse_task_role_spec,
    role_policy_from_mapping,
    validate,
)

#: The one floor glob, written out. Checked against the live `FLOOR_GLOBS`
#: rather than read off it: reading it off would make this seal agree with any
#: value the constant happened to hold, including `()`.
_THE_CONFIG_FLOOR = "**/.dispatcher.yaml"

#: The real paths git emits for that glob — a root config and a nested one.
_ROOT_CONFIG = ".dispatcher.yaml"
_NESTED_CONFIG = "sub/project/.dispatcher.yaml"


# --------------------------------------------------------------------------- #
# The git seam. Answers only the diff read; a blob read is unscripted and
# raises, so a seal cannot pass on a code path it never modelled.
# --------------------------------------------------------------------------- #


class _RunResult(tuple):
    def __new__(cls, rc: int, out: str = "", err: str = "") -> "_RunResult":
        return super().__new__(cls, (rc, out, err))

    @property
    def returncode(self) -> int:
        return self[0]

    @property
    def stdout(self) -> str:
        return self[1]

    @property
    def stderr(self) -> str:
        return self[2]


def _run_stub(changed: list[str]):
    def run(cmd, *_args, **_kwargs):
        argv = [str(c) for c in cmd]
        if "diff" in argv:
            return _RunResult(0, "".join(p + "\n" for p in changed), "")
        raise AssertionError(f"unscripted git command: {argv}")

    return run


def _check(role: Role, changed: list[str], **kwargs):
    kwargs.setdefault("policy", built_in_policy())
    return check_branch(
        "/x", "main", "feat/x", role, run=_run_stub(changed), **kwargs
    )


#: A rationale nothing in the module can produce, so a seal can prove the
#: violation it got carried the FLOOR's reason and not the role rule's.
_STRIPPED_RATIONALE = "injected policy with the floor deliberately absent"


def _policy_without_the_floor() -> RolePolicy:
    """A complete, well-formed policy in which no rule mentions a floor glob.

    This models the two things the floor must survive: a base-pinned `roles:`
    section from a repo that does not carry the floor, and a caller-supplied
    policy (`check_branch(..., policy=...)`, which the contract says wins
    verbatim). Every seal that uses it first PROVES the probe is writable under
    it, so a pass can only come from the floor.
    """
    rules: list[RoleRule] = []
    for role in Role:
        if role is Role.LEGACY:
            rules.append(
                RoleRule(Role.LEGACY, RuleKind.UNRESTRICTED, (), "legacy")
            )
        elif role is Role.ADJUDICATE:
            rules.append(
                RoleRule(
                    Role.ADJUDICATE, RuleKind.ALLOW_ONLY_GLOBS, (),
                    _STRIPPED_RATIONALE,
                )
            )
        else:
            rules.append(
                RoleRule(
                    role, RuleKind.DENY_GLOBS, ("**/never-touched/**",),
                    _STRIPPED_RATIONALE,
                )
            )
    return RolePolicy(
        rules=tuple(rules),
        source=PolicySource.BASE_PINNED_CONFIG,
        base_ref="main",
    )


def _spec(role: Role, *disputed: str) -> TaskRoleSpec:
    return TaskRoleSpec(
        task_key="D1-P4-DISPUTE", role=role, disputed_paths=tuple(disputed)
    )


# --------------------------------------------------------------------------- #
# Totality: a floor glob added later cannot go unsealed
# --------------------------------------------------------------------------- #

#: (floor glob, a real path git would report for it). WRITTEN OUT, one row per
#: (glob, probe) pair. P4 lesson, 2026-08-07: when this list was derived by a
#: comprehension over the constant it pins, deleting an entry from the constant
#: deleted the row rather than reddening it, and 18 of 28 deletions went
#: undetected across the five D1 seal files. Derive nothing here.
_FLOOR_ROWS: tuple[tuple[str, str], ...] = (
    ("**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
)


def test_the_floor_is_exactly_the_written_out_set_of_globs() -> None:
    """The coverage half of the totality seal, guarding ONE direction: every
    glob in `FLOOR_GLOBS` must appear in the literal tables below.

    Adding a glob to `FLOOR_GLOBS` without writing its rows out reddens HERE
    (and only here). REMOVING one reddens the parametrized rows below, which is
    what "no floor glob can be deleted silently" requires — and that split only
    works because those rows are literal.

    Red now: `FLOOR_GLOBS` is a P2 stub nothing consumes, so this specific
    assertion passes; the seal's value is the *next* glob. It is kept
    non-vacuous by the two assertions after it, which put every written-out
    (glob, probe) pair through the module's real glob lens.
    Green when: the constant and the written list agree.
    Falsify: append a glob to `FLOOR_GLOBS` — this goes red naming it.
    """
    written = {glob for glob, _probe in _FLOOR_ROWS}
    unsealed = sorted(set(FLOOR_GLOBS) - written)
    assert not unsealed, (
        "FLOOR_GLOBS carries globs with no literal row in this file, so they "
        "are unsealed. Write them into _FLOOR_ROWS and _FLOOR_x_ROLE_ROWS "
        f"(and give each a real probe path): {unsealed}"
    )
    # Non-vacuity: the written rows must be real matches under the module's own
    # glob lens, or this file's probes prove nothing about the floor.
    for glob, probe in _FLOOR_ROWS:
        assert first_matching_glob(probe, (glob,)) == glob, (
            f"{probe!r} does not match floor glob {glob!r} — the probe, not "
            "the floor, is wrong"
        )
    assert len(_FLOOR_ROWS) >= 2, _FLOOR_ROWS


def test_the_config_file_is_on_the_floor() -> None:
    """The floor's whole reason for existing, pinned as data.

    Red now: passes trivially against the P2 stub — its job is to make the
    ruling itself falsifiable, so that emptying `FLOOR_GLOBS` to `()` (the
    "could this pass without doing anything?" mutation) cannot leave a no-op
    floor looking like a floor.
    Falsify: `FLOOR_GLOBS = ()` — this goes red, and so does every decision-time
    row below (measured: 21 of the 37 seals in this file redden under that
    mutation once the mechanism exists).
    """
    assert _THE_CONFIG_FLOOR in FLOOR_GLOBS, (
        "the file that configures every role's permissions is not on the "
        f"floor: {FLOOR_GLOBS}"
    )


# --------------------------------------------------------------------------- #
# Point 1a — the exploit itself
# --------------------------------------------------------------------------- #


def test_an_adjudicate_task_cannot_declare_its_way_into_the_policy_file() -> None:
    """THE exploit: an adjudicate row declaring `.dispatcher.yaml` in
    `disputed_paths:`, on a branch that changes that file.

    Today `effective_rule` hands ADJUDICATE an allowlist of exactly the declared
    paths, the changed path matches it, and `check_branch` answers CLEAN — the
    most privileged role rewriting the policy file that configures its own
    permissions, with the gate blessing it.

    Red now: `check_branch` returns `DiffVerdict.CLEAN` with `violations == ()`
    (verified against the built worktree, not asserted from the contract).
    Green when: the floor is unioned into the decision and the changed path is a
    violation naming the floor glob.
    Falsify: drop the floor union from `check_branch` — this goes red.
    """
    spec = _spec(Role.ADJUDICATE, _ROOT_CONFIG)
    result = _check(Role.ADJUDICATE, [_ROOT_CONFIG], spec=spec)

    # The fixture exhibits the defect: the declaration really does grant the
    # path, so this row cannot pass on an allowlist miss.
    assert first_matching_glob(_ROOT_CONFIG, spec.disputed_paths) == _ROOT_CONFIG

    assert result.verdict is DiffVerdict.VIOLATION, (
        "an adjudicate task declared the policy file as its disputed artifact "
        "and the gate blessed the change"
    )
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        (_ROOT_CONFIG, _THE_CONFIG_FLOOR)
    ]
    # The floor must report its OWN reason. Printing ADJUDICATE's rationale
    # ("P4 rules on ONE disputed artifact ... its writable set is the task's
    # disputed_paths:") for this violation would tell the agent the opposite of
    # the truth: the path IS in disputed_paths, and that is exactly why it is
    # refused.
    rationale = result.violations[0].rationale
    assert rationale.strip(), "a floor violation must print why"
    assert rationale != built_in_policy().rule_for(Role.ADJUDICATE).rationale, (
        "the floor violation printed the ADJUDICATE rule's rationale, which "
        "says the writable set IS disputed_paths — the one sentence that "
        "cannot explain this refusal"
    )


def test_a_real_adjudication_still_passes() -> None:
    """The non-vacuity companion to every refusal in this file: the floor must
    refuse the policy file and NOTHING ELSE.

    Without this row, "refuse every adjudicate task" satisfies the whole file.

    Red now: passes (nothing refuses anything yet) — it is the control, and it
    must STILL pass after P3.
    Falsify: implement the floor as "ADJUDICATE may write nothing" — this goes
    red while every other seal here stays green.
    """
    spec = _spec(Role.ADJUDICATE, "tests/test_role_protocol_floor.py")
    result = _check(
        Role.ADJUDICATE, ["tests/test_role_protocol_floor.py"], spec=spec
    )
    assert result.verdict is DiffVerdict.CLEAN
    assert result.violations == ()


# --------------------------------------------------------------------------- #
# Point 1b — spelling independence: the property most likely to be faked
# --------------------------------------------------------------------------- #

#: (declaration written in `disputed_paths:`, path git reports as changed,
#: does that declaration actually GRANT that path today?).
#:
#: Written out literally. Six of these eight rows are CLEAN today, and the two
#: that are not are CLEAN-adjacent: they are violations for the WRONG reason (an
#: allowlist miss), which loses the fact that the file is on the floor.
#:
#: The last two rows are the ones that kill a shallow implementation: `sub/**`
#: and `**/*.yaml` contain no trace of `.dispatcher.yaml`, so NO amount of
#: inspecting the declaration string can catch them. Only checking the path git
#: actually reported can.
_SPELLING_ROWS: tuple[tuple[str, str, bool], ...] = (
    # The plain spelling. Not in FLOOR_GLOBS, so `decl in FLOOR_GLOBS` misses it.
    (".dispatcher.yaml", ".dispatcher.yaml", True),
    # A leading `./`. The glob lens does not normalise it, so today this is an
    # allowlist miss — a violation whose reported reason is the wrong one.
    ("./.dispatcher.yaml", ".dispatcher.yaml", False),
    # The floor glob spelled verbatim — the ONE row a literal-membership
    # implementation would catch.
    ("**/.dispatcher.yaml", ".dispatcher.yaml", True),
    # A `?` wildcard inside the extension: defeats a normalise-then-compare.
    ("**/.dispatcher.yam?", ".dispatcher.yaml", True),
    # Extension wildcard.
    (".dispatcher.*", ".dispatcher.yaml", True),
    # Basename wildcard — `*` crosses `/` in this dialect, so it also grants
    # the nested config.
    ("*.yaml", "sub/project/.dispatcher.yaml", True),
    # Nothing in this declaration names the floor file. A string test on the
    # declaration cannot ever catch it.
    ("**/*.yaml", "sub/project/.dispatcher.yaml", True),
    ("sub/**", "sub/project/.dispatcher.yaml", True),
)


@pytest.mark.parametrize("declaration, changed, declaration_grants_it", _SPELLING_ROWS)
def test_the_floor_does_not_care_how_the_declaration_was_spelled(
    declaration: str, changed: str, declaration_grants_it: bool
) -> None:
    """The crux of the ruling: the floor is matched against the path GIT
    REPORTS, never against the string the task declared.

    Every row declares the policy file some other way and changes the same real
    file. Because the floor never reads the declaration, all eight must produce
    the same answer — a violation naming the floor glob.

    The fixture exhibits the defect on every row: `declaration_grants_it` is
    asserted against the module's own glob lens, so a row can never quietly
    become "the allowlist missed it" and pass for a reason it was not testing.

    Red now: six rows return `DiffVerdict.CLEAN`; the two `declaration_grants_it
    is False` rows return VIOLATION with `matched_glob == ALLOWLIST_MISS`, which
    is not the floor and is refused here by name.
    Green when: the floor is unioned at evaluation time against the changed
    paths.
    Falsify — and this is the reason the table is this long: implement the floor
    as a string test on the declaration
    (`any(g in FLOOR_GLOBS for g in spec.disputed_paths)`) and only the
    `**/.dispatcher.yaml` row goes green; the other seven stay red.
    """
    spec = _spec(Role.ADJUDICATE, declaration)
    granted = first_matching_glob(changed, (declaration,)) is not None
    assert granted is declaration_grants_it, (
        f"the fixture is stale: {declaration!r} "
        f"{'grants' if granted else 'does not grant'} {changed!r}, but the "
        f"table says {declaration_grants_it}"
    )

    result = _check(Role.ADJUDICATE, [changed], spec=spec)
    assert result.checked_paths == (changed,)
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        (changed, _THE_CONFIG_FLOOR)
    ], (
        f"declaring {declaration!r} bought {changed!r}; the floor must be "
        "matched against the path git reported, not against the declaration"
    )
    assert result.verdict is DiffVerdict.VIOLATION


def test_the_floor_fires_on_the_floor_path_and_leaves_the_rest_of_the_diff_alone(
) -> None:
    """A mixed diff: the legitimate disputed artifact AND the policy file.

    The interesting failure this catches is a floor implemented by short-circuit
    — "any floor path in the diff ⇒ the whole branch is a violation" — which
    would report the innocent path as violated too and send the agent hunting
    for a rule that does not exist.

    Red now: CLEAN — the declaration grants both paths.
    Green when: exactly one violation, naming the config file and the floor glob.
    Falsify: report the whole diff on a floor hit — this goes red.
    """
    spec = _spec(Role.ADJUDICATE, "docs/adr/0007.md", _ROOT_CONFIG)
    result = _check(Role.ADJUDICATE, ["docs/adr/0007.md", _ROOT_CONFIG], spec=spec)
    assert result.verdict is DiffVerdict.VIOLATION
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        (_ROOT_CONFIG, _THE_CONFIG_FLOOR)
    ]


# --------------------------------------------------------------------------- #
# Point 1c — the floor is not a property of the policy, so nothing can lower it
# --------------------------------------------------------------------------- #

#: (role, floor glob, probe path). WRITTEN OUT — four authorable roles times the
#: two probes of the one floor glob. Same P4 lesson as `_FLOOR_ROWS`: derived
#: from `AUTHORABLE_ROLES` or from `FLOOR_GLOBS`, deleting either constant's
#: entry would delete rows instead of reddening them.
#:
#: LEGACY is absent deliberately —
#: `test_role_protocol_diff.test_legacy_is_clean_on_any_non_empty_diff` pins
#: LEGACY + `.dispatcher.yaml` to CLEAN and a pre-protocol row must behave
#: exactly as it does today. Raised as a P2 dispute against "the floor applies
#: to EVERY role".
_FLOOR_x_ROLE_ROWS: tuple[tuple[str, str, str], ...] = (
    ("scaffold", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("scaffold", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("seals", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("seals", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("bodies", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("bodies", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("adjudicate", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("adjudicate", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
)


@pytest.mark.parametrize("role_value, glob, probe", _FLOOR_x_ROLE_ROWS)
def test_a_policy_that_omits_the_floor_cannot_lower_it_for_any_role(
    role_value: str, glob: str, probe: str
) -> None:
    """"Unioned into the decision at evaluation time" means the floor is NOT
    merged into a `RolePolicy` — because a policy is something a caller supplies
    and `check_branch`'s contract says a supplied policy wins verbatim.

    This is what makes the floor unlowerable: a base-pinned `roles:` section, a
    caller-supplied policy, a future config shape that replaces rather than adds
    — none of them can reach the floor, because the floor was never in there.

    A floor that any role can escape is not a floor, so all four authorable
    roles are checked. For the three DENY roles the compiled-in table already
    denies this path; that is exactly why the injected policy is stripped —
    under the built-in table these rows would pass without a floor existing at
    all.

    The fixture exhibits the defect first: the probe is asserted WRITABLE under
    the injected policy (no deny glob covers it; ADJUDICATE's declaration grants
    it), so a pass can only come from the floor.

    Red now: `DiffVerdict.CLEAN` for all eight rows.
    Green when: the floor fires regardless of the policy in hand.
    Falsify: merge `FLOOR_GLOBS` into `built_in_policy()` instead of unioning at
    evaluation time — every row here goes red, because the injected policy never
    went through `built_in_policy`.
    """
    role = Role(role_value)
    policy = _policy_without_the_floor()
    rule = policy.rule_for(role)
    assert glob in FLOOR_GLOBS, f"{glob!r} was deleted from FLOOR_GLOBS"
    assert first_matching_glob(probe, rule.globs) is None, (
        "the injected policy denies the probe; this row would then pass "
        "without a floor existing"
    )

    spec = _spec(role, probe) if role is Role.ADJUDICATE else None
    if spec is not None:
        assert first_matching_glob(probe, spec.disputed_paths) is not None

    result = _check(role, [probe], policy=policy, spec=spec)
    assert [(v.path, v.matched_glob) for v in result.violations] == [(probe, glob)], (
        f"role {role_value} wrote {probe!r} under a policy that does not "
        "mention it: the floor was lowered by supplying a policy"
    )
    assert result.verdict is DiffVerdict.VIOLATION
    assert result.violations[0].rationale != _STRIPPED_RATIONALE, (
        "the floor violation printed the injected rule's rationale; a floor "
        "violation must carry the floor's own reason, not whatever text the "
        "policy that failed to contain it happened to hold"
    )


def test_a_repo_roles_section_cannot_buy_back_a_floor_path() -> None:
    """The config face of the same property, through the real parser.

    `roles:` is ADD-only, so a repo cannot spell a removal — but "cannot spell
    it" is an argument, not a test, and the argument has already been wrong once
    in this unit (it is the argument the module docstring uses to conclude that
    role_protocol "needs no separate floor tier the way risk.py does", which is
    the reasoning this whole change overturns).

    Red now: CLEAN — the adjudicate row's declaration grants the config file and
    the parsed policy has no say in an allow-only rule at all.
    Green when: the floor fires over a policy that came out of the repo's own
    config.
    Falsify: make the floor a merge step inside `role_policy_from_mapping` — the
    caller-supplied-policy rows above go red instead.
    """
    policy = role_policy_from_mapping(
        {"bodies": {"immutable_paths": ["**/vendor/**"]}}
    )
    assert policy.source is PolicySource.CONFIG_MAPPING

    spec = _spec(Role.ADJUDICATE, _ROOT_CONFIG)
    result = _check(Role.ADJUDICATE, [_ROOT_CONFIG], policy=policy, spec=spec)
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        (_ROOT_CONFIG, _THE_CONFIG_FLOOR)
    ]
    assert result.verdict is DiffVerdict.VIOLATION


def test_a_per_task_override_cannot_add_a_floor_path_to_the_writable_set() -> None:
    """The per-task face: a row cannot ADD its way past the floor either.

    For a DENY role `immutable_paths:` can only add protection, so the
    expressible per-task attempt is ADJUDICATE's — declare the floor path
    alongside a genuine artifact and let the allowlist grant both. The genuine
    artifact is asserted CLEAN in the same call, so this row cannot pass by the
    floor swallowing the whole declaration.

    Red now: CLEAN, both paths granted.
    Green when: the genuine path is untouched by the floor and the floor path is
    a violation naming the floor glob.
    """
    spec = _spec(Role.ADJUDICATE, "features/d1/tasks.yaml", "**/.dispatcher.yaml")
    result = _check(
        Role.ADJUDICATE, ["features/d1/tasks.yaml", _ROOT_CONFIG], spec=spec
    )
    assert result.verdict is DiffVerdict.VIOLATION
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        (_ROOT_CONFIG, _THE_CONFIG_FLOOR)
    ], "a `.yaml` file that is not the policy file must stay writable"


# --------------------------------------------------------------------------- #
# Point 2 — plan-time refusal
# --------------------------------------------------------------------------- #

#: `disputed_paths:` lists that NAME a floor path, written out literally. Each
#: must be refused by `parse_task_role_spec`.
#:
#: Deliberately narrower than `_SPELLING_ROWS`: these all name the floor FILE,
#: whereas `sub/**` and `**/*.yaml` merely *could contain* one. A plan-time rule
#: broad enough to refuse those would refuse `docs/**` and `src/**` too, which
#: is hostile and unnecessary — the decision-time floor catches them for real,
#: which is the entire reason the ruling has two independent points. This seal
#: is a LOWER bound on the refusal set; refusing more is legal.
_DECLARATIONS_THAT_NAME_THE_FLOOR: tuple[tuple[tuple[str, ...], str], ...] = (
    ((".dispatcher.yaml",), "the plain spelling"),
    (("./.dispatcher.yaml",), "a leading ./"),
    (("**/.dispatcher.yaml",), "the floor glob verbatim"),
    (("sub/project/.dispatcher.yaml",), "a nested config, named exactly"),
    ((".dispatcher.*",), "an extension wildcard over the same basename"),
    (("**/.dispatcher.yam?",), "a ? inside the extension"),
    (("docs/adr/0007.md", ".dispatcher.yaml"), "hidden behind a genuine artifact"),
)


@pytest.mark.parametrize(
    "disputed, case",
    _DECLARATIONS_THAT_NAME_THE_FLOOR,
    ids=[case for _d, case in _DECLARATIONS_THAT_NAME_THE_FLOOR],
)
def test_declaring_a_floor_path_is_refused_at_plan_time(
    disputed: tuple[str, ...], case: str
) -> None:
    """The second, independent point: the mistake surfaces at planning rather
    than after a whole build cycle has been spent on a task that could never
    have been allowed to land.

    Independent by construction — nothing here calls `check_branch`, and the
    diff-time seals above construct their `TaskRoleSpec` directly, so neither
    point can be satisfied by the other.

    Red now: `parse_task_role_spec` returns a `TaskRoleSpec` carrying the floor
    path in `disputed_paths` (verified against the built worktree); no exception
    is raised.
    Green when: it raises `RoleProtocolError` naming the task key and the path.
    Falsify: drop the check — every row goes red.
    """
    row = {"key": "D1-P4", "role": "adjudicate", "disputed_paths": list(disputed)}
    with pytest.raises(RoleProtocolError) as exc:
        parse_task_role_spec(row, task_key="D1-P4")
    message = str(exc.value)
    assert "D1-P4" in message, "the message is read out of a run log; name the task"
    assert any(entry in message for entry in disputed), (
        f"the refusal must name the offending entry, not just the rule: {message}"
    )


@pytest.mark.parametrize(
    "disputed",
    [
        ("tests/test_role_protocol_floor.py",),
        ("docs/adr/0007.md",),
        # A yaml file, and a tasks file, and one under a `sub/` tree: the
        # refusal must be about the POLICY file, not about yaml, not about
        # config-shaped names, and not about nesting.
        ("features/d1/tasks.yaml",),
        ("sub/project/settings.yaml",),
        ("src/claude_dispatcher/role_protocol.py",),
    ],
    ids=["a seal", "a doc", "a tasks file", "a nested yaml", "a source file"],
)
def test_a_legitimate_disputed_path_still_parses(disputed: tuple[str, ...]) -> None:
    """The non-vacuity companion to the plan-time refusal.

    Without it, "refuse every adjudicate row" — or "refuse every `*.yaml`" —
    satisfies the seal above. `features/d1/tasks.yaml` is the row that matters:
    a real dispute is very often about a tasks file.

    Red now: passes (nothing refuses anything yet). It is the control and must
    STILL pass after P3.
    Falsify: implement the plan-time rule as "no yaml in disputed_paths" — the
    two yaml rows go red.
    """
    row = {"key": "D1-P4", "role": "adjudicate", "disputed_paths": list(disputed)}
    spec = parse_task_role_spec(row, task_key="D1-P4")
    assert spec.disputed_paths == disputed


# --------------------------------------------------------------------------- #
# Point 2, through the one plan-time entrypoint
# --------------------------------------------------------------------------- #


def _task(key: str, *, role: str, blocked_by: tuple[str, ...] = (), **extra):
    raw: dict = {"key": key, "summary": key, "status": plan.TODO, "role": role}
    if blocked_by:
        raw["blockedBy"] = list(blocked_by)
    raw.update(extra)
    return plan.Task(
        key=key,
        summary=key,
        description="",
        type="task",
        labels=[],
        blocked_by=list(blocked_by),
        status=plan.TODO,
        raw=raw,
        model=None,
        agent=None,
    )


def _worklist(disputed: list[str]) -> list[plan.Task]:
    """A complete, legal unit plus one adjudicate row — so the ONLY thing that
    can refuse the worklist is the adjudicate row's declaration."""
    return [
        _task("D1-P1", role="scaffold"),
        _task("D1-P2", role="seals", blocked_by=("D1-P1",)),
        _task("D1-P3", role="bodies", blocked_by=("D1-P2",)),
        _task(
            "D1-P4",
            role="adjudicate",
            blocked_by=("D1-P3",),
            disputed_paths=disputed,
        ),
    ]


def test_validate_refuses_the_worklist_rather_than_warning_about_it() -> None:
    """`validate` is what `plan.load_tasks` raises on, so the refusal has to
    arrive as an ERROR — a warning would let the task dispatch and the mistake
    would still cost a build cycle, which is the entire point of point 2.

    Red now: `validate(...).ok is True` — the row parses cleanly today
    (verified against the built worktree).
    Green when: `.ok is False` and the error names D1-P4 and the path.
    Falsify: report it in `.warnings` instead of `.errors` — this goes red on
    `.ok`.
    """
    validation = validate(_worklist([".dispatcher.yaml"]))
    assert validation.ok is False
    offending = [e for e in validation.errors if "D1-P4" in e]
    assert offending, f"no error names the offending row: {validation.errors}"
    assert any(".dispatcher.yaml" in e for e in offending), offending
    assert not any(".dispatcher.yaml" in w for w in validation.warnings), (
        "a floor declaration must refuse the worklist, not merely be mentioned"
    )


def test_the_same_worklist_with_a_real_artifact_validates() -> None:
    """The control for the seal above: the unit, the edges and the adjudicate
    row are otherwise identical, so the refusal above is attributable to the
    declaration and to nothing else in the fixture.

    Red now: passes. Must STILL pass after P3.
    Falsify: refuse every adjudicate row — this goes red.
    """
    validation = validate(_worklist(["features/d1/tasks.yaml"]))
    assert validation.ok is True, validation.errors
    assert [s.task_key for s in validation.specs if s.role is Role.ADJUDICATE] == [
        "D1-P4"
    ]
