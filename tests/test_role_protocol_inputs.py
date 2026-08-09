"""D1 seals: what the gate READS — the inputs, not the rules.

Every seal in `test_role_protocol_diff.py` and `test_role_protocol_floor.py`
asks whether the right *rule* was applied. This file asks the prior question:
was the rule applied to the right *input*? A gate whose rules are perfect and
whose inputs are wrong reports CLEAN and is worse than no gate, because it also
reports that it checked.

Five findings from the five-seat panel's REJECT on D1, all of them about inputs:

  I1  a path git C-quotes matches no glob, so the deny table and the
      non-overridable floor are both bypassed by an unusual filename.
  I2  the wildcard denylist and ADJUDICATE's allowlist are OPEN sets in the
      unit whose whole doctrine is closed ones.
  I3  the branch ref is read more than once, so the path list and the blob
      reads can describe different revisions.
  I4  the signature baseline is the base ref's TIP, not the merge-base the
      diff was taken against.
  I5  the signature gate reports `signatures: checked` for work it did not do.

**The non-vacuity technique used throughout is the benign twin.** Every seal
runs the gate twice on fixtures that differ in exactly the property under seal —
an ASCII filename next to a quote-bearing one, a base that advanced next to one
that did not, a ref that moved next to one that did not — and requires the two
answers to differ in the stated way. So a row cannot pass by the gate refusing
everything, and cannot pass by the fixture having been innocuous. Where the
twins live in one call they are asserted as one list, so a fix that catches only
the ASCII half still reddens.

No row here is parametrized over a comprehension across the constant it pins:
deleting an entry from a table must redden a row, not delete it. The pairs are
written out.

WHAT WAS ESTABLISHED BY EXECUTION, not read off the contract (I1 in particular
was reported as possibly already closed):

  * `-c core.quotePath=false` — which `changed_paths_between` does carry —
    disables ONLY the octal escaping of non-ASCII bytes. Git C-quotes a path
    containing `"`, `\\`, or a control character **regardless** of that setting.
    Against a real repo whose branch adds five files under `tests/`, today's
    `changed_paths_between` returns:

        'tests/plain.py'                     <- matched by `**/tests/**`
        'tests/tést.py'                      <- matched (this is what
                                                core.quotePath=false bought)
        '"tests/a\\tb.py"'                    <- matches NOTHING
        '"tests/back\\\\slash.py"'              <- matches NOTHING
        '"tests/say\\"hi\\".py"'                <- matches NOTHING

    so three of the five bypass the BODIES deny table entirely. The existing
    seal `test_a_non_ascii_path_survives_the_diff_and_is_still_gate_matched`
    covers only the second row. I1 is open.
  * the RAW (unquoted) names round-trip through `file_text_at` unharmed, so a
    fix that decodes the quoting has a working blob read waiting for it, and a
    fix that merely strips the surrounding quotes without unescaping does not.

TWO THINGS THE FIXER MUST HAVE RULED BEFORE I4 AND I5 CAN LAND, both found by
turning these seals green against a throwaway implementation in a clone:

  1. I4 cannot be fixed without a THIRD git read. The merge-base the three-dot
     diff measured from is not derivable from any command this module already
     runs, and `_run_stub` in `test_role_protocol_diff.py` and
     `test_role_protocol_floor.py` raises `AssertionError: unscripted git
     command` on anything but a diff and a blob spec — so adding
     `git merge-base` reddens ten existing BODIES rows in files a BODIES agent
     may not edit. Those stubs need one row each (answer `merge-base` with the
     base ref, which is what it IS in a stub that models no advanced base).
     That is an extension of a helper, not a weakening of a seal, but it is not
     the implementer's to make unilaterally. The stub in THIS file already
     answers it.
  2. I5's "examined nothing" has a boundary an existing seal already fixes.
     `test_the_ci_script_delegates_instead_of_reporting_not_implemented` runs a
     BODIES branch whose only changed path is a NEWLY ADDED `src/app.py` and
     requires CLEAN with exit 0 — a comparison that also examined zero files.
     So "zero files examined" cannot be turned into a non-CHECKED state
     wholesale; the seals below are scoped to zero-examined-because-nothing-
     was-comparable, which is the state the enum already names. Whether the
     new-file case should also stop reporting `checked` is a live question and
     is deliberately NOT sealed here, because sealing it would contradict a
     seal this author may not amend.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher.role_protocol import (
    DiffVerdict,
    Role,
    RoleProtocolError,
    SignatureCheckStatus,
    TaskRoleSpec,
    built_in_policy,
    changed_paths_between,
    check_branch,
    effective_rule,
    evaluate_changed_paths,
    file_text_at,
    parse_task_role_spec,
)

# --------------------------------------------------------------------------- #
# Seams and fixtures
# --------------------------------------------------------------------------- #


class _RunResult(tuple):
    """A `(rc, stdout, stderr)` triple that also answers `CompletedProcess`."""

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


def _run_stub(changed: list[str], blobs: dict[str, str] | None = None):
    """A git seam answering only the two reads this module may do.

    `blobs` is keyed `"<ref>:<path>"` exactly as git spells it, so a stub answer
    cannot be mistaken for a different revision. An unscripted command raises,
    so a seal cannot pass on a read it never modelled.

    `merge-base` and `rev-parse` answer with the ref they were handed. This
    models a repo in which the refs are stable and the base has NOT advanced,
    which is the deliberate choice for the seals that use this stub: they are
    about what the signature gate REPORTS (I5), and must not go red or green
    according to how I3 and I4 are fixed. The moving ref and the advanced base
    get real repositories, below, because a stub cannot model a ref that moves.
    """
    blobs = blobs or {}

    def run(cmd, *_args, **_kwargs):
        argv = [str(c) for c in cmd]
        if "diff" in argv:
            return _RunResult(0, "".join(p + "\n" for p in changed), "")
        if "merge-base" in argv:
            return _RunResult(0, argv[argv.index("merge-base") + 1] + "\n", "")
        if "rev-parse" in argv:
            return _RunResult(0, argv[-1] + "\n", "")
        spec = next((a for a in argv if ":" in a and not a.startswith("-")), None)
        if spec is not None:
            if spec in blobs:
                return _RunResult(0, blobs[spec], "")
            ref, _, path = spec.partition(":")
            return _RunResult(
                128, "", f"fatal: path '{path}' does not exist in '{ref}'"
            )
        raise AssertionError(f"unscripted git command: {argv}")

    return run


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repo on `main` with one base commit; each test branches off it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    return repo


#: A scaffolded stub and the widening of it a body agent must not get away with.
_STUB_PY = "def f(a: int) -> None:\n    raise NotImplementedError\n"
_WIDENED_PY = "def f(a: int, b: int) -> None:\n    raise NotImplementedError\n"


def _bodies_denies(path: str) -> bool:
    """Does the built-in BODIES deny table forbid `path`? Used as a control."""
    rule = built_in_policy().rule_for(Role.BODIES)
    return bool(evaluate_changed_paths(rule, [path]))


# --------------------------------------------------------------------------- #
# I1 — a path git C-quotes matches no glob (CRITICAL)
#
# `-c core.quotePath=false` closes the non-ASCII case and NOTHING ELSE. Each
# seal below puts the awkward name and its ordinary ASCII twin in ONE commit, so
# one call to the gate answers for both and the seal proves that the QUOTING is
# the difference — not the directory, not the extension, not the rule.
# --------------------------------------------------------------------------- #


def test_a_double_quote_in_a_filename_does_not_buy_a_path_past_the_deny_table(
    git_repo: Path,
) -> None:
    """A body agent may not edit a seal. `tests/plain.py` is stopped. Today
    `tests/say"hi".py` is not, because git renders it `"tests/say\\"hi\\".py"` —
    C-quoted and backslash-escaped — and that string matches `**/tests/**` no
    more than any other sentence does. `core.quotePath=false` does not help:
    it governs the octal escaping of non-ASCII bytes, and a `"` is ASCII.

    Red now (verified against the built worktree, not asserted from contract):
    `changed_paths_between` returns `('"tests/say\\"hi\\".py"', 'tests/plain.py')`
    and only the second is a violation.
    Green when: the raw path comes back and BOTH are violations.
    Falsify: the ASCII twin is in the same diff and the same assertion, so an
    implementation that catches only it still reddens; and the round-trip
    through `file_text_at` reddens a fix that strips the quotes without
    unescaping, which would yield the unreadable `tests/say\\"hi\\".py`.
    """
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / 'say"hi".py').write_text("def test_a():\n    pass\n", "utf-8")
    (git_repo / "tests" / "plain.py").write_text("def test_b():\n    pass\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "two seals, one with a quote in its name"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert sorted(paths) == ['tests/plain.py', 'tests/say"hi".py'], (
        "git C-quotes a path containing a double quote whatever core.quotePath "
        f"says; the gate must be handed the real name: {paths!r}"
    )

    # The path the gate reports must also be the path the gate can READ, or the
    # signature half of the check silently skips the file.
    for path in paths:
        assert file_text_at(git_repo, "feat/x", path) is not None, (
            f"{path!r} came back in a form no blob read can resolve"
        )

    assert _bodies_denies("tests/plain.py"), "control: the ASCII twin is denied"
    violations = evaluate_changed_paths(
        built_in_policy().rule_for(Role.BODIES), list(paths)
    )
    assert sorted(v.path for v in violations) == [
        "tests/plain.py",
        'tests/say"hi".py',
    ], "a seal with a quote in its name is still a seal, and BODIES may not edit it"


def test_a_backslash_in_a_filename_does_not_buy_a_path_past_the_deny_table(
    git_repo: Path,
) -> None:
    """The same hole through the other always-quoted character. Git renders
    `tests/back\\slash.py` as `"tests/back\\\\slash.py"` — quoted AND with the
    backslash doubled — so a fix that only strips the surrounding quotes leaves
    `tests/back\\\\slash.py`, which is neither glob-matchable nor readable.

    Red now: the awkward path comes back quoted and is not a violation; the
    ASCII twin `tests/ordinary.py` in the same commit is.
    Green when: both come back raw and both are violations.
    Falsify: the twin, and the `file_text_at` round-trip, which the
    strip-the-quotes-only fix fails.
    """
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "back\\slash.py").write_text("def test_a():\n    pass\n", "utf-8")
    (git_repo / "tests" / "ordinary.py").write_text("def test_b():\n    pass\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "a seal with a backslash in its name"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert sorted(paths) == ["tests/back\\slash.py", "tests/ordinary.py"], (
        f"the backslash must survive undoubled and unquoted: {paths!r}"
    )
    for path in paths:
        assert file_text_at(git_repo, "feat/x", path) is not None, (
            f"{path!r} came back in a form no blob read can resolve"
        )

    assert _bodies_denies("tests/ordinary.py"), "control: the ASCII twin is denied"
    violations = evaluate_changed_paths(
        built_in_policy().rule_for(Role.BODIES), list(paths)
    )
    assert sorted(v.path for v in violations) == [
        "tests/back\\slash.py",
        "tests/ordinary.py",
    ]


def test_a_control_character_in_a_filename_does_not_buy_a_path_past_the_deny_table(
    git_repo: Path,
) -> None:
    """The third always-quoted class, and the one `changed_paths_between`'s own
    docstring already reasons about: it argues that splitting on newlines is
    safe *because* git C-quotes a path containing a control character. That
    reasoning is correct and it is also the proof that the quoting happens — the
    function relies on the quoting for its parse and then never undoes it.

    Red now: `"tests/a\\tb.py"` comes back quoted and escapes the deny table.
    Green when: the tab survives as a tab and the path is a violation.
    Falsify: the ASCII twin in the same diff.
    """
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "a\tb.py").write_text("def test_a():\n    pass\n", "utf-8")
    (git_repo / "tests" / "ab.py").write_text("def test_b():\n    pass\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "a seal with a tab in its name"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert sorted(paths) == ["tests/a\tb.py", "tests/ab.py"], (
        f"the tab must survive as one character, not as backslash-t: {paths!r}"
    )
    assert _bodies_denies("tests/ab.py"), "control: the ASCII twin is denied"
    violations = evaluate_changed_paths(
        built_in_policy().rule_for(Role.BODIES), list(paths)
    )
    assert sorted(v.path for v in violations) == ["tests/a\tb.py", "tests/ab.py"]


def test_a_quoted_parent_directory_does_not_buy_a_path_past_the_FLOOR(
    git_repo: Path,
) -> None:
    """The consequence that makes I1 CRITICAL rather than cosmetic.

    `.dispatcher.yaml` cannot itself carry a quote — but its *directory* can,
    and `**/.dispatcher.yaml` is matched against the whole path. A branch that
    writes `sub"x/.dispatcher.yaml` rewrites the file configuring every role's
    permissions, and the floor — the thing with no override, the thing the
    2026-08-07 ruling extended to LEGACY precisely so it could not be escaped by
    deleting one line — never sees it, because git hands the gate
    `"sub\\"x/.dispatcher.yaml"`.

    LEGACY is used deliberately: it is the role with the fewest other rules, so
    a violation here can only have come from the floor.

    Red now: `subx/.dispatcher.yaml` is the only reported violation.
    Green when: both are, each naming `**/.dispatcher.yaml`.
    Falsify: the ASCII twin is in the same diff and the same assertion.
    """
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    for directory in ('sub"x', "subx"):
        (git_repo / directory).mkdir()
        (git_repo / directory / ".dispatcher.yaml").write_text("roles: {}\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "rewrite the policy from two directories"], git_repo)

    result = check_branch(
        git_repo, "main", "feat/x", Role.LEGACY, policy=built_in_policy()
    )
    assert sorted(result.checked_paths) == [
        'sub"x/.dispatcher.yaml',
        "subx/.dispatcher.yaml",
    ], f"the gate was handed a path list it cannot match: {result.checked_paths!r}"
    assert sorted((v.path, v.matched_glob) for v in result.violations) == [
        ('sub"x/.dispatcher.yaml', "**/.dispatcher.yaml"),
        ("subx/.dispatcher.yaml", "**/.dispatcher.yaml"),
    ], (
        "a quote in a parent directory name bought a write to the policy file; "
        "the floor has no override, so it also has no excuse for missing one"
    )
    assert result.verdict is DiffVerdict.VIOLATION


# --------------------------------------------------------------------------- #
# I2 — open sets where the doctrine requires closed ones (CRITICAL)
#
# `FORBIDDEN_DISPUTED_GLOBS` is six literals. These seals do NOT pin a
# particular closed rule; they pin its two edges. The refused rows are wildcard
# escapes that name no artifact at all; the accepted rows are the shapes a real
# adjudication takes, and the 2026-08-07 P4 ruling says a rule that refuses
# those is worse than the hole, because a floor has no override and the paths
# become permanently unplannable.
#
# Established by execution against `first_matching_glob`, over the probe set
# {src/…/role_protocol.py, tests/test_x.py, .dispatcher.yaml,
#  sub/project/.dispatcher.yaml, docs/a.md, README.md, a.py}:
#   `**/**`, `**/**/*`, `**/**/**` match 7/7 — the entire repo — and all parse.
#   `*/**`, `**/*/**`, `*/*` match every nested path and all parse.
#   `*`, `**`, `**/*` match 7/7 and ARE refused. That is the whole denylist's
#   contribution: three spellings out of at least nine.
# --------------------------------------------------------------------------- #

#: (declaration, why it is not an adjudication). Written out literally, one row
#: per spelling, NOT derived from `FORBIDDEN_DISPUTED_GLOBS` — a row derived
#: from the constant it pins vanishes when the constant is emptied instead of
#: going red.
_WILDCARD_ESCAPES: tuple[tuple[str, str], ...] = (
    ("**/**", "the panel's row: two doubled stars, grants the whole repo"),
    ("**/**/*", "three segments, still the whole repo"),
    ("**/**/**", "more stars, same set"),
    ("*/**", "every path below the root"),
    ("**/*/**", "the same set with a star buried in the middle"),
    ("*/*", "every path at depth two, naming nothing"),
)


@pytest.mark.parametrize(
    "declaration, why",
    _WILDCARD_ESCAPES,
    ids=[decl for decl, _why in _WILDCARD_ESCAPES],
)
def test_a_wildcard_adjudication_is_refused_however_it_is_spelled(
    declaration: str, why: str
) -> None:
    """A wildcard adjudication is not an adjudication — that sentence is already
    the constant's own docstring. What is missing is that it is enforced by a
    six-entry membership test, so the sentence is true of six strings and false
    of every other spelling of the same thing.

    Red now: every row here returns a `TaskRoleSpec` carrying the escape
    (verified against the built worktree). No exception is raised.
    Green when: `parse_task_role_spec` refuses each, naming the task and entry.
    Falsify: `test_a_named_artifact_still_parses_under_the_closed_rule` is the
    upper bound — refuse-everything reddens it.
    """
    row = {"key": "D1-P4", "role": "adjudicate", "disputed_paths": [declaration]}
    with pytest.raises(RoleProtocolError) as exc:
        parse_task_role_spec(row, task_key="D1-P4")
    message = str(exc.value)
    assert "D1-P4" in message, "the message is read out of a run log; name the task"
    assert declaration in message, (
        f"the refusal must name the offending entry, not just the rule: {message}"
    )


#: The upper bound, written out literally. Each names a tree or a file a real
#: dispute is actually about. A rule broad enough to catch a wildcard escape
#: must not catch these: the 2026-08-07 P4 ruling is that a false refusal makes
#: them permanently unplannable, because a floor has no override.
_NAMED_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("docs/**", "the commonest shape a real adjudication takes"),
    ("src/claude_dispatcher/**", "the second commonest"),
    ("sub/**", "a one-segment tree — the row closest to `*/**` and NOT the same"),
    ("docs/*.md", "a wildcard basename under a named tree"),
    ("features/d1/tasks.yaml", "a real dispute is very often about a tasks file"),
    ("tests/test_role_protocol_inputs.py", "a dispute over one seal"),
)


@pytest.mark.parametrize(
    "declaration, why",
    _NAMED_ARTIFACTS,
    ids=[decl for decl, _why in _NAMED_ARTIFACTS],
)
def test_a_named_artifact_still_parses_under_the_closed_rule(
    declaration: str, why: str
) -> None:
    """The non-vacuity partner of the row above, and the boundary a prior
    adjudicator ruled deliberately.

    `sub/**` is the row that matters: it is one wildcard segment away from
    `*/**`, which the seal above refuses. An implementation that cannot tell
    them apart has not closed the set, it has closed the door.

    Green now, and it must STAY green.
    Falsify: implement the closed rule as "refuse any glob containing `**`" or
    "refuse any glob that could match anything" — `docs/**`,
    `src/claude_dispatcher/**` and `sub/**` all go red.
    """
    row = {"key": "D1-P4", "role": "adjudicate", "disputed_paths": [declaration]}
    spec = parse_task_role_spec(row, task_key="D1-P4")
    assert spec.disputed_paths == (declaration,)


def test_effective_rule_does_not_build_an_allowlist_it_would_refuse_to_validate(
    ) -> None:
    """The second half of I2, and the one the plan-time check cannot cover.

    `effective_rule` builds ADJUDICATE's writable set straight out of
    `spec.disputed_paths` and never validates the result — not against
    `FORBIDDEN_DISPUTED_GLOBS`, not through `validate_rule`, which would have
    refused `**` on sight. `parse_task_role_spec` is not a defence here: nothing
    obliges a `TaskRoleSpec` reaching `check_branch` to have come through it,
    and the seals in this repo construct them directly.

    Red now: `effective_rule` returns `RoleRule(kind=ALLOW_ONLY_GLOBS,
    globs=('**',))` — an allow-only rule that allows everything, which is
    `UNRESTRICTED` with extra steps and is exactly what `validate_rule` exists
    to refuse.
    Green when: it refuses, or produces a rule that still forbids a path the
    declaration named nothing about. Which of the two is the fixer's choice;
    what it must not do is hand back a rule that clears the repo.
    Falsify: the `docs/**` control below — an implementation that refuses every
    allow-only rule reddens it.
    """
    probe = "src/claude_dispatcher/role_protocol.py"

    spec = TaskRoleSpec(
        task_key="D1-P4", role=Role.ADJUDICATE, disputed_paths=("**",)
    )
    try:
        rule = effective_rule(spec, built_in_policy())
    except RoleProtocolError:
        pass
    else:
        assert evaluate_changed_paths(rule, [probe]), (
            "an adjudicate row declaring `**` was handed an allowlist that "
            f"clears {probe}; `validate_rule` refuses that exact glob, and "
            "nothing put the built rule in front of it"
        )

    # The control: a real declaration must still produce a working allowlist,
    # so the row above cannot be satisfied by refusing ADJUDICATE outright.
    legitimate = effective_rule(
        TaskRoleSpec(
            task_key="D1-P4", role=Role.ADJUDICATE, disputed_paths=("docs/**",)
        ),
        built_in_policy(),
    )
    assert evaluate_changed_paths(legitimate, ["docs/adr/0007.md"]) == (), (
        "a legitimate adjudication over docs/** no longer permits its own tree"
    )
    assert evaluate_changed_paths(legitimate, [probe]), (
        "docs/** must still refuse a source file, or this control proves nothing"
    )


@pytest.mark.parametrize("declaration", ["**", "**/**"])
def test_check_branch_does_not_bless_a_wildcard_adjudication(
    declaration: str,
) -> None:
    """The consequence, at the one entrypoint all three callers share: an
    adjudicate branch that rewrote the role-protocol module itself and a seal,
    under a declaration that named neither, must not be told it is CLEAN.

    Both spellings are here on purpose. `**` is in the denylist and still gets
    through, because the denylist is only ever consulted at plan time; `**/**`
    is not in the denylist at all. One fix must close both, and they fail for
    different reasons — which is why they are two rows and not one.

    Red now: CLEAN with `violations == ()` for both (verified against the built
    worktree).
    Green when: not CLEAN.
    Falsify: the control below, which must stay CLEAN.
    """
    changed = ["src/claude_dispatcher/role_protocol.py", "tests/test_x.py"]
    spec = TaskRoleSpec(
        task_key="D1-P4", role=Role.ADJUDICATE, disputed_paths=(declaration,)
    )
    result = check_branch(
        "/x",
        "main",
        "feat/x",
        Role.ADJUDICATE,
        spec=spec,
        policy=built_in_policy(),
        run=_run_stub(changed),
    )
    assert result.verdict is not DiffVerdict.CLEAN, (
        f"an adjudicate row declaring {declaration!r} was blessed for rewriting "
        "the module that enforces the protocol"
    )

    # The benign twin: a declaration that names its artifact still passes, so
    # the row above cannot be satisfied by refusing ADJUDICATE wholesale.
    honest = TaskRoleSpec(
        task_key="D1-P4", role=Role.ADJUDICATE, disputed_paths=("docs/**",)
    )
    clean = check_branch(
        "/x",
        "main",
        "feat/x",
        Role.ADJUDICATE,
        spec=honest,
        policy=built_in_policy(),
        run=_run_stub(["docs/adr/0007.md"]),
    )
    assert clean.verdict is DiffVerdict.CLEAN, (
        "a real adjudication over its own declared tree stopped passing; the "
        "closed rule went too far"
    )


# --------------------------------------------------------------------------- #
# I3 — time of check, time of use (HIGH)
# --------------------------------------------------------------------------- #


def test_a_branch_that_moved_mid_check_does_not_get_a_clean_verdict_in_its_name(
    git_repo: Path,
) -> None:
    """`check_branch` resolves `branch_ref` once for the diff and again for
    every blob read. Between the two, the branch can move — the orchestrator
    calls this the instant the implementer returns, and the implementer's own
    session is what is holding the worktree.

    The fixture is the exact damage: at commit A the branch has done innocuous
    body work in `src/app.py`. The gate reads the diff — `('src/app.py',)` —
    and the branch then advances to B, which guts `tests/test_seal.py`. The path
    gate has already run, on a list that predates the seal edit, and the blob
    reads that follow read B. The gate returns CLEAN, stamped
    `branch_ref='feat/x'`, and `feat/x` is now a branch that edited its own
    seal.

    Red now (verified against the built worktree): `verdict=CLEAN`,
    `checked_paths=('src/app.py',)`, `branch_ref='feat/x'`, while
    `git diff main...feat/x` names `tests/test_seal.py` too.

    Green when: the gate does not issue a clean verdict in the moved name. Two
    shapes satisfy that and the fixer picks: notice the move and answer
    UNDETERMINED, or pin the revision up front and report the pinned revision
    rather than the name, so the CLEAN is a claim about a commit that really
    was clean and not about a branch that is not. The assertion is written as
    the conjunction it forbids, so neither shape is pinned.

    Falsify: the `moved=False` control below runs the identical fixture with the
    ref held still and requires CLEAN in the name `feat/x`, so this cannot be
    satisfied by refusing every check, by always answering UNDETERMINED, or by
    never reporting the plain ref name.
    """

    def _build(*, moved: bool):
        _git(["checkout", "-q", "-b", "feat/x"], git_repo)
        (git_repo / "src" / "app.py").write_text(_STUB_PY + "\n# body work\n", "utf-8")
        _git(["add", "."], git_repo)
        _git(["commit", "-q", "-m", "A: innocuous body work"], git_repo)

        fired = {"diff": False}

        def run(cmd, **kwargs):
            argv = [str(c) for c in cmd]
            result = subprocess.run(argv, **kwargs)
            if "diff" in argv and not fired["diff"]:
                fired["diff"] = True
                if moved:
                    (git_repo / "tests" / "test_seal.py").write_text(
                        "def test_contract():\n    assert True  # gutted\n", "utf-8"
                    )
                    _git(["add", "."], git_repo)
                    _git(["commit", "-q", "-m", "B: edits its own seal"], git_repo)
            return result

        return run

    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text(_STUB_PY, encoding="utf-8")
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "test_seal.py").write_text(
        "def test_contract():\n    assert f(1) is None\n", encoding="utf-8"
    )
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "scaffold and seal"], git_repo)

    # The control first, on its own clone of the fixture, so the two runs cannot
    # contaminate each other.
    held_still = check_branch(
        git_repo, "main", "feat/x", Role.BODIES,
        policy=built_in_policy(), run=_build(moved=False),
    )
    assert held_still.verdict is DiffVerdict.CLEAN, (
        "the control: a branch that did honest body work and did NOT move is "
        f"clean, and must stay clean — {held_still.detail}"
    )
    assert held_still.checked_paths == ("src/app.py",), (
        "the control must reach the verdict through the same path list the "
        f"moved run does, or the two are not twins: {held_still.checked_paths!r}"
    )

    _git(["checkout", "-q", "main"], git_repo)
    _git(["branch", "-q", "-D", "feat/x"], git_repo)

    moved = check_branch(
        git_repo, "main", "feat/x", Role.BODIES,
        policy=built_in_policy(), run=_build(moved=True),
    )
    after = subprocess.run(
        ["git", "diff", "--name-only", "main...feat/x"],
        cwd=str(git_repo), capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "tests/test_seal.py" in after, (
        "fixture check: the branch really did edit its own seal by the time the "
        f"check finished — git says {after!r}"
    )
    assert not (
        moved.verdict is DiffVerdict.CLEAN and moved.branch_ref == "feat/x"
    ), (
        "the gate issued a CLEAN verdict in the name 'feat/x' for a branch that "
        f"had edited its own seal by the time it finished reading it; it judged "
        f"{moved.checked_paths!r} and git now reports {after!r}"
    )


# --------------------------------------------------------------------------- #
# I4 — the signature baseline is the wrong revision (HIGH)
# --------------------------------------------------------------------------- #


def test_an_advanced_base_does_not_turn_a_widened_signature_clean(
    git_repo: Path,
) -> None:
    """`changed_paths_between` takes the diff `base...branch` — three-dot, so
    the paths are the branch's own work measured from the MERGE-BASE.
    `_compare_branch_signatures` then reads the baseline text at `base_ref`
    itself: its TIP. The two halves of the same check are taken against two
    different revisions, and a base that has advanced since the branch forked is
    the ordinary case, not an exotic one.

    Both fixtures are the same violating branch: it widens `f(a)` to `f(a, b)`,
    which is precisely the change §2a's gate exists to catch. They differ in one
    thing — whether `main` also advanced to carry that signature. When it did,
    the gate compares the branch against a tip that already agrees with it,
    finds no change, and reports CLEAN.

    Red now (verified against the built worktree):
      base advanced     -> CLEAN,     changes=[]
      base did not      -> VIOLATION, changes=['f']
    Green when: both are VIOLATION naming `f`.
    Falsify: the second half IS the control — it is red-free today and must stay
    that way, so this cannot be satisfied by refusing every BODIES branch, and
    the two halves differ in nothing but the advance.
    """

    def _verdict(*, advance_base: bool):
        repo = git_repo
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "app.py").write_text(_STUB_PY, encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-q", "-m", "M: the scaffolded stub"], repo)

        _git(["checkout", "-q", "-b", "feat/x"], repo)
        (repo / "src" / "app.py").write_text(_WIDENED_PY, encoding="utf-8")
        _git(["add", "."], repo)
        _git(["commit", "-q", "-m", "branch widens the sealed signature"], repo)

        _git(["checkout", "-q", "main"], repo)
        if advance_base:
            (repo / "src" / "app.py").write_text(_WIDENED_PY, encoding="utf-8")
            _git(["add", "."], repo)
            _git(["commit", "-q", "-m", "base advanced past the merge-base"], repo)
        return check_branch(
            repo, "main", "feat/x", Role.BODIES, policy=built_in_policy()
        )

    still = _verdict(advance_base=False)
    assert still.signature is not None
    assert [c.symbol for c in still.signature.changes] == ["f"], (
        "the control: with the base held still the widening IS caught today, "
        "and must stay caught — otherwise the row below proves nothing"
    )
    assert still.verdict is DiffVerdict.VIOLATION

    _git(["checkout", "-q", "main"], git_repo)
    _git(["branch", "-q", "-D", "feat/x"], git_repo)
    (git_repo / "src" / "app.py").unlink()
    _git(["add", "-A"], git_repo)
    _git(["commit", "-q", "-m", "reset the fixture"], git_repo)

    advanced = _verdict(advance_base=True)
    assert advanced.signature is not None
    assert [c.symbol for c in advanced.signature.changes] == ["f"], (
        "the branch widened a sealed signature and the gate found no change, "
        "because it compared the branch against the base's TIP instead of "
        "against the merge-base the path list was taken from"
    )
    assert advanced.verdict is DiffVerdict.VIOLATION


# --------------------------------------------------------------------------- #
# I5 — the signature gate reports work it did not do (CRITICAL/HIGH)
#
# `SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE`'s own docstring already
# rules this: "At least one changed source file is not Python, so this module
# cannot compare its signatures. Named, not silent: an unchecked file must not
# report as an unchanged signature." `_compare_branch_signatures` `continue`s
# past every non-`.py` path before that state can be produced, and the aggregate
# stays CHECKED. So this is not a new rule — it is the existing one, unenforced.
# --------------------------------------------------------------------------- #


def test_a_skipped_non_python_file_is_not_reported_as_a_checked_signature() -> None:
    """A BODIES branch that changed a Go source file and a Python one. The Go
    file's signatures were not compared by anything — this module cannot compare
    them, and the plan's Go side needs its own comparator — yet the result says
    `signatures: checked`, which is the one thing the enum member for this exact
    situation exists to prevent.

    Red now (verified against the built worktree): `status=CHECKED`, and
    `detail` ends `signatures: checked`, for a diff in which one of the two
    changed source files was never opened.
    Green when: the reported status is not CHECKED. Which named state it is —
    the existing `UNCHECKED_UNSUPPORTED_LANGUAGE`, or a new member — is the
    fixer's choice and is not pinned here.
    Falsify: the control below is the same call with the Go file removed and
    requires CHECKED, so this cannot be satisfied by never reporting CHECKED.
    """
    blobs = {"main:src/app.py": _STUB_PY, "feat/x:src/app.py": _STUB_PY}

    mixed = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(["src/app.py", "cmd/x/main.go"], blobs),
    )
    assert mixed.signature is not None
    assert mixed.signature.status is not SignatureCheckStatus.CHECKED, (
        "cmd/x/main.go was skipped and the result still claims the signatures "
        f"were checked: {mixed.detail}"
    )
    assert "signatures: checked" not in mixed.detail, (
        f"the report repeats the claim the status does not support: {mixed.detail}"
    )

    # The control: the identical call with only the Python file. This one really
    # was checked and must keep saying so.
    only_python = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(["src/app.py"], blobs),
    )
    assert only_python.signature is not None
    assert only_python.signature.status is SignatureCheckStatus.CHECKED, (
        "a diff whose only changed file WAS compared must still report checked"
    )
    assert only_python.verdict is DiffVerdict.CLEAN


def test_a_comparison_that_examined_nothing_is_not_reported_as_checked() -> None:
    """The third state collapsed into the same word. This diff contains no
    Python file at all, so `_compare_branch_signatures` iterates, skips
    everything, and returns CHECKED with zero files opened — "I compared them
    and they agree" for a comparison that never happened. "Checked", "not
    applicable" and "examined nothing" are three facts, and the explicit-state
    doctrine this repo enforces says the third is a named state, not the absence
    of a report.

    Red now (verified against the built worktree): `status=CHECKED`,
    `verdict=CLEAN`, `detail` ending `signatures: checked`, for a call that read
    no blob whatsoever — the stub's blob table is empty and it was never asked.
    Green when: the reported status is not CHECKED.
    Falsify: the control below examines exactly one real file and requires
    CHECKED.
    """
    examined_nothing = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(["docs/notes.md", "README.md"]),
    )
    assert examined_nothing.signature is not None
    assert examined_nothing.signature.status is not SignatureCheckStatus.CHECKED, (
        "the gate examined zero files and reported that it had checked them: "
        f"{examined_nothing.detail}"
    )
    assert "signatures: checked" not in examined_nothing.detail

    examined_one = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(
            ["src/app.py"],
            {"main:src/app.py": _STUB_PY, "feat/x:src/app.py": _STUB_PY},
        ),
    )
    assert examined_one.signature is not None
    assert examined_one.signature.status is SignatureCheckStatus.CHECKED, (
        "the control: one real comparison must still report checked, or the row "
        "above is satisfied by never reporting checked at all"
    )
