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

LEGACY — resolved by P4, 2026-08-07
-----------------------------------
This file originally sealed the floor for the four AUTHORABLE roles only, and
said so under a heading reading "what is deliberately NOT sealed here". The
reason was real and was not the seal author's to overrule: two committed seals
asserted the opposite (`test_role_protocol_diff.py::test_legacy_is_clean_on_any_
non_empty_diff` pinned LEGACY + `.dispatcher.yaml` to CLEAN with
`violations == ()`, and `test_role_protocol_table.py`'s UNRESTRICTED row probed
the same path expecting none), and a seal author may not amend a seal.

The operator has ruled that the floor applies to LEGACY too, on the ground that
the alternative is not a floor: LEGACY is the state a row acquires by having no
`role:` key, so a floor LEGACY escapes is bypassed by DELETING ONE LINE, and the
deleted line buys the right to rewrite the file that configures every role's
permissions. Both seals were amended by P4 — each carries its own AMENDED BY P4
note and justification — and the coverage here is extended to all five roles:
the LEGACY rows of `_FLOOR_x_ROLE_ROWS`, plus
`test_a_role_less_task_cannot_omit_its_way_past_the_floor` and its control
`test_legacy_still_writes_everything_that_is_not_on_the_floor`.

Note for P3: `check_branch` short-circuits LEGACY to CLEAN *before* the changed
paths are evaluated, and its docstring still says "LEGACY always returns CLEAN
when the diff read succeeded and was non-empty". That sentence is overridden by
this ruling and must be updated in the same commit that implements the floor;
P4 left `src/` alone deliberately (see the FLOOR_GLOBS note below).

Plan time and LEGACY: nothing to seal. `disputed_paths:` is forbidden on every
role but ADJUDICATE, and `immutable_paths:` only ADDs, so a LEGACY row has no
way to DECLARE a floor path at all. Point 2 is ADJUDICATE-shaped by
construction; point 1 is what covers LEGACY.

`FLOOR_GLOBS` living in `src/` — P4 reading, noted not acted on
---------------------------------------------------------------
The typed constant this file binds to was added by the SEALS author to
`src/claude_dispatcher/role_protocol.py`, and `**/src/**` is denied to SEALS.
The gate this unit builds would flag that commit. P4's reading: the write was
sanctioned (the SEALS brief allows the typed stub a seal needs something to bind
to, and the constant carries no behaviour — nothing reads it), but the gate is
right to flag it and the exemption is not expressible in the policy today. It is
recorded as a known, accepted divergence rather than papered over; the durable
fix is for the SCAFFOLD phase to land the typed name, so the seal author never
needs to write under `src/` at all. No seal here asserts anything about it.

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


def _run_stub(changed: list[str], *, base_ref: str = "main"):
    """P4 (2026-08-08), adjudicating D1-inputs blocker 1: `merge-base` answers,
    and nothing else was added.

    Fixing I4 — the signature baseline is read at the base ref's TIP, not at the
    merge-base the three-dot diff measured from — needs a third git read that no
    seal here had modelled, and a BODIES implementer may not edit `tests/**` to
    model it. The answer is the BASE REF, because that is what the merge-base IS
    in a stub that models no advanced base: these rows are about the floor, and
    must not go red or green according to how I4 is fixed.

    It is answered explicitly rather than by echoing whichever argument follows
    `merge-base`, so a call spelled with a flag or with the refs reversed cannot
    collect a rubber stamp; a `merge-base` between refs this stub does not model
    raises like any other unscripted read; and a blob read is STILL unscripted
    here, which is the property that makes these floor rows prove the floor was
    applied to the path list rather than to some file's contents.
    """

    def run(cmd, *_args, **_kwargs):
        argv = [str(c) for c in cmd]
        if "diff" in argv:
            return _RunResult(0, "".join(p + "\n" for p in changed), "")
        if "merge-base" in argv:
            if base_ref not in argv:
                raise AssertionError(
                    f"merge-base asked for refs this stub does not model "
                    f"(it models {base_ref!r} as the merge-base): {argv}"
                )
            return _RunResult(0, base_ref + "\n", "")
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
            # P4: `_STRIPPED_RATIONALE` here too, not the word "legacy", so the
            # LEGACY rows of `_FLOOR_x_ROLE_ROWS` get the same proof as every
            # other row that the violation carried the FLOOR's reason.
            rules.append(
                RoleRule(
                    Role.LEGACY, RuleKind.UNRESTRICTED, (), _STRIPPED_RATIONALE
                )
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
#:
#: **P4, 2026-08-09 — the gate's own two halves join the floor, and this table
#: fixes their SPELLING.** `test_role_protocol_provenance.py` seals in twenty
#: literal rows, under a policy stripped of every relevant glob, that no role may
#: write `scripts/check_body_branch.sh` or
#: `src/claude_dispatcher/role_protocol.py`; only a tier no supplied policy can
#: lower satisfies that, which is `FLOOR_GLOBS`. That file deliberately asserts
#: nothing about the glob STRING ("the fixer chooses the mechanism"), but the
#: seal below is a set difference AGAINST `FLOOR_GLOBS` and so cannot be
#: spelling-neutral: a glob P3 writes that is not a string written here reddens
#: it, and P3 may not amend a seal. P4 therefore rules the spelling rather than
#: leaving P3 to guess it and be blocked. **P3: use these two strings, or
#: escalate — do not edit this table.**
#:
#: Path-qualified (`**/src/claude_dispatcher/role_protocol.py`), NOT
#: basename-only (`**/role_protocol.py`):
#:
#:   1. A floor has no override, which the 2026-08-07 ruling weighs as the
#:      dominant cost. A basename-only glob permanently forbids every file that
#:      ever acquires that basename anywhere in the tree — a vendored copy, a
#:      fixture, an unrelated future module — and nothing can buy it back. The
#:      panel named TWO artifacts, and `_STILL_WRITABLE_ROWS` in the provenance
#:      seals says so in as many words: "the protection is about TWO named
#:      artifacts, not about the directories they live in".
#:   2. The nested layout costs no extra width, because a leading `**/` matches
#:      zero directories in this module's translation — the same
#:      one-pattern-two-layouts reasoning `DEFAULT_ROLE_RULES` states for
#:      `**/x/**`. Measured 2026-08-09: both probes of each glob match, and
#:      `src/claude_dispatcher/plan.py` and `scripts/some_other_helper.sh` (the
#:      provenance controls) match neither.
#:   3. The move-then-edit bypass a path-qualified glob might seem to leave open
#:      is closed elsewhere: `changed_paths_between` runs `--no-renames`, "so
#:      each side of a move is its own path", and the old path is a floor hit. A
#:      move sanctioned on the protected base must edit `FLOOR_GLOBS`, and this
#:      literal table makes that edit visible instead of silent.
#:
#: `_FLOOR_x_ROLE_ROWS` is deliberately NOT extended with these globs. Its job —
#: every role times every probe, under a policy that omits the floor — already
#: exists for the gate, written out, as `_GATE_ROWS` in
#: `test_role_protocol_provenance.py` (twenty rows, five roles, both probes of
#: both halves). A second copy here would be two notions of one fact, which is
#: invariant 5's failure mode, and the two copies would drift.
#:
#: THE GATE'S THIRD ARTIFACT — the Go signature helper (P4 ruling, 2026-08-09,
#: unit D2). **P3: use this string, or escalate — do not edit this table.**
#:
#:     **/src/claude_dispatcher/go_signature_fingerprint/**
#:
#: The same standing before the same two constraints, decided the same way:
#:
#:   1. PATH-QUALIFIED, not basename-only. `**/go_signature_fingerprint/**`
#:      would permanently forbid every directory that ever acquires that name
#:      anywhere in the tree — a vendored copy, a fixture holding a deliberately
#:      broken helper for a seal to point at, a second implementation under
#:      `tools/` — with nothing able to buy any of them back, because a floor
#:      has no override. Measured 2026-08-09 under the module's own glob lens:
#:      the path-qualified spelling matches `src/claude_dispatcher/
#:      go_signature_fingerprint/main.go`, its `go.mod`, a nested
#:      `internal/deep/x.go` under it, and the vendored
#:      `sub/project/...` layout — and does NOT match
#:      `tools/go_signature_fingerprint/main.go` or
#:      `vendor/go_signature_fingerprint/main.go`, which is precisely the
#:      difference the basename spelling would erase.
#:   2. The trailing `/**` is a SUBTREE, and that is the ruling rather than a
#:      typing convenience. The helper is a Go module: `go.mod` fixes the
#:      language version the parse runs under, so it is a parser input as much
#:      as `main.go` is, and any file a later unit adds beside them is too. A
#:      floor naming `.../go_signature_fingerprint/main.go` would protect the
#:      file while leaving the module that configures it writable — the same
#:      shape as protecting `role_protocol.py` and leaving `.dispatcher.yaml`
#:      open, which is the hole S2/S3 closed.
#:
#: Because `_FLOOR_ROWS` is a set difference against `FLOOR_GLOBS`, this
#: spelling is BINDING on P3: a glob P3 writes that is not this exact string
#: reddens `test_the_floor_is_exactly_the_written_out_set_of_globs`, and P3 may
#: not amend a seal. The probes below are files UNDER the directory, never the
#: directory itself — git reports files, and `**` matches no path component at
#: the bare directory (measured: `.../go_signature_fingerprint` alone does not
#: match). A probe naming the bare directory would be a row that can never fire.
_FLOOR_ROWS: tuple[tuple[str, str], ...] = (
    ("**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("**/scripts/check_body_branch.sh", "scripts/check_body_branch.sh"),
    (
        "**/scripts/check_body_branch.sh",
        "sub/project/scripts/check_body_branch.sh",
    ),
    (
        "**/src/claude_dispatcher/role_protocol.py",
        "src/claude_dispatcher/role_protocol.py",
    ),
    (
        "**/src/claude_dispatcher/role_protocol.py",
        "sub/project/src/claude_dispatcher/role_protocol.py",
    ),
    (
        "**/src/claude_dispatcher/go_signature_fingerprint/**",
        "src/claude_dispatcher/go_signature_fingerprint/main.go",
    ),
    (
        "**/src/claude_dispatcher/go_signature_fingerprint/**",
        "sub/project/src/claude_dispatcher/go_signature_fingerprint/main.go",
    ),
    # The subtree half of the ruling, as its own rows rather than as prose: a
    # spelling that named `main.go` alone would leave the module definition and
    # anything nested writable, and these two are the only rows that would
    # catch it.
    (
        "**/src/claude_dispatcher/go_signature_fingerprint/**",
        "src/claude_dispatcher/go_signature_fingerprint/go.mod",
    ),
    (
        "**/src/claude_dispatcher/go_signature_fingerprint/**",
        "src/claude_dispatcher/go_signature_fingerprint/internal/parse/decl.go",
    ),
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

    P4, 2026-08-09: the written list now also carries the two globs the gate's
    own halves need (see the ruling on `_FLOOR_ROWS`), so P3 can extend
    `FLOOR_GLOBS` without this reddening — provided it uses those two strings.
    The length bound below moved 2 -> 6 in the same edit, so DELETING a written
    row still reddens something even when the matching constant entry is deleted
    with it, which is the 18-of-28 failure mode this table exists to avoid.

    P4, 2026-08-09 (unit D2): a THIRD gate artifact, the Go signature helper,
    with four rows and the bound 6 -> 10. Four and not two because this glob is
    a SUBTREE, and the extra two rows are what makes the subtree half of the
    ruling falsifiable rather than decorative. Measured, both ways:

      * narrow ONLY `FLOOR_GLOBS` to `.../go_signature_fingerprint/main.go` and
        the set-difference above fires first, naming the unsealed glob;
      * narrow the constant AND this table together — the edit someone
        "tidying" both would make — and the set difference is satisfied, so the
        NON-VACUITY LOOP is the only thing left: the `go.mod` row goes red
        because it no longer matches. Without that row the narrowing lands
        silently and the module definition that fixes the Go language version
        the parse runs under becomes writable by the branch being parsed.
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
    assert len(_FLOOR_ROWS) >= 10, _FLOOR_ROWS


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

#: (role, floor glob, probe path). WRITTEN OUT — every role times the two probes
#: of the one floor glob. Same P4 lesson as `_FLOOR_ROWS`: derived from
#: `AUTHORABLE_ROLES` or from `FLOOR_GLOBS`, deleting either constant's entry
#: would delete rows instead of reddening them.
#:
#: The two `legacy` rows were added by P4 on the 2026-08-07 ruling that the
#: floor applies to LEGACY as well (see the module docstring). They are the
#: policy-independent half of that ruling: the four authorable rows prove no
#: supplied policy can lower the floor, and the LEGACY rows prove the same for
#: the one role whose rule has no globs to lower.
_FLOOR_x_ROLE_ROWS: tuple[tuple[str, str, str], ...] = (
    ("scaffold", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("scaffold", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("seals", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("seals", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("bodies", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("bodies", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("adjudicate", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("adjudicate", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
    ("legacy", "**/.dispatcher.yaml", ".dispatcher.yaml"),
    ("legacy", "**/.dispatcher.yaml", "sub/project/.dispatcher.yaml"),
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

    A floor that any role can escape is not a floor, so all FIVE roles are
    checked (P4, 2026-08-07: LEGACY was added on the operator's ruling — a floor
    the role-less state escapes is bypassed by deleting the `role:` line). For
    the three DENY roles the compiled-in table already denies this path; that is
    exactly why the injected policy is stripped — under the built-in table those
    rows would pass without a floor existing at all.

    The fixture exhibits the defect first: the probe is asserted WRITABLE under
    the injected policy (no deny glob covers it; ADJUDICATE's declaration grants
    it; LEGACY's rule is UNRESTRICTED and covers nothing), so a pass can only
    come from the floor.

    Red now: `DiffVerdict.CLEAN` for all ten rows.
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
    if role is Role.LEGACY:
        # The same "the fixture exhibits the defect" step, for the one role
        # whose rule carries no globs to inspect: UNRESTRICTED permits the probe
        # outright, so nothing but the floor can produce a violation here.
        assert rule.kind is RuleKind.UNRESTRICTED, rule.kind

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
# Point 1d — LEGACY, the state you get by deleting a line (P4, 2026-08-07)
# --------------------------------------------------------------------------- #


def test_a_role_less_task_cannot_omit_its_way_past_the_floor() -> None:
    """The cheapest bypass of all: no `role:` key, therefore `Role.LEGACY`.

    Added by P4 on the operator's ruling, with the operator's reasoning: a floor
    LEGACY escapes is not a floor, because LEGACY is not a role anyone has to be
    granted — it is what a row IS when the `role:` line is missing. Every seal
    above could hold and the policy file would still be one deleted line away
    from writable. The seal author could not add this row (two committed seals
    asserted the opposite and a seal author may not amend a seal); both were
    amended by P4 and are named in the module docstring.

    This goes through `built_in_policy()` rather than the stripped policy on
    purpose: the stripped-policy version is `_FLOOR_x_ROLE_ROWS`' two `legacy`
    rows, and this one pins the same answer under the policy the gate actually
    runs with.

    The diff is mixed on purpose — a doc, the policy file and a seal — so this
    cannot be satisfied by refusing legacy work wholesale, and so the report
    names only the path that is actually on the floor.

    Red now: `DiffVerdict.CLEAN`, `violations == ()`. `check_branch` returns
    CLEAN for LEGACY *before* it evaluates any path (verified against the built
    worktree), which is the specific place P3 has to union the floor in.
    Green when: exactly one violation, the policy file, naming the floor glob.
    Falsify: exempt LEGACY from the floor — this goes red. Refuse legacy work
    wholesale — the control below goes red.
    """
    changed = ["docs/x.md", _ROOT_CONFIG, "tests/test_x.py"]
    result = _check(Role.LEGACY, changed)
    assert result.checked_paths == tuple(changed)
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        (_ROOT_CONFIG, _THE_CONFIG_FLOOR)
    ], (
        "a row with no `role:` key rewrote the file that configures every "
        "role's permissions; the floor was bypassed by deleting one line"
    )
    assert result.verdict is DiffVerdict.VIOLATION


def test_legacy_still_writes_everything_that_is_not_on_the_floor() -> None:
    """The control for the ruling above, and the reason it is a narrowing rather
    than a withdrawal.

    Every `features/*/tasks.yaml` in this repo is role-less, so "the floor
    applies to LEGACY" must cost those rows nothing outside the floor. The
    probes are the paths OTHER roles are denied — tests, schema, src, the
    reviewer's own instructions — none of which LEGACY has ever been gated on.

    Green now, and it must STILL be green after P3. If it ever goes red, the
    floor was implemented as "gate legacy work like a role", which is a
    different and much larger change than the one that was ruled.
    """
    result = _check(
        Role.LEGACY,
        [
            "docs/x.md",
            "tests/test_x.py",
            "schema/merge.yaml",
            "src/claude_dispatcher/plan.py",
            "roles/reviewer.md",
            "features/d1/tasks.yaml",
        ],
    )
    assert result.verdict is DiffVerdict.CLEAN
    assert result.violations == ()


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
#:
#: **P4 RULING, 2026-08-07 — the line above is the right line, and it is now
#: bounded on BOTH sides.** The seal author raised where to draw it as an open
#: question. Upheld, for three reasons:
#:
#:   1. The two points are not two attempts at the same check. Point 1 is a
#:      DECISION over the paths git reported and is complete: `sub/**` and
#:      `**/*.yaml` are caught there for real, by
#:      `test_the_floor_does_not_care_how_the_declaration_was_spelled`. Point 2
#:      is an EARLY WARNING over a declaration, and a declaration is a string
#:      about the future — it cannot know whether `sub/**` will contain a config
#:      file on the branch that eventually exists. Making the early warning try
#:      to answer a question only the diff can answer is what produces the
#:      false refusals.
#:   2. The cost of being wrong is asymmetric in the safe direction. A missed
#:      plan-time refusal costs one build cycle and the branch is still stopped;
#:      a false plan-time refusal makes a legitimate dispute over `docs/**` or
#:      `src/**` — the two most common shapes a real adjudication takes —
#:      unplannable, with no override, because the whole point of a floor is
#:      that it cannot be overridden.
#:   3. A refusal must be explainable to the agent that trips it. "Your
#:      declaration names the policy file" is a fact about the row. "Your
#:      declaration could match the policy file" is a fact about a hypothetical
#:      tree, and an agent cannot act on it except by narrowing a declaration
#:      that was already correct.
#:
#: The lower bound stays a lower bound (refusing more IS legal), but it is no
#: longer unbounded above: `test_a_legitimate_disputed_path_still_parses` now
#: carries `docs/**`, `src/claude_dispatcher/**` and `sub/**` as rows, so an
#: implementation that reaches for "refuse any glob that could contain a floor
#: path" reddens instead of quietly making real disputes unplannable.
#:
#: **P4 RULING, 2026-08-09 — point 2 covers the WHOLE floor, not just the config
#: file.** The seal author raised, and correctly refused to decide, that once the
#: gate library joins `FLOOR_GLOBS` the row
#: `("src/claude_dispatcher/role_protocol.py",)` in
#: `test_a_legitimate_disputed_path_still_parses` reddens, because
#: `_floor_glob_named_by` compares basenames and reads the whole of
#: `FLOOR_GLOBS`. The question put was whether the floor should refuse
#: *declaring* the gate library or only refuse *writing* it — the two points
#: being separable, and not obliged to cover the same path set.
#:
#: Ruled: they cover the same set, the row's premise is void, and the row is
#: RETARGETED (below) rather than deleted. Three reasons, each answering the
#: 2026-08-07 ruling on its own terms:
#:
#:   1. **The refusal is TRUE, not false.** 2026-08-07 refused to extend point 2
#:      to `docs/**` and `sub/**` because such a declaration *might* contain a
#:      floor path — the refusal would be a guess about a tree that does not
#:      exist. A declaration naming `src/claude_dispatcher/role_protocol.py` is
#:      not a guess: `disputed_paths:` is ADJUDICATE's WRITABLE set, the
#:      decision-time floor refuses that exact write for every role
#:      (`_GATE_ROWS`), so the task could not have landed. Unplannable and
#:      unlandable are the same set here, and point 2 exists precisely to say so
#:      a build cycle earlier.
#:   2. **The cost cited is a cost of the seals, not of this ruling.** "An
#:      adjudication genuinely about `role_protocol.py` becomes unplannable"
#:      conflates subject with write authority. Declaring a path claims the right
#:      to WRITE it; an adjudication may rule on the gate all day — this very
#:      ruling does — while writing only its seals. What the provenance seals
#:      remove is the right to write the gate, from every role including
#:      ADJUDICATE, and the escape stays where `DEFAULT_ROLE_RULES` already puts
#:      it: a reviewed edit on the protected base, i.e. a plan amendment.
#:      Refusing at plan time removes no authority the diff-time floor leaves.
#:   3. **One floor, one meaning.** A `FLOOR_GLOBS` some of whose members are
#:      refused at plan time and some of which are not needs a second constant
#:      saying which — two notions of "is this on the floor" that can disagree,
#:      invariant 5's failure mode, in the module whose docstring names it. And
#:      2026-08-07's own reason 3 points this way: "your declaration names the
#:      gate library, which is on the floor" is a fact about the row, which is
#:      the actionable kind of refusal it asked for.
#:
#: The upper bound is untouched: `docs/**`, `src/claude_dispatcher/**` and
#: `sub/**` remain legitimate rows below, and `src/claude_dispatcher/**` is worth
#: noting — a subtree glob that CONTAINS the gate library is still plannable,
#: because its tail is pure wildcards and names a tree, not a file. The line
#: 2026-08-07 drew has not moved; the floor underneath it grew.
#:
#: The two rows added here are RED until P3 lands the floor globs, exactly like
#: the fifty rows they belong with.
_DECLARATIONS_THAT_NAME_THE_FLOOR: tuple[tuple[tuple[str, ...], str], ...] = (
    ((".dispatcher.yaml",), "the plain spelling"),
    (("./.dispatcher.yaml",), "a leading ./"),
    (("**/.dispatcher.yaml",), "the floor glob verbatim"),
    (("sub/project/.dispatcher.yaml",), "a nested config, named exactly"),
    ((".dispatcher.*",), "an extension wildcard over the same basename"),
    (("**/.dispatcher.yam?",), "a ? inside the extension"),
    (("docs/adr/0007.md", ".dispatcher.yaml"), "hidden behind a genuine artifact"),
    # P4, 2026-08-09 — the ruling above, as data. Without these the ruling is
    # prose and "refuse a declaration of the config file only" satisfies the
    # file.
    (
        ("src/claude_dispatcher/role_protocol.py",),
        "the gate library, named exactly",
    ),
    (("scripts/check_body_branch.sh",), "the gate entrypoint, named exactly"),
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
        # P4, 2026-08-09. This row was `src/claude_dispatcher/role_protocol.py`.
        # Once the gate library is on the floor that path is no longer an
        # ordinary source file, and the row asserted the opposite of
        # `_DECLARATIONS_THAT_NAME_THE_FLOOR`'s new gate-library row — two seals
        # that cannot both hold. RETARGETED, not deleted: the property the row
        # carries is "the plan-time refusal is about the floor FILE, not about
        # `.py`, not about `src/`, and not about the dispatcher package", and
        # `plan.py` states it exactly as well. Deleting it would have dropped
        # that upper bound, which is the one that keeps a fix from refusing
        # every source path an adjudication can name. `plan.py` is the unit's
        # established ordinary-source probe (`_GLOB_PROBES["**/src/**"]`,
        # `_STILL_WRITABLE_ROWS`, the LEGACY control below), and is on no floor
        # glob — measured, not assumed.
        ("src/claude_dispatcher/plan.py",),
        # P4, 2026-08-07 — the UPPER bound on the plan-time refusal set. Each of
        # these three COULD contain a `.dispatcher.yaml` on some tree, and each
        # is a shape real adjudications take. A rule broad enough to refuse
        # `sub/**` refuses these too, and there is no override for a floor.
        ("docs/**",),
        ("src/claude_dispatcher/**",),
        ("sub/**",),
    ],
    ids=[
        "a seal",
        "a doc",
        "a tasks file",
        "a nested yaml",
        "a source file",
        "a docs subtree",
        "a source subtree",
        "an arbitrary subtree",
    ],
)
def test_a_legitimate_disputed_path_still_parses(disputed: tuple[str, ...]) -> None:
    """The non-vacuity companion to the plan-time refusal, and (P4) its upper
    bound.

    Without it, "refuse every adjudicate row" — or "refuse every `*.yaml`" —
    satisfies the seal above. `features/d1/tasks.yaml` is the row that matters
    for the original five: a real dispute is very often about a tasks file.

    The last three rows carry the 2026-08-07 P4 ruling on where the plan-time
    line sits (stated in full above `_DECLARATIONS_THAT_NAME_THE_FLOOR`): plan
    time refuses declarations that NAME the floor file, and does not refuse
    subtree globs that merely could contain one, because only the diff knows
    whether they do — and the diff-time floor catches those for real. Without
    these rows the ruling would be prose; with them, an implementation that
    over-reaches reddens instead of making `docs/**` and `src/**` unplannable.

    **AMENDED BY P4, 2026-08-09**: the "a source file" row was retargeted from
    `src/claude_dispatcher/role_protocol.py` to `src/claude_dispatcher/plan.py`,
    because the gate library joins the floor and a floor path is not a
    legitimate declaration. The row's assertion is unchanged in kind and the
    reasoning is recorded in full above `_DECLARATIONS_THAT_NAME_THE_FLOOR`. The
    upper bound is untouched: `src/claude_dispatcher/**` still parses, so a
    subtree that CONTAINS the gate library is still plannable.

    Red now: passes (nothing refuses anything yet). It is the control and must
    STILL pass after P3.
    Falsify: implement the plan-time rule as "no yaml in disputed_paths" — the
    two yaml rows go red. Implement it as "refuse any glob that could match a
    floor path" — the last three rows go red.
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
