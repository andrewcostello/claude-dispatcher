r"""Seals: a path is matched by WHAT IT IS, not by what it can be rendered as.

The hole these seals close
--------------------------
This repo translates a gitignore-style glob to a regex in exactly one place —
``risk._glob_to_regex``, compiled by ``risk._compiled`` — and `*` and `**`
become ``.*``. Python's ``.`` does not match a line feed and the pattern is
compiled without ``re.DOTALL``, so **a path containing a newline matches no
glob**. Every deny table, every allowlist and the non-overridable floor are
built on glob matching, so a path with a newline in it walks past all of them.

Measured against the built worktree at ``48471a5`` (not read off a contract)::

    role_protocol.first_matching_glob('tests/a\nb.py', ('**/tests/**',))  -> None
    role_protocol.first_matching_glob('tests/ab.py',   ('**/tests/**',))  -> '**/tests/**'
    risk.matches_any_glob('docs/a\nb.md', ['**/docs/**'])                 -> False
    risk.matches_any_glob('docs/ab.md',   ['**/docs/**'])                 -> True
    risk._compiled('**/tests/**')  ->  re.compile('(?:.*/)?tests/.*\\Z')   flags: no DOTALL

Why this is not the C-quoting bug again, and why it is worse
------------------------------------------------------------
It is the C-quoting bug's *successor*, introduced by its fix. Before I1
(``test_role_protocol_inputs.py``), ``changed_paths_between`` handed the gate
git's rendering, ``"tests/a\nb.py"`` — six literal characters ending in
``b.py"`` — which matched nothing because it was not a path. I1's fix decodes
that rendering (``_unquote_git_path``), and the decoded name contains a REAL
line feed, which matches nothing for a different reason. One bypass was traded
for another, and the trade is invisible in I1's own seals because they were
written with ``"``, ``\`` and a TAB — and regex ``.`` matches a tab.

**Nothing here weakens or replaces the I1 seals.** They are correct and must
stay green: the decode is right, and these seals sit downstream of it. Every
end-to-end seal below asserts ``checked_paths`` first, so a fix that "solves"
the newline by un-decoding the path reddens here before it reddens I1.

Which control characters actually bypass — MEASURED, not assumed
-----------------------------------------------------------------
``.`` excludes exactly one character, ``\n``. Probing every plausible candidate
against ``**/tests/**`` in basename position, in parent-directory position and
in trailing position:

    \n  LF   BYPASSES  (the whole of this defect)
    \r  CR   matched today
    \f  FF   matched today
    \v  VT   matched today
    \t  TAB  matched today  (this is why I1's control-character seal missed it)
    NUL ESC NEL U+2028      matched today

So the seals for ``\r``, ``\f`` and ``\v`` are GREEN today and are written as
regression guards, not as bypass reports — the brief asked for them because a
fix that special-cases ``\n`` alone would reopen them. The specific way that
happens is the ANCHOR: ``_compiled`` appends ``\Z``, which is why a trailing
``\r`` is harmless. Swap ``\Z`` for ``$`` — the obvious "handle line endings"
reflex — and ``$`` matches before a string-final newline, so an ALLOW_ONLY
declaration of ``sub/x.py`` starts granting the DIFFERENT file ``sub/x.py\n``.
``test_the_match_is_anchored_at_the_end_of_the_string_not_at_a_line_break``
pins that edge closed while it is still closed.

One translator, not two
-----------------------
The brief was written expecting two independent glob→regex translators. There
is ONE. ``role_protocol.first_matching_glob`` delegates to
``risk.matches_any_glob`` one pattern at a time (invariant 5, already
implemented), so a single fix inside ``risk`` closes both gates.
``test_both_gates_answer_the_same_question_the_same_way`` seals the shared
PROPERTY (the two entry points agree) and deliberately does not seal the
mechanism: which module owns the translation is the fixer's call.

Amended by P4, 2026-08-09 — prose only; no assertion here depended on it. As
written this paragraph continued "``risk.py`` is NOT on ``FLOOR_GLOBS`` while
``role_protocol.py`` is, so the fix needs no floor edit". Both halves are now
false. ``tests/test_floor_closure.py`` seals the floor's DELEGATION CLOSURE, and
``risk.py`` is on it precisely BECAUSE of the delegation this paragraph
describes: the single translator every floor decision runs through was writable
by the roles it judges. The fix recorded below landed before that ruling; a
future one inside ``risk`` is a reviewed edit on the protected base, not a line
in a branch under review.

Vacuity discipline
------------------
Every seal runs the matcher over the awkward path AND its ordinary twin, and
wherever the two can share a call they are asserted as one list — so a seal
cannot pass by the matcher refusing everything, cannot pass by the fixture
having been innocuous, and a fix that catches only the twin still reddens.
No row is parametrized over a comprehension across the constant it pins: the
character table and the probe pairs are written out literally, and the live
constants are checked AGAINST the written list, never derived from it.

Non-vacuity evidence recorded per seal in its own docstring under "Red now" /
"Green when" / "Falsify"; the green-today rows carry the mutation that reddens
them.

Evidence, run before this file was committed
---------------------------------------------
19 seals: 12 RED at ``48471a5``, 7 green-today.

JOINT SATISFIABILITY. A throwaway reference implementation in a ``.git``-less
``cp -a`` clone turns all 19 green together and breaks nothing else: one line —
``re.DOTALL`` on ``risk._compiled`` — closes all eleven glob-engine rows across
both gates, and a C-quote-aware header pattern in ``blast_radius.changed_files``
closes the twelfth. Full suite before and after the reference fix: identical
result sets (the only entries in either are four ``test_role_protocol_
provenance.py`` errors caused by the clone having no ``.git``; those four pass
in the worktree). So the twelve reds are one defect with one fix in each of two
surfaces, and the seven green rows survive it.

MUTATION VERIFICATION of the seven green-today rows, each in a fresh clone with
``__pycache__`` cleared immediately before the run, applied to the FIXED tree so
the question asked is "does breaking this redden that":

    \Z -> $ in `_compiled`               -> the anchor row, and only it
    `first_matching_glob` gets its own
      translator (fnmatch)                -> the two-gates-agree row (+4 others)
    `first_matching_glob` returns
      `patterns[0]`                       -> the covers-neither row and the
                                             ordinary-branch-is-CLEAN row
    `risk._first_matching_glob` returns
      `patterns[0]`                       -> the ordinary-diff-is-low row
    `_is_doc` rejects a newline           -> the docs-carve-out row
    `/tests?/` -> `/tests./` in
      `_EXCLUDE_REF`                      -> the blast-radius-exclusion row
    `re.MULTILINE` added                  -> the not-line-oriented row
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import blast_radius, risk
from claude_dispatcher.risk import ELEVATED, LOW, FileDiff, RiskConfig
from claude_dispatcher.role_protocol import (
    FLOOR_GLOBS,
    DiffVerdict,
    Role,
    built_in_policy,
    changed_paths_between,
    check_branch,
    evaluate_changed_paths,
    file_text_at,
    first_matching_glob,
)

# --------------------------------------------------------------------------- #
# The characters, written out. Named rather than inlined because a bare "\n" in
# a path literal is invisible in a diff and unreadable in a failure message.
# --------------------------------------------------------------------------- #

LF = "\n"
CR = "\r"
FF = "\f"
VT = "\v"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repo on `main` with one base commit; each seal branches off it.

    A real repository, not a stubbed `run`, because the whole point of this
    defect is what happens between git's rendering of an awkward name and the
    glob engine. A stub would let a seal pass against a rendering git never
    emits.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    _git(["checkout", "-q", "-b", "feat/x"], repo)
    return repo


def _bodies_denies(path: str) -> bool:
    """Does the built-in BODIES deny table forbid `path`? Used as a control."""
    return bool(
        evaluate_changed_paths(built_in_policy().rule_for(Role.BODIES), [path])
    )


# --------------------------------------------------------------------------- #
# 1. The unit: `role_protocol.first_matching_glob`
# --------------------------------------------------------------------------- #


def test_a_newline_in_a_filename_does_not_buy_a_path_past_the_deny_glob() -> None:
    r"""The defect at its smallest. `tests/a\nb.py` is a file under `tests/`,
    so `**/tests/**` covers it, exactly as it covers `tests/ab.py`.

    Both paths go through ONE assertion so a fix that catches only the ordinary
    twin still reddens, and so the seal proves the NEWLINE is the difference —
    not the directory, not the extension, not the pattern.

    Red now: `('tests/a\nb.py', None)` — the newline path matched nothing.
    Green when: both entries name `**/tests/**`.
    Falsify: the twin in the same assertion; and a matcher that returned the
    pattern for everything would redden
    `test_a_glob_that_covers_neither_twin_matches_neither` below.
    """
    awkward = "tests/a" + LF + "b.py"
    ordinary = "tests/ab.py"

    assert [
        (awkward, first_matching_glob(awkward, ("**/tests/**",))),
        (ordinary, first_matching_glob(ordinary, ("**/tests/**",))),
    ] == [
        (awkward, "**/tests/**"),
        (ordinary, "**/tests/**"),
    ], (
        "a line feed in a filename is not a licence to ignore the glob that "
        "covers the file's directory"
    )


def test_a_glob_that_covers_neither_twin_matches_neither() -> None:
    r"""The other edge, so no seal here can be satisfied by a matcher that
    simply says yes. `**/schema/**` covers neither path.

    Green now and green after: this row exists to make the fix a MATCHER, not
    a rubber stamp.
    Falsify: a `first_matching_glob` hard-wired to return its first pattern
    reddens this row while turning every other row in this file green.
    """
    awkward = "tests/a" + LF + "b.py"
    ordinary = "tests/ab.py"

    assert [
        first_matching_glob(awkward, ("**/schema/**",)),
        first_matching_glob(ordinary, ("**/schema/**",)),
    ] == [None, None]


def test_a_newline_in_a_parent_directory_does_not_buy_a_write_to_the_policy_file() -> (
    None
):
    r"""The shape that makes this a FLOOR bypass rather than a nuisance.

    `.dispatcher.yaml` cannot itself carry a newline in any sane workflow — but
    its DIRECTORY can, and `**/.dispatcher.yaml` is matched against the whole
    path. A branch that writes `a\nb/.dispatcher.yaml` rewrites the file that
    configures every role's permissions, its own included, and the floor — the
    thing with no override, the thing the 2026-08-07 ruling extended to LEGACY
    so it could not be escaped by deleting one line — never sees it.

    `FLOOR_GLOBS` is checked against the written-out literal first, so this row
    cannot silently agree with a `FLOOR_GLOBS` that no longer contains the
    config file (or is empty).

    Red now: `('a\nb/.dispatcher.yaml', None)`.
    Green when: both entries name `**/.dispatcher.yaml`.
    Falsify: the twin in the same assertion.
    """
    assert "**/.dispatcher.yaml" in FLOOR_GLOBS, (
        "this seal binds to the config-file floor glob; if it has been renamed "
        "the seal must be rewritten, not silently pass against its absence"
    )

    awkward = "a" + LF + "b/.dispatcher.yaml"
    ordinary = "ab/.dispatcher.yaml"

    assert [
        (awkward, first_matching_glob(awkward, FLOOR_GLOBS)),
        (ordinary, first_matching_glob(ordinary, FLOOR_GLOBS)),
    ] == [
        (awkward, "**/.dispatcher.yaml"),
        (ordinary, "**/.dispatcher.yaml"),
    ], (
        "a newline in a parent directory name bought a write to the policy "
        "file; a floor with no override has no excuse for missing one"
    )


def test_the_match_is_anchored_at_the_end_of_the_string_not_at_a_line_break() -> None:
    r"""GREEN TODAY. The trap a `\n`-only fix walks into.

    `_compiled` appends `\Z`, which matches only at the true end of the string.
    `$` matches there too — and ALSO immediately before a string-final newline.
    A fixer reaching for "handle line endings" may well reach for `$`, and then
    `sub/x.py` — a literal ADJUDICATE `disputed_paths:` entry naming one
    artifact — starts granting `sub/x.py\n`, which is a DIFFERENT FILE. That is
    the allowlist widening by one character of whitespace.

    Green now. Green when: still green.
    Falsify (verified): change `_compiled`'s `r"\Z"` to `r"$"` and this row goes
    red on the first two entries while every other seal in this file is
    unaffected.
    """
    declared = "sub/x.py"

    assert [
        first_matching_glob(declared + LF, (declared,)),
        first_matching_glob(declared + CR + LF, (declared,)),
        first_matching_glob(declared, (declared,)),
    ] == [None, None, declared], (
        "an allowlist entry names one artifact; a trailing line feed makes a "
        "different artifact and must not be granted by it"
    )


def test_only_the_line_feed_is_missing_and_the_other_control_characters_hold() -> None:
    r"""The measured character table, written out literally.

    `.` excludes exactly one character. Measured against the built worktree:
    `\r`, `\f`, `\v` and `\t` are matched TODAY; `\n` is not. So three of these
    four rows are green now and exist to stay green — a fix that special-cases
    `\n` (say, by rewriting `.*` as `[^\n]*` plus a newline alternative) can
    easily drop one of the others, and a fix that switches the anchor reopens
    the trailing case sealed above.

    Red now: the `\n` row only.
    Green when: all four, plus the twin.
    Falsify: the ordinary twin is in the same assertion; and narrowing
    `_glob_to_regex`'s `.*` to `[^\r]*` reddens the `\r` row alone, which is
    what makes the three green rows load-bearing rather than decorative.
    """
    ordinary = "tests/ab.py"

    assert [
        ("LF", first_matching_glob("tests/a" + LF + "b.py", ("**/tests/**",))),
        ("CR", first_matching_glob("tests/a" + CR + "b.py", ("**/tests/**",))),
        ("FF", first_matching_glob("tests/a" + FF + "b.py", ("**/tests/**",))),
        ("VT", first_matching_glob("tests/a" + VT + "b.py", ("**/tests/**",))),
        ("--", first_matching_glob(ordinary, ("**/tests/**",))),
    ] == [
        ("LF", "**/tests/**"),
        ("CR", "**/tests/**"),
        ("FF", "**/tests/**"),
        ("VT", "**/tests/**"),
        ("--", "**/tests/**"),
    ], "a control character in a filename does not change which glob covers it"


def test_both_gates_answer_the_same_question_the_same_way() -> None:
    r"""GREEN TODAY. The shared property, sealed without sealing a refactor.

    `role_protocol.first_matching_glob` today delegates to
    `risk.matches_any_glob`, so there is ONE translator and a fix in `risk`
    closes both gates. That is a fact about the current code, not a requirement
    this seal may impose. So what is sealed is the PROPERTY — the two entry
    points give the same answer for the same path — and not the mechanism.

    Amended by P4, 2026-08-09 (prose only; nothing asserted here changes). This
    docstring used to add "`role_protocol.py` is on `FLOOR_GLOBS` and `risk.py`
    is not, which constrains where a fix can live". `risk.py` is on the floor
    now — `tests/test_floor_closure.py` seals the floor's delegation closure,
    and the delegation described in the sentence above is exactly why. The
    constraint on where a fix may live has not disappeared, it has inverted:
    both modules are protected, so a change to either is a reviewed edit on the
    protected base. This seal still asserts only that the two answers agree.

    Probe pairs written out literally; neither module's constants are read to
    generate them.

    Green now. Green when: still green.
    Falsify (verified): give `role_protocol.first_matching_glob` its own
    translator — even `fnmatch.fnmatch`, which disagrees on `**/` matching zero
    directories — and this row reddens on the third pair while the delegating
    implementation passes.
    """
    pairs = [
        ("tests/a" + LF + "b.py", "**/tests/**"),
        ("tests/ab.py", "**/tests/**"),
        ("a" + LF + "b/.dispatcher.yaml", "**/.dispatcher.yaml"),
        (".dispatcher.yaml", "**/.dispatcher.yaml"),
        ("docs/a" + LF + "b.md", "**/docs/**"),
        ("docs/ab.md", "**/docs/**"),
        ("src/a" + LF + "b.py", "**/schema/**"),
    ]
    disagreements = [
        (path, glob)
        for path, glob in pairs
        if (first_matching_glob(path, (glob,)) is not None)
        != risk.matches_any_glob(path, (glob,))
    ]
    assert disagreements == [], (
        "the role gate and the risk gate must not hold two notions of what a "
        "glob covers; invariant 5's failure mode is exactly two matchers that "
        "disagree about one path"
    )


# --------------------------------------------------------------------------- #
# 2. End to end: `check_branch` over a real repository
#
# `checked_paths` is asserted FIRST in every seal here. That is the I1 seals'
# property (the decoded, real name reaches the gate) and it must stay green: a
# fix that dodges the newline by handing the gate git's `"..."` rendering again
# reddens here before it reddens `test_role_protocol_inputs.py`.
# --------------------------------------------------------------------------- #


def test_a_newline_named_seal_is_denied_by_the_glob_that_covers_it(
    git_repo: Path,
) -> None:
    r"""What the brief asked for, and the reason the unit seal above is not
    enough on its own — with a finding attached.

    A BODIES branch whose only new files are `tests/a\nb.py` and its twin is
    already reported VIOLATION today. It is NOT the deny table that catches the
    newline one: `**/tests/**` misses it, and `seal_verify.is_test_path` — the
    delegated backstop, a plain regex containing no `.` and therefore blind to
    nothing — catches it and reports the DELEGATION MARKER as the matched glob.

    That backstop is real and this seal does not disturb it. But it covers only
    the two roles in `TEST_PATH_DELEGATED_ROLES` and only paths that look like
    tests; `test_a_newline_named_file_the_test_backstop_cannot_see_walks_through
    _the_deny_table` below shows what happens one directory over. So this seal
    pins the thing that IS wrong here: `evaluate_changed_paths` documents that
    "globs are tried first so a violation names the specific pattern when there
    is one", and there is one.

    Red now: the newline path's `matched_glob` is
    `"<seal_verify.is_test_path: this repo's test files>"` — the report says the
    glob table missed a file the glob table covers.
    Green when: both violations name `**/tests/**`.
    Falsify: the twin is in the same assertion and already names the glob, so a
    change that only reformats the report still reddens; and `checked_paths`
    reddens a fix that stops decoding.
    """
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / ("a" + LF + "b.py")).write_text("def test_a():\n    pass\n", "utf-8")
    (git_repo / "tests" / "ab.py").write_text("def test_b():\n    pass\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "two seals, one with a newline in its name"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert sorted(paths) == ["tests/a" + LF + "b.py", "tests/ab.py"], (
        "I1's decode must keep working: the gate is handed the real name, not "
        f"git's rendering of it: {paths!r}"
    )
    for path in paths:
        assert file_text_at(git_repo, "feat/x", path) is not None, (
            f"{path!r} came back in a form no blob read can resolve"
        )

    result = check_branch(
        git_repo, "main", "feat/x", Role.BODIES, policy=built_in_policy()
    )
    assert result.verdict is DiffVerdict.VIOLATION
    assert sorted((v.path, v.matched_glob) for v in result.violations) == [
        ("tests/a" + LF + "b.py", "**/tests/**"),
        ("tests/ab.py", "**/tests/**"),
    ], (
        "a seal with a newline in its name is caught only by the test-path "
        "backstop, and the report names the backstop instead of the glob that "
        "covers the file — the glob table missed a path it covers"
    )


def test_a_newline_named_file_the_test_backstop_cannot_see_walks_through_the_deny_table(
    git_repo: Path,
) -> None:
    r"""The same defect one directory over, where nothing catches it.

    `**/schema/**` is denied to BODIES ("the schema is the sole source"), and
    `seal_verify.is_test_path` does not think a `.sql` file under `schema/` is a
    test — correctly. So there is no backstop, and the newline path is simply
    not a violation. The branch is reported VIOLATION only because of its twin;
    commit the newline file alone and the verdict is CLEAN.

    Both facts are asserted: the pair in one call (so the twin proves the
    difference) and the newline file alone on a second branch (so the seal
    reports the consequence that matters — a CLEAN, not a mis-labelled
    violation).

    Red now: the first assertion gets `[('schema/ab.sql', '**/schema/**')]`,
    one entry instead of two; the second gets `DiffVerdict.CLEAN`.
    Green when: both paths are violations naming `**/schema/**`, and the
    newline-only branch is VIOLATION.
    Falsify: the twin in the same call; and the control branch below, which is
    VIOLATION today and must stay so, so a fix cannot pass by refusing
    everything.
    """
    (git_repo / "schema").mkdir()
    (git_repo / "schema" / ("a" + LF + "b.sql")).write_text("CREATE TABLE t();\n", "utf-8")
    (git_repo / "schema" / "ab.sql").write_text("CREATE TABLE u();\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "two schema files, one with a newline"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert sorted(paths) == ["schema/a" + LF + "b.sql", "schema/ab.sql"], (
        f"I1's decode must keep working: {paths!r}"
    )
    assert _bodies_denies("schema/ab.sql"), "control: the ordinary twin is denied"

    result = check_branch(
        git_repo, "main", "feat/x", Role.BODIES, policy=built_in_policy()
    )
    assert sorted((v.path, v.matched_glob) for v in result.violations) == [
        ("schema/a" + LF + "b.sql", "**/schema/**"),
        ("schema/ab.sql", "**/schema/**"),
    ], "a newline in a filename walked a body agent into the schema"

    # And alone, with no twin to redeem the verdict: the branch reports CLEAN.
    _git(["checkout", "-q", "main"], git_repo)
    _git(["checkout", "-q", "-b", "feat/alone"], git_repo)
    (git_repo / "schema").mkdir()
    (git_repo / "schema" / ("c" + LF + "d.sql")).write_text("CREATE TABLE v();\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "one schema file, newline-named"], git_repo)

    alone = check_branch(
        git_repo, "main", "feat/alone", Role.BODIES, policy=built_in_policy()
    )
    assert alone.checked_paths == ("schema/c" + LF + "d.sql",), (
        f"the gate read the branch and saw the file: {alone.checked_paths!r}"
    )
    assert alone.verdict is DiffVerdict.VIOLATION, (
        "a body agent rewrote the schema and the gate said CLEAN; that is the "
        "whole defect, stated as the verdict a human reads"
    )


def test_a_newline_in_a_parent_directory_buys_a_write_to_the_policy_file(
    git_repo: Path,
) -> None:
    r"""The CRITICAL, end to end, against the floor.

    LEGACY is used deliberately, as the existing floor seals do: it is the role
    with the fewest other rules, so a violation here can only have come from the
    floor. The 2026-08-07 ruling extended the floor to LEGACY precisely so it
    could not be escaped by deleting one `role:` line; a newline in a directory
    name escapes it anyway.

    Red now: only `ab/.dispatcher.yaml` is reported, and the newline-only branch
    is CLEAN — a branch rewrote the file that configures every role's
    permissions and the gate certified it.
    Green when: both are floor violations, and the newline-only branch is
    VIOLATION.
    Falsify: the ASCII twin is in the same diff and the same assertion; and the
    `checked_paths` assertion reddens a fix that stops decoding.
    """
    for directory in ("a" + LF + "b", "ab"):
        (git_repo / directory).mkdir()
        (git_repo / directory / ".dispatcher.yaml").write_text("roles: {}\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "rewrite the policy from two directories"], git_repo)

    result = check_branch(
        git_repo, "main", "feat/x", Role.LEGACY, policy=built_in_policy()
    )
    assert sorted(result.checked_paths) == [
        "a" + LF + "b/.dispatcher.yaml",
        "ab/.dispatcher.yaml",
    ], f"the gate was handed a path list it cannot match: {result.checked_paths!r}"
    assert sorted((v.path, v.matched_glob) for v in result.violations) == [
        ("a" + LF + "b/.dispatcher.yaml", "**/.dispatcher.yaml"),
        ("ab/.dispatcher.yaml", "**/.dispatcher.yaml"),
    ], (
        "a newline in a parent directory name bought a write to the policy "
        "file; the floor has no override, so it also has no excuse for missing "
        "one"
    )
    assert result.verdict is DiffVerdict.VIOLATION

    _git(["checkout", "-q", "main"], git_repo)
    _git(["checkout", "-q", "-b", "feat/alone"], git_repo)
    (git_repo / ("c" + LF + "d")).mkdir()
    (git_repo / ("c" + LF + "d") / ".dispatcher.yaml").write_text("roles: {}\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "rewrite the policy from one directory"], git_repo)

    alone = check_branch(
        git_repo, "main", "feat/alone", Role.LEGACY, policy=built_in_policy()
    )
    assert alone.checked_paths == ("c" + LF + "d/.dispatcher.yaml",)
    assert alone.verdict is DiffVerdict.VIOLATION, (
        "the branch rewrote the policy file and the floor certified it CLEAN"
    )


def test_an_ordinary_branch_is_still_clean(git_repo: Path) -> None:
    """The refusal control for every end-to-end seal above.

    A BODIES branch that touches only `src/` is CLEAN today and must stay CLEAN.
    Without this row, a "fix" that reddens the newline cases by reporting every
    path as a violation would turn this whole file green.

    Green now. Green when: still green.
    Falsify: it is the row that a deny-everything fix reddens.
    """
    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text("def f(a: int) -> None:\n    pass\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "ordinary body work"], git_repo)

    result = check_branch(
        git_repo, "main", "feat/x", Role.BODIES, policy=built_in_policy()
    )
    assert result.violations == ()
    assert result.verdict is DiffVerdict.CLEAN


# --------------------------------------------------------------------------- #
# 3. `risk.matches_any_glob` — the half the five-seat panel filed as CRITICAL
# --------------------------------------------------------------------------- #


def test_matches_any_glob_reads_a_newline_named_file_as_being_where_it_is() -> None:
    r"""The panel's literal repro, with its control in the same assertion.

    Red now: `[False, True]`.
    Green when: `[True, True]`.
    Falsify: the twin; and `test_a_glob_that_covers_neither_twin_matches_neither`
    keeps a yes-to-everything matcher out.
    """
    assert [
        risk.matches_any_glob("docs/a" + LF + "b.md", ["**/docs/**"]),
        risk.matches_any_glob("docs/ab.md", ["**/docs/**"]),
    ] == [True, True], (
        "a newline in a filename does not move the file out of `docs/`"
    )


def test_a_newline_named_file_under_a_forbidden_tree_is_still_forbidden() -> None:
    r"""The consequence in the classifier: the low-risk floor.

    `**/auth/**` is a default forbidden path. A change under it must never
    classify low-risk, because a low-risk verdict is what lets a PR skip the
    panel and be self-approved. Both files ride in ONE diff and ONE call, so the
    seal is about the count of reasons: today the classifier finds the ordinary
    twin and reports one reason, having walked straight past the other file.

    Red now: one reason, naming `internal/auth/ab.go` only.
    Green when: two reasons, one per path, each naming `**/auth/**`.
    Falsify: the twin is in the same call and already produces its reason, so a
    change that only reworded the message still reddens; and
    `test_an_ordinary_diff_is_still_low_risk` keeps a fail-everything
    classifier out.
    """
    awkward = "internal/auth/a" + LF + "b.go"
    ordinary = "internal/auth/ab.go"
    verdict = risk.evaluate(
        size_label="XS",
        labels=[],
        changed_files=[
            FileDiff(path=awkward, insertions=1, deletions=0),
            FileDiff(path=ordinary, insertions=1, deletions=0),
        ],
        verified=True,
        verification_iterations=0,
    )
    forbidden_reasons = sorted(
        r for r in verdict.reasons if r.startswith("forbidden path touched:")
    )
    assert forbidden_reasons == [
        f"forbidden path touched: {awkward} (matches **/auth/**)",
        f"forbidden path touched: {ordinary} (matches **/auth/**)",
    ], "a newline in a filename carried a change to auth past the denylist"
    assert verdict.level == ELEVATED


def test_a_newline_named_file_alone_under_a_forbidden_tree_classifies_low(
) -> None:
    r"""The same defect with nothing to redeem it — the verdict a human reads.

    One file, under `**/auth/**`, small, verified first pass. Today: `low`, with
    no reasons at all — the classifier is not merely mis-labelling, it is
    reporting that it checked and found nothing.

    Red now: `('low', ())`.
    Green when: `elevated`, with a reason naming the path.
    Falsify: the control call in the same test, which is `low` today and must
    stay `low`, so a classifier that elevated everything reddens.
    """
    def _classify(path: str):
        return risk.evaluate(
            size_label="XS",
            labels=[],
            changed_files=[FileDiff(path=path, insertions=1, deletions=0)],
            verified=True,
            verification_iterations=0,
        )

    forbidden = _classify("internal/auth/a" + LF + "b.go")
    innocent = _classify("internal/util/a" + LF + "b.go")

    assert (forbidden.level, innocent.level) == (ELEVATED, LOW), (
        "a newline in a filename bought a change to auth a low-risk verdict, "
        "which is what lets a PR skip the panel and self-approve"
    )
    assert any("**/auth/**" in r for r in forbidden.reasons), (
        f"the elevated verdict must say why: {forbidden.reasons!r}"
    )


def test_an_ordinary_diff_is_still_low_risk() -> None:
    """The refusal control for the two classifier seals above.

    Green now. Green when: still green.
    Falsify: it is the row an elevate-everything fix reddens.
    """
    verdict = risk.evaluate(
        size_label="XS",
        labels=[],
        changed_files=[FileDiff(path="internal/util/ab.go", insertions=1, deletions=0)],
        verified=True,
        verification_iterations=0,
    )
    assert (verdict.level, verdict.reasons) == (LOW, ())


def test_the_docs_only_carve_out_is_not_decided_by_a_glob() -> None:
    r"""GREEN TODAY — and a correction to the panel's wording, sealed so it
    stays true.

    The panel's CRITICAL says "docs-only carve-out granted". Measured, the
    carve-out is granted for the newline path AND for its twin, identically:
    `risk._is_doc` is `path.lower().endswith('.md')`, a string test with no
    glob and therefore no newline blindness. So the carve-out is not part of
    this defect — what the panel observed is the `forbidden_paths` miss sealed
    above, which is inside the same verdict.

    That is worth a seal rather than a footnote, because the obvious tidy-up
    during this fix is to express the carve-out as a glob (`**/*.md`) for
    consistency with the rest of the module — which, before the matcher is
    fixed, would MOVE the hole into the carve-out and make a newline-named
    `.md` file stop being a doc.

    Green now. Green when: still green.
    Falsify (verified): make `_is_doc` glob-based against the unfixed matcher,
    or add `and "\n" not in path`, and the first entry reddens.
    """
    assert [
        risk._is_doc("docs/a" + LF + "b.md"),
        risk._is_doc("docs/ab.md"),
        risk._is_doc("docs/ab.go"),
    ] == [True, True, False]

    # And the same statement at the verdict level: an all-Markdown diff is
    # low-risk at any size whether or not a name carries a newline.
    def _docs_only(path: str):
        return risk.evaluate(
            size_label="XL",
            labels=[],
            changed_files=[FileDiff(path=path, insertions=9999, deletions=0)],
            verified=False,
            verification_iterations=3,
            config=RiskConfig(),
        )

    assert (
        _docs_only("docs/a" + LF + "b.md").level,
        _docs_only("docs/ab.md").level,
    ) == (LOW, LOW)


def test_a_newline_named_test_file_is_still_excluded_from_the_effective_diff(
) -> None:
    r"""The same blindness in the direction that is SAFE, sealed for
    correctness rather than for exposure.

    `test_globs` shrinks the counted diff. A newline-named test file is not
    recognised, so its churn is COUNTED — which pushes a change toward
    `elevated`, not away from it. Nobody is exploited by this; it is a false
    refusal, and the unit that owns false refusals in this repo has ruled twice
    that they are defects too.

    Recorded plainly so the fixer does not read this row as a second CRITICAL.

    Red now: `[500, 0]` — the newline-named file's 500 lines are counted and
    its twin's are not.
    Green when: `[0, 0]`.
    Falsify: the twin is in the same assertion, so a matcher that excluded
    nothing reddens on the second entry.
    """
    def _count(path: str) -> int:
        return risk.effective_diff_lines(
            [FileDiff(path=path, insertions=500, deletions=0)], RiskConfig()
        )

    assert [_count("tests/a" + LF + "b.py"), _count("tests/ab.py")] == [0, 0], (
        "`tests/**` excludes a file under `tests/` whatever its name contains"
    )


# --------------------------------------------------------------------------- #
# 4. `blast_radius` — the sibling surface the panel named at line 11
#
# ESTABLISHED BY MEASUREMENT, and the finding is mixed:
#
#   * `_EXCLUDE_REF` is NOT newline-blind. Its pattern contains no `.`
#     metacharacter, so `/tests?/` matches `/tests/a\nb.py` exactly as it
#     matches `/tests/ab.py`. Nothing to seal.
#   * `changed_files` IS blind, and by BOTH mechanisms at once: its `.+?`/`.+`
#     stop at a newline, and — this is the panel's actual point at line 11,
#     which claims the module mirrors `cross_family_reviewer.collect_diff` —
#     neither that function nor this one carries `-c core.quotePath=false` or
#     undoes C-quoting, so the header git really emits for such a file,
#     `diff --git "a/tests/a\nb.py" "b/tests/a\nb.py"`, does not even begin with
#     the literal `a/` the pattern requires. Measured: `changed_files` returns
#     `[]` for that header and `['tests/ab.py']` for the plain one.
#
# WHAT THIS IS NOT: a gate. `blast_radius` is fail-open prompt enrichment
# ("an empty artifact never blocks a review"), so the consequence is a reviewer
# prompt that lists the diff's own file as an unexamined sibling surface, not a
# write anybody was not entitled to. It is sealed because it is the same
# property and it is cheap, and it is flagged here so the fixer sequences it
# behind the two gates.
# --------------------------------------------------------------------------- #


def test_the_blast_radius_reads_a_quoted_diff_header_as_the_path_it_names() -> None:
    r"""One diff, two files, one of them with a newline in its name.

    Red now: `['tests/ab.py']` — the quoted header is not recognised at all, so
    the file is missing from `in_diff` and can be reported back to the panel as
    a sibling surface the diff did not touch.
    Green when: both paths, in header order, decoded.
    Falsify: the ordinary header is in the same string and the same assertion.
    """
    diff = (
        'diff --git "a/tests/a\\nb.py" "b/tests/a\\nb.py"\n'
        "--- /dev/null\n"
        '+++ "b/tests/a\\nb.py"\n'
        "@@ -0,0 +1 @@\n"
        "+def test_a():\n"
        "diff --git a/tests/ab.py b/tests/ab.py\n"
        "--- /dev/null\n"
        "+++ b/tests/ab.py\n"
        "@@ -0,0 +1 @@\n"
        "+def test_b():\n"
    )
    assert blast_radius.changed_files(diff) == [
        "tests/a" + LF + "b.py",
        "tests/ab.py",
    ], (
        "git C-quotes a path containing a control character whatever "
        "core.quotePath says; a rendering is not a path"
    )


def test_the_blast_radius_exclusion_is_already_newline_transparent() -> None:
    r"""GREEN TODAY, recorded as measurement rather than assumed.

    `_EXCLUDE_REF` decides which referencing files are review-relevant. It
    contains no `.` metacharacter, so it is blind to nothing, and a newline
    changes neither answer.

    Green now. Green when: still green.
    Falsify (verified): rewrite one alternative as `/tests./` — a `.` where a
    literal belongs — and the first entry reddens.
    """
    def _excluded(path: str) -> bool:
        return bool(blast_radius._EXCLUDE_REF.search("/" + path))

    assert [
        _excluded("tests/a" + LF + "b.py"),
        _excluded("tests/ab.py"),
        _excluded("a" + LF + "b/src/x.go"),
        _excluded("ab/src/x.go"),
    ] == [True, True, False, False]


def test_the_compiled_glob_is_not_line_oriented() -> None:
    r"""The mechanism, stated once so a fix cannot satisfy the behaviour seals
    by a special case that leaves the engine line-oriented.

    Two properties, neither of them a particular implementation: a compiled
    pattern must not treat a line feed as a boundary, and it must not be
    `re.MULTILINE` (which would make `^`/`$` fire at every line break — the
    other half of the same mistake).

    Red now: `_compiled('**/tests/**')` does not match a newline-bearing path.
    Green when: it does, and MULTILINE is still off.
    Falsify: the ordinary twin, and the MULTILINE assertion, which is green
    today and reddens the "just add re.MULTILINE" reflex.
    """
    compiled = risk._compiled("**/tests/**")
    assert not compiled.flags & re.MULTILINE, (
        "MULTILINE makes every line break an anchor point; the fix wanted is "
        "the opposite — a path is one string, not a document"
    )
    assert [
        bool(compiled.match("tests/a" + LF + "b.py")),
        bool(compiled.match("tests/ab.py")),
    ] == [True, True]
