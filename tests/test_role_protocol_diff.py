"""D1 seals (P2): diff-time enforcement — the gate that saves a build cycle.

The vacuity trap in this unit is specific and is sealed against directly: a deny
row can pass because the *changed-path list was empty*, so every violation row
asserts the returned `PathViolation` (path AND matched_glob), and
`test_empty_diff_is_undetermined_never_clean` pins the empty case to
UNDETERMINED. "I could not compute the diff" is never "clean".

`check_branch`'s three distinct UNDETERMINED causes each get their own row —
unreadable policy, unreadable/empty diff, and (BODIES only) an `UNCHECKED_*`
signature status — because a single "returns non-clean" assertion conflates
them, and the third is the subtle one: an unchecked signature, on the very role
whose gate that is, is not a pass.

The git seams are exercised two ways on purpose: against a real tiny repo (which
pins the three-dot / no-renames *behaviour* without guessing an argv), and
through the injectable `run` seam (which pins the failure mapping).
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import repo_config, role_protocol
from claude_dispatcher.role_protocol import (
    DiffVerdict,
    ExitCode,
    PolicySource,
    Role,
    RoleDiffError,
    RoleDiffResult,
    RolePolicy,
    RoleProtocolError,
    RoleRule,
    RuleKind,
    SignatureCheckStatus,
    TaskRoleSpec,
    built_in_policy,
    changed_paths_between,
    check_branch,
    compare_signatures,
    file_text_at,
)

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"


# --------------------------------------------------------------------------- #
# The injectable subprocess seam
# --------------------------------------------------------------------------- #


class _RunResult(tuple):
    """A `(rc, stdout, stderr)` triple that also answers `.returncode/.stdout/
    .stderr`.

    The scaffold types `run` as `Callable[..., object]` and names `push_verify`
    as the precedent (a 3-tuple), but a `CompletedProcess`-shaped consumer is
    equally consistent with that annotation. Answering both shapes keeps these
    seals from pinning a convention the contract never states.
    """

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


def _run_stub(
    *,
    changed: list[str] | None = None,
    diff_rc: int = 0,
    diff_stderr: str = "",
    blobs: dict[str, str] | None = None,
    raise_on: str | None = None,
    base_ref: str = "main",
):
    """A git seam that answers only the reads this module is allowed to do.

    `blobs` is keyed `"<ref>:<path>"`, exactly as git spells the argument, so a
    stub answer cannot be mistaken for a different revision of the same file. An
    unscripted command raises, so a seal cannot pass on a path it never modelled.

    P4 (2026-08-08), adjudicating D1-inputs blocker 1. `merge-base` was added,
    and nothing else was: fixing I4 (the signature baseline is the base ref's
    TIP, not the merge-base the three-dot diff measured from) needs a third git
    read that no seal here had modelled, and a BODIES implementer may not edit
    `tests/**` to model it. Depending on where the fix places the call this
    reddens between 7 and 14 rows across these two files, every one of them by
    the seam raising and `_run_git_capture` turning that into UNDETERMINED.

    The answer is the BASE REF, and only for a `merge-base` naming it. That is
    what the merge-base IS in a stub that models no advanced base — these rows
    are about which paths the rule forbids, and must not go red or green
    according to how I4 is fixed. It is answered explicitly rather than by
    echoing whichever argument follows `merge-base`, so a call spelled with a
    flag or with the refs reversed cannot collect a rubber stamp; and a
    `merge-base` between refs this stub does not model raises like any other
    unscripted read, so the extension buys exactly one command and no leniency.
    A base that really did advance cannot be stubbed at all and is sealed
    against a real repository, in `test_role_protocol_inputs.py`.
    """
    blobs = blobs or {}

    def run(cmd, *_args, **_kwargs):
        argv = [str(c) for c in cmd]
        if "diff" in argv:
            if raise_on == "diff":
                raise OSError("git not on PATH")
            out = "" if changed is None else "".join(p + "\n" for p in changed)
            return _RunResult(diff_rc, out, diff_stderr)
        if "merge-base" in argv:
            if base_ref not in argv:
                raise AssertionError(
                    f"merge-base asked for refs this stub does not model "
                    f"(it models {base_ref!r} as the merge-base): {argv}"
                )
            return _RunResult(0, base_ref + "\n", "")
        spec = next((a for a in argv if ":" in a and not a.startswith("-")), None)
        if spec is not None:
            if raise_on == "blob":
                raise subprocess.TimeoutExpired(cmd=argv, timeout=30)
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
    """A repo on `main` with one base commit; tests branch off it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "base.txt").write_text("seed\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    return repo


# --------------------------------------------------------------------------- #
# changed_paths_between — three-dot, no renames, and never () for failure
# --------------------------------------------------------------------------- #


def test_changed_paths_are_the_branchs_own_commits_only(git_repo: Path) -> None:
    """Three-dot: a base that advanced underneath must not read as the branch's
    work (`risk.collect_diff`'s reasoning applies here too).

    Red now: `changed_paths_between` raises NotImplementedError.
    Green when: the diff is `base...branch`.
    Falsify: use two-dot — `moved_on_main.txt` appears and this goes red.
    """
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "branch work"], git_repo)
    _git(["checkout", "-q", "main"], git_repo)
    (git_repo / "moved_on_main.txt").write_text("later\n", encoding="utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "base advanced"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert paths == ("src/app.py",)


def test_a_move_out_of_a_protected_directory_shows_both_paths(git_repo: Path) -> None:
    """`--no-renames`, so a file moved OUT of a protected directory appears as a
    deletion of the protected path — otherwise a body agent could relocate a
    seal and the gate would see one innocuous new path.

    Red now: NotImplementedError.
    Green when: rename detection is off.
    Falsify: drop `--no-renames` — git reports one `R` entry and the deleted
    `tests/...` path vanishes.
    """
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "test_seal.py").write_text("def test_x():\n    pass\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "add seal"], git_repo)
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    _git(["mv", "tests/test_seal.py", "moved_seal.py"], git_repo)
    _git(["commit", "-q", "-m", "relocate the seal"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert set(paths) == {"tests/test_seal.py", "moved_seal.py"}


def test_git_failure_raises_rather_than_returning_no_paths() -> None:
    """An empty list from a failed command is indistinguishable from an empty
    diff, so failure must raise. It must NEVER return () to mean failure.

    Red now: NotImplementedError is not RoleDiffError.
    Green when: a non-zero rc raises RoleDiffError.
    """
    run = _run_stub(changed=[], diff_rc=128, diff_stderr="fatal: bad revision")
    with pytest.raises(RoleDiffError):
        changed_paths_between("/x", "main", "feat/x", run=run)


def test_subprocess_explosion_raises_role_diff_error() -> None:
    """Red now: NotImplementedError.
    Green when: an OSError/timeout from the seam becomes RoleDiffError.
    """
    with pytest.raises(RoleDiffError):
        changed_paths_between("/x", "main", "feat/x", run=_run_stub(raise_on="diff"))


def test_a_successful_read_of_an_empty_diff_returns_no_paths() -> None:
    """The genuinely-empty case is NOT an error here; `check_branch` is what
    turns it into UNDETERMINED. Keeping the two apart is what lets the empty-diff
    seal below be about the verdict rather than about git.

    Red now: NotImplementedError.
    Green when: rc 0 with no output returns ().
    """
    assert changed_paths_between("/x", "main", "feat/x", run=_run_stub(changed=[])) == ()


def test_a_non_ascii_path_survives_the_diff_and_is_still_gate_matched(
    git_repo: Path,
) -> None:
    """`-c core.quotePath=false`, sealed by its consequence rather than by its
    argv. With quoting ON git renders a non-ASCII path as `\\NNN` octal escapes,
    and a path this function mis-renders is a path `evaluate_changed_paths`
    cannot glob-match: a body agent could add a seal file named `tests/tést.py`
    and the gate would report CLEAN. That is a silent hole in the one thing this
    module exists to prevent, so the seal goes all the way to the verdict.

    Green when: the raw path round-trips AND `**/tests/**` still forbids it.
    Falsify: drop `-c core.quotePath=false` from the argv — git returns
    `"tests/t\\303\\251st.py"` (quoted, escaped), the raw-path assertion goes
    red, and so does the BODIES violation, because no glob matches that string.
    """
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "tést.py").write_text("def test_x():\n    pass\n", "utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "a seal with a non-ascii name"], git_repo)

    paths = changed_paths_between(git_repo, "main", "feat/x")
    assert paths == ("tests/tést.py",), (
        "the path must come back as git's raw bytes decoded, not octal-escaped "
        f"and not quoted: {paths!r}"
    )
    violations = role_protocol.evaluate_changed_paths(
        built_in_policy().rule_for(Role.BODIES), list(paths)
    )
    assert [(v.path, v.matched_glob) for v in violations] == [
        ("tests/tést.py", "**/tests/**")
    ], "a non-ASCII seal path must still be forbidden to BODIES"


def test_changed_paths_keep_gits_order_and_collapse_only_duplicates() -> None:
    """Order is the report's order: the paths are printed back to the agent that
    tripped the gate, and a re-ordered list makes the report disagree with the
    diff it claims to describe. Duplicates collapse because a merge-shaped range
    can name a path twice and a doubled violation reads as two offences.

    The fixture is chosen so that every plausible mutation is visible — this is
    the seal a `sorted(reverse=True)` in the implementation previously survived,
    because both existing fixtures happened to be reverse-ordered already (one
    of them is compared as a `set`, so it could never have caught it):

      * `sorted(...)`          -> ('docs/mid.md', 'src/zeta.py', 'tests/alpha.py')
      * `sorted(..., reverse)` -> ('tests/alpha.py', 'src/zeta.py', 'docs/mid.md')
      * no dedup               -> four entries
      * `set(...)`             -> arbitrary order, and reddens on CPython's hash

    none of which equal the expected tuple.
    """
    run = _run_stub(
        changed=["src/zeta.py", "tests/alpha.py", "src/zeta.py", "docs/mid.md"]
    )
    assert changed_paths_between("/x", "main", "feat/x", run=run) == (
        "src/zeta.py",
        "tests/alpha.py",
        "docs/mid.md",
    )


# --------------------------------------------------------------------------- #
# file_text_at — None means absent-from-that-tree and nothing else
# --------------------------------------------------------------------------- #


def test_file_text_at_returns_the_blob_text(git_repo: Path) -> None:
    """Red now: `file_text_at` raises NotImplementedError.
    Green when: it returns the file's text at that ref.
    """
    assert file_text_at(git_repo, "main", "base.txt") == "seed\n"


def test_file_text_at_returns_none_only_for_absent_from_the_tree(git_repo: Path) -> None:
    """Red now: NotImplementedError.
    Green when: a path the tree does not contain is None.
    """
    assert file_text_at(git_repo, "main", "never/existed.py") is None


def test_file_text_at_raises_on_an_unresolvable_ref(git_repo: Path) -> None:
    """An unreadable base must never be mistaken for a newly-added file, which
    would suppress every signature change in it.

    Red now: NotImplementedError.
    Green when: a bad ref raises RoleDiffError rather than returning None.
    Falsify: `return None` on any git failure — this row goes red.
    """
    with pytest.raises(RoleDiffError):
        file_text_at(git_repo, "no-such-ref", "base.txt")


def test_file_text_at_raises_on_a_non_utf8_blob(git_repo: Path) -> None:
    """Red now: NotImplementedError.
    Green when: undecodable bytes raise instead of returning None or mojibake.
    """
    (git_repo / "blob.bin").write_bytes(b"\xff\xfe\x00binary")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "binary"], git_repo)
    with pytest.raises(RoleDiffError):
        file_text_at(git_repo, "main", "blob.bin")


def test_file_text_at_raises_on_a_symlink_entry(git_repo: Path) -> None:
    """A symlink is a redirect to somewhere the ref does not govern; reading it
    as text would read the link target's *name* as file content.

    Red now: NotImplementedError.
    Green when: a non-regular-file entry raises RoleDiffError.
    Falsify: implement with a bare `git show ref:path` — it happily prints the
    link target and this row goes red.
    """
    (git_repo / "link.py").symlink_to("base.txt")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "symlink"], git_repo)
    with pytest.raises(RoleDiffError):
        file_text_at(git_repo, "main", "link.py")


# --------------------------------------------------------------------------- #
# compare_signatures — the half of the P3 gate that no path glob can see
# --------------------------------------------------------------------------- #

_BASE_PY = textwrap.dedent(
    '''
    """Module docstring."""

    from dataclasses import dataclass


    @dataclass(frozen=True)
    class Spec:
        name: str
        count: int = 0


    def top(a: int, *, b: str = "x") -> bool:
        raise NotImplementedError


    class Holder:
        def method(self, a: int) -> None:
            raise NotImplementedError
    '''
)


def _changed_symbols(base: str | None, head: str | None, path: str = "src/m.py"):
    result = compare_signatures(path, base, head)
    assert result.status is SignatureCheckStatus.CHECKED, result
    return result, {c.symbol for c in result.changes}


@pytest.mark.parametrize(
    "head, why",
    [
        (_BASE_PY, "identical"),
        # Formatting is not a contract: the fingerprint is AST-derived.
        (_BASE_PY.replace("def top(a: int, *, b: str = \"x\") -> bool:",
                          "def top(\n    a: int,\n    *,\n    b: str = 'x',\n) -> bool:"),
         "reformatted signature"),
        (_BASE_PY.replace('"""Module docstring."""', '"""Rewritten by P3."""'),
         "module docstring edited"),
        (_BASE_PY.replace("    raise NotImplementedError\n",
                          "    return True\n", 1),
         "body implemented"),
        # The default's VALUE is a body concern.
        (_BASE_PY.replace("count: int = 0", "count: int = 5"), "default value changed"),
        # A body may add private helpers and new symbols.
        (_BASE_PY + "\n\ndef _helper(x: int) -> int:\n    return x\n", "helper added"),
        # A docstring added to a stubbed function: P1's contract may be extended.
        (_BASE_PY.replace("def top(a: int, *, b: str = \"x\") -> bool:\n",
                          "def top(a: int, *, b: str = \"x\") -> bool:\n    \"\"\"Doc.\"\"\"\n"),
         "docstring added"),
    ],
)
def test_honest_body_work_is_not_a_signature_change(head: str, why: str) -> None:
    """Red now: `compare_signatures` raises NotImplementedError.
    Green when: the fingerprint is AST-derived and excludes bodies, docstrings
    and default VALUES.
    Falsify: fingerprint the source text — every row here goes red.

    P4 (2026-08-08) — DISPOSITION of the panel finding "the frozen signature
    check ignores default values" (filed against `role_protocol.py:2221`).
    OVERTURNED. Not a defect; do not re-raise it, and do not delete the
    `count: int = 0` -> `count: int = 5` row above to make it true.

      * It contradicts `compare_signatures`' own contract, which states the
        exclusion as a decision and not an oversight: "whether each parameter
        has a default (the default's *value* is a body concern and is NOT part
        of the fingerprint)". Sealing the finding would require deleting a
        correct row — the tell that the finding, not the row, is wrong.
      * The has-default FLAG is in the fingerprint, and is sealed in BOTH
        directions and on BOTH kinds of symbol: the "a default was removed" row
        and the "a default added to a parameter that had none" row in
        `test_a_widened_or_altered_signature_is_a_change` below (the second
        added by this ruling so the disposition is self-evident rather than
        asserted), plus the dataclass-field rows. Confirmed by execution:
        `count: int = 0` fingerprints as `count: int = <default>`, so adding or
        removing a default IS a change and only the value is invisible.
        Dropping `_HAS_DEFAULT` from `_parameter_fingerprint` reddens both rows.
      * A default's value is body behaviour, and body behaviour is the whole
        category this seal protects. It is also the category the SEALS already
        cover: a seal that cares what the default is asserts it and goes red.
        The signature gate exists for the changes no seal CAN see — widening a
        parameter list breaks no existing seal — and pulling the value into the
        fingerprint would make the scaffold's placeholder defaults unchangeable
        by the role whose job is to choose them.
    """
    _result, changed = _changed_symbols(_BASE_PY, head)
    assert changed == set(), why


@pytest.mark.parametrize(
    "head, expected, why",
    [
        (_BASE_PY.replace("def top(a: int", "def top(a2: int"), {"top"},
         "parameter renamed"),
        (_BASE_PY.replace("def top(a: int", "def top(a: str"), {"top"},
         "annotation changed"),
        (_BASE_PY.replace("-> bool:", "-> str:"), {"top"},
         "return annotation changed"),
        (_BASE_PY.replace("def top(a: int, *, b: str = \"x\")",
                          "def top(a: int, b: str = \"x\")"), {"top"},
         "keyword-only became positional — the kind is part of the contract"),
        (_BASE_PY.replace("def top(a: int, *, b: str = \"x\")",
                          "def top(a: int, /, *, b: str = \"x\")"), {"top"},
         "positional-only marker added"),
        (_BASE_PY.replace("def top(a: int, *, b: str = \"x\")",
                          "def top(a: int, *args, b: str = \"x\", **kw)"), {"top"},
         "var-positional and var-keyword added"),
        (_BASE_PY.replace("def top(", "async def top("), {"top"},
         "sync became async"),
        (_BASE_PY.replace("def top(a: int, *, b: str = \"x\")",
                          "def top(a: int, *, b: str)"), {"top"},
         "a default was removed — has-default is part of the fingerprint"),
        # P4 (2026-08-08): the other direction of the same flag, added while
        # overturning the panel's "ignores default values" finding — see the
        # disposition in `test_honest_body_work_is_not_a_signature_change`. The
        # VALUE is invisible and the FLAG is not, in both directions, which is
        # the whole of what that finding disputed.
        (_BASE_PY.replace("def top(a: int, *, b: str = \"x\")",
                          "def top(a: int = 1, *, b: str = \"x\")"), {"top"},
         "a default was added to a parameter that had none"),
        (_BASE_PY.replace("def top(", "@staticmethod\ndef top("), {"top"},
         "decorator added"),
        # Frozen dataclass FIELDS are the contract in this codebase.
        (_BASE_PY.replace("name: str", "name: bytes"), {"Spec"},
         "dataclass field retyped"),
        (_BASE_PY.replace("    name: str\n    count: int = 0",
                          "    count: int = 0\n    name: str"), {"Spec"},
         "dataclass fields reordered"),
        (_BASE_PY.replace("@dataclass(frozen=True)", "@dataclass"), {"Spec"},
         "dataclass decorator changed — frozen-ness is the contract"),
        (_BASE_PY.replace("class Holder:", "class Holder(Spec):"), {"Holder"},
         "base class added"),
        (_BASE_PY.replace("def method(self, a: int) -> None:",
                          "def method(self, a: int, b: int = 0) -> None:"),
         {"Holder.method"}, "method parameter added, reported qualified"),
    ],
)
def test_a_widened_or_altered_signature_is_a_change(
    head: str, expected: set[str], why: str
) -> None:
    """§2a's P3 gate is "no protected diff AND no changed signature": a body
    agent that widens a parameter list has changed the contract P2 sealed
    without touching a protected path.

    Red now: NotImplementedError.
    Green when: each of these fingerprints differs from base.
    Falsify: drop parameter kinds / annotations / decorators / dataclass fields
    from the fingerprint — the corresponding row goes red.
    """
    result, changed = _changed_symbols(_BASE_PY, head)
    assert changed == expected, why
    for change in result.changes:
        assert change.path == "src/m.py"
        assert change.before, "the before-fingerprint must be reported"
        assert change.after is not None, "an altered symbol still exists at head"


def test_a_removed_symbol_is_a_change_with_no_after() -> None:
    """Deleting a scaffolded signature is not implementing it.

    Red now: NotImplementedError.
    Green when: the removed symbol is reported with `after is None`.
    """
    head = _BASE_PY.replace(
        'def top(a: int, *, b: str = "x") -> bool:\n    raise NotImplementedError\n', ""
    )
    result, changed = _changed_symbols(_BASE_PY, head)
    assert changed == {"top"}
    assert result.changes[0].after is None


def test_a_file_new_on_the_branch_is_checked_with_no_changes() -> None:
    """A file that did not exist at base has no scaffolded signature to preserve.

    Red now: NotImplementedError.
    Green when: `base_text=None` is CHECKED with no changes.
    Falsify: treat None as "unparseable" — the body agent's new module reads as
    a violation and honest work fails.
    """
    result = compare_signatures("src/new.py", None, _BASE_PY)
    assert result.status is SignatureCheckStatus.CHECKED
    assert result.changes == ()


def test_a_deleted_file_makes_every_base_symbol_a_change() -> None:
    """Deleting the file defeats the contract as thoroughly as editing it.

    Red now: NotImplementedError.
    Green when: `head_text=None` reports every base symbol with `after is None`.
    """
    result = compare_signatures("src/m.py", _BASE_PY, None)
    assert result.status is SignatureCheckStatus.CHECKED
    assert {c.symbol for c in result.changes} == {
        "Spec",
        "top",
        "Holder",
        "Holder.method",
    }
    assert all(c.after is None for c in result.changes)


def test_both_texts_none_is_not_a_silent_pass() -> None:
    """Neither revision has the file: there is nothing to compare, and reporting
    CHECKED-with-no-changes for a path git says changed is the "could this pass
    without doing anything?" shape.

    Red now: NotImplementedError.
    Green when: it raises `RoleDiffError`.
    Falsify: return `CHECKED` with no changes (the shape the pre-ruling
    docstring literally licensed) — this goes red.

    P4 (2026-08-07): the NOTE here said the docstring did not state this case
    and sealed only "not a vacuous CHECKED-clean", accepting ANY exception. The
    P2 ruling settled it — "`compare_signatures` with both revisions absent ⇒
    raise (the caller has a bug)" — and the contract now says so, so the seal
    names the exception type. An `except Exception: return` also swallowed a
    stray TypeError as a pass, which is a seal satisfied by two different
    answers.
    """
    with pytest.raises(RoleDiffError):
        compare_signatures("src/m.py", None, None)


@pytest.mark.parametrize(
    "path, base, head, expected_status",
    [
        # Not Python: named, not silent. The Go side needs its own comparator.
        ("cmd/classify/main.go", "package main\n", "package main\n",
         SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE),
        ("web/app.ts", "export const a = 1;\n", "export const a = 2;\n",
         SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE),
        # Either revision failing to parse is UNCHECKED, never "unchanged".
        ("src/m.py", "def broken(:\n", _BASE_PY,
         SignatureCheckStatus.UNCHECKED_UNPARSEABLE),
        ("src/m.py", _BASE_PY, "def broken(:\n",
         SignatureCheckStatus.UNCHECKED_UNPARSEABLE),
    ],
)
def test_an_unchecked_comparison_is_named_never_reported_as_unchanged(
    path: str, base: str, head: str, expected_status: SignatureCheckStatus
) -> None:
    """Red now: NotImplementedError.
    Green when: each unchecked cause has its own named status and empty changes.
    Falsify: `except SyntaxError: return CHECKED` — the last two rows go red.
    """
    result = compare_signatures(path, base, head)
    assert result.status is expected_status
    assert result.changes == ()
    if expected_status is SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE:
        assert path in result.detail, "the unchecked path must be reportable"


def test_every_signature_check_status_is_reachable() -> None:
    """Closed set 4 of 4, sealed by PRODUCTION rather than by enumeration: a
    status nothing can produce is a state the gate cannot report.

    NOT_APPLICABLE is produced by `check_branch` for a non-BODIES role (the only
    place it can be), so this seal spans both functions.

    Red now: both functions raise NotImplementedError.
    Green when: all five statuses are produced.

    AMENDED by P4 on 2026-08-09, and by P4 only, because this seal pins
    `SignatureCheckStatus` by VALUE-SET EQUALITY: adding a member reddens it,
    which is the whole point of writing it that way, and the fifth member could
    not land without a ruling. The ruling — a BODIES diff this gate has no
    comparator for is CLEAN, in its own named state, and must say what it could
    not read — and the argument for a new member rather than a reuse of
    NOT_APPLICABLE are in the I6 section header of
    `test_role_protocol_inputs.py`, where the behaviour is sealed.

    The amendment does not relax anything. The written set gains exactly one
    literal, still spelled out rather than derived; the equality is still an
    equality, so a sixth member reddens this the same way the fifth did; and the
    new member is added to `produced` by a PRODUCING call — a BODIES diff with
    no Python in it — not by naming it, so a member the code cannot reach still
    fails here. The two ways this could have been weakened were `>=` on the
    value set and `produced.add(SignatureCheckStatus.<new>)`; neither was used.
    """
    assert {s.value for s in SignatureCheckStatus} == {
        "checked",
        "unchecked_unsupported_language",
        "unchecked_unparseable",
        "unchecked_no_supported_file",
        "not_applicable",
    }
    produced = {
        compare_signatures("src/m.py", _BASE_PY, _BASE_PY).status,
        compare_signatures("m.go", "package m\n", "package m\n").status,
        compare_signatures("src/m.py", "def x(:\n", _BASE_PY).status,
    }
    result = check_branch(
        "/x",
        "main",
        "feat/x",
        Role.SCAFFOLD,
        policy=built_in_policy(),
        run=_run_stub(changed=["src/app.py"], blobs={"main:src/app.py": _BASE_PY}),
    )
    assert result.signature is not None
    produced.add(result.signature.status)

    # The fifth: a BODIES diff with nothing in it this gate can read. Produced,
    # like every other row here, rather than named.
    unreadable = check_branch(
        "/x",
        "main",
        "feat/x",
        Role.BODIES,
        policy=built_in_policy(),
        run=_run_stub(changed=["cmd/x/main.go"]),
    )
    assert unreadable.signature is not None
    produced.add(unreadable.signature.status)

    assert produced == set(SignatureCheckStatus)


# --------------------------------------------------------------------------- #
# check_branch — the single diff-time entrypoint
# --------------------------------------------------------------------------- #


def _check(role: Role, changed: list[str] | None, **kwargs) -> RoleDiffResult:
    kwargs.setdefault("policy", built_in_policy())
    run = kwargs.pop("run", None) or _run_stub(
        changed=changed, blobs=kwargs.pop("blobs", None) or {}
    )
    return check_branch("/x", "main", "feat/x", role, run=run, **kwargs)


def test_a_clean_branch_records_what_it_actually_checked() -> None:
    """A CLEAN verdict must be auditable for having examined something — the
    A-stream's coverage lesson applied to this gate.

    Red now: `check_branch` raises NotImplementedError.
    Green when: CLEAN carries the exact path list and the policy source.
    """
    result = _check(Role.SEALS, ["tests/test_new_seal.py", "tests/conftest.py"])
    assert result.verdict is DiffVerdict.CLEAN
    assert result.role is Role.SEALS
    assert result.base_ref == "main"
    assert result.branch_ref == "feat/x"
    assert result.checked_paths == ("tests/test_new_seal.py", "tests/conftest.py")
    assert result.violations == ()
    assert result.policy_source is PolicySource.BUILT_IN_DEFAULTS


@pytest.mark.parametrize(
    "role, path, expected_glob",
    [
        # The plan's headline row: a bodies task touching tests/**.
        (Role.BODIES, "tests/test_role_protocol_diff.py", "**/tests/**"),
        (Role.BODIES, "src/claude_dispatcher/conftest.py", "**/conftest.py"),
        (Role.BODIES, "schema/merge.yaml", "**/schema/**"),
        (Role.BODIES, "roles/reviewer.md", "**/roles/*.md"),
        # A seal author who may edit the implementation can make its own seal
        # pass — the definition of a vacuous seal.
        #
        # P4 ruling (2026-08-09), and the SAME class of amendment as the row
        # below: this probe was `src/claude_dispatcher/role_protocol.py`. Once
        # the gate library is on `FLOOR_GLOBS`, that path is covered by TWO
        # protections — SEALS' `**/src/**` and the floor — and `_union_with_floor`
        # makes the floor win per path, by design, so `matched_glob` becomes the
        # floor glob. Exactly the 2026-08-07 finding recorded two lines down: the
        # fixture, not the table and not the matcher, is the defect, because a
        # doubly-covered probe cannot distinguish the protection its row names.
        # Retargeted to `src/claude_dispatcher/plan.py`, where `**/src/**` is the
        # SOLE cover under SEALS (measured: no other SEALS glob and no floor glob
        # matches it), so this row can again only be satisfied by the glob it
        # names. The property is unchanged and so is the point it makes — a seal
        # author editing the implementation — and `plan.py` is the unit's
        # established ordinary-source probe.
        (Role.SEALS, "src/claude_dispatcher/plan.py", "**/src/**"),
        # P4 ruling (2026-08-07). This row was `Role.SEALS` and expected
        # `**/reviewer_prompts/**`; the gate answered `**/src/**`, which is
        # correct under the FIRST-match contract because SEALS denies `**/src/**`
        # too and it sits earlier in the table. The fixture, not the table and
        # not the matcher, was the defect: under SEALS this real path is covered
        # by TWO globs, so the assertion could not distinguish the protection it
        # named. Retargeted to BODIES, where `**/reviewer_prompts/**` is the SOLE
        # cover of this exact path — BODIES has no `**/src/**` deny, because
        # writing `src/` is its job — so this row can only be satisfied by the
        # glob it names. This is also the case that matters operationally: the
        # role that legitimately writes `src/` is the one for which this glob is
        # the only thing standing between a body agent and the reviewer prompt
        # that is about to judge it.
        (Role.BODIES, "src/claude_dispatcher/reviewer_prompts/_shared.md",
         "**/reviewer_prompts/**"),
        # The twin hole, sealed for the same reason and by the same argument.
        (Role.BODIES, "src/claude_dispatcher/verifier_prompts/verifier.md",
         "**/verifier_prompts/**"),
        # P1 must not write the seals it will be judged by.
        (Role.SCAFFOLD, "tests/test_role_protocol_table.py", "**/tests/**"),
        (Role.SCAFFOLD, "pkg/testdata/golden.json", "**/testdata/**"),
    ],
)
def test_a_forbidden_path_is_a_violation_naming_the_path_and_the_glob(
    role: Role, path: str, expected_glob: str
) -> None:
    """The anti-vacuity assertion for every deny row: a violation is proven by
    the returned `PathViolation`, not by "the verdict was not CLEAN". A deny row
    that passes because the changed-path list was empty proves nothing, so the
    innocuous companion path is asserted absent from the violations too.

    Red now: NotImplementedError.
    Green when: the violation names the path AND the glob that forbade it.
    Falsify: report violations without `matched_glob` — every row goes red.
    """
    result = _check(role, [path, "docs/notes.md"])
    assert result.verdict is DiffVerdict.VIOLATION
    assert result.checked_paths == (path, "docs/notes.md")
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        (path, expected_glob)
    ]
    assert result.violations[0].rule_kind is RuleKind.DENY_GLOBS


def test_every_forbidden_path_is_reported_not_just_the_first() -> None:
    """An under-reporting gate sends the agent round the loop once per offence.

    P4 (2026-08-07): no fixture in this file put TWO forbidden paths in one
    diff, so `return tuple(violations[:1])` in `evaluate_changed_paths` was
    invisible to the whole suite. The innocuous path is kept in the middle so
    the seal also pins that reporting order follows the diff, not the violation
    order.

    Green when: all three forbidden paths are reported, in the diff's order.
    Falsify: `violations[:1]`, or reporting only the last — this goes red.
    """
    result = _check(
        Role.BODIES,
        [
            "tests/test_one.py",
            "src/claude_dispatcher/app.py",
            "schema/merge.yaml",
            "roles/reviewer.md",
        ],
    )
    assert result.verdict is DiffVerdict.VIOLATION
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        ("tests/test_one.py", "**/tests/**"),
        ("schema/merge.yaml", "**/schema/**"),
        ("roles/reviewer.md", "**/roles/*.md"),
    ]


def test_empty_diff_is_undetermined_never_clean() -> None:
    """UNDETERMINED cause 2 of 3, half one: a role task that changed nothing has
    not done its phase, and "did nothing" must not look like "succeeded".

    Red now: NotImplementedError.
    Green when: zero changed paths yields UNDETERMINED with a detail saying so.
    Falsify: `if not paths: return CLEAN` — this goes red. (This is THE vacuity
    trap for every deny row in this file.)
    """
    result = _check(Role.BODIES, [])
    assert result.verdict is DiffVerdict.UNDETERMINED
    assert result.checked_paths == ()
    assert result.detail.strip(), "UNDETERMINED must say why"


def test_an_unreadable_diff_is_undetermined() -> None:
    """UNDETERMINED cause 2 of 3, half two: a failed git read is not a pass.

    Red now: NotImplementedError.
    Green when: a RoleDiffError becomes UNDETERMINED with the message carried.
    Falsify: let the RoleDiffError escape, or swallow it into CLEAN.
    """
    result = _check(Role.BODIES, None, run=_run_stub(raise_on="diff"))
    assert result.verdict is DiffVerdict.UNDETERMINED
    assert result.detail.strip()


@pytest.mark.parametrize(
    "error",
    [
        repo_config.BaseConfigError("cannot read .dispatcher.yaml at main"),
        RoleProtocolError("roles: section invalid"),
    ],
)
def test_an_unreadable_policy_is_undetermined_not_the_built_in_defaults(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """UNDETERMINED cause 1 of 3. Falling back to the compiled-in defaults would
    silently drop the repo's ADDITIONS, so "I could not read the policy" must
    not be answered with a policy.

    Red now: NotImplementedError.
    Green when: the base-pinned load's failure becomes UNDETERMINED.
    Falsify: `except Exception: policy = built_in_policy()` — this goes red.
    """

    def _boom(*_a, **_k):
        raise error

    monkeypatch.setattr(role_protocol, "load_role_policy_from_base", _boom)
    result = check_branch(
        "/x",
        "main",
        "feat/x",
        Role.BODIES,
        run=_run_stub(changed=["tests/test_x.py"]),
    )
    assert result.verdict is DiffVerdict.UNDETERMINED
    assert result.violations == ()


def test_an_unchecked_signature_on_bodies_is_undetermined_not_a_pass() -> None:
    """UNDETERMINED cause 3 of 3 — the subtle one.

    The changed file's BASE revision does not parse, so the signature comparison
    could not run. On BODIES — the one role whose gate that is — an unchecked
    signature is not a pass.

    Red now: NotImplementedError.
    Green when: an UNCHECKED_* status on BODIES forces UNDETERMINED.
    Falsify: verdict on path violations alone — this row goes CLEAN and red.
    """
    result = _check(
        Role.BODIES,
        ["src/claude_dispatcher/thing.py"],
        blobs={"main:src/claude_dispatcher/thing.py": "def broken(:\n"},
    )
    assert result.signature is not None
    assert result.signature.status is SignatureCheckStatus.UNCHECKED_UNPARSEABLE
    assert result.verdict is DiffVerdict.UNDETERMINED


def test_the_same_unchecked_file_is_clean_for_a_role_with_no_signature_duty() -> None:
    """The non-vacuity partner of the row above: identical inputs, different
    role, opposite verdict. Without this pair, "UNDETERMINED" could come from the
    unparseable file rather than from the role's obligation.

    Red now: NotImplementedError.
    Green when: non-BODIES roles get NOT_APPLICABLE and stay CLEAN.
    """
    result = _check(
        Role.SCAFFOLD,
        ["src/claude_dispatcher/thing.py"],
        blobs={"main:src/claude_dispatcher/thing.py": "def broken(:\n"},
    )
    assert result.signature is not None
    assert result.signature.status is SignatureCheckStatus.NOT_APPLICABLE
    assert result.verdict is DiffVerdict.CLEAN


def test_a_changed_signature_is_a_violation_even_with_no_forbidden_path() -> None:
    """The half of the P3 gate no path glob can see.

    Red now: NotImplementedError.
    Green when: a widened signature on an otherwise-permitted path is VIOLATION.
    """
    head = _BASE_PY.replace("def top(a: int", "def top(a: int, extra: int = 0")
    result = _check(
        Role.BODIES,
        ["src/claude_dispatcher/m.py"],
        blobs={
            "main:src/claude_dispatcher/m.py": _BASE_PY,
            "feat/x:src/claude_dispatcher/m.py": head,
        },
    )
    assert result.violations == ()
    assert result.signature is not None
    assert result.signature.status is SignatureCheckStatus.CHECKED
    assert {c.symbol for c in result.signature.changes} == {"top"}
    assert result.verdict is DiffVerdict.VIOLATION


def test_legacy_is_clean_on_any_non_empty_diff_except_a_floor_path() -> None:
    """A pre-protocol task has no immutable paths, and this function must not
    become a new gate on legacy work — with exactly one exception, the floor.

    **AMENDED BY P4, 2026-08-07.** The original body asserted LEGACY +
    `.dispatcher.yaml` ⇒ CLEAN with `violations == ()`. The operator has ruled
    that the non-overridable floor (`role_protocol.FLOOR_GLOBS`) applies to
    LEGACY too, and the reason is that the alternative is not a floor at all: a
    floor LEGACY escapes is bypassed by DELETING one line — omit `role:` and the
    row is LEGACY, and a LEGACY row may then rewrite the file that configures
    every role's permissions. The seal author could not make this change (a seal
    author may not amend a seal) and raised it as a dispute; this is the ruling.

    What this seal exists to protect — backward compatibility for the role-less
    rows that every `features/*/tasks.yaml` in this repo carries — survives
    intact, narrowed to "clean on any non-empty diff EXCEPT a floor path". That
    narrowing is asserted as two calls with OPPOSITE answers, not as one relaxed
    assertion: a relaxed assertion that both CLEAN and VIOLATION satisfy would
    seal nothing.

    This overrides the sentence in `check_branch`'s docstring reading "LEGACY
    always returns CLEAN when the diff read succeeded and was non-empty"; P3
    updates that contract line in the commit that implements the floor.

    Red now: the second half. `check_branch` short-circuits LEGACY to CLEAN
    before the changed paths are evaluated at all (verified against the built
    worktree), which is the exact place the floor has to be unioned in.
    Green when: LEGACY is CLEAN for everything off the floor and VIOLATION for a
    floor path.
    Falsify: give LEGACY a deny list — the first half goes red (and so does the
    UNRESTRICTED row in the table seals). Exempt LEGACY from the floor — the
    second half goes red. Refuse legacy work wholesale — the first half goes red.
    """
    clean = _check(Role.LEGACY, ["tests/test_x.py", "schema/merge.yaml"])
    assert clean.verdict is DiffVerdict.CLEAN, (
        "a role-less row was refused for paths that are not on the floor; the "
        "pre-protocol guarantee is narrowed by the floor, not withdrawn"
    )
    assert clean.violations == ()

    floored = _check(
        Role.LEGACY, ["tests/test_x.py", ".dispatcher.yaml", "schema/merge.yaml"]
    )
    assert [(v.path, v.matched_glob) for v in floored.violations] == [
        (".dispatcher.yaml", "**/.dispatcher.yaml")
    ], (
        "a row bought write access to the policy file by having no `role:` "
        "key; a floor that LEGACY escapes is bypassed by deleting one line"
    )
    assert floored.verdict is DiffVerdict.VIOLATION


def test_legacy_with_an_empty_diff_is_still_undetermined() -> None:
    """"No immutable paths" is not "nothing to check": the empty-diff state is
    about whether the check ran at all.

    Red now: NotImplementedError.
    Green when: LEGACY + zero paths is UNDETERMINED.
    """
    assert _check(Role.LEGACY, []).verdict is DiffVerdict.UNDETERMINED


def test_adjudicate_without_a_spec_is_undetermined() -> None:
    """ADJUDICATE's writable set lives on the task row. Without it the answer is
    UNDETERMINED — never "may touch nothing" (a wrong CLEAN for an empty diff)
    and never "may touch anything".

    Red now: NotImplementedError.
    Green when: a missing required `spec` is UNDETERMINED.
    Falsify: fall back to the table's ALLOW_ONLY entry with its empty globs —
    every changed path becomes a violation and the *reason* is lost, so this row
    (asserting UNDETERMINED, not VIOLATION) goes red.
    """
    result = _check(Role.ADJUDICATE, ["tests/test_x.py"])
    assert result.verdict is DiffVerdict.UNDETERMINED
    assert result.detail.strip()


def test_adjudicate_with_a_spec_permits_only_the_disputed_paths() -> None:
    """Red now: NotImplementedError.
    Green when: the disputed path is CLEAN and anything else is a violation.

    NOTE: `PathViolation.matched_glob` is unspecified for an ALLOW_ONLY
    violation (there is no glob that "says so" — the path matched none), so only
    `path` and `rule_kind` are asserted here. Raised as a P2 dispute; the DENY
    rows above keep the full path+glob assertion.
    """
    spec = TaskRoleSpec(
        task_key="DISPUTE-7",
        role=Role.ADJUDICATE,
        disputed_paths=("tests/test_role_protocol_diff.py",),
    )
    clean = _check(Role.ADJUDICATE, ["tests/test_role_protocol_diff.py"], spec=spec)
    assert clean.verdict is DiffVerdict.CLEAN

    strayed = _check(
        Role.ADJUDICATE,
        ["tests/test_role_protocol_diff.py", "src/claude_dispatcher/plan.py"],
        spec=spec,
    )
    assert strayed.verdict is DiffVerdict.VIOLATION
    assert [v.path for v in strayed.violations] == ["src/claude_dispatcher/plan.py"]
    assert strayed.violations[0].rule_kind is RuleKind.ALLOW_ONLY_GLOBS


def test_a_per_task_override_is_applied_at_diff_time() -> None:
    """The override is only useful if the diff-time point honours it.

    Red now: NotImplementedError.
    Green when: the added glob produces a violation naming that glob, proving
    `check_branch` went through `effective_rule` rather than the policy alone.
    """
    spec = TaskRoleSpec(
        task_key="D1-P3",
        role=Role.BODIES,
        added_immutable_globs=("**/cmd/reviewer/**",),
    )
    result = _check(Role.BODIES, ["cmd/reviewer/main.go"], spec=spec)
    assert result.verdict is DiffVerdict.VIOLATION
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        ("cmd/reviewer/main.go", "**/cmd/reviewer/**")
    ]


def test_an_illegal_override_does_not_produce_a_verdict_of_clean() -> None:
    """Validate before apply: a narrowing-shaped override must not be silently
    ignored on the way to a pass.

    Red now: NotImplementedError.
    Green when: the illegal override raises or yields UNDETERMINED — what it
    must not do is answer CLEAN.
    NOTE: `check_branch` does not state which of the two it is; only the "never
    CLEAN" half is sealed. Raised as a P2 dispute.
    """
    spec = TaskRoleSpec(
        task_key="D1-P3", role=Role.BODIES, added_immutable_globs=("!tests/**",)
    )
    try:
        result = _check(Role.BODIES, ["src/claude_dispatcher/plan.py"], spec=spec)
    except NotImplementedError:
        raise
    except RoleProtocolError:
        return
    assert result.verdict is not DiffVerdict.CLEAN


def test_every_diff_verdict_is_reachable_through_check_branch() -> None:
    """Closed set 3 of 4, sealed by production: three states, not two-plus-null.

    Red now: NotImplementedError.
    Green when: one scenario each produces CLEAN, VIOLATION and UNDETERMINED.
    """
    assert {v.value for v in DiffVerdict} == {"clean", "violation", "undetermined"}
    produced = {
        _check(Role.SEALS, ["tests/test_x.py"]).verdict,
        _check(Role.BODIES, ["tests/test_x.py"]).verdict,
        _check(Role.BODIES, []).verdict,
    }
    assert produced == set(DiffVerdict)


def test_the_policy_argument_wins_so_the_three_call_sites_cannot_disagree() -> None:
    """One callable, so a PR-time pass and a task-loop pass can never disagree
    (invariant 1): a supplied policy is used verbatim, with no re-derivation.

    Red now: NotImplementedError.
    Green when: a caller-supplied policy governs the verdict.
    Falsify: ignore `policy` and always load from base — the injected stub is
    never consulted, `**/cmd/**` is not denied to BODIES, and this goes red.
    """
    policy = RolePolicy(
        rules=tuple(
            RoleRule(
                role=role,
                kind=RuleKind.DENY_GLOBS,
                globs=("**/cmd/**",),
                rationale="injected policy",
            )
            if role is not Role.LEGACY
            else RoleRule(
                role=Role.LEGACY,
                kind=RuleKind.UNRESTRICTED,
                globs=(),
                rationale="legacy",
            )
            for role in Role
        ),
        source=PolicySource.BASE_PINNED_CONFIG,
        base_ref="main",
    )
    result = _check(Role.BODIES, ["cmd/x/main.go", "tests/test_x.py"], policy=policy)
    assert result.policy_source is PolicySource.BASE_PINNED_CONFIG
    assert [(v.path, v.matched_glob) for v in result.violations] == [
        ("cmd/x/main.go", "**/cmd/**")
    ]


# --------------------------------------------------------------------------- #
# The CLI face and the script that CI runs
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "verdict, expected",
    [
        (DiffVerdict.CLEAN, ExitCode.OK),
        (DiffVerdict.VIOLATION, ExitCode.VIOLATION),
        (DiffVerdict.UNDETERMINED, ExitCode.UNDETERMINED),
    ],
)
def test_main_maps_each_verdict_to_its_own_exit_code(
    monkeypatch: pytest.MonkeyPatch, verdict: DiffVerdict, expected: ExitCode
) -> None:
    """A CI job that cannot tell "violation" from "could not check" will treat
    the second as the first or, worse, as a pass.

    Red now: `main` raises NotImplementedError.
    Green when: the three verdicts map to 0 / 2 / 3 respectively.
    Falsify: map UNDETERMINED to 0 (or to 2) — the third row goes red.
    """
    assert (ExitCode.OK.value, ExitCode.VIOLATION.value, ExitCode.UNDETERMINED.value) == (
        0,
        2,
        3,
    )
    monkeypatch.setattr(
        role_protocol,
        "check_branch",
        lambda *a, **k: RoleDiffResult(
            verdict=verdict, role=Role.BODIES, base_ref="main", branch_ref="feat/x",
            checked_paths=("src/x.py",),
        ),
    )
    assert role_protocol.main(["main", "feat/x", "bodies"]) == expected.value


@pytest.mark.parametrize(
    "argv",
    [[], ["main"], ["main", "feat/x"], ["main", "feat/x", "bodies", "extra"]],
)
def test_main_requires_exactly_three_positional_arguments(argv: list[str]) -> None:
    """Red now: NotImplementedError.
    Green when: any other arity is ExitCode.USAGE (64).
    """
    assert role_protocol.main(argv) == ExitCode.USAGE.value


def test_main_never_answers_ok_for_the_role_word_legacy() -> None:
    """A checker invoked with `legacy` is a checker invoked with no role;
    answering OK would let a caller disable the gate by passing a word.

    Red now: NotImplementedError.
    Green when: the call returns a non-zero code.
    NOTE: the contract does not say WHICH non-zero code an unparseable role is
    (USAGE and UNDETERMINED are both defensible), so only "never OK" is sealed.
    Raised as a P2 dispute.
    """
    code = role_protocol.main(["main", "feat/x", "legacy"])
    assert code != ExitCode.OK.value
    assert code in {ExitCode.USAGE.value, ExitCode.UNDETERMINED.value}


def test_main_prints_every_violated_path_with_the_glob_that_forbade_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An agent that trips the gate must be told what tripped it, from the run
    log alone.

    Red now: NotImplementedError.
    Green when: each violated path, its glob AND the violated rule's rationale
    appear on stdout.
    Falsify: drop the `why:` line from `_print_report` — this goes red.

    P4 (2026-08-07): the NOTE here called the rationale half "unsatisfiable
    from the declared result type" and left it unsealed. That was true when it
    was written and is now stale: the 2026-08-04 P2 ruling put `rationale` on
    `PathViolation`, P1 added the field, and `main` prints it — but nothing
    asserted it, so the print was one deletion away from silently going. The
    rationale is the whole point of the report: an agent that trips the gate
    has to learn WHY the path is not its to touch, from the run log alone.
    """
    monkeypatch.setattr(
        role_protocol,
        "check_branch",
        lambda *a, **k: RoleDiffResult(
            verdict=DiffVerdict.VIOLATION,
            role=Role.BODIES,
            base_ref="main",
            branch_ref="feat/x",
            violations=(
                role_protocol.PathViolation(
                    path="tests/test_seal.py",
                    matched_glob="**/tests/**",
                    rule_kind=RuleKind.DENY_GLOBS,
                    rationale="P3 implements the seals, never edits them",
                ),
            ),
            checked_paths=("tests/test_seal.py",),
        ),
    )
    assert role_protocol.main(["main", "feat/x", "bodies"]) == ExitCode.VIOLATION.value
    out = capsys.readouterr().out
    assert "tests/test_seal.py" in out
    assert "**/tests/**" in out
    assert "P3 implements the seals, never edits them" in out, (
        "the violated rule's rationale must reach stdout: an agent that trips "
        "the gate is told WHY the path is not its to touch, from the log alone"
    )


def test_the_ci_script_delegates_instead_of_reporting_not_implemented(
    git_repo: Path,
) -> None:
    """`scripts/check_body_branch.sh` is the PR-time and CI face; while it exits
    70 nothing is enforced on a branch's diff.

    Red now: the stub prints NOT IMPLEMENTED and exits 70.
    Green when: it execs the Python entrypoint (`python -m
    claude_dispatcher.role_protocol`) so CI and the task loop cannot disagree.
    Falsify: reimplement the path matching in bash — the exit codes may agree
    but `main`'s seals above stop covering CI, which is why this asserts
    delegation by asserting the stub's own code is gone.
    """
    script = Path(__file__).resolve().parent.parent / "scripts" / "check_body_branch.sh"
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "work"], git_repo)

    import os
    import sys

    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "PYTHONPATH": str(SRC_ROOT),
    }
    proc = subprocess.run(
        ["bash", str(script), "main", "feat/x", "bodies"],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != ExitCode.NOT_IMPLEMENTED.value, (
        "the CI face still reports not-implemented: no branch diff is checked"
    )
    # P4 (2026-08-07): `rc in {0, 2, 3}` was the whole of this seal, and
    # `src/app.py` is a path BODIES may write, so the expected verdict is CLEAN
    # → 0 — exactly what a rubber stamp emits. Replacing the entire delegation
    # with `[ $# -ne 3 ] && exit 64; exit 0` left the suite green. The report
    # text is asserted instead: only the real `_print_report` can produce it.
    assert proc.returncode == ExitCode.OK.value, proc.stderr
    assert "check_body_branch: CLEAN role=bodies base=main branch=feat/x" in (
        proc.stdout
    ), proc.stdout
    assert "changed paths examined: 1" in proc.stdout, proc.stdout
    assert "src/app.py" in proc.stdout, proc.stdout

    usage = subprocess.run(
        ["bash", str(script), "main"],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        env=env,
    )
    assert usage.returncode == ExitCode.USAGE.value, usage.stderr


def test_the_ci_script_does_not_let_the_judged_checkout_supply_its_own_gate(
    git_repo: Path,
) -> None:
    """The branch under judgement must not be able to supply the code that
    judges it (design §8 / invariant 6). This is the gate-evasion seal for the
    script's import path, and it is written as the attack rather than as an
    assertion about how the script computes PYTHONPATH — because the script
    computed PYTHONPATH correctly, from `BASH_SOURCE`, and was exploitable
    anyway.

    The hole (found and confirmed by P4, 2026-08-07): for `python -m pkg.mod`,
    Python sets `sys.path[0]` to the CWD, and PYTHONPATH entries are searched
    AFTER it. The script runs with cwd = the checkout under judgement, as CI
    does. So a bodies branch that commits a top-level `claude_dispatcher/`
    package wins the import over the real one no matter how carefully the
    wrapper resolved its own `src/`. Run against the pre-fix script, the planted
    gate below printed "everything is fine" and exited 0 while the same branch
    added a file under `tests/`.

    Green when: the script suppresses the cwd entry (`-P` / PYTHONSAFEPATH), so
    the REAL gate runs and reports the planted seal file as a violation.
    Falsify: remove `-P` and `PYTHONSAFEPATH=1` from the script — the planted
    `main` runs, returns 0, and this goes red on the exit code AND on the
    marker string.

    Note this test must NOT put the real `src` on PYTHONPATH: doing so would
    prove nothing, since the question is precisely whether the wrapper gets the
    right module onto the path by itself.
    """
    import os
    import sys

    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    # The body agent's payload: a gate that approves everything...
    pkg = git_repo / "claude_dispatcher"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "role_protocol.py").write_text(
        "import sys\n"
        "def main(argv):\n"
        "    print('HOSTILE GATE: everything is fine')\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    # ...and the forbidden edit it exists to hide.
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "test_planted_seal.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    _git(["add", "."], git_repo)
    _git(["commit", "-q", "-m", "a seal, and a gate that approves it"], git_repo)

    script = Path(__file__).resolve().parent.parent / "scripts" / "check_body_branch.sh"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHON"] = sys.executable
    proc = subprocess.run(
        ["bash", str(script), "main", "feat/x", "bodies"],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        env=env,
    )

    assert "HOSTILE GATE" not in proc.stdout, (
        "the checkout under judgement supplied the module that judged it: "
        f"{proc.stdout}"
    )
    assert proc.returncode == ExitCode.VIOLATION.value, (
        "the real gate must run and must refuse the planted seal file; got "
        f"rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "tests/test_planted_seal.py" in proc.stdout
