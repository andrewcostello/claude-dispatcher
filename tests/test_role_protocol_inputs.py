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

and one finding that is I5's own shadow, ruled by P4 on 2026-08-09 and sealed in
the I6 section at the foot of this file:

  I6  after I5, a BODIES diff containing no Python at all is UNDETERMINED
      forever — a false refusal with no override, on most of the operator's
      real work. Ruled CLEAN, in a NEW named state, and required to say which
      paths it could not read and that the reason is language support.

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
turning these seals green against a throwaway implementation in a clone, and
both RULED by P4 on 2026-08-08. The rulings are recorded here rather than in a
document because the next panel reads the seals, not the docket:

  1. I4 cannot be fixed without a THIRD git read. The merge-base the three-dot
     diff measured from is not derivable from any command this module already
     runs, and `_run_stub` in `test_role_protocol_diff.py` and
     `test_role_protocol_floor.py` raises `AssertionError: unscripted git
     command` on anything but a diff and a blob spec — so adding
     `git merge-base` reddens existing BODIES rows in files a BODIES agent may
     not edit.

     GRANTED (P4, 2026-08-08). Both stubs now answer `merge-base` with the base
     ref and nothing else. Verified rather than accepted:

       * The count in this docstring was ten; it is not a constant. A throwaway
         fix that reads the merge-base once at the top of
         `_compare_branch_signatures` reddens 14 rows (12 in
         `test_role_protocol_diff.py`, 2 in `test_role_protocol_floor.py`); one
         that reads it lazily, only when a `.py` path is actually about to be
         compared, reddens 7 of those same 14. The remedy is one stub row
         either way.
       * Not one assertion in those 14 rows was touched. The whole change is
         confined to the two `_run_stub` bodies and their docstrings.
       * The strictness those fixtures are worth survives. With the module made
         to run `git rev-parse` — a command the extended stubs do NOT answer —
         the identical 14 rows go red again, and both stubs still raise on
         `rev-parse`, `rev-list` and `log`. The extension buys exactly one
         command.
       * The answer is not a rubber stamp. `merge-base` is answered with the
         base ref explicitly, not by echoing whichever argument follows it, so
         a call spelled with a flag or with the refs reversed cannot be
         satisfied by accident; a `merge-base` between refs the stub does not
         model raises like any other unscripted read; and answering it with a
         ref that is NOT the base reddens the two rows that consume the
         resulting blob, so the answer is load-bearing.
       * `rev-parse` was deliberately NOT added, though the stub in THIS file
         answers it. I3 is satisfiable without it — re-reading the diff and
         comparing is one of the shapes its seal permits — so a row for it
         would be pre-authorising a fix shape the I3 seal deliberately leaves
         open. If the I3 fixer needs it, that is a fresh ruling, not this one.

  2. I5's "examined nothing" has a boundary an existing seal already fixes.
     `test_the_ci_script_delegates_instead_of_reporting_not_implemented` runs a
     BODIES branch whose only changed path is a NEWLY ADDED `src/app.py` and
     requires CLEAN with exit 0 — a comparison that also examined zero files.

     RULED (P4, 2026-08-08): the new-file case KEEPS reporting `checked`, and
     the seal author was right not to touch it. It is not the same lie in a
     nicer hat, for three reasons:

       * I5's complaint is that the aggregate CONTRADICTS the per-file
         contract. `compare_signatures('cmd/x/main.go', ...)` returns
         UNCHECKED_UNSUPPORTED_LANGUAGE and `compare_signatures(
         'docs/notes.md', ...)` returns it too, and yet
         `_compare_branch_signatures` `continue`s past both before that state
         can be produced and reports CHECKED. For a new file the aggregate
         AGREES with the per-file contract: `compare_signatures('src/app.py',
         None, text)` returns CHECKED, by a clause the 2026-08-04 P2 ruling
         wrote deliberately — the same ruling that carved out the genuinely
         vacuous both-texts-None case as a RAISE. The line has been drawn here
         once already, on the same reasoning.
       * They differ in what the gate knows. For a new file the gate MADE a
         determination: it read the base tree and established that the file is
         absent from it, and `file_text_at` guarantees None means "not in that
         tree" and nothing else, because a read error raises. "There was no
         scaffolded signature to preserve, so none was broken" is knowledge.
         For the skipped Go file the gate established nothing: a Go parameter
         list could have been widened under it and it would never know.
         CHECKED means "`changes` is authoritative" — which is true of the
         new-file case and false of the skipped one.
       * The cost of ruling the other way is a false refusal. `check_branch`
         maps every UNCHECKED_* status to UNDETERMINED on BODIES, so a body
         branch whose Python work is all in new files would become permanently
         UNDETERMINED — never CLEAN, and non-zero out of the CI face — for work
         that could not have violated anything. A floor has no override and
         neither does this; that is the 2026-08-07 harm, bought for no
         knowledge.

     So the boundary is now SEALED rather than left live, in
     `test_a_new_file_with_no_base_signature_is_still_a_real_check` below: the
     I5 fixer may not satisfy I5 by turning zero-comparisons-ran into a
     non-CHECKED state wholesale.

TWO PANEL DISPUTES RULED BY P4 (2026-08-08), recorded where the next panel will
read them rather than in a docket:

  * "the frozen signature check ignores default values" — OVERTURNED. The
    disposition and the evidence are in the docstring of
    `test_honest_body_work_is_not_a_signature_change` in
    `test_role_protocol_diff.py`, which is the live row the finding would have
    required deleting.
  * which rule owns `**/*.*` and `*.yaml` — SPLIT. See the note above
    `_WILDCARD_ESCAPES` below.
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
    compare_signatures,
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

#: P4 (2026-08-08) — WHICH RULE OWNS `**/*.*` AND `*.yaml`. Both are refused
#: today, but by the FLOOR's plan-time name check (`_floor_glob_named_by`):
#: their basenames pattern-match `.dispatcher.yaml`, so both are refused with
#: the floor's message. The seal author left both out of this list and asked
#: whether the wildcard rule should own them. Ruled, and the two go different
#: ways — established by execution against `first_matching_glob`, over the same
#: seven-path probe set the section header above uses:
#:
#:   `**/*.*` matches 7/7. It is the whole repo and it names nothing, which is
#:   this list's own criterion, and its refusal today is an ACCIDENT of what
#:   `FLOOR_GLOBS` happens to contain — it is caught only because
#:   `.dispatcher.yaml` has a dot in it. Rename the floor glob and `**/*.*`
#:   sails through. That coupling is exactly what "open set" means here, so the
#:   wildcard rule must own it. It is added to
#:   `test_check_branch_does_not_bless_a_wildcard_adjudication` below, and NOT
#:   to this list: at plan time the floor already refuses it with a message
#:   naming both the task and the entry, so a row here would be green today for
#:   a reason unrelated to what it claims to seal, which is a vacuous seal.
#:   `check_branch` takes its `TaskRoleSpec` directly and never consults the
#:   plan-time floor check, so the row there is red today for the right reason.
#:
#:   `*.yaml` matches 2/7 — the two config files, no source, no tests, no docs.
#:   The wildcard rule must NOT own it. `*` crosses `/` in this repo's glob
#:   engine (`risk._glob_to_regex`), so `*.yaml` is "every YAML file", a real
#:   and bounded class of artifacts; it is the same shape as `docs/*.md`, which
#:   this file's upper bound deliberately ALLOWS. Refusing it from here means
#:   refusing extension-only declarations, and `*.md` and `**/*.md` — every
#:   markdown file, in a repo whose docs live both under `docs/` and at the
#:   root — parse today and would stop. A floor has no override, so that is the
#:   2026-08-07 harm exactly. Its refusal today is CORRECT and is the floor's
#:   business, on the floor's own grounds: `*.yaml` does name `.dispatcher.yaml`
#:   and "this declaration names the floor file" is the true and useful reason.
#:   Two independent rules refusing for two different reasons is the design; one
#:   rule refusing for the other's reason is not.
#:
#: Existence proof that both edges are still satisfiable together, offered so
#: the next fixer knows this docket is not over-constrained, and NOT a mandate —
#: these seals pin edges, not a rule: "the declaration must contain at least one
#: literal alphanumeric character outside its wildcards" refuses all six rows
#: below plus `**/*.*` plus all six literals in `FORBIDDEN_DISPUTED_GLOBS`, and
#: allows every row in `_NAMED_ARTIFACTS` plus `*.md`, `*.yaml` and
#: `**/conftest.py`.
#:
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


@pytest.mark.parametrize("declaration", ["**", "**/**", "**/*.*"])
def test_check_branch_does_not_bless_a_wildcard_adjudication(
    declaration: str,
) -> None:
    """The consequence, at the one entrypoint all three callers share: an
    adjudicate branch that rewrote the role-protocol module itself and a seal,
    under a declaration that named neither, must not be told it is CLEAN.

    All three spellings are here on purpose, and they fail for three different
    reasons — which is why they are three rows and not one. `**` is in the
    denylist and still gets through, because the denylist is only ever consulted
    at plan time. `**/**` is not in the denylist at all. `**/*.*` (added by P4,
    2026-08-08, ruling dispute 2 — see the note above `_WILDCARD_ESCAPES`) is
    not in the denylist either, and is refused at plan time only by accident:
    the floor's name check catches it because `.dispatcher.yaml` has a dot in
    it. Here, where the `TaskRoleSpec` is constructed directly and the plan-time
    floor check never runs, nothing catches it at all. One fix must close all
    three.

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
    """A BODIES branch that changed a SQL migration and a Python file. The SQL
    file's signatures were not compared by anything — this module cannot compare
    them, and nothing here ever will — yet the result says
    `signatures: checked`, which is the one thing the enum member for this exact
    situation exists to prevent.

    Red now (verified against the built worktree): `status=CHECKED`, and
    `detail` ends `signatures: checked`, for a diff in which one of the two
    changed source files was never opened.
    Green when: the reported status is not CHECKED. Which named state it is —
    the existing `UNCHECKED_UNSUPPORTED_LANGUAGE`, or a new member — is the
    fixer's choice and is not pinned here.
    Falsify: the control below is the same call with the unreadable file removed
    and requires CHECKED, so this cannot be satisfied by never reporting
    CHECKED.

    RE-LANGUAGED by P4 on 2026-08-10, ahead of Go enrolment, and by P4 only.
    The unreadable file was `cmd/x/main.go`. Enrolling `GO_SUPPORT` makes this
    diff fully readable, the mixed row reports CHECKED, and this seal reddens on
    behaviour that is CORRECT — the false alarm the standing convention in the
    I6 header below exists to prevent. `.sql` has no plausible signature
    comparator in this codebase, so the row survives this enrolment and the
    next. This is the eighth seal, the one an earlier checklist undercounted.
    Nothing was relaxed: both halves of the diff, the control, and every
    assertion are unchanged.
    """
    blobs = {"main:src/app.py": _STUB_PY, "feat/x:src/app.py": _STUB_PY}

    mixed = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(["src/app.py", "db/migrate/001_bay.sql"], blobs),
    )
    assert mixed.signature is not None
    assert mixed.signature.status is not SignatureCheckStatus.CHECKED, (
        "db/migrate/001_bay.sql was skipped and the result still claims the "
        f"signatures were checked: {mixed.detail}"
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


def test_a_new_file_with_no_base_signature_is_still_a_real_check() -> None:
    """P4 (2026-08-08). The boundary the two rows above stop at, sealed rather
    than left live — the ruling and its reasoning are in this module's
    docstring, item 2.

    A BODIES branch whose only changed path is a NEWLY ADDED `src/app.py` also
    runs zero comparisons: `_compare_branch_signatures` reads the base tree,
    finds the file absent, and skips it. That is NOT the state the two rows
    above forbid, and it must keep reporting CHECKED and CLEAN. The gate made a
    determination here — the file did not exist at base, so it had no scaffolded
    signature to preserve and none was broken — which is what `compare_signatures`
    answers for this exact input and what CHECKED ("`changes` is authoritative")
    means. The skipped Go file and the Python-free diff above are ignorance
    wearing the same word.

    Green now, and it must STAY green. This is the twin of the two rows above,
    and the pair is what makes either non-vacuous: they forbid a fix that always
    reports CHECKED, and this forbids the wholesale fix that stops reporting
    CHECKED whenever zero files were compared. Falsify: make
    `_compare_branch_signatures` report a non-CHECKED status when it opened no
    file — this goes red, and so does
    `test_the_ci_script_delegates_instead_of_reporting_not_implemented`, whose
    branch is this same fixture end to end and which requires exit 0. That
    second casualty is the cost of the other ruling, made visible: a body branch
    whose Python work is all new files would be permanently UNDETERMINED, since
    `check_branch` maps every unchecked status to UNDETERMINED on BODIES.
    """
    run = _run_stub(["src/app.py"], {"feat/x:src/app.py": _STUB_PY})

    # Fixture check: the base really does not hold the file, so this really is
    # the zero-comparisons case and not an accidental comparison of two texts.
    assert file_text_at("/x", "main", "src/app.py", run=run) is None, (
        "the fixture must model a file absent at base, or this seals nothing"
    )

    added = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(), run=run
    )
    assert added.signature is not None
    assert added.signature.status is SignatureCheckStatus.CHECKED, (
        "a file that did not exist at base has no scaffolded signature to "
        "preserve; reporting that as unchecked turns every body branch that "
        f"adds a module into UNDETERMINED: {added.detail}"
    )
    assert added.signature.changes == ()
    assert added.verdict is DiffVerdict.CLEAN, added.detail


# --------------------------------------------------------------------------- #
# I6 — a diff this gate cannot READ is a false refusal, not an unchecked pass
#
# P4 ruling, 2026-08-09 (operator). After I5 a changed non-`.py` file sets
# UNCHECKED_UNSUPPORTED_LANGUAGE, and `check_branch` maps every unchecked status
# to UNDETERMINED on BODIES. So a BODIES branch that changed only
# `docs/adr/0007.md`, or only `scripts/some_other_helper.sh`, or only
# `cmd/x/main.go`, is UNDETERMINED **forever**. Nothing the branch can do makes
# it CLEAN, the CI face never returns 0, and there is no override — the same
# harm the 2026-08-08 ruling used to keep the new-file case out of I5's scope
# ("a body branch whose Python work is all new files could never be CLEAN"), in
# a case that ruling did not consider.
#
# RULED: the verdict is CLEAN. **It must not be silently CLEAN.**
#
# Why the loudness is the substance of this ruling and not decoration. The
# signature gate is Python-only — a recorded limitation from 2026-08-04, "a
# widened Go signature on a bodies branch passes" — and this repository's
# operator writes Go and TypeScript. So for most real work the ruling means the
# signature half of the protocol returns CLEAN having opened no file at all.
# Turning a loud-but-wrong UNDETERMINED into a quiet-and-wrong CLEAN would be a
# downgrade, so the verdict is only half of what is sealed here: the other half
# is that the result NAMES the paths it could not read and says the reason is
# language support.
#
# THE STATE NAME. Ruled: a NEW `SignatureCheckStatus` member,
# `UNCHECKED_NO_SUPPORTED_FILE` (value `"unchecked_no_supported_file"`), and
# NOT a reuse of `NOT_APPLICABLE`. Adding a member reddens
# `test_every_signature_check_status_is_reachable`, which pins the enum by
# value-set equality; that seal is amended in `test_role_protocol_diff.py` in
# the same commit, by P4, which is the only role that may. The justification,
# because "add a member" is the lazy answer and had to be argued for:
#
#   * the ruled verdict DIFFERS between a Go-only diff (CLEAN) and a
#     Go-plus-Python diff (still UNDETERMINED — see rule 4 below). Both are
#     UNCHECKED_UNSUPPORTED_LANGUAGE today. `check_branch` decides the verdict
#     from the status, so with one status it would have to re-derive the
#     distinction from the path list — i.e. spell `path.endswith(".py")` a
#     second time, outside the function that owns that rule. Two copies of
#     "which languages can this gate read" is precisely the drift this unit
#     exists to remove, and the day a Go comparator lands, the copy that is not
#     updated fails towards a silent CLEAN.
#
#     P4, 2026-08-09: the PREMISE of this bullet has been overruled — under the
#     per-file ruling both diffs are CLEAN, so the verdicts no longer differ.
#     The conclusion survives, on stronger ground: with the verdict unable to
#     tell "read nothing" from "read some", the STATUS is now the ONLY place
#     that distinction can live, and collapsing the two would leave the gate
#     with no way to report which it did. Re-pinned independently in
#     `test_role_protocol_perfile.py`
#     ::test_read_nothing_read_some_and_no_duty_stay_three_states. The
#     one-copy-of-the-language-rule argument is untouched and is why
#     `_supported_language_refusal` is the single dispatch point.
#   * reusing NOT_APPLICABLE would give the right verdict for the wrong reason.
#     NOT_APPLICABLE is a fact about the ROLE — "this role has no
#     scaffolded-signature obligation", true of every role but BODIES. The new
#     state is a fact about the LANGUAGE — "this role has the obligation and
#     this gate cannot discharge it". They diverge the moment a Go comparator
#     exists: the role fact survives, the language fact disappears. Collapsing
#     them would also make every consumer that reads `not_applicable` as "no
#     duty here" start reading it over BODIES branches, which is exactly the
#     conflation the operator forbade.
#   * the `UNCHECKED_` prefix is deliberate even though the verdict is CLEAN.
#     The comparison genuinely did not run. The ruling is about what the
#     VERDICT is worth, not about pretending the check happened, and a name
#     that hid the non-check would reintroduce the I5 lie one level up.
#
# WHAT THE FIXER STILL OWNS. `_UNCHECKED_SIGNATURE_STATUSES` means "the
# comparison did not run" and the new member is one of those, so it belongs in
# that set and the BODIES verdict mapping needs a second, separately named
# notion — "which unchecked states block a pass". Nothing below pins that
# private shape; it is named here so the fix is not forced to lie in its own
# constant to satisfy a seal.
#
# NOT SEALED, deliberately: which status `_compare_branch_signatures` gives an
# EMPTY path list. `check_branch` refuses an empty diff at step 3, so no public
# call can reach it, and a seal on a state no entrypoint can produce is a seal
# on a private implementation detail. The reasoning, for the fixer: an empty
# diff has no unsupported path to NAME, so it is not this state; keeping it
# UNCHECKED_UNSUPPORTED_LANGUAGE fails closed if it ever becomes reachable.
#
# THE BOUNDARY THIS RULING STOPPED AT — **AND HOW IT WAS CLOSED.** This section
# ruled only the diff with NO supported file, and left the diff with one `.go`
# and one `.py` refused, calling it "a question for a fresh ruling (a per-file
# verdict, or a Go comparator), not something to be settled by widening this
# one".
#
# That fresh ruling arrived the same day. **Operator, 2026-08-09: the verdict is
# PER FILE.** Each changed path is judged by whether its language is supported;
# supported files are compared and their changes decide the verdict; unsupported
# files are named and do not block. The ruling, the argument for it (every
# comparator added later is then a MONOTONIC improvement — enrolling a language
# can turn a CLEAN into a VIOLATION for a real finding but can never newly block
# a class of branch) and its seals are in `tests/test_role_protocol_perfile.py`.
#
# So the paragraph that used to stand here argued a position that has been
# overruled, and `test_the_paths_named_unread_are_the_skipped_ones_not_the_whole_diff`
# below — whose verdict assertion was this section's rule 4 in force — is
# AMENDED to CLEAN by P4, 2026-08-09. Measured before amending, by turning the
# per-file rows green against a throwaway reference implementation in a clone
# and running the whole suite: that one assertion is the ONLY thing in the suite
# that contradicts the per-file ruling. Nothing else in this section moves —
# UNCHECKED_NO_SUPPORTED_FILE keeps its own state and its own argument, and the
# naming discipline this section created is what the per-file ruling now rests
# its whole weight on.
#
# The measurement this section made of what it was leaving open still stands and
# is what the per-file ruling acted on: `compare_signatures` dispatches on
# `path.endswith(".py")` and on nothing else, and `_scaffolded_signatures` is
# built on `ast`, so the signature half of this protocol is 0% implemented for
# Go and TypeScript — a widened Go signature on a bodies branch passes, exactly
# as recorded on 2026-08-04, and this ruling does not change that. What it
# changes is that the branch is no longer refused for it, and that the report
# now says which files nobody read.
#
# HOW THE RESULT NAMES WHAT IT COULD NOT READ. `SignatureComparison` grows
# `unsupported_paths: tuple[str, ...] = ()` — the changed paths this gate has no
# comparator for, in diff order. A field and not only prose, because prose is
# the claim and the field is the mechanism, and because for a wholly-unsupported
# diff every path is unsupported, so a prose seal there is satisfied equally by
# an honest report and by dumping the path list. The field is sealed on the
# MIXED diff too, where those two answers differ — that is the row that makes
# the naming non-vacuous. An unparseable `*.py` is NOT in it: that file was
# opened and read, the gate failed on it rather than skipping it, and its reason
# is not language support.
#
# FOR WHOEVER LANDS THE FIRST GO COMPARATOR — P4, 2026-08-09, and a standing
# convention for this unit, ENDORSED after re-measuring it.
#
# A seal that probes "a language this gate cannot read" with a `.go` file is a
# seal that reddens the day Go becomes readable, on behaviour that is CORRECT.
# That is a false alarm, and a suite that cries wolf at the first comparator is
# a suite whose assertions get deleted by the person landing the comparator —
# which is how a real seal dies. THE CONVENTION: a seal about unreadability
# must probe with a language that will still be unreadable when the comparator
# lands. `.sql` (781 files) and `.java` (316) have no plausible signature
# comparator in this codebase — there is no scaffolded-stub discipline in a
# migration or a POJO to preserve — and a `.md` file has no signatures at all.
# `.go` (2,288) and `.ts` (996) are the obvious first enrolments and are the
# wrong probe. `tests/test_role_protocol_perfile.py` was written to this
# convention and it works: with a stub Go comparator enrolled, ZERO of its nine
# rows redden.
#
# The existing Go-probing seals are the debt. MEASURED (2026-08-09, throwaway
# clone carrying the per-file ruling and a stub Go comparator that moves `.go`
# from unsupported to supported and finds nothing) — EIGHT redden, not the seven
# an earlier scaffold reported.
#
# **DISCHARGED by P4 on 2026-08-10, and the count was wrong a fourth time: it is
# NINE.** Re-measured the only way that settles it — `GO_SUPPORT` moved from
# `PENDING_COMPARATORS` into `COMPARATORS` in a `cp -a` clone of the IMPLEMENTED
# tree, `__pycache__` cleared, whole suite run. The ninth is
# `tests/test_go_comparator.py::test_go_is_still_not_enrolled`, which did not
# exist when the list above was written: it is not a stale-probe seal at all but
# a deliberate tripwire asserting the row is UNENROLLED, and it is re-languaged
# in the only sense available to it — see the note at its replacement,
# `test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees`.
#
# Every one of the nine is re-languaged, none deleted. Where they are now:
#
#   test_role_protocol_diff.py
#     ::test_an_unchecked_comparison_is_named_never_reported_as_unchanged
#       [the `cmd/classify/main.go` row -> `db/migrate/001_bay.sql`; the
#        `web/app.ts` row, which survived Go enrolment, -> `svc/Handler.java`
#        so that it survives the next one too]
#     ::test_every_signature_check_status_is_reachable
#       [both Go PRODUCERS -> `db/migrate/001_bay.sql`; the faulting-row probe
#        stays `.go` on purpose, see its note]
#   test_role_protocol_inputs.py
#     ::test_a_skipped_non_python_file_is_not_reported_as_a_checked_signature
#     ::test_a_bodies_diff_this_gate_cannot_read_is_clean_and_names_what_it_missed
#     ::test_cannot_read_this_language_and_no_duty_here_stay_two_different_states
#     ::test_the_paths_named_unread_are_the_skipped_ones_not_the_whole_diff
#     ::test_the_per_file_comparator_names_the_file_it_could_not_read
#     ::test_the_ci_face_clears_a_wholly_unreadable_branch_and_names_the_file_it_could_not_read
#       [RENAMED from ...clears_a_go_only_branch...; the name carried the probe]
#   test_go_comparator.py
#     ::test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees
#       [RENAMED from test_go_is_still_not_enrolled]
#
# NONE of them contradicts the per-file ruling — they pin a language as
# unreadable, which that ruling does not change — so the amendment is the probe
# and the prose, never an assertion. **They are re-languaged, not deleted.**
# `test_every_signature_check_status_is_reachable` is the one to read first: it
# pins the enum by VALUE-SET EQUALITY and produces its members by CALL, and two
# of those producing calls were Go. Delete the Go probes there and
# UNCHECKED_UNSUPPORTED_LANGUAGE and UNCHECKED_NO_SUPPORTED_FILE stop being
# producible, `produced == set(SignatureCheckStatus)` reddens, and the closed-set
# seal is gone. Swapped to `.sql`, the row is untouched by every future
# enrolment.
#
# TWO SEALS ARE NOT IN THIS CLASS AND WERE NOT AMENDED:
# `tests/test_role_protocol_provenance.py::test_no_role_gets_a_clean_verdict_for_editing_the_gate`
# and `::test_the_gate_is_refused_under_the_policy_the_gate_actually_runs_with`,
# whose probes include the Go helper's own path since it joined `FLOOR_GLOBS`.
# They reddened on enrolment only while `GoSignatureFingerprinter` was
# unimplemented and `check_branch` raised `NotImplementedError`. Re-measured
# 2026-08-10 on the implemented tree with the row enrolled: both GREEN. They
# need no amendment and must not be given one.
# --------------------------------------------------------------------------- #


def test_a_bodies_diff_this_gate_cannot_read_is_clean_and_names_what_it_missed(
) -> None:
    """The ruling, stated at `check_branch`: a BODIES diff with no Python in it
    is CLEAN, in a named state that is neither CHECKED nor NOT_APPLICABLE, and
    the result says which paths went unread and why.

    The three probes are the operator's real tree: a migration, a Java file and
    a document. Under today's code all three are
    UNCHECKED_UNSUPPORTED_LANGUAGE, which `check_branch` maps to UNDETERMINED on
    BODIES with no way out.

    RE-LANGUAGED by P4 on 2026-08-10, ahead of Go enrolment, and by P4 only.
    The trio was `["cmd/x/main.go", "web/app.ts", "docs/adr/0007.md"]`.
    Enrolling `GO_SUPPORT` makes the Go file readable, so the diff stops being
    wholly-unreadable, the status stops being UNCHECKED_NO_SUPPORTED_FILE and
    `unsupported_paths` stops being the whole list — three assertions redden on
    behaviour that is CORRECT. `.ts` went with it because TypeScript (996
    files) is the other obvious next enrolment. `.sql` (781) and `.java` (316)
    have no plausible signature comparator in this codebase and a `.md` file
    has no signatures at all, so the trio survives this enrolment and the next.
    It is now the same trio `tests/test_role_protocol_perfile.py` uses, which
    was written to this convention from the start. Nothing was relaxed: three
    paths still, the tuple equality is still an equality in diff order, and
    every naming assertion still runs over all three.

    Red now (measured against the built worktree, 2026-08-09):
    `AttributeError: UNCHECKED_NO_SUPPORTED_FILE` — the member does not exist;
    and with the status assertion removed, `verdict=UNDETERMINED`.
    Green when: the verdict is CLEAN, the status is the new member, and both
    the comparison and the top-level result name all three paths.
    Falsify: map the new state to CLEAN without populating
    `unsupported_paths` — the naming assertions go red while the verdict one
    stays green, which is the quiet-and-wrong CLEAN this ruling exists to
    prevent. Delete the `.java` row from whatever produces the list — the
    equality goes red rather than the seal shrinking.
    """
    unreadable = [
        "db/migrate/001_bay.sql",
        "svc/Handler.java",
        "docs/adr/0007.md",
    ]
    result = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(unreadable),
    )

    assert result.signature is not None
    assert result.signature.status is (
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
    ), (
        "a diff this gate has no comparator for is its own state: not CHECKED "
        "(nothing was compared), not NOT_APPLICABLE (bodies HAS the "
        f"obligation), and not a permanent refusal: {result.signature.status}"
    )
    assert result.verdict is DiffVerdict.CLEAN, (
        "a bodies branch that changed only files this gate cannot read was "
        f"refused with no override available: {result.detail}"
    )
    assert result.violations == ()

    # ...and it is not SILENTLY clean. Both halves of the report name every
    # path that went unread, and say the reason is language support.
    assert result.signature.unsupported_paths == tuple(unreadable), (
        "the CLEAN verdict does not say which paths it could not read; a "
        "claim without the mechanism is what this unit exists to remove"
    )
    for path in unreadable:
        assert path in result.signature.detail, path
        assert path in result.detail, (
            f"{path} went unexamined and the verdict's own detail — the line "
            f"`_print_report` puts on stdout — does not mention it: "
            f"{result.detail}"
        )
    assert "signatures: checked" not in result.detail, result.detail
    assert result.signature.status.value in result.detail, (
        "the report must carry the state it is reporting, or a reader cannot "
        f"tell a real check from an unread one: {result.detail}"
    )


def test_cannot_read_this_language_and_no_duty_here_stay_two_different_states(
) -> None:
    """`NOT_APPLICABLE` and the new state are not interchangeable, sealed on the
    one input where a fix would be tempted to merge them: the SAME unreadable
    diff, judged once as BODIES and once as SCAFFOLD.

    SCAFFOLD has no scaffolded-signature obligation at all, so its answer is
    NOT_APPLICABLE and stays so. BODIES has the obligation and could not
    discharge it, which is a different fact and must have a different name — the
    operator's rule 1. Both are CLEAN, so the VERDICT cannot distinguish them
    and the status is the only place the difference can live.

    Red now: the new member does not exist.
    Green when: the two statuses differ and each is the right one.
    Falsify: implement the ruling by returning NOT_APPLICABLE for an unreadable
    BODIES diff — the inequality and the BODIES row both go red.

    RE-LANGUAGED by P4 on 2026-08-10, ahead of Go enrolment, and by P4 only.
    The probe was `["cmd/x/main.go"]`; enrolling `GO_SUPPORT` makes it readable
    and the whole seal stops testing what it says it tests — the BODIES status
    becomes CHECKED and `unsupported_paths` empties. `.sql` has no plausible
    signature comparator in this codebase, so the probe survives this enrolment
    and the next. Nothing was relaxed: the same one path, judged twice under
    two roles in the same seal, and all five assertions unchanged.
    """
    unreadable = ["db/migrate/001_bay.sql"]
    as_bodies = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(unreadable),
    )
    as_scaffold = check_branch(
        "/x", "main", "feat/x", Role.SCAFFOLD, policy=built_in_policy(),
        run=_run_stub(unreadable),
    )
    assert as_bodies.signature is not None
    assert as_scaffold.signature is not None

    assert as_scaffold.signature.status is SignatureCheckStatus.NOT_APPLICABLE
    assert as_bodies.signature.status is (
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
    )
    assert as_bodies.signature.status is not as_scaffold.signature.status, (
        "'this role has no signature duty' and 'this role has the duty and "
        "this gate cannot read the language' were reported as one fact"
    )
    # The role with no duty has nothing to confess; the role with the duty does.
    assert as_scaffold.signature.unsupported_paths == ()
    assert as_bodies.signature.unsupported_paths == ("db/migrate/001_bay.sql",)


def test_the_paths_named_unread_are_the_skipped_ones_not_the_whole_diff(
) -> None:
    """The row that makes the naming worth anything.

    A MIXED diff — one `.py` this gate compared, one `.sql` it could not read.
    Two things at once:

      * `unsupported_paths` is the unread file ALONE. A fix that satisfies the
        naming requirement by handing back `checked_paths` passes the
        wholly-unreadable row above (where every path is unsupported) and dies
        here, which is why that row is not sufficient on its own.
      * the verdict is CLEAN. The compared file decides; the file nobody can
        read is NAMED and does not block.

    AMENDED by P4 on 2026-08-09, and by P4 only. This row previously required
    UNDETERMINED here, on the operator's rule 4 ("a diff with one `.go` and one
    `.py` is not a diff with only `.go`"), and the I6 section header below
    argued for leaving the mixed case refused. **The operator has closed that
    boundary the other way**: the signature gate's verdict is PER FILE. The
    ruling, the measured composition of the target trees that forced it, and
    the seals for it are in `tests/test_role_protocol_perfile.py`; the boundary
    paragraph in the I6 header carries the closure. This was a deliberate
    assertion overruled by a later ruling, not an oversight, which is why the
    prose it stood on is rewritten here rather than left contradicting the line
    below it.

    WHAT THE AMENDMENT DID NOT TOUCH, verified by mutation on 2026-08-09
    against a throwaway reference implementation in a clone (each mutation
    applied downward, `__pycache__` cleared before every run, restored after):

      * `unsupported_paths` is the one unread path — hand back the whole
        changed list and this row is the only place in the suite that reddens.
      * `status is not CHECKED` — report CHECKED for the mixed diff and this
        reddens (I5 is unchanged by the per-file ruling: a file nobody compared
        is not a checked signature).
      * `status is not UNCHECKED_NO_SUPPORTED_FILE` — collapse the two states
        and this reddens. Now that BOTH verdicts are CLEAN, the status is the
        only thing left that separates "read nothing" from "read some", so this
        inequality carries strictly more weight after the amendment than
        before. `test_read_nothing_read_some_and_no_duty_stay_three_states` in
        the per-file file re-pins the same separation independently.
      * the all-Python control — always name something and it reddens.

    Each of those four was individually broken and individually restored; none
    is carried by the verdict assertion, and none was relaxed.

    Red now: CLEAN is not what today's gate answers — `check_branch` maps
    UNCHECKED_UNSUPPORTED_LANGUAGE through `_BODIES_BLOCKING_SIGNATURE_STATUSES`
    to UNDETERMINED on BODIES.
    Green when: the Go file alone is named, the verdict is CLEAN, and an
    all-Python diff names nothing and reports CHECKED.
    Falsify: name every changed path instead of the skipped ones — the first
    equality goes red. Keep the mixed diff blocking (leave
    UNCHECKED_UNSUPPORTED_LANGUAGE in the blocking set) — the CLEAN assertion
    goes red, measured. Reach the CLEAN by giving the mixed diff the
    NO_SUPPORTED_FILE state — the third assertion goes red.

    RE-LANGUAGED by P4 on 2026-08-10, ahead of Go enrolment, and by P4 only.
    The unread half of the mixed diff was `cmd/x/main.go`; enrolling
    `GO_SUPPORT` makes the diff all-readable, which turns this row into a
    duplicate of its own all-Python control and deletes the mixed case from the
    suite silently. `.sql` has no plausible signature comparator in this
    codebase, so the mixed shape survives this enrolment and the next. Nothing
    from the 2026-08-09 amendment note below was relaxed: the same four
    protections, in the same four assertions, over the same two-file diff.
    """
    blobs = {"main:src/app.py": _STUB_PY, "feat/x:src/app.py": _STUB_PY}

    mixed = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(["src/app.py", "db/migrate/001_bay.sql"], blobs),
    )
    assert mixed.signature is not None
    assert mixed.signature.unsupported_paths == ("db/migrate/001_bay.sql",), (
        "the report must name the file the gate could not read and only that "
        f"file: {mixed.signature.unsupported_paths}"
    )
    assert mixed.signature.status is not SignatureCheckStatus.CHECKED
    assert mixed.signature.status is not (
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
    ), (
        "a diff in which one file WAS compared is not a diff with no supported "
        "file in it; the new state must not absorb the partial-check case"
    )
    assert mixed.verdict is DiffVerdict.CLEAN, (
        "the signature gate's verdict is PER FILE (operator, 2026-08-09): the "
        "`.py` was compared and found nothing, so it decides, and the `.sql` "
        "nobody can read is named rather than blocking. Refusing this branch "
        "refuses the ordinary shape of a diff on a tree with 2,288 Go files "
        f"and no Python comparator for them: {mixed.detail}"
    )

    all_python = check_branch(
        "/x", "main", "feat/x", Role.BODIES, policy=built_in_policy(),
        run=_run_stub(["src/app.py"], blobs),
    )
    assert all_python.signature is not None
    assert all_python.signature.unsupported_paths == (), (
        "the control: a diff the gate read in full has nothing to confess, or "
        "the row above is satisfied by always naming something"
    )
    assert all_python.signature.status is SignatureCheckStatus.CHECKED
    assert all_python.verdict is DiffVerdict.CLEAN


def test_the_per_file_comparator_names_the_file_it_could_not_read() -> None:
    """The aggregate and the per-file contract agree about the naming, the same
    way I5 made them agree about the status.

    `compare_signatures` already answers UNCHECKED_UNSUPPORTED_LANGUAGE for a
    non-Python path and already puts the path in `detail`. The new field is the
    machine-readable half of that same fact, so it is populated in the one
    function that KNOWS a file was skipped for its language — and the aggregate
    unions rather than re-deriving. An unparseable Python file is the control:
    it was opened and read, the gate failed ON it rather than skipping it, and
    its reason is not language support.

    Red now: `AttributeError: unsupported_paths`.
    Green when: the unsupported rows name their path and the unparseable row
    names none.
    Falsify: populate the field for every non-CHECKED status — the unparseable
    row goes red.

    RE-LANGUAGED by P4 on 2026-08-10, ahead of Go enrolment, and by P4 only.
    The two unsupported rows were `cmd/x/main.go` and `web/app.ts`; enrolling
    `GO_SUPPORT` turns the first into a CHECKED comparison and both the status
    and the naming assertion redden on behaviour that is CORRECT. `.ts` went
    with `.go` because TypeScript is the other obvious next enrolment. `.sql`
    and `.java` have no plausible signature comparator in this codebase, so
    both rows survive this enrolment and the next. Nothing was relaxed: two
    unsupported rows still, each naming its own path and only its own path,
    with the unparseable-Python and CHECKED controls untouched — those two are
    what stop this being satisfied by naming everything or naming nothing.
    """
    sql = compare_signatures(
        "db/migrate/001_bay.sql",
        "CREATE TABLE bay (id int);\n",
        "CREATE TABLE bay (id bigint);\n",
    )
    assert sql.status is SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE
    assert sql.unsupported_paths == ("db/migrate/001_bay.sql",)

    java = compare_signatures(
        "svc/Handler.java",
        "class Handler { void run(int a) {} }\n",
        "class Handler { void run(long a) {} }\n",
    )
    assert java.status is SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE
    assert java.unsupported_paths == ("svc/Handler.java",)

    unparseable = compare_signatures("src/m.py", "def broken(:\n", _STUB_PY)
    assert unparseable.status is SignatureCheckStatus.UNCHECKED_UNPARSEABLE
    assert unparseable.unsupported_paths == (), (
        "an unparseable Python file was read, not skipped for its language; "
        "naming it as unsupported would tell the reader to go write a "
        "comparator that already exists"
    )

    checked = compare_signatures("src/m.py", _STUB_PY, _STUB_PY)
    assert checked.status is SignatureCheckStatus.CHECKED
    assert checked.unsupported_paths == ()


def test_the_ci_face_clears_a_wholly_unreadable_branch_and_names_the_file_it_could_not_read(
    git_repo: Path,
) -> None:
    """The ruling end to end, through the real script, real git and a real
    checkout — because the harm is in CI, not in a stub.

    A BODIES branch whose only change is `db/migrate/001_bay.sql`: ordinary
    work, no forbidden path, nothing this gate has any comparator for. Today
    `scripts/check_body_branch.sh` exits 3 on it and prints UNDETERMINED, and no
    commit the author can write changes that. This is the operator's own
    workload — 781 SQL files beside 316 Java — so it is the shape the protocol
    actually meets, and it is sealed against the entrypoint CI runs rather than
    against `check_branch` alone: exit 0 is the whole of the ruling's benefit,
    and the named paths on stdout are the whole of its price.

    The WHOLLY-unreadable shape is this row's alone.
    `tests/test_role_protocol_perfile.py::test_the_ci_face_clears_a_mixed_branch_and_still_names_the_unread_file`
    runs the same script over a MIXED branch, where the extra assertion is that
    the file the gate DID read appears exactly once. Neither subsumes the other
    and both must stay.

    Red now (measured, 2026-08-09): rc=3, stdout carries `UNDETERMINED`.
    Green when: rc=0, the headline says CLEAN, and stdout still names the one
    changed file as a file that was not read.
    Falsify: return CLEAN with `unsupported_paths` empty and no detail — rc
    goes green and every naming assertion goes red. Keep the refusal — the rc
    assertion goes red.

    RE-LANGUAGED AND RENAMED by P4 on 2026-08-10, ahead of Go enrolment, and by
    P4 only. The branch changed `cmd/x/main.go` and the seal was called
    `test_the_ci_face_clears_a_go_only_branch_and_names_the_file_it_could_not_read`.
    Enrolling `GO_SUPPORT` makes the branch fully readable: the status stops
    being UNCHECKED_NO_SUPPORTED_FILE, the `>= 2` count drops to 1, and this
    goes red end to end on behaviour that is CORRECT. The name was carrying the
    probe rather than the property, so it was changed with the probe — a name
    that says "go" over a branch with no Go in it is the same stale claim the
    convention exists to remove. The three call sites that referred to it by
    name (this file's I6 list, and the enrolment checklist at `GO_SUPPORT`) are
    updated in the same commit. `.sql` has no plausible signature comparator in
    this codebase, so the branch stays unreadable through this enrolment and
    the next. Nothing was relaxed: rc, the CLEAN headline, the `>= 2` count and
    the status-value assertion are unchanged, and the `>= 2` still rests on the
    same measurement recorded below.
    """
    import os
    import sys

    src_root = Path(__file__).resolve().parent.parent / "src"
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "db" / "migrate").mkdir(parents=True)
    (git_repo / "db" / "migrate" / "001_bay.sql").write_text(
        "ALTER TABLE bay ADD COLUMN real_money_capable boolean NOT NULL;\n",
        encoding="utf-8",
    )
    _git(["add", "."], git_repo)
    _git(
        ["commit", "-q", "-m", "a migration, which this gate cannot read"],
        git_repo,
    )

    script = Path(__file__).resolve().parent.parent / "scripts" / "check_body_branch.sh"
    proc = subprocess.run(
        ["bash", str(script), "main", "feat/x", "bodies"],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON": sys.executable, "PYTHONPATH": str(src_root)},
        timeout=180,
    )
    assert proc.returncode == 0, (
        "a bodies branch doing ordinary Go work is refused by the CI face and "
        "no commit its author can write will clear it — a false refusal with "
        f"no override\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "check_body_branch: CLEAN role=bodies" in proc.stdout, proc.stdout
    # Twice, and the count is the whole assertion. `_print_report` lists every
    # path under "changed paths examined:" whatever happened to it, so a single
    # occurrence is printed by a gate that read the file and by one that never
    # opened it alike — measured (2026-08-09): with both the per-path detail and
    # the verdict's own detail stripped, the bare path was still in stdout and
    # this seal stayed green. A seal two different answers satisfy is not a
    # seal.
    assert proc.stdout.count("db/migrate/001_bay.sql") >= 2, (
        "the branch was cleared and the only mention of the one file it "
        "changed is the bare path listing every run prints; nothing on stdout "
        f"says that file was never read\nstdout={proc.stdout}"
    )
    assert SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE.value in proc.stdout, (
        "the report announces CLEAN without announcing that the signature half "
        f"of the check did not run\nstdout={proc.stdout}"
    )
    assert "scaffolded signatures: checked" not in proc.stdout, proc.stdout
