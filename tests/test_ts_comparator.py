"""D4 seals (P2): the TypeScript comparator is READ CORRECTLY, and its parser is
the one this build vouches for.

WHY THIS FILE EXISTS
--------------------
`tests/test_go_comparator.py` is the model and its opening argument transfers
verbatim: enrolment alone bought nothing for Go, because dropping parameter
names from the Go fingerprint left the suite green before and after. The seals
that pin a language UNREADABLE cannot notice a comparator that runs and answers
WRONG. TypeScript is 996 files in the primary target, 475 of them `.tsx`.

It differs from the Go file in one way that governs everything below: **the Go
comparator existed when its seals were written, and this one does not.**
`TypeScriptSignatureFingerprinter.fingerprints` raises `NotImplementedError`,
and even once it is written `ts_parser_home()` raises `HELPER_MISSING` on every
machine, because nothing is vendored. So a large part of this file is RED, and
the shape of that red is the first thing a reader has to understand.

HOW THIS FILE BEHAVES WITH NO PARSER, AND WHY IT DOES NOT SKIP
---------------------------------------------------------------
Every execution seal here — every seal that has to ask a real comparator a real
question — FAILS while the comparator is absent. None of them skips, none is
`xfail`, and none is conditioned on `ts_parser_home()` succeeding.

That is a deliberate refusal of the single failure mode this unit exists to
prevent. A suite that skips when the parser is absent reports green, and green
over 996 files is a certificate. The three states have to stay distinguishable
and only two of them are acceptable answers:

  * the comparator answered, and it answered as ruled          -> green
  * the comparator answered, and it answered wrong             -> red
  * the comparator could not answer at all                     -> red

`_ts_changed` is the one place that decides this, and it fails with a message
naming WHICH of the two red states it is in — `NOT IMPLEMENTED`, `NO TRUSTED
PARSER`, or a wrong answer — so that a reader of a failure list can tell "this
unit has not been built" from "this unit has been built wrong" without opening
the code.

WHAT THE NO-PARSER STATE CAN AND CANNOT HIDE
--------------------------------------------
Stated plainly, because the honest answer is not "nothing".

It CAN hide a wrong answer: while every execution seal is red for absence, none
of them is exercising the comparator, so a defective implementation and no
implementation are indistinguishable *from this file's exit code*. That is a
real limit and it is why the sections below are ordered so that the seals which
can bite TODAY come first, and why the reference-implementation satisfiability
check recorded in this commit's report was run rather than argued.

It CANNOT manufacture a pass, and that is the property that matters. There is
no state of the world in which the parser is absent and this file goes green.
The failure this project keeps paying for is a vacuous GREEN — a seal that
certifies because it asked nothing. A seal that is RED for absence is not
vacuous; it is loud, and it is loud in the direction that blocks.

THE VACUITY TRAPS, AND WHAT IS DONE ABOUT EACH
-----------------------------------------------
1. *A table where every row is a CHANGE* is satisfied by a comparator that
   answers "changed" to everything — a gate nobody can pass, which is a gate
   everybody routes around. Section 4 refuses a rulings table that lost its
   silent half; sections 6 and 7 each ship a silent table beside a change table
   and assert both with paired rows.
2. *A table where every row is SILENT* is satisfied by a comparator that returns
   `{}` for every file. Same seals, other direction, plus
   `test_an_empty_answer_and_a_real_one_are_distinguishable`.
3. *Asserting on the rulings dataclass instead of on the comparator.* Section 4
   does the dataclass half deliberately and says so; section 5 feeds the same
   rows to the live comparator, which is the half that was never measured for
   Go until its P2 file existed.
4. *A seal that cannot fail.* Each seal's docstring carries a `Falsify:` line
   naming the edit that reddens it. For the seals that can run today those
   mutations were applied to a `cp -a` clone and confirmed red. For the seals
   that cannot run today, the reference implementation built in that clone was
   mutated instead, and both directions — the correct implementation going
   green and the mutant going red — are recorded in this commit's report.
5. *Normalising so hard that the signal goes with the noise.* Section 6 is
   built entirely out of PAIRS: every respelling that must be silent sits
   beside a real change in the same syntactic position that must still be
   caught. A renderer that deletes string-literal types passes the silent half
   and fails its partner.

WHAT THIS FILE DOES NOT DO
---------------------------
It does not enrol. `TYPESCRIPT_SUPPORT` stays in `PENDING_COMPARATORS`;
enrolment is a two-line move in a separate reviewable commit after a P4
re-language pass, and section 0 pins the registry's internal consistency rather
than one transient state of it, exactly as the Go file's section 0 was amended
to do.

It does not depend on the target repository's copy of TypeScript. The only
parser this file will ever accept is the one `ts_parser_home()` resolves out of
the dispatcher's own package directory, which is the whole of unit D4's answer
to the untrusted-parser problem. A seal that reached into
`evenplay-mono/node_modules` to get itself green would be asserting the defect.

It does not seal a refusal of the cross-file declaration-merging bypass,
because the design does not implement one. Section 11 seals that the limit is
RECORDED and that the protocol rule which creates it is still the protocol
rule. See its docstring for why recording is the honest seal and refusing would
be a seal against nothing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from claude_dispatcher import role_protocol
from claude_dispatcher.role_protocol import (
    ComparatorFault,
    ComparatorUnavailable,
    Language,
    RoleProtocolError,
    SignatureCheckStatus,
    TsSignatureEditRuling,
    compare_signatures,
    ts_symbol_key,
)


_FP = role_protocol.TypeScriptSignatureFingerprinter()

#: The two dialects. Both are real paths in the primary target's shape, and the
#: distinction is not cosmetic: `.tsx` selects a different GRAMMAR for the same
#: bytes, which section 8 seals.
_TS = "src/betting/stake.ts"
_TSX = "src/components/Button.tsx"

#: Prefixes on every failure `_ts_changed` raises, so a reader scanning a
#: failure list can separate "this was never built" from "this was built wrong"
#: without opening a file. Section 12 asserts they are distinct.
_UNIMPLEMENTED = "TS COMPARATOR NOT IMPLEMENTED"
_NO_PARSER = "TS COMPARATOR HAS NO TRUSTED PARSER"

#: What `pytest.fail` raises. `pytest.fail.Exception` is the public spelling;
#: `_pytest.outcomes.Failed` is not, and section 12 has to catch it by name to
#: prove that absence produces a FAILURE and never a skip.
Failed = pytest.fail.Exception


# --------------------------------------------------------------------------- #
# fixtures and helpers
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _restore_comparator_globals():
    """Put back every module global these seals can dirty.

    Section 2 rewrites `TS_HELPER_PACKAGE_DIR` and the prepared-parser cache on
    purpose — that is the only way to drive a digest mismatch on a machine
    whose vendored parser is correct — and a leak would break the rest of the
    suite in file order, which is the worst kind of red because it blames the
    wrong test.
    """
    names = (
        "COMPARATORS",
        "TS_HELPER_PACKAGE_DIR",
        "TS_VENDORED_PARSER_SHA256",
        "_TS_HELPER_PREPARED",
        "_HELPER_TIMEOUT_SECONDS",
    )
    saved = {n: getattr(role_protocol, n) for n in names if hasattr(role_protocol, n)}
    yield
    for name, value in saved.items():
        setattr(role_protocol, name, value)
    for name in names:
        if name not in saved and hasattr(role_protocol, name):
            delattr(role_protocol, name)


@pytest.fixture
def compare_ts(monkeypatch: pytest.MonkeyPatch):
    """`compare_signatures` with the TypeScript row registered FOR THIS TEST ONLY.

    Registering is not enrolling. The shipped `COMPARATORS` tuple on disk is
    unchanged whatever it holds, and section 0 pins that the registry and the
    lookup agree either way. What this buys is that the ruled answers are
    measured through the REAL protocol — added-is-not-a-change, removed-is,
    status CHECKED — rather than through a re-implementation of those rules
    living in this file, which would be a second copy of the thing under test.

    It PREPENDS rather than replaces, so it supplies the row before enrolment
    and shadows it with the same object after; nothing here has to be edited on
    the day the row moves.
    """
    monkeypatch.setattr(
        role_protocol,
        "COMPARATORS",
        (role_protocol.TYPESCRIPT_SUPPORT,) + role_protocol.COMPARATORS,
        raising=True,
    )

    def _compare(before: str | None, after: str | None, path: str = _TS):
        return compare_signatures(path, before, after)

    return _compare


def _ts_changed(compare, before: str, after: str, path: str = _TS) -> bool:
    """Did the live comparator report a change? **Never skips. Never xfails.**

    THE ONE PLACE that decides how this file behaves when the comparator cannot
    answer, and the reason it is a function rather than three lines inlined
    thirty times. Three outcomes, two of which are failures:

      * a CHECKED comparison -> True/False, and the caller asserts the ruling;
      * `NotImplementedError` -> fail, prefixed `_UNIMPLEMENTED`. This is the
        shipped state today: the P1 scaffold is contracts only.
      * any non-CHECKED status -> fail, prefixed `_NO_PARSER` when the detail
        carries a fault. Today that is `HELPER_MISSING` from `ts_parser_home`,
        because nothing is vendored.

    A `pytest.skip` here would turn this whole file green on every machine in
    the world, which is the certificate this unit exists to refuse issuing.
    """
    try:
        result = compare(before, after, path)
    except NotImplementedError as exc:
        pytest.fail(
            f"{_UNIMPLEMENTED}: {exc}. This seal is red because unit D4 is a "
            "contract, not because the ruling below is wrong. It goes green "
            "when TypeScriptSignatureFingerprinter is implemented AND a "
            "trusted parser is vendored — and not one step earlier."
        )
    except ComparatorUnavailable as exc:  # pragma: no cover - protocol catches
        pytest.fail(f"{_NO_PARSER}: {exc.fault.value}: {exc.message}")

    if result.status is not SignatureCheckStatus.CHECKED:
        marker = (
            _NO_PARSER
            if result.status
            is SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
            else "TS COMPARATOR DID NOT READ THESE REVISIONS"
        )
        pytest.fail(
            f"{marker}: status={result.status.name} detail={result.detail!r}. "
            "The comparator never reached the question this seal asks."
        )
    return bool(result.changes)


def _fingerprints(path: str, text: str) -> dict[str, str]:
    """The comparator's raw answer for one revision, or a loud failure."""
    try:
        return _FP.fingerprints(path, text)
    except NotImplementedError as exc:
        pytest.fail(f"{_UNIMPLEMENTED}: {exc}")
    except ComparatorUnavailable as exc:
        pytest.fail(f"{_NO_PARSER}: {exc.fault.value}: {exc.message}")
    raise AssertionError("unreachable")  # pragma: no cover


def _prose(text: str) -> str:
    """Comment and docstring text with its line wrapping taken back out.

    Every sentence sections 2 and 11 cite is wrapped mid-phrase, so a literal
    `in` check would be asserting where the author happened to break a line —
    which reformatting alone would redden, for no reason a reader could act on.
    Leading `#` goes too, so module comments and docstrings search alike.
    """
    return " ".join(text.replace("#", " ").split())


def _role_protocol_source() -> str:
    return Path(role_protocol.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 0 — the precondition every seal below rests on: the registry
#
# GREEN TODAY.
# --------------------------------------------------------------------------- #


def test_the_typescript_row_is_in_exactly_one_registry_and_the_lookup_agrees() -> None:
    """The TS row is enrolled or pending, never both and never neither, and what
    the gate actually READS says the same thing.

    Every seal below registers TypeScript through `compare_ts`, so this file's
    answers do not depend on which state the shipped registry is in. What this
    pins is that the two registries and the lookup cannot DISAGREE.
    `PENDING_COMPARATORS` is the named state for "written but not live"
    (`skills/explicit-state.md`), and a pending row that `support_for_path`
    nevertheless returns is coverage reported that does not exist — in exactly
    the direction that reads as safe.

    The direction that matters here is sharper than it was for Go. A pending
    `.ts` row answering a lookup would put 996 files under a comparator that
    raises `NotImplementedError`, and the file count is the reason the enrolment
    checklist at `TYPESCRIPT_SUPPORT` has five items rather than one.

    Green when: membership is exclusive, and `support_for_path` and
    `enrolled_languages` both follow `COMPARATORS` alone.
    Falsify: make `support_for_path` consult `PENDING_COMPARATORS` too — the
    second assertion reddens for both `.ts` and `.tsx`. Derive
    `enrolled_languages` from both tuples — the third reddens. Drop the row
    from both tuples — the first reddens. Put it in both — collection fails
    upstream at `validate_registry`, which is why that state is not asserted
    here.
    """
    row = role_protocol.TYPESCRIPT_SUPPORT
    enrolled = row in role_protocol.COMPARATORS
    pending = row in role_protocol.PENDING_COMPARATORS

    assert enrolled != pending, (
        "the TypeScript row is in both registries or in neither; 'scaffolded "
        "but not enrolled' is a named state, and a row in two tables or none "
        f"has no name (enrolled={enrolled}, pending={pending})"
    )
    for path in (_TS, _TSX):
        assert (role_protocol.support_for_path(path) is not None) is enrolled, (
            f"what the gate READS for {path!r} disagrees with the registry it "
            "is derived from. A PENDING row answering a lookup reports "
            "coverage that does not exist, over 996 files"
        )
    assert (Language.TYPESCRIPT in role_protocol.enrolled_languages()) is enrolled, (
        "`enrolled_languages` is the falsifiable statement of what this build "
        "covers; sourcing it from anything but `COMPARATORS` makes it prose"
    )


def test_the_shipped_state_is_no_trusted_parser_and_that_is_a_fault_not_a_gap() -> None:
    """Today `ts_parser_home()` refuses, and the refusal is HELPER_MISSING.

    This is the seal on the sentence the whole unit turns on: **absence of the
    trusted parser is a FAULT, never "this build has no TypeScript support".**
    The second reading is the broken-wheel fail-open — it would hand every
    TypeScript branch a clean bill of health for as long as the install stayed
    broken, because an unsupported language is promoted to
    UNCHECKED_NO_SUPPORTED_FILE and a diff of nothing else is CLEAN.

    It is written to survive vendoring rather than to pin today's state: if a
    parser IS installed the function returns a directory inside the package,
    and that is asserted instead. What may never happen is a *third* answer —
    a refusal carrying any fault but HELPER_MISSING, or a returned path outside
    the package.

    Green when: either the named refusal, or a contained directory.
    Falsify: change the fault to TOOLCHAIN_MISSING (a fact about the machine,
    not about this build's own apparatus) — the fault assertion reddens.
    Return `Path(".")` when the directory is absent instead of raising — the
    containment assertion reddens.
    """
    package = Path(role_protocol.__file__).parent.resolve()
    try:
        home = role_protocol.ts_parser_home()
    except ComparatorUnavailable as exc:
        assert exc.fault is ComparatorFault.HELPER_MISSING, (
            f"an absent trusted parser raised {exc.fault.value}, not "
            "HELPER_MISSING. A missing vendored artifact is this build's own "
            "apparatus missing, which is what HELPER_MISSING names; calling it "
            "a toolchain fault blames the machine for a broken wheel"
        )
        assert role_protocol.signature_status_for_fault(exc.fault) is (
            SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
        ), "the shipped refusal must be BLOCKING, not a language nobody reads"
        return

    assert home.resolve().is_relative_to(package), (
        f"ts_parser_home() returned {home}, which is not inside {package}. The "
        "parser's location is a pure function of the DISPATCHER's installed "
        "location and of nothing else; a path outside the package is a parser "
        "this gate cannot vouch for"
    )


# --------------------------------------------------------------------------- #
# 1 — the resolution rule: the parser's location is a pure function of
#     `Path(__file__).parent`, and of nothing else.
#
# GREEN TODAY. These are the seals on the one sentence unit D4 adopted, and
# they bite whether or not anything is vendored, because they assert that the
# ANSWER does not move when the things it is forbidden to depend on move.
# --------------------------------------------------------------------------- #


#: Every input the section header explicitly rejected as a way to find the
#: parser. Each is set to a plausible attacker-controlled value; none of them
#: may change what `ts_parser_home` names.
_REJECTED_PARSER_INPUTS: tuple[tuple[str, str], ...] = (
    ("NODE_PATH", "/home/andrew/Project/evenplay-mono/node_modules"),
    ("NODE_OPTIONS", "--require /tmp/evil.js"),
    ("NPM_CONFIG_PREFIX", "/tmp/fake-global"),
    ("CLAUDE_DISPATCHER_TS_PARSER", "/tmp/fake-parser/typescript.js"),
    ("TS_HELPER_PACKAGE_DIR", "/tmp/fake-package"),
)


def test_the_parser_location_ignores_the_environment_and_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No environment variable and no CWD moves the trusted parser.

    THE RULE, sealed. The section header rejects an env-var override with the
    argument worth having: anything that redirects the gate's parser is part of
    the machinery that computes the verdict, and this project's answer to "who
    may change the machinery" is `FLOOR_GLOBS` — a table of PATHS. **An
    environment variable cannot be put on the floor.** It has no diff, no base
    revision, and `scripts/check_body_branch.sh` has nothing to read it from.

    The CWD arm is the same property for the other half of the rejection list:
    the gate judges branches in OTHER repositories and is routinely run from
    inside the checkout it is judging, so an answer that moved with the CWD
    would be an answer the branch chooses.

    This seal works while nothing is vendored because it compares the ANSWER
    across environments rather than asserting one value: a refusal names the
    directory it looked in, and that name may not move either.

    Green when: the answer is byte-identical under every rejected input.
    Falsify: add `os.environ.get("CLAUDE_DISPATCHER_TS_PARSER")` as a first
    branch of `ts_parser_home` — the fourth row reddens. Resolve the package
    dir against `Path.cwd()` instead of `Path(__file__).parent` — the CWD arm
    reddens.
    """

    def answer() -> str:
        try:
            return f"ok:{role_protocol.ts_parser_home()}"
        except ComparatorUnavailable as exc:
            return f"{exc.fault.value}:{exc.message}"

    baseline = answer()

    for name, value in _REJECTED_PARSER_INPUTS:
        monkeypatch.setenv(name, value)
        assert answer() == baseline, (
            f"setting ${name} moved the trusted parser. Anything that "
            "redirects the gate's parser belongs on FLOOR_GLOBS, and an "
            "environment variable is not a path: it has no diff and "
            "check_body_branch.sh cannot read it"
        )
        monkeypatch.delenv(name, raising=False)

    monkeypatch.chdir(tmp_path)
    assert answer() == baseline, (
        "the trusted parser moved with the working directory. This gate is "
        "run from inside the checkout it judges; a parser chosen by the CWD is "
        "a parser the branch chooses"
    )


def test_the_vendored_layout_is_the_flat_named_trio() -> None:
    """The three artifacts are named constants, and the layout is FLAT.

    Not a style assertion. `pyproject.toml`'s package-data glob for the Go
    helper is `go_signature_fingerprint/*`, and setuptools package-data globs
    **do not recurse** — so a parser vendored as
    `node_modules/typescript/lib/typescript.js` is dropped from the wheel and
    every install becomes HELPER_MISSING. The flatness is a measured constraint
    and it costs nothing, because `typescript.js` is a self-contained CommonJS
    bundle.

    The `.cjs` suffix is the other half: it is the only way to say "this is
    CommonJS" that a `"type": "module"` package.json in any ancestor directory
    cannot override.

    Green when: the three names are present, distinct, and flat.
    Falsify: change `TS_HELPER_ENTRY_POINT` to `main.js` — the CommonJS
    assertion reddens. Set `TS_HELPER_PACKAGE_DIR` to a nested path — the
    flatness assertion reddens.
    """
    names = (
        role_protocol.TS_HELPER_ENTRY_POINT,
        role_protocol.TS_VENDORED_PARSER,
        role_protocol.TS_VENDORED_PARSER_LICENSE,
    )
    assert len(set(names)) == 3, f"the vendored trio is not three things: {names}"
    for name in names + (role_protocol.TS_HELPER_PACKAGE_DIR,):
        assert "/" not in name and not name.startswith("."), (
            f"{name!r} is not a flat name. setuptools package-data globs do "
            "not recurse, so a nested vendored layout is dropped from the "
            "wheel and every install is HELPER_MISSING"
        )
    assert role_protocol.TS_HELPER_ENTRY_POINT.endswith(".cjs"), (
        "the helper must be `.cjs`: it is the only statement of 'this is "
        "CommonJS' that a `\"type\": \"module\"` package.json above the "
        "install cannot override"
    )
    assert role_protocol.TS_VENDORED_PARSER_LICENSE, (
        "the parser's license travels with the vendored parser; it is also the "
        "cheapest evidence that what was vendored is what it claims to be"
    )


def test_the_helper_subtree_is_on_the_floor_before_anything_is_vendored_into_it() -> (
    None
):
    """`FLOOR_GLOBS` must cover the TS helper subtree, and must cover it FIRST.

    **GREEN as of the D4 P4 adjudication, 2026-08-10, and it was RED when
    written.** This is the precondition the scaffold states at `ts_parser_home`
    and repeats at `TYPESCRIPT_SUPPORT`: the glob lands **before** anything is
    vendored, "for the reason the Go entry records — a floor that arrives with
    enrolment is a floor that was absent for every commit that built the thing
    it protects." It went green on exactly that commit and nothing else: the
    glob, its four rows in `_FLOOR_ROWS`, and the two bounds those rows move.
    The subtree still does not exist on disk, which is the state this row was
    written to demand and not a reason to soften it.

    It matters more here than it did for Go. When this repository judges
    ITSELF, `Path(__file__).parent` IS inside the tree under judgement, so
    "dispatcher-owned" and "branch-writable" stop being opposites, and the
    resolution rule alone stops being sufficient. The floor is what restores
    the distinction, and a 9.1 MB third-party blob is exactly the artifact
    nobody re-reads in a diff.

    This seal was P4's to satisfy, not P3's: `_FLOOR_ROWS` in
    `tests/test_role_protocol_floor.py` is a written-out table P3 may not edit,
    so the glob and its rows are one P4 commit — as the Go subtree's were.

    What this row does NOT cover, stated so its green is not read as more than
    it is. The floor makes editing the vendored bytes a VIOLATION when a
    trusted run reads the diff; it does not make the gate EXECUTE the base's
    copy. For the Go helper those are two separate facts with two separate
    seals, the second being
    `test_the_go_helper_is_read_from_the_base_not_from_the_branch`. Measured
    2026-08-10 rather than inherited: the TS subtree travels from `<base>` by
    the same whole-subtree `ls-tree -r` of the `src/` prefix, with no change to
    `scripts/check_body_branch.sh`. It gets no seal of its own because, unlike
    the Go helper, it cannot be moved out from under that prefix — `main.cjs`
    and `typescript.js` are resolved against `Path(__file__).parent` and
    `test_the_vendored_layout_is_the_flat_named_trio` pins the directory name
    flat, so the placement the Go seal exists to catch is unreachable here.

    Green when: the subtree glob is on the floor.
    Falsify: it is falsified by its own subject — remove the glob and this
    reddens. Measured 2026-08-10 in a clone: removing it reddens this row and
    `test_every_floor_glob_the_ruling_wrote_out_is_in_the_constant`, and
    nothing else.
    """
    expected = f"**/src/claude_dispatcher/{role_protocol.TS_HELPER_PACKAGE_DIR}/**"
    assert expected in role_protocol.FLOOR_GLOBS, (
        f"{expected!r} is not on FLOOR_GLOBS. Nothing may be vendored into "
        "the TS helper subtree until it is: when this repo judges itself, the "
        "package directory is inside the tree under judgement, and the floor "
        "is the only thing that makes 'dispatcher-owned' mean anything there. "
        "This is a P4 commit — the floor's row table is a seal P3 may not edit"
    )


# --------------------------------------------------------------------------- #
# 2 — THE DIGEST, AND WHERE IT IS CHECKED. Operator ruling, 2026-08-10.
#
# RED TODAY, all of it.
#
# The parser is a separately-versioned artifact fetched at install time into a
# dispatcher-owned path and verified against a hash that lives on the floor.
# The constraint that decides whether the scheme works at all is WHERE the
# verification happens:
#
#   a fetch-time-only check leaves a window in which anyone who can write the
#   installed path defeats the whole thing — and the installed path is outside
#   the repository, so `check_body_branch.sh` cannot see it.
#
# So the seals below do not ask "was a digest checked". They ask a question a
# fetch-time check answers WRONG: with the bytes on disk already tampered,
# does the VERDICT PATH still produce a fingerprint? It must not. A parser
# whose bytes do not match the floored digest produces a FAULT, never CHECKED.
#
# WHAT THIS DOES NOT CHANGE, and section 1 still stands: the parser's location
# remains a pure function of the dispatcher's installed location. The scaffold
# rejected `npx` partly because it caches into `~/.npm/_npx`, "a mutable path
# outside FLOOR_GLOBS whose bytes decide a verdict". An install-time fetch
# lands bytes in exactly that kind of path. The difference — the only thing
# that makes it survivable — is that the digest is recomputed at use, so the
# mutable path's bytes stop deciding the verdict the moment they stop matching
# the immutable, floored constant. That constant is in `role_protocol.py`,
# which IS on FLOOR_GLOBS. Section 2 seals that difference and nothing less.
#
# THE RESIDUAL WINDOW, recorded rather than sealed. The scaffold rules the
# resolution and probe to be cached once per PROCESS. So a tamper that lands
# *after* a given gate process has prepared its parser is not caught by that
# process. That is a deliberate scaffold ruling and a seal against it would be
# a seal against the contract; the gate runs a fresh process per judgement, so
# per-process is per-verdict. `_fresh_gate_process` below is how these seals
# simulate that, and naming it is why `_TS_HELPER_PREPARED` is required by name.
# --------------------------------------------------------------------------- #

#: The measured artifact, 2026-08-10, TypeScript 5.9.3. Written out here as
#: well as in the module so that a body author who edits the module constant to
#: match a parser they happened to fetch reddens a seal rather than moving the
#: floor. This is the same instrument as `_FLOOR_ROWS`: a value that must not
#: drift is written twice, on purpose, in two files with different owners.
_MEASURED_PARSER_SHA256 = (
    "3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675"
)
_MEASURED_PARSER_BYTES = 9_112_572


@pytest.fixture
def _fresh_gate_process(monkeypatch: pytest.MonkeyPatch):
    """Clear the once-per-process parser cache, as a new gate invocation would.

    The scaffold caches the resolution and the probe in memory for the life of
    the process (`_GO_HELPER_PREPARED`'s argument, which it says transfers
    whole). A seal about what happens at USE therefore has to be able to say
    "this is a new use", and the only way to say that inside one pytest process
    is to clear the cache.

    That REQUIRES the cache to have a name this file can reach, so this seal
    fixes one: `role_protocol._TS_HELPER_PREPARED`, the exact analogue of
    `_GO_HELPER_PREPARED`. It is a small constraint on the implementation and
    it is stated openly rather than smuggled — without it, "verified at use"
    has no falsifiable form at all.

    **P4 ADJUDICATION, 2026-08-10: the coupling is ALLOWED, and the contract
    now names the same global.** The seal author was right to flag it and right
    to keep it: a seal that reaches for a private name is depending on a
    contract, and the fix is to write the contract down, not to delete the
    dependency. `TypeScriptSignatureFingerprinter.fingerprints` now specifies
    `_TS_HELPER_PREPARED` by name, that it starts `None`, and that rebinding it
    to `None` must force a re-resolve, re-probe and re-verify. So this fixture
    no longer asserts a name of its own invention against an implementation
    that was never told about it — P3 reads the requirement where P3 reads
    everything else.

    What was REFUSED, because it is the reform this dispute invites: a public
    reset entry point. The cache is per-process by contract and a gate runs a
    fresh process per verdict, so no production caller has a reason to reset
    it; a public reset would be new machinery on the verdict path whose only
    user is a test, and the argument for adding it would be exactly the
    argument that `npx` and an env-var override were rejected on. A private
    name that a seal reaches into is honest about being a test seam. A public
    one would not be.
    """
    if not hasattr(role_protocol, "_TS_HELPER_PREPARED"):
        pytest.fail(
            f"{_UNIMPLEMENTED}: role_protocol._TS_HELPER_PREPARED does not "
            "exist. The once-per-process parser cache must be reachable by "
            "name, because 'the digest is verified at USE' is only falsifiable "
            "if a seal can say 'this is a new use'. Mirror _GO_HELPER_PREPARED"
        )

    def _reset() -> None:
        monkeypatch.setattr(role_protocol, "_TS_HELPER_PREPARED", None)

    _reset()
    return _reset


@pytest.fixture
def vendored_parser_copy(monkeypatch: pytest.MonkeyPatch):
    """A writable copy of the vendored trio, INSIDE the package, torn down after.

    Section 2 has to tamper with the parser's bytes, and it may not tamper with
    the shipped ones: this is a test, and a test that leaves the gate's own
    parser corrupted has broken the machine it was measuring.

    It cannot use `tmp_path` either, because `ts_parser_home` enforces
    containment — a parser reached outside the package is refused by design,
    which is the belt-and-braces symlink check. So the copy goes into a
    uniquely named sibling directory inside the package and is removed in
    teardown whatever happens.

    Yields the directory, or fails loudly if there is nothing to copy — which
    is the state today, and the reason every seal in this section is red.
    """
    try:
        source = role_protocol.ts_parser_home()
    except ComparatorUnavailable as exc:
        pytest.fail(
            f"{_NO_PARSER}: {exc.fault.value}: {exc.message}. Section 2 cannot "
            "measure where a digest is checked until there is a parser whose "
            "digest could be checked. This seal is red for absence and it must "
            "not be made to skip: a digest seal that skips is the exact shape "
            "of the defect it exists to catch"
        )

    package = Path(role_protocol.__file__).parent.resolve()
    scratch = package / f"{role_protocol.TS_HELPER_PACKAGE_DIR}__sealtmp"
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        shutil.copytree(source, scratch)
        monkeypatch.setattr(role_protocol, "TS_HELPER_PACKAGE_DIR", scratch.name)
        yield scratch
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_the_floored_digest_is_a_module_constant_and_it_is_the_measured_one() -> None:
    """The expected digest lives in `role_protocol.py`, which is on the floor.

    RED TODAY: the constant does not exist yet.

    Where the expected value lives is the whole scheme. A digest read from a
    file beside the parser is not a check, it is a formality — whoever wrote
    the parser wrote the manifest. The expected value has to sit in a file the
    branch cannot edit without a floor violation, and `role_protocol.py` is
    already the first entry on `FLOOR_GLOBS`.

    The size is pinned beside the hash because it is the cheap half: a
    truncated or swapped file is caught by a comparison that costs no read.

    Green when: the constant is a 64-character lowercase hex string equal to
    the measured digest of TypeScript 5.9.3, and the byte count matches.
    Falsify: move the expected digest into
    `ts_signature_fingerprint/SHA256SUMS` and read it from there — the
    `hasattr` assertion reddens, and it stays red however faithfully the file
    is parsed, because a manifest beside the artifact is not a floor.
    """
    assert hasattr(role_protocol, "TS_VENDORED_PARSER_SHA256"), (
        f"{_UNIMPLEMENTED}: role_protocol.TS_VENDORED_PARSER_SHA256 does not "
        "exist. The floored digest must be a constant in role_protocol.py — "
        "the first entry on FLOOR_GLOBS — and never a manifest beside the "
        "parser, which whoever wrote the parser also wrote"
    )
    digest = role_protocol.TS_VENDORED_PARSER_SHA256
    assert isinstance(digest, str) and len(digest) == 64, (
        f"the floored digest is {digest!r}, not a 64-character sha256 hex"
    )
    assert digest == digest.lower(), "the floored digest must be lowercase hex"
    assert digest == _MEASURED_PARSER_SHA256, (
        "the floored digest is not the measured one. This file writes the "
        "measured value out a second time on purpose: a body author who edits "
        "the module constant to match whatever parser they fetched has moved "
        "the floor, and moving the floor must redden a seal rather than pass"
    )
    assert hasattr(role_protocol, "TS_VENDORED_PARSER_BYTES"), (
        f"{_UNIMPLEMENTED}: role_protocol.TS_VENDORED_PARSER_BYTES does not "
        "exist. Asserted with `hasattr` rather than read through a "
        "`getattr(..., default)`, because a default here would make this row "
        "pass by the constant being ABSENT — which is this file's own version "
        "of the vacuity it exists to refuse"
    )
    assert role_protocol.TS_VENDORED_PARSER_BYTES == _MEASURED_PARSER_BYTES, (
        f"the pinned byte count is "
        f"{role_protocol.TS_VENDORED_PARSER_BYTES}, not the measured "
        f"{_MEASURED_PARSER_BYTES}"
    )


def test_the_verdict_path_recomputes_the_digest_from_the_bytes_on_disk(
    vendored_parser_copy: Path, _fresh_gate_process
) -> None:
    """A tampered parser FAULTS. This is the fetch-time-versus-use-time seal.

    RED TODAY, for absence of a parser.

    THE QUESTION THIS ASKS, and why a fetch-time check answers it wrong. The
    bytes are tampered with here *after* installation and *before* the gate
    process prepares its parser — which is precisely the window the operator
    ruling names: "anyone who can write the installed path defeats the whole
    scheme, and the installed path is outside the repo, so
    check_body_branch.sh cannot see it."

    An implementation that verified the digest when it fetched the artifact and
    recorded a boolean, or wrote a stamp file, sails through this: nothing it
    checks has changed. An implementation that hashes the bytes it is about to
    load cannot.

    Note what is asserted and what is not. It is not asserted that the fault is
    raised from any particular function, and it is not asserted that the
    message says "digest" — a body author may name it however they like. What
    is asserted is the only thing that matters: **no fingerprint comes back.**

    Green when: a byte-tampered parser raises `ComparatorUnavailable` and never
    returns a mapping.

    Falsify, MEASURED against the reference implementation: making the
    verification a no-op — the code shape a fetch-time-only design leaves
    behind, where the runtime trusts a check somebody else already did —
    reddens this seal and
    `test_the_module_constant_is_the_authority_over_the_bytes_on_disk`, and
    nothing else in the suite. Neither can be made green again without putting
    a recomputation back on the path that produces the verdict.
    """
    parser = vendored_parser_copy / role_protocol.TS_VENDORED_PARSER
    original = parser.read_bytes()
    assert hashlib.sha256(original).hexdigest() == _MEASURED_PARSER_SHA256, (
        "the copied parser is not the measured artifact; this seal has nothing "
        "meaningful to tamper with"
    )

    # One byte, in the middle, in a comment-safe position is not the point —
    # the point is that the bytes that get LOADED are not the floored ones.
    parser.write_bytes(original + b"\n// tampered by test_ts_comparator\n")

    with pytest.raises(ComparatorUnavailable) as caught:
        _FP.fingerprints(_TS, "export function f(a: string): void {}\n")

    assert caught.value.fault in (
        ComparatorFault.HELPER_MISSING,
        ComparatorFault.TOOLCHAIN_UNUSABLE,
    ), (
        f"a parser whose bytes do not match the floored digest produced "
        f"{caught.value.fault.value}. It must be an apparatus fault; the six "
        "existing faults cover it and unit D4 adds no seventh"
    )


def test_a_parser_that_fails_its_digest_never_produces_a_checked_verdict(
    vendored_parser_copy: Path, _fresh_gate_process, compare_ts
) -> None:
    """The same fact, one level up: through the protocol, it is BLOCKING.

    RED TODAY, for absence of a parser.

    `test_the_verdict_path_recomputes_the_digest_from_the_bytes_on_disk` pins
    that the comparator refuses. This pins what the refusal is worth, which is
    the half that decides a branch's fate: the comparison comes back
    UNCHECKED_COMPARATOR_UNAVAILABLE with no changes, `unsupported_paths` stays
    EMPTY, and it is never CHECKED.

    The empty `unsupported_paths` is not a detail. A fault that leaked into
    `unsupported_paths` would read as "this gate cannot read TypeScript", a
    diff of nothing else would be promoted to UNCHECKED_NO_SUPPORTED_FILE, and
    the branch would come back CLEAN — a poisoned parser buying a certificate,
    which is the exact fail-open `ComparatorFault` exists to name.

    Green when: status is UNCHECKED_COMPARATOR_UNAVAILABLE, no changes, no
    unsupported paths.
    Falsify: catch `ComparatorUnavailable` in `fingerprints` and return `{}` —
    status becomes CHECKED with no changes, this reddens, and that mutation is
    exactly the shape of the certificate this seal refuses to issue.
    """
    parser = vendored_parser_copy / role_protocol.TS_VENDORED_PARSER
    parser.write_bytes(b"module.exports = { version: '5.9.3' };\n")

    result = compare_ts(
        "export function f(a: string): void {}\n",
        "export function f(a: string, b: number): void {}\n",
    )

    assert result.status is SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE, (
        f"a parser that failed its digest produced status "
        f"{result.status.name}. CHECKED here is a certificate bought with a "
        f"parser this build does not vouch for. detail={result.detail!r}"
    )
    assert not result.changes, "a faulted comparison must report no changes"
    assert not result.unsupported_paths, (
        "an environment fault leaked into `unsupported_paths`, which reads as "
        "'this gate cannot read TypeScript' — and a diff of nothing else is "
        "then promoted to UNCHECKED_NO_SUPPORTED_FILE and comes back CLEAN"
    )


def test_the_module_constant_is_the_authority_over_the_bytes_on_disk(
    vendored_parser_copy: Path, _fresh_gate_process, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Change the floored constant and the UNTAMPERED parser must be refused.

    RED TODAY, for absence of a parser.

    The other direction, and the one that proves which value is in charge. The
    two previous seals move the bytes and expect a refusal; this one leaves the
    bytes alone and moves the CONSTANT. If the parser still loads, then the
    constant is decoration and the real authority is something else — a stamp
    file, a cached boolean, or nothing at all.

    Together the three make the property total: the verdict path compares
    *these bytes* against *that constant*, every time it prepares a parser.

    Green when: a mismatched floored digest refuses a pristine parser.
    Falsify: compute the expected digest from the file itself (`digest =
    sha256(parser.read_bytes())`) — the tamper seals above still pass and this
    one reddens, which is why it is here.
    """
    monkeypatch.setattr(
        role_protocol,
        "TS_VENDORED_PARSER_SHA256",
        "0" * 64,
        raising=False,
    )

    with pytest.raises(ComparatorUnavailable):
        _FP.fingerprints(_TS, "export function f(a: string): void {}\n")


# --------------------------------------------------------------------------- #
# 3 — trap 1: the key grammar, and the collision property
#
# GREEN TODAY. `ts_symbol_key` is one of the two things the scaffold implements
# rather than stubs, precisely so this property has a callable subject.
# --------------------------------------------------------------------------- #


#: Member names that spell the markers. Every one of these is legal TypeScript
#: in the position it occupies — a member name is not required to be an
#: identifier, so `/` and `:` are both reachable, which is strictly worse than
#: the Go unit's `embedded` collision.
_NAMES_THAT_SPELL_A_MARKER: tuple[str, ...] = (
    "a/b",
    "i:x",
    "s:x",
    "c:x",
    "k:default",
    "k:export",
    "i:I/i:m",
    "\\",
    "\\/",
    "a\\/b",
    "//",
    ":",
    # THE ROW THAT MAKES THE `/` ESCAPING FALSIFIABLE, and it took a measurement
    # to find. Most names that merely CONTAIN a separator collide with nothing,
    # because the other segments differ anyway. This one is built to collide:
    # unescaped it renders as `i:I/s:a/s:b`, which is exactly the key of the
    # two-segment symbol `[("i","I"),("s","a"),("s","b")]` — a member `b` of a
    # member `a` of `I`. One name forging another symbol's key IS trap 1, and
    # without this row the escaping could be deleted with nothing going red.
    "a/s:b",
)


@pytest.mark.parametrize("name", _NAMES_THAT_SPELL_A_MARKER)
def test_a_member_name_cannot_forge_a_key_that_belongs_to_another_symbol(
    name: str,
) -> None:
    """Trap 1, sealed as a property rather than as a list of bad names.

    Go's embed marker was defeated by a struct field literally named
    `embedded`: a marker a name can spell is not a marker. TypeScript makes it
    much easier to hit, because `interface I { "a/b": string; "i:x": number }`
    is ordinary code and puts the separator and the tag prefix *in the member
    position*.

    The property is not "these twelve names are handled". It is: **for any two
    different segment lists, the keys differ.** That is what stops one symbol
    answering to another's key, which is what would make a real change read as
    no change at all — the symbol matched across revisions would be the wrong
    one.

    Green when: a member whose NAME spells a marker keys differently from the
    symbol that marker names.

    Falsify: drop the `/` escaping from `ts_symbol_key`. The `a/s:b` row then
    renders as `i:I/s:a/s:b`, which is the key of a member `b` of a member `a`
    of `I`, and the nested-key assertion below reddens.

    A MEASUREMENT THAT CORRECTED THIS DOCSTRING, recorded because the wrong
    version of it was written first. Dropping the BACKSLASH escaping does NOT
    redden this seal, and it was verified in a clone that it does not (mutation
    M2). The reason is that escaping `/` alone is already an injective map — a
    key can still be decoded unambiguously by scanning for `\\/` — so no two
    names collide. The backslash escaping is defensive rather than
    collision-bearing, and this file does not claim a falsification it does not
    have. The property that carries trap 1 is the `/` escaping, and it is
    falsifiable by exactly one row of the table above.
    """
    forged = ts_symbol_key([("i", "I"), ("s", name)])

    assert forged != ts_symbol_key([("i", "I"), ("s", "a"), ("s", "b")]), (
        f"a member named {name!r} forged the key of a NESTED symbol — the "
        "member `b` of the member `a` of `I`. A separator a name can spell is "
        "not a separator, which is trap 1 in its original form"
    )

    for other in _NAMES_THAT_SPELL_A_MARKER:
        if other == name:
            continue
        assert forged != ts_symbol_key([("i", "I"), ("s", other)]), (
            f"the member names {name!r} and {other!r} produce the same key. "
            "Two symbols answering to one key means one is unreachable, and "
            "which one wins is decided by dict insertion order"
        )

    assert forged != ts_symbol_key([("i", "I"), ("i", "m")]), (
        f"a member named {name!r} forged the key of a different symbol"
    )
    assert forged != ts_symbol_key([("k", "default")]), (
        f"a member named {name!r} reached the anonymous-default-export slot; "
        "the `k` tag exists so that a position no identifier can name is a "
        "position no identifier can FORGE"
    )
    assert forged.startswith("i:I/s:"), (
        "the LEADING tag is what is read and the rest of the segment is data; "
        f"{forged!r} does not have that shape"
    )


def test_the_documented_key_positions_are_all_representable_and_all_distinct() -> None:
    """Every key shape the contract names can be built, and none collides.

    The `k` tag is the piece with no Go analogue and it is the reason tags
    exist at all rather than a bare escape: TypeScript has declaration
    positions with no name — an anonymous `export default class {}`, a call
    signature, an index signature — and the obvious keys for them (`default`,
    `index`, `call`) are ordinary spellable identifiers.

    **P4, 2026-08-10 — the contract's own worked example is now checked against
    the function.** The scaffold cited the star re-export's key as
    `k:export/k:star/s:./m`, unescaped. That is not a key `ts_symbol_key` can
    produce: the `/` inside a module specifier is escaped exactly as the `/`
    inside a member name is, and unescaped it spells the segment separator, so
    `./m` would key as two segments. A reader checking the example against the
    function would have concluded the function was wrong. Corrected in the
    docstring under this repository's standing ruling against a citation that
    sends a reader to something they cannot reproduce — and pinned HERE, so the
    ruling has an enforcement rather than a note: the example the contract
    prints must be the string the function returns.

    Green when: all documented positions build, the set is as large as the
    list, and the contract's printed example is the built key.
    Falsify: drop `k` from `TS_KEY_TAGS` — every keyword-slot row raises and
    this reddens. Render a `k` segment as its bare text — `k:default` and a
    top-level declaration named `default` collide. Rewrite the docstring
    example back to its unescaped spelling — the citation assertion reddens
    (measured).
    """
    positions = {
        "top-level declaration": [("i", "f")],
        "member of a declaration": [("i", "C"), ("i", "m")],
        "nested namespace member": [("i", "N"), ("i", "M"), ("i", "f")],
        "call signature": [("i", "I"), ("k", "call")],
        "construct signature": [("i", "I"), ("k", "new")],
        "index signature": [("i", "I"), ("k", "index")],
        "class constructor": [("i", "C"), ("k", "ctor")],
        "ambient module": [("s", "foo")],
        "declare global": [("k", "global")],
        "anonymous default export": [("k", "default")],
        "named export": [("k", "export"), ("i", "b")],
        "star re-export": [("k", "export"), ("k", "star"), ("s", "./m")],
        "string-literal member": [("i", "I"), ("s", "a/b")],
        "computed member": [("i", "I"), ("c", "[Symbol.iterator]")],
    }
    built = {name: ts_symbol_key(segs) for name, segs in positions.items()}

    assert len(set(built.values())) == len(built), (
        "two documented key positions produce the same key: "
        f"{sorted(built.items())}"
    )
    assert built["anonymous default export"] == "k:default"
    assert built["star re-export"] == "k:export/k:star/s:.\\/m"
    assert built["string-literal member"] == "i:I/s:a\\/b", (
        "a `/` inside a member name must be escaped; unescaped it spells the "
        "segment separator, which is trap 1"
    )

    # The contract PRINTS one of these keys as a worked example. It must be the
    # one the function builds, or the example teaches the wrong grammar to
    # everybody who reads the contract instead of the code — which is
    # everybody, because the contract is where the grammar is stated.
    cited = role_protocol.TypeScriptSignatureFingerprinter.__doc__ or ""
    assert built["star re-export"] in cited, (
        f"the contract does not print {built['star re-export']!r} as the key "
        "of `export * from './m'`. Whatever it prints instead is a key no "
        "input produces, and the `/` escaping is the whole of trap 1 in the "
        "one position — a module specifier — where every real value contains "
        "a separator"
    )


def test_a_key_built_from_a_helper_bug_is_refused_rather_than_returned() -> None:
    """An empty segment list, an unknown tag or empty text is an error.

    All three are helper bugs rather than facts about a file, and a key built
    from a bug matches nothing across revisions — which reports every symbol in
    the file as removed AND added. Removed is a change, so the branch fails
    noisily; but the added half is the direction that clears, and a partially
    keyed file would clear the part it dropped.

    The closed tag set is what makes this checkable: an open set could not tell
    a bug from a new position.

    Green when: all three raise `RoleProtocolError`.
    Falsify: make the tag check a warning and pass the tag through — the
    unknown-tag row reddens, and a helper emitting `x:foo` would key symbols
    nothing ever matches.
    """
    with pytest.raises(RoleProtocolError):
        ts_symbol_key([])
    with pytest.raises(RoleProtocolError):
        ts_symbol_key([("x", "f")])
    with pytest.raises(RoleProtocolError):
        ts_symbol_key([("i", "")])
    assert role_protocol.TS_KEY_TAGS == frozenset({"i", "s", "c", "k"}), (
        "the tag set is closed so that no member name can spell one; opening "
        "it reopens trap 1"
    )


# --------------------------------------------------------------------------- #
# 4 — the rulings table's own shape
#
# GREEN TODAY. This is the dataclass half, and it is asserted separately from
# section 5 on purpose: `test_role_protocol_faults.py` does exactly this for the
# Go table and does not touch the comparator, which is how the Go hole survived.
# Doing only this half is vacuity trap 3; doing neither is worse.
# --------------------------------------------------------------------------- #


def test_the_table_rules_both_ways_and_still_has_its_controls() -> None:
    """A rulings table that only ever says one thing rules nothing.

    The controls are named individually rather than counted, because the count
    is satisfied by any four rows and the JOB is done by these four: a rewritten
    body, rewritten JSX, a requoted string literal, and an un-annotated
    initialiser. Each one forbids a different cheap comparator. Without the body
    row, "changed" to everything passes. Without the JSX row, a comparator that
    read `.tsx` markup passes. Without the requoting row, a comparator built on
    `ts.createPrinter` passes. Without the un-annotated row, a comparator that
    guessed at inference passes.

    **P4 ADJUDICATION, 2026-08-10 — `a class method added` LEFT this list.**
    It was a control here and it is now ruled a change, because the scaffold
    contradicted itself: the same contract said a method's rendering is inside
    the class fingerprint AND that adding one is not a change. The ruling is at
    `TypeScriptSignatureFingerprinter` and the row is at
    `TS_SIGNATURE_EDIT_RULINGS`; this seal follows it rather than the other way
    round, which is the rule this file states everywhere else ("reopen it
    there, not here"). Six controls remain and each still forbids a distinct
    cheap comparator, so nothing this list was doing is lost — the row was the
    seventh, not the load-bearing one. What IS lost is the Python parity
    measurement that row carried, and it is replaced rather than dropped: see
    `test_the_class_method_parity_break_is_measured_and_not_a_drift`.

    Green when: both answers are present and all six controls rule silent.
    Falsify: flip `is_a_change` on the body-rewrite row — a gate nobody can
    pass, and this reddens. Delete the requoting row — the third assertion
    reddens and section 6's whole argument loses its anchor in the table.
    """
    rulings = {r.name: r for r in role_protocol.TS_SIGNATURE_EDIT_RULINGS}

    controls = (
        "body rewritten, declaration untouched",
        "JSX markup rewritten in a component body",
        "a string-literal type requoted",
        "an un-annotated const's initialiser changed",
        "interface members reordered",
        "destructured parameter's bindings reordered",
    )
    for name in controls:
        assert name in rulings, (
            f"the control row {name!r} is gone. Without it a comparator that "
            "calls everything a change satisfies this table, which is a gate "
            "nobody can pass and therefore a gate everybody routes around"
        )
        assert rulings[name].is_a_change is False, (
            f"{name!r} stopped being a control; it is now a change and the "
            "table has lost the row that made it falsifiable in that direction"
        )

    load_bearing = (
        "parameter renamed",
        "same-type parameters reordered",
        "type parameters reordered",
        "an overload added",
        "two overloads reordered",
        "export removed from a declaration",
        "a public name re-exported under a different alias",
        "a decorator's argument changed",
        "enum members reordered",
        "a class property added",
        # P4, 2026-08-10. Moved here from `controls` by the class-method
        # ruling. It sits beside `a class property added` on purpose: the two
        # rows are now one rule with one reason, where before they were two
        # answers the contract could not both justify.
        "a class method added",
        "an arrow const's declared signature changed",
        "a component's props type gains a required member",
        "a required property made optional",
    )
    for name in load_bearing:
        assert rulings[name].is_a_change is True, (
            f"{name!r} is ruled a change at TS_SIGNATURE_EDIT_RULINGS; reopen "
            "it there rather than by editing this row"
        )

    answers = {r.is_a_change for r in role_protocol.TS_SIGNATURE_EDIT_RULINGS}
    assert answers == {True, False}, (
        f"a rulings table that only ever says {answers} rules nothing"
    )


@pytest.mark.parametrize(
    "ruling", role_protocol.TS_SIGNATURE_EDIT_RULINGS, ids=lambda r: r.name
)
def test_every_ruled_edit_is_a_real_edit_in_a_registered_dialect(
    ruling: TsSignatureEditRuling,
) -> None:
    """Each row is a genuine edit, with a reason, in a path the row can select.

    Without this a row can be "ruled" with `before == after`, which no
    comparator can fail and which reads in a report exactly like a row that
    passed.

    The extension assertion is the TypeScript-specific half and it is not
    decoration: `path` is on this dataclass because it selects the parse
    DIALECT, so a row whose path is not in `TYPESCRIPT_SUPPORT.extensions` is a
    row the comparator would never be asked. `.mts` is the live trap — it is
    NOT covered by the `.ts` entry, because matching is a suffix match and
    `".mts".endswith(".ts")` is false.

    Parametrised over the live tuple, so a row added tomorrow is covered the
    moment it is added.

    Green when: every row differs, is reasoned, and names a covered dialect.
    Falsify: set any row's `after` equal to its `before`; or add a row on a
    `.mts` path.
    """
    assert ruling.before != ruling.after, f"{ruling.name}: not an edit at all"
    assert ruling.rationale.strip(), f"{ruling.name}: ruled with no reason given"
    assert ruling.before.strip() and ruling.after.strip(), (
        f"{ruling.name}: an empty revision is not a ruled edit"
    )
    assert any(
        ruling.path.endswith(ext)
        for ext in role_protocol.TYPESCRIPT_SUPPORT.extensions
    ), (
        f"{ruling.name}: path {ruling.path!r} is not selected by any extension "
        f"in {role_protocol.TYPESCRIPT_SUPPORT.extensions}. The row would "
        "never be asked of the comparator — and note `.mts` is not covered by "
        "`.ts`, because matching is a suffix match"
    )


@pytest.mark.parametrize(
    "ruling",
    [r for r in role_protocol.TS_SIGNATURE_EDIT_RULINGS if r.python_analogue],
    ids=lambda r: r.name,
)
def test_the_ruled_answer_is_what_the_live_python_comparator_already_gives(
    ruling: TsSignatureEditRuling,
) -> None:
    """The parity claims, MEASURED against the comparator that exists today.

    This is the strongest assertion available while the TypeScript comparator
    is a contract. It cannot check TypeScript, but it can prove the ruling is
    not inventing a standard TypeScript alone would be held to: the rename IS a
    change in Python, the same-type reorder IS, a body rewrite is NOT, and
    adding an annotated class attribute IS — all four measured rather than
    asserted.

    The rows with `python_analogue=None` are the recorded claim that the
    languages differ there or that Python has no such shape, and their absence
    from this parametrisation is deliberate. Top-level `const` is the loudest
    of them: it is a deliberate parity BREAK, so asserting parity for it would
    assert the opposite of the ruling.

    **P4, 2026-08-10: `a class method added` left this parametrisation**, from
    four measured claims to three plus one measured BREAK. It was ruled a
    change for TypeScript, Python still answers NOT a change, and a row whose
    analogue disagrees with it reddens here by design — which is this seal
    working, not this seal being in the way. The honest move is the one the
    `const` rows already model: `python_analogue=None` records that the
    languages differ. What that spelling cannot do is prove they still differ,
    so the break is measured in its own seal below rather than left as prose.

    Green when: every analogue agrees with the row's ruled answer.
    Falsify: rule "a class property added" NOT a change while Python still
    reports one — this reddens, which is what stops a TypeScript ruling
    drifting away from the language it claims parity with.
    """
    assert ruling.python_analogue is not None
    before, after = ruling.python_analogue
    result = compare_signatures("pkg/m.py", before, after)

    assert result.status is SignatureCheckStatus.CHECKED, (
        f"the analogue for {ruling.name!r} did not even parse: {result.detail}"
    )
    assert bool(result.changes) is ruling.is_a_change, (
        f"{ruling.name!r} is ruled "
        f"{'a change' if ruling.is_a_change else 'NOT a change'} for "
        "TypeScript, and its own Python analogue disagrees. Either the "
        "analogue is not the same edit, or the parity claim is wrong; both are "
        "questions for TS_SIGNATURE_EDIT_RULINGS, not for this file"
    )


#: The class-method edit, transliterated to Python. Written out HERE rather
#: than carried on the ruling row, because the row's `python_analogue` field
#: means "the languages agree" and they do not: the whole point of this seal is
#: the disagreement. Same two revisions the ruling row uses, one language over.
_CLASS_METHOD_IN_PYTHON = (
    "class Svc:\n    def do(self, a):\n        pass\n",
    "class Svc:\n    def do(self, a):\n        pass\n"
    "    def _helper(self, b):\n        pass\n",
)


def test_the_class_method_parity_break_is_measured_and_not_a_drift() -> None:
    """Adding a class method: a change in TypeScript, NOT one in Python.

    GREEN TODAY — it asks the live Python comparator and a dataclass, and
    neither needs a TypeScript parser.

    P4, 2026-08-10, and it exists because a ruling took something away. `a
    class method added` used to carry a `python_analogue`, so the claim "this
    row agrees with Python" was MEASURED. The class-method adjudication makes
    the row a change while Python still answers not-a-change, so the analogue
    had to go — and with it, silently, the measurement. `python_analogue=None`
    is the right value (it is what the top-level `const` rows use for their own
    deliberate break) and it is a claim nothing checks: a field that is absent
    proves nothing about the language it stopped comparing against.

    So the break is measured as a BREAK. That is a strictly stronger seal than
    the parity row it replaces, because it fails in two directions where the
    old row failed in one:

      * the TypeScript ruling drifting back to silent — assertion 1;
      * the row quietly re-acquiring an analogue, which would put it back in a
        parametrisation that would then redden for the right reason in the
        wrong file — assertion 2;
      * Python's own comparator changing under it, so that the two languages
        stop differing and the "deliberate break" becomes a stale story —
        assertion 3.

    The class PROPERTY row is asserted alongside, and that pairing is the
    point rather than thoroughness: property and method are ONE rule in
    TypeScript now, and they are TWO rules in Python. A seal that measured only
    the method half would go green on a Python comparator that had stopped
    reading class fields at all, which is the direction that clears branches.

    Green when: TypeScript rules it a change, the row carries no analogue,
    Python rules the same edit silent, and Python still rules the property edit
    a change.
    Falsify: set `is_a_change=False` on the row (assertion 1); restore its
    `python_analogue` (assertion 2); make `_class_fingerprint` render methods
    (assertion 3, and Python would then agree with TypeScript rather than
    differ from it).
    """
    rulings = {r.name: r for r in role_protocol.TS_SIGNATURE_EDIT_RULINGS}
    method_row = rulings["a class method added"]

    assert method_row.is_a_change is True, (
        "adding a class method is ruled a CHANGE for TypeScript (P4, "
        "2026-08-10): the class fingerprint renders its members in full, "
        "because no rendering position in this grammar is name-only and "
        "sub-symbols are never the sole storage of a signature. Reopen it at "
        "TS_SIGNATURE_EDIT_RULINGS, not here"
    )
    assert method_row.python_analogue is None, (
        "this row is a deliberate parity BREAK, so it may not carry a "
        "`python_analogue` — that field is the claim that the languages agree, "
        "and asserting it here would assert the opposite of the ruling"
    )

    before, after = _CLASS_METHOD_IN_PYTHON
    python = compare_signatures("pkg/m.py", before, after)
    assert python.status is SignatureCheckStatus.CHECKED, (
        f"the Python transliteration did not parse: {python.detail}"
    )
    assert not python.changes, (
        "Python no longer rules 'a body may add private helpers' silent, so "
        "the TypeScript ruling is no longer a parity BREAK — it is now "
        "agreement, and the reasoning recorded at "
        "TypeScriptSignatureFingerprinter and on the ruling row is stale"
    )

    property_row = rulings["a class property added"]
    assert property_row.is_a_change is True
    assert property_row.python_analogue is not None, (
        "the class PROPERTY row's parity claim is what bounds this break: "
        "without it, a Python comparator that had stopped reading class "
        "bodies entirely would satisfy the assertion above"
    )
    property_before, property_after = property_row.python_analogue
    python_property = compare_signatures(
        "pkg/m.py", property_before, property_after
    )
    assert python_property.status is SignatureCheckStatus.CHECKED
    assert python_property.changes, (
        "Python stopped reporting an added annotated class field as a change, "
        "so the silence measured above is a comparator that reads no class "
        "members rather than a rule about methods"
    )


# --------------------------------------------------------------------------- #
# 5 — the rulings table, fed to the LIVE comparator
#
# RED TODAY. This is the half that did not exist for Go until its P2 file did,
# and the half whose absence let a Go comparator with no parameter names sit
# green through enrolment.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "ruling", role_protocol.TS_SIGNATURE_EDIT_RULINGS, ids=lambda r: r.name
)
def test_every_ruled_edit_gets_its_ruled_answer_from_the_live_comparator(
    ruling: TsSignatureEditRuling, compare_ts
) -> None:
    """THE ACCEPTANCE CRITERION, measured.

    Twenty rows, each a complete file, each fed to the real comparator on its
    own ruled path so the dialect is the one the row was written for. The
    rulings are not suggestions and they are not this file's to reopen: a
    disagreement is either a comparator defect or a ruling that needs
    revisiting at `TS_SIGNATURE_EDIT_RULINGS`, and the second is P4's.

    Green when: all twenty agree.

    Verified satisfiable: a reference implementation was built in a throwaway
    clone for this commit — a vendored `typescript.js`, a `main.cjs` that
    renders entirely from the AST, and the Python side — and all twenty rows
    agree with it, with the rest of the suite unchanged at 1994 passed / 13
    skipped. So these rows are red for absence and not because they are
    mutually unsatisfiable.

    **P4, 2026-08-10 — that satisfiability claim NO LONGER COVERS ONE ROW, and
    saying so is the point of writing measurements down.** The reference
    implementation stored class methods as sub-symbols ONLY. It had to: `a
    class method added` was ruled silent, and the scaffold's other sentences
    said the opposite, so an implementer could satisfy one or the other and not
    both. The adjudication rules the class fingerprint carries its members in
    full, so that reference implementation now DISAGREES with this row and
    would be red here. Nineteen rows are measured-satisfiable and one is
    ruled-and-not-yet-measured. It is not re-measured in this commit because
    doing so means building a comparator, which is P3's. What the ruling does
    guarantee is that the row is no longer mutually unsatisfiable with the
    contract, which is what it WAS: an implementation cannot both render a
    class's members and not render them, and before the ruling it was asked to.

    Falsify — every one MEASURED against that reference implementation, with
    the number of seals in this file that each mutation reddens:

      * drop parameter NAMES from the rendering            -> 2 (rename, reorder)
      * render string literals from original source text,
        which is what `printNode` does                     -> 2 (requoting)
      * stop normalising numeric literal spelling          -> 2
      * sort the per-name fold instead of keeping order    -> 2 (overloads)
      * drop the fold, last declaration wins               -> 3
      * render decorator NAMES only, dropping arguments    -> 1
      * sort enum members                                  -> 1
      * hard-code `ScriptKind.TS`, ignoring `.tsx`         -> 4
      * report `parse_error` only when nothing recovered   -> 5
      * render an interface's name but not its members     -> 5
      * render a CLASS's name but not its members          -> not measured,
        and named rather than left out: it is the shape the reference
        implementation had, and after the 2026-08-10 ruling it is a mutation
        rather than the design. It must redden at least `a class method added`
        and `a class property added`; the count is P3's to take on the day
        there is something to count.
      * fingerprint a binding's INITIALISER                -> 3
      * stop reading the export surface                    -> 1
      * stop reading top-level `const`/`let`/`var`         -> 1
    """
    assert (
        _ts_changed(compare_ts, ruling.before, ruling.after, ruling.path)
        is ruling.is_a_change
    ), (
        f"{ruling.name!r} is ruled "
        f"{'a change' if ruling.is_a_change else 'NOT a change'} and the live "
        "TypeScript comparator disagrees. The ruling is the acceptance "
        "criterion; reopen it at TS_SIGNATURE_EDIT_RULINGS, not here"
    )


# --------------------------------------------------------------------------- #
# 6 — THE RENDERER IS NOT THE PRINTER
#
# RED TODAY.
#
# `ts.createPrinter().printNode(node, sourceFile)` reuses ORIGINAL SOURCE TEXT
# (measured 2026-08-10), so `type A = 'x'` and `type A = "x"` print differently.
# A fingerprint built on it reports a signature change for every string-literal
# type in a 996-file repository the day someone changes a Prettier setting. The
# rulings table has one row for this and one row is not enough: the cheapest way
# to pass one row is to special-case string quoting and leave every other
# source-text dependency in place.
#
# So this section is built out of PAIRS. `_SPELLING` is respelling that must be
# silent; `_AND_THE_SAME_POSITION_STILL_MOVES` is a real change in the SAME
# syntactic position that must still be caught. The pairing is the anti-vacuity
# device and it is the whole point of the section: a renderer that normalises by
# DELETING — dropping string-literal types, dropping numeric literal types,
# dropping parenthesised types — passes every row of the first table and fails
# its partner in the second.
# --------------------------------------------------------------------------- #

#: Respelling. Two revisions that mean the same thing to every consumer. Each
#: row is a complete file. Silent, every one.
_SPELLING: tuple[tuple[str, str, str], ...] = (
    (
        "string literal type requoted",
        "export type Mode = 'live' | 'draft';\n",
        'export type Mode = "live" | "draft";\n',
    ),
    (
        "numeric literal type respelled",
        "export type Limit = 1000;\n",
        "export type Limit = 1_000;\n",
    ),
    (
        "numeric literal type respelled in hex",
        "export type Mask = 255;\n",
        "export type Mask = 0xff;\n",
    ),
    (
        "redundant parentheses around a type",
        "export function f(a: string): void {}\n",
        "export function f(a: (string)): void {}\n",
    ),
    (
        "object type member separator changed from ; to ,",
        "export interface Bet { id: string; amountCents: number }\n",
        "export interface Bet { id: string, amountCents: number }\n",
    ),
    (
        "object type members put on separate lines",
        "export interface Bet { id: string; amountCents: number }\n",
        "export interface Bet {\n  id: string;\n  amountCents: number;\n}\n",
    ),
    (
        "trailing comma added to a parameter list",
        "export function f(a: string, b: number): void {}\n",
        "export function f(\n  a: string,\n  b: number,\n): void {}\n",
    ),
    (
        "type parameter list reflowed",
        "export type Pair<K, V> = { key: K; value: V };\n",
        "export type Pair<\n  K,\n  V,\n> = { key: K; value: V };\n",
    ),
    (
        "declaration reindented",
        "export class Svc {\n  do(a: string): void {}\n}\n",
        "export class Svc {\n\t\tdo(a: string): void {}\n}\n",
    ),
    (
        "a JSDoc comment added above a declaration",
        "export function f(a: string): void {}\n",
        "/** Does the thing.\n * @param a the thing\n */\n"
        "export function f(a: string): void {}\n",
    ),
)

#: The partner table, and the reason `_SPELLING` cannot be passed by deletion.
#: Every row moves the SAME syntactic position one of the rows above respells.
#: A renderer that drops string-literal types to make the requoting row silent
#: makes row 1 here silent too, and row 1 here is a real contract change.
_AND_THE_SAME_POSITION_STILL_MOVES: tuple[tuple[str, str, str], ...] = (
    (
        "a string literal type's VALUE changed",
        "export type Mode = 'live' | 'draft';\n",
        "export type Mode = 'live' | 'settled';\n",
    ),
    (
        "a string literal type constituent removed",
        "export type Mode = 'live' | 'draft';\n",
        "export type Mode = 'live';\n",
    ),
    (
        "a numeric literal type's VALUE changed",
        "export type Limit = 1000;\n",
        "export type Limit = 2000;\n",
    ),
    (
        "a parenthesised type's INNER type changed",
        "export function f(a: (string)): void {}\n",
        "export function f(a: (number)): void {}\n",
    ),
    (
        "an object type member's TYPE changed, separator untouched",
        "export interface Bet { id: string; amountCents: number }\n",
        "export interface Bet { id: string; amountCents: string }\n",
    ),
    (
        "an object type member added across a reflow",
        "export interface Bet { id: string; amountCents: number }\n",
        "export interface Bet {\n  id: string;\n  amountCents: number;\n"
        "  currency: string;\n}\n",
    ),
    (
        "a parameter added across a reflow",
        "export function f(a: string, b: number): void {}\n",
        "export function f(\n  a: string,\n  b: number,\n  c: boolean,\n): void {}\n",
    ),
    (
        "a type parameter constrained across a reflow",
        "export type Pair<K, V> = { key: K; value: V };\n",
        "export type Pair<\n  K extends string,\n  V,\n> = { key: K; value: V };\n",
    ),
    (
        "a method's parameter retyped across a reindent",
        "export class Svc {\n  do(a: string): void {}\n}\n",
        "export class Svc {\n\t\tdo(a: number): void {}\n}\n",
    ),
    (
        "a declaration retyped under an added JSDoc comment",
        "export function f(a: string): void {}\n",
        "/** Does the thing. */\nexport function f(a: number): void {}\n",
    ),
)


@pytest.mark.parametrize(
    "name, before, after", _SPELLING, ids=[r[0] for r in _SPELLING]
)
def test_respelling_a_declaration_is_not_a_signature_change(
    name: str, before: str, after: str, compare_ts
) -> None:
    """Formatting is not contract, and the renderer must not depend on source text.

    RED TODAY.

    Row 1 is the one the scaffold calls the largest concrete implementation
    hazard, and rows 2-10 are why one row was not enough: the printer's reuse of
    original source text is not a quirk of string quoting, it is the printer's
    design, and every position where a body author's formatter can reach is a
    position where it manufactures a signature change.

    A gate that reports a contract change when Prettier's `singleQuote` flips
    is a gate that reports 996 violations on a formatting commit, and a gate
    that does that once is a gate whose output nobody reads again.

    Green when: every respelling is silent.

    Falsify, MEASURED against the reference implementation built for this
    commit: render string literals from the original source text — which is
    exactly what `printNode` does, confirmed on TypeScript 5.9.3, where `type
    A = 'x'` and `type A = "x"` print with their original quotes — and the
    requoting row reddens here and in the rulings table. Stop normalising
    numeric literal spelling and both numeric rows redden. The general form is
    `node.getText()`: any use of it reintroduces the whole class.
    """
    assert _ts_changed(compare_ts, before, after) is False, (
        f"{name}: two revisions that mean the same thing to every consumer "
        "fingerprinted differently. The renderer must not depend on original "
        "source text — see the normalisation list on "
        "TypeScriptSignatureFingerprinter, and the requoting row of "
        "TS_SIGNATURE_EDIT_RULINGS"
    )


@pytest.mark.parametrize(
    "name, before, after",
    _AND_THE_SAME_POSITION_STILL_MOVES,
    ids=[r[0] for r in _AND_THE_SAME_POSITION_STILL_MOVES],
)
def test_the_same_position_still_catches_a_real_change(
    name: str, before: str, after: str, compare_ts
) -> None:
    """The partner table. Normalising may not become deleting.

    RED TODAY.

    This is the seal that stops the section above being satisfied the cheap
    way. Each row moves the same syntactic position one of the `_SPELLING` rows
    respells, so the two tables cannot be satisfied by the same shortcut:

      * drop string-literal types from the rendering -> `_SPELLING` row 1 goes
        silent and rows 1 and 2 here go silent with it;
      * drop numeric-literal types -> `_SPELLING` rows 2-3 pass and row 3 here
        fails;
      * unwrap and then discard parenthesised types -> row 4 here fails;
      * render an object type as its member NAMES only, which normalises every
        separator and reflow at a stroke -> `_SPELLING` rows 5-6 pass and row 5
        here fails, which is trap 2 arriving by the back door;
      * render a parameter list as its arity -> `_SPELLING` rows 7-8 pass and
        rows 7-8 here fail.

    Green when: every row is caught.

    Falsify: any of the five shortcuts above. The fourth was MEASURED against
    the reference implementation — rendering an interface's name and heritage
    but not its members reddens five seals, two of them rows of THIS table
    ("an object type member's TYPE changed" and "an object type member added
    across a reflow") while every `_SPELLING` row stays green. That is the
    pairing doing precisely the job it is here for.
    """
    assert _ts_changed(compare_ts, before, after) is True, (
        f"{name}: a real contract change in a position this section also asks "
        "to be normalised. Normalisation that reaches this row is deletion — "
        "the signal went out with the noise"
    )


def test_the_normalisation_tables_are_paired_and_rule_both_ways() -> None:
    """The two tables above are the same size and pair up, row for row.

    GREEN TODAY.

    A structural seal on this file rather than on the comparator, and it earns
    its place: the pairing IS the argument, and a pairing that quietly loses
    half its rows still runs, still reports green for whatever survives, and
    stops proving the thing the section claims. If a future author adds a
    respelling they must add its partner, and this is where they find out.

    Green when: both tables are the same length, names are unique, and no row
    is a non-edit.
    Falsify: delete a row from `_AND_THE_SAME_POSITION_STILL_MOVES`.
    """
    assert len(_SPELLING) == len(_AND_THE_SAME_POSITION_STILL_MOVES), (
        "the respelling table and its partner have drifted apart. Every "
        "respelling that must be silent needs a real change in the SAME "
        "position that must not be, or 'normalised' and 'deleted' become "
        "indistinguishable"
    )
    for table in (_SPELLING, _AND_THE_SAME_POSITION_STILL_MOVES):
        names = [row[0] for row in table]
        assert len(names) == len(set(names)), f"duplicate probe names: {names}"
        for _, before, after in table:
            assert before != after, "a probe whose two revisions are equal proves nothing"


# --------------------------------------------------------------------------- #
# 7 — ONE KEY PER NAME, and the empty answer
#
# RED TODAY (except the last seal).
#
# The fold is what makes the scheme total. Three `function f` declarations are
# three nodes with one name; separate keys would be a DUPLICATE KEY, which
# `decode_ts_helper_response` must refuse as HELPER_OUTPUT_INVALID — i.e. the
# gate faulting on ordinary, legal, compiling code. This is the one place where
# getting the grammar wrong turns the gate off rather than making it lenient,
# so it is sealed at the fingerprint level rather than only through
# `compare_signatures`.
# --------------------------------------------------------------------------- #

#: Every declaration-merging shape the contract folds. Each is legal
#: TypeScript that declares ONE name more than once.
_ONE_NAME_DECLARED_TWICE: tuple[tuple[str, str, str], ...] = (
    (
        "function overloads",
        "i:f",
        "export function f(x: string): string;\n"
        "export function f(x: number): number;\n"
        "export function f(x: any): any { return x; }\n",
    ),
    (
        "interface declared twice",
        "i:Bet",
        "export interface Bet { id: string }\n"
        "export interface Bet { amountCents: number }\n",
    ),
    (
        "class plus interface",
        "i:C",
        "export class C { do(): void {} }\nexport interface C { extra: string }\n",
    ),
    (
        "namespace declared twice",
        "i:N",
        "export namespace N { export const a: number = 1; }\n"
        "export namespace N { export const b: string = 'x'; }\n",
    ),
    (
        "a name in both declaration spaces",
        "i:Foo",
        "export interface Foo { a: string }\nexport const Foo: number = 1;\n",
    ),
)


@pytest.mark.parametrize(
    "name, key, source",
    _ONE_NAME_DECLARED_TWICE,
    ids=[r[0] for r in _ONE_NAME_DECLARED_TWICE],
)
def test_one_name_declared_twice_is_one_symbol_not_a_duplicate_key(
    name: str, key: str, source: str
) -> None:
    """The fold, sealed where it can actually fail: at the fingerprint level.

    RED TODAY.

    `compare_signatures` cannot see this. If the helper emitted two entries
    keyed `i:f`, the decoder would raise HELPER_OUTPUT_INVALID and the whole
    file would come back as a FAULT — and a fault on legal code is the gate
    switching itself off across 996 files, not a lenient answer. If instead the
    helper silently kept the last one, a widening overload would vanish. Both
    failures live below `compare_signatures`, so the seal has to reach the
    mapping.

    Green when: the name appears exactly once as a key, at its documented key.
    Falsify: emit one symbol per declaration node — the key-count assertion
    reddens for every row, and in production the decoder would fault instead.
    """
    fingerprints = _fingerprints(_TS, source)

    assert key in fingerprints, (
        f"{name}: {key!r} is not among the symbols {sorted(fingerprints)}. "
        "Every declaration of a name folds into ONE key"
    )
    at_this_name = [k for k in fingerprints if k == key or k.startswith(f"{key}/")]
    assert at_this_name.count(key) == 1, (
        f"{name}: {key!r} appears more than once. A duplicate key is "
        "HELPER_OUTPUT_INVALID, which is the gate faulting on legal code"
    )


def test_an_overload_set_is_ordered_and_reordering_it_moves_the_fingerprint(
    compare_ts,
) -> None:
    """The fold is ORDERED, because TypeScript resolves overloads in order.

    RED TODAY.

    The rulings table has the reorder row; this pins the mechanism the row
    depends on, one level down, so a comparator that passed the row by accident
    (say, by hashing the whole declaration list unordered and getting lucky on
    a collision) is still caught. After the edit, `f('a')` returns `number`
    rather than `string`, at every call site, with no error anywhere.

    Green when: the reorder moves `i:f` and the symbol set is unchanged.
    Falsify: sort the signature list before rendering — the fingerprint stops
    moving and this reddens.
    """
    before = (
        "export function f(x: string): string;\n"
        "export function f(x: unknown): number;\n"
        "export function f(x: any): any { return x; }\n"
    )
    after = (
        "export function f(x: unknown): number;\n"
        "export function f(x: string): string;\n"
        "export function f(x: any): any { return x; }\n"
    )
    first = _fingerprints(_TS, before)
    second = _fingerprints(_TS, after)

    assert set(first) == set(second), (
        "reordering overloads changed the SYMBOL SET; it must change one "
        f"symbol's fingerprint instead ({sorted(first)} vs {sorted(second)})"
    )
    assert first["i:f"] != second["i:f"], (
        "an overload set was rendered unordered. TypeScript resolves overloads "
        "in declaration order, so this edit silently changes what every call "
        "site returns"
    )


def test_an_empty_answer_and_a_real_one_are_distinguishable() -> None:
    """A file that declares nothing and a file that declares something differ.

    RED TODAY.

    Vacuity trap 2, sealed directly. A comparator that returns `{}` for
    everything satisfies every silent row in this file — sections 6 and 7's
    silent tables, four of the twenty rulings — and reports no change on any
    branch, ever. The empty mapping is a legitimate answer for a file that
    genuinely declares nothing, and it is exactly that legitimacy that makes it
    a good disguise.

    Green when: a file of nothing but bodies and imports yields an empty
    mapping, and a file with declarations does not.
    Falsify: return `{}` unconditionally — the second assertion reddens. Emit a
    symbol for a function declared INSIDE a body — the first reddens, and that
    is the other direction: bodies are the work the gate exists to permit.

    THE DECLARATIONS ARE WRAPPED IN AN IIFE, and the first draft of this seal
    was wrong for want of it. It used a top-level `function outer()` as the
    container and asserted the file declared nothing — but a top-level function
    IS a declaration, `export` or not, so the correct answer was `{'i:outer':
    …}` and the seal was asserting against the contract. It was caught by
    running this file against a reference implementation rather than by reading
    it. An IIFE is an expression statement, so the file below genuinely has no
    top-level declaration, which is the state the seal means to describe.
    """
    nothing = _fingerprints(
        _TS,
        "import { x } from './x';\n"
        "(function () {\n"
        "  function inner(a: string): void {}\n"
        "  const c = 1;\n"
        "  void [inner, c, x];\n"
        "})();\n",
    )
    something = _fingerprints(_TS, "export function f(a: string): void {}\n")

    assert nothing == {}, (
        "a file whose only declarations are inside a body and an import "
        f"produced {nothing}. Bodies are the work this gate exists to permit, "
        "and imports are not this module's declarations"
    )
    assert something, (
        "a file with a top-level exported function produced no symbols at all; "
        "an empty mapping is a CHECKED comparison with no changes, which is a "
        "pass bought by having read nothing"
    )


# --------------------------------------------------------------------------- #
# 8 — THE DIALECT COMES FROM THE PATH
#
# RED TODAY.
#
# `.ts` and `.tsx` are different grammars for the same bytes. This is the whole
# of JSX's effect on the comparator — JSX is an expression, expressions are
# bodies, and no JSX syntax appears in any fingerprint — but the parse is not
# optional, and a helper that used one ScriptKind for both would manufacture
# parse errors across half the target repository.
# --------------------------------------------------------------------------- #


def test_the_same_bytes_parse_in_one_dialect_and_not_the_other(compare_ts) -> None:
    """`const x = <T>(y);` is a type assertion in `.ts` and JSX in `.tsx`.

    RED TODAY.

    Measured 2026-08-10: it parses clean as `.ts` and produces two diagnostics
    as `.tsx`, where `<T>` opens a JSX element. A helper that guessed the
    dialect, or used one setting for both, gets one of these wrong — and the
    direction that matters is a manufactured parse error on 475 `.tsx` files,
    or worse, a `.tsx` file read under `.ts` rules and silently mis-parsed.

    UNPARSEABLE is the correct answer for the `.tsx` arm, and it is a fact
    about the FILE, not about the machine: `unsupported_paths` stays empty
    because the file was read, not skipped.

    Green when: the `.ts` arm is CHECKED and the `.tsx` arm is UNPARSEABLE.
    Falsify: hard-code `ts.ScriptKind.TS` — the `.tsx` arm comes back CHECKED
    and this reddens. Hard-code TSX — the `.ts` arm goes UNPARSEABLE.
    """
    source = "export const x = <T>(y);\nexport const y: number = 1;\n"

    try:
        as_ts = compare_ts(source, source, _TS)
        as_tsx = compare_ts(source, source, _TSX)
    except NotImplementedError as exc:
        pytest.fail(f"{_UNIMPLEMENTED}: {exc}")

    if as_ts.status is SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE:
        pytest.fail(f"{_NO_PARSER}: {as_ts.detail!r}")

    assert as_ts.status is SignatureCheckStatus.CHECKED, (
        f"`const x = <T>(y);` must parse as a type assertion in a .ts file; "
        f"got {as_ts.status.name} ({as_ts.detail!r})"
    )
    assert as_tsx.status is SignatureCheckStatus.UNCHECKED_UNPARSEABLE, (
        f"the same bytes must NOT parse as .tsx, where `<T>` opens a JSX "
        f"element; got {as_tsx.status.name}. The dialect comes from the path, "
        "and a helper that used one ScriptKind for both would mis-read half "
        "the target repository"
    )
    assert not as_tsx.unsupported_paths, (
        "unparseable source is a fact about the FILE; naming it in "
        "`unsupported_paths` sends a reader off to write a comparator that "
        "already exists"
    )


def test_jsx_is_out_and_a_component_contract_is_still_read(compare_ts) -> None:
    """JSX is excluded and `.tsx` coverage is still real. Both halves.

    RED TODAY.

    The exclusion and the coverage are one ruling and they have to be sealed
    together, because each alone is satisfiable the wrong way: a comparator
    that read `.tsx` as plain text passes the first half, and a comparator that
    refused `.tsx` outright passes it too.

    A React component's contract is its props type and its declared signature.
    What is not read is the markup it returns, which is its body.

    Green when: the markup rewrite is silent and the props widening is caught.
    Falsify: descend into JSX expressions — the first assertion reddens on 475
    files' worth of ordinary body work. Skip `.tsx` — the second reddens.
    """
    props = "export interface Props { label: string }\n"
    plain = f"{props}export const Button = (p: Props) => <button>{{p.label}}</button>;\n"
    remarked = (
        f"{props}export const Button = (p: Props) => (\n"
        '  <button className="primary" onClick={() => undefined}>\n'
        "    <span>{p.label}</span>\n  </button>\n);\n"
    )
    widened = (
        "export interface Props { label: string; onClick: () => void }\n"
        "export const Button = (p: Props) => <button>{p.label}</button>;\n"
    )

    assert _ts_changed(compare_ts, plain, remarked, _TSX) is False, (
        "rewriting JSX markup in a component body was reported as a signature "
        "change. A JSX element is an EXPRESSION and expressions are bodies — "
        "this is the work the gate exists to permit, over 475 files"
    )
    assert _ts_changed(compare_ts, plain, widened, _TSX) is True, (
        "widening a component's props type was not reported. Every existing "
        "`<Button label=… />` now fails to compile; .tsx coverage is real or "
        "the JSX exclusion is just a hole"
    )


# --------------------------------------------------------------------------- #
# 9 — A RECOVERED PARSE IS NOT A SMALLER ANSWER
#
# RED TODAY.
#
# `ts.createSourceFile` is an error-recovering parser designed for an editor:
# given `export function ok(a: string): void {}\nexport class` it returns one
# diagnostic AND a syntax tree containing two statements (measured 2026-08-10).
#
# The direction of the danger is what makes this a seal rather than a
# preference. If the BASE revision parses partially and drops a declaration,
# that declaration is ADDED at head — and an added symbol is not a change. A
# recovered tree is not a conservative answer, it is a SMALLER one, and smaller
# is the direction that clears branches.
# --------------------------------------------------------------------------- #

#: Sources that TypeScript's parser recovers from: each yields diagnostics AND
#: a usable partial tree containing the declaration above the damage.
_RECOVERABLE_DAMAGE: tuple[tuple[str, str], ...] = (
    (
        "a truncated class declaration",
        "export function ok(a: string): void {}\nexport class",
    ),
    (
        "an unclosed interface body",
        "export function ok(a: string): void {}\nexport interface I { a: string\n",
    ),
    (
        "a stray closing brace",
        "export function ok(a: string): void {}\n}\n",
    ),
    (
        "an unterminated string literal type",
        "export function ok(a: string): void {}\nexport type M = 'live;\n",
    ),
)


@pytest.mark.parametrize(
    "name, source", _RECOVERABLE_DAMAGE, ids=[r[0] for r in _RECOVERABLE_DAMAGE]
)
def test_any_parse_diagnostic_is_unparseable_and_never_a_partial_answer(
    name: str, source: str, compare_ts
) -> None:
    """Any diagnostic at all means UNPARSEABLE. Not "the symbols we recovered".

    RED TODAY.

    Each of these sources contains a perfectly good `export function ok` above
    the damage, which is exactly why the seal is written this way: a helper
    that returned the recovered symbols would return `ok` and look entirely
    reasonable. The assertion is not "no symbols were returned" but "the
    comparison did not proceed", because a partial answer that happens to be
    complete is still a partial answer.

    The corollary the helper author must not miss is sealed by implication: a
    parser build that cannot expose the diagnostics channel must exit non-zero
    — HELPER_FAILED — rather than proceed assuming the parse was clean.

    Green when: every damaged revision comes back UNCHECKED_UNPARSEABLE.
    Falsify: report `parse_error` only when `sourceFile.statements` is empty —
    all four rows redden. Return symbols alongside `parse_error` — the decoder
    refuses the document and the status becomes a FAULT, which also reddens,
    and correctly: those two fields are mutually exclusive.
    """
    good = "export function ok(a: string): void {}\n"

    try:
        result = compare_ts(good, source, _TS)
    except NotImplementedError as exc:
        pytest.fail(f"{_UNIMPLEMENTED}: {exc}")

    if result.status is SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE:
        pytest.fail(f"{_NO_PARSER}: {result.detail!r}")

    assert result.status is SignatureCheckStatus.UNCHECKED_UNPARSEABLE, (
        f"{name}: got {result.status.name}. TypeScript's parser recovers "
        "aggressively and hands back a tree containing `ok`; taking it is a "
        "SMALLER answer, and if the BASE revision is the damaged one, every "
        "declaration it dropped is ADDED at head — and added is not a change"
    )


# --------------------------------------------------------------------------- #
# 10 — THE DECODER IS ONE DECODER
#
# `decode_go_helper_response` is ~110 lines of language-independent validation
# whose only Go-shaped element is a schema string. `decode_ts_helper_response`'s
# docstring rules that P3 may neither copy it nor reimplement it, names the
# required P4 extraction, and says the seal author should write the seal that
# FORCES it. This is that seal.
#
# THE SIGNATURE, corrected by P4 on 2026-08-10 and now normative in the scaffold:
#
#     _decode_helper_response(stdout, schema, response_type, symbol_type)
#
# The scaffold wrote it with two arguments. The seal author reported that two
# cannot be met — the shared function BUILDS the result, and there are two
# response/symbol dataclass pairs, so a two-argument version needs a second
# construction step per language, which is the second implementation this
# section exists to forbid arriving one level down. The seals below were
# written to accommodate the extras and needed no edit for the correction: what
# they observe is that `stdout` and `schema` are the first two POSITIONALS and
# that each wrapper passes its OWN schema — which is precisely what the
# corrected signature fixes, and why the scaffold now pins the parameter order
# rather than leaving it to the implementer.
#
# The malformed-document table is verified against the GO decoder TODAY, which
# is what stops this section being red on both arms and therefore unfalsifiable:
# the table is known non-vacuous because it already bites a real implementation.
# --------------------------------------------------------------------------- #

#: One table of bad documents, `{schema}` substituted per language. The
#: duplicate-key row is the load-bearing one: the scaffold's argument is that a
#: copy which forgets it CLEARS branches the original refuses, so a divergence
#: here is a fail-open and not a tidiness complaint.
_MALFORMED: tuple[tuple[str, str], ...] = (
    ("empty stdout", ""),
    ("whitespace only", "   \n\t \n"),
    ("not JSON", "this is not json"),
    ("a JSON array", '["{schema}"]'),
    ("a JSON string", '"{schema}"'),
    ("a JSON number", "42"),
    ("null", "null"),
    ("no schema", '{"symbols": []}'),
    ("the wrong schema", '{"schema": "someone-elses/protocol/v1", "symbols": []}'),
    ("a null schema", '{"schema": null, "symbols": []}'),
    ("both symbols and parse_error", '{"schema": "{schema}", "symbols": [], "parse_error": "x"}'),
    ("neither symbols nor parse_error", '{"schema": "{schema}"}'),
    ("symbols is an object", '{"schema": "{schema}", "symbols": {}}'),
    ("symbols is a string", '{"schema": "{schema}", "symbols": "none"}'),
    ("a symbol entry is not an object", '{"schema": "{schema}", "symbols": ["X"]}'),
    (
        "a symbol has no fingerprint",
        '{"schema": "{schema}", "symbols": [{"symbol": "X", "kind": "function"}]}',
    ),
    (
        "a symbol has an empty fingerprint",
        '{"schema": "{schema}", "symbols": '
        '[{"symbol": "X", "fingerprint": "", "kind": "function"}]}',
    ),
    (
        "a symbol has a non-string symbol name",
        '{"schema": "{schema}", "symbols": '
        '[{"symbol": 7, "fingerprint": "f", "kind": "function"}]}',
    ),
    (
        "parse_error is not a string",
        '{"schema": "{schema}", "parse_error": {"line": 1}}',
    ),
    (
        "a DUPLICATE symbol key",
        '{"schema": "{schema}", "symbols": ['
        '{"symbol": "X", "fingerprint": "a", "kind": "function"}, '
        '{"symbol": "X", "fingerprint": "b", "kind": "function"}]}',
    ),
)


def _decode(language: str, document: str):
    if language == "go":
        return role_protocol.decode_go_helper_response(
            document.replace("{schema}", role_protocol.GO_HELPER_SCHEMA)
        )
    return role_protocol.decode_ts_helper_response(
        document.replace("{schema}", role_protocol.TS_HELPER_SCHEMA)
    )


@pytest.mark.parametrize(
    "name, document", _MALFORMED, ids=[r[0] for r in _MALFORMED]
)
@pytest.mark.parametrize("language", ("go", "ts"))
def test_both_decoders_refuse_the_same_malformed_document_with_the_same_fault(
    language: str, name: str, document: str
) -> None:
    """One table of bad documents, both decoders, identical verdict.

    The `go` arm is GREEN TODAY and the `ts` arm is RED. That asymmetry is
    deliberate and it is what makes this table trustworthy: every row is known
    to bite a real, shipped implementation right now, so a green `ts` arm later
    cannot be green because the row asks nothing.

    Every one of these is HELPER_OUTPUT_INVALID and never a partial result: a
    response half-understood produces a fingerprint set missing a symbol, a
    missing symbol is reported as a REMOVED one, and a wholly dropped document
    manufactures a pass.

    Green when: both decoders raise `ComparatorUnavailable` with
    HELPER_OUTPUT_INVALID for every row.
    Falsify: write a TS decoder that omits the duplicate-key check — the last
    row's `ts` arm reddens while its `go` arm stays green, which is exactly the
    divergence the scaffold predicts a copy will produce, and exactly the
    direction that clears branches.
    """
    try:
        with pytest.raises(ComparatorUnavailable) as caught:
            _decode(language, document)
    except NotImplementedError as exc:
        pytest.fail(
            f"{_UNIMPLEMENTED}: decode_ts_helper_response is a stub ({exc}). "
            "It must not be written as a copy of the Go decoder — see the "
            "extraction seal below"
        )

    assert caught.value.fault is ComparatorFault.HELPER_OUTPUT_INVALID, (
        f"{language}/{name}: got {caught.value.fault.value}. Every way the "
        "document can be wrong is HELPER_OUTPUT_INVALID"
    )


def test_one_decoder_serves_both_languages_and_neither_is_a_copy() -> None:
    """THE EXTRACTION, FORCED. A copy-paste body cannot satisfy this seal.

    RED TODAY.

    The two seals above pin that both decoders BEHAVE the same. That is
    necessary and it is not sufficient: two copies behave the same on the day
    they are written, and the scaffold's whole argument is about the day after
    — the copy that forgets the duplicate-key check clears branches the
    original refuses, and it does so in the one place where a divergence is a
    fail-open.

    So this seal asserts SHARING, not agreement, and it does it behaviourally
    rather than by reading source: `_decode_helper_response` is replaced with a
    spy, and both public decoders must be observed routing through it with
    their own schema. A body that copied the Go decoder fails at the first
    assertion; a body that added the shared function but left
    `decode_go_helper_response` as its own implementation fails at the last.

    Note what is NOT asserted: the wrappers may do whatever they like with the
    result — build their own dataclasses, rename fields — because the response
    types genuinely differ. What may not differ is the VALIDATION.

    P4, 2026-08-10: that sentence is what the arity dispute turned on, and the
    scaffold now answers it the other way round. The response types differ, so
    the SHARED function is handed them (`response_type`, `symbol_type`) rather
    than each wrapper building its own — because "each wrapper builds its own"
    is where a divergence would live once the validation stopped diverging.
    The spy below already accepted the extra positionals, so this seal reads
    the same against the corrected signature as against the scaffold's, which
    is why the correction cost no seal edit; it is recorded rather than left,
    because a seal that would have passed either way should say which one it
    is now asserting.

    Green when: both decoders call the one shared function.

    Falsify, MEASURED: replacing `decode_ts_helper_response`'s delegation with a
    hand-written second implementation — a faithful one, differing only in that
    it forgets the duplicate-key check, which is the divergence the scaffold
    predicts a copy will produce — reddens **TWO** rows: this one, and
    `test_both_decoders_refuse_the_same_malformed_document_with_the_same_fault
    [ts-a DUPLICATE symbol key]`.

    **P4, 2026-08-10 — this docstring said EIGHT and the reproducible number is
    TWO.** The correction matters more than the arithmetic. Eight was measured
    against the reference implementation's particular copy, and the other six
    rows were properties of THAT copy — a hand transcription that also diverged
    in ways nobody was claiming a copy would necessarily diverge in — rather
    than of the table. Re-measured here against a copy that is faithful except
    for the one predicted divergence, only two rows bite. Both directions this
    seal cares about are among them, so the seal works exactly as designed: the
    extraction row catches "there are two implementations" and the duplicate-key
    row catches "and they have already diverged". A number nobody can reproduce
    is worse than a smaller one, because the next author to re-measure concludes
    the seals have rotted rather than that the count was never the claim.

    A copy-paste body cannot satisfy this section, which is what it was asked
    for, and TWO rows is enough for that: one of them is unsatisfiable by any
    second implementation at all.

    Note the shape that does NOT falsify it, also measured: routing through a
    private helper that itself calls `_decode_helper_response` stays green, and
    should — that is still one implementation of the validation, which is the
    property being sealed. This asserts sharing, not call depth.
    """
    shared = getattr(role_protocol, "_decode_helper_response", None)
    assert shared is not None, (
        f"{_UNIMPLEMENTED}: role_protocol._decode_helper_response does not "
        "exist. `decode_ts_helper_response`'s docstring rules that P3 may "
        "neither copy `decode_go_helper_response` nor reimplement it, and "
        "names the required shape: one `_decode_helper_response(stdout, "
        "schema)` with both public decoders as thin, schema-fixing wrappers. "
        "Two implementations of one wire protocol is the two-copies problem "
        "arriving in the plumbing, in the exact place a divergence fails OPEN"
    )

    seen: list[str] = []

    def spy(stdout: str, schema: str, *args, **kwargs):
        seen.append(schema)
        return shared(stdout, schema, *args, **kwargs)

    original = role_protocol._decode_helper_response
    role_protocol._decode_helper_response = spy
    try:
        role_protocol.decode_go_helper_response(
            json.dumps({"schema": role_protocol.GO_HELPER_SCHEMA, "symbols": []})
        )
        role_protocol.decode_ts_helper_response(
            json.dumps({"schema": role_protocol.TS_HELPER_SCHEMA, "symbols": []})
        )
    finally:
        role_protocol._decode_helper_response = original

    assert seen == [role_protocol.GO_HELPER_SCHEMA, role_protocol.TS_HELPER_SCHEMA], (
        "both decoders must route through the one shared validator, each "
        f"fixing its own schema; observed {seen!r}. A decoder that did not "
        "appear here is a second copy of the protocol, and the copy that "
        "forgets the duplicate-key check clears branches the original refuses"
    )


def test_the_shared_decoder_is_told_its_schema_and_enforces_it() -> None:
    """The extraction may not become a decoder that accepts any schema.

    RED TODAY.

    The cheap way to make one function serve two protocols is to stop checking
    the schema. That would pass every seal above — both decoders would share an
    implementation and reject every malformed row — while destroying the reason
    the schema is on the wire: a fingerprint is compared for EQUALITY across
    two invocations, so a helper from a different version of the grammar reads
    as every symbol having been rewritten.

    Green when: each decoder refuses the other's schema.
    Falsify: drop the schema comparison from `_decode_helper_response`, or pass
    the schema in and ignore it.
    """
    go_doc = json.dumps({"schema": role_protocol.GO_HELPER_SCHEMA, "symbols": []})
    ts_doc = json.dumps({"schema": role_protocol.TS_HELPER_SCHEMA, "symbols": []})

    assert role_protocol.GO_HELPER_SCHEMA != role_protocol.TS_HELPER_SCHEMA, (
        "the two helpers must not share a schema string; the schema is what "
        "says which grammar produced a fingerprint"
    )

    with pytest.raises(ComparatorUnavailable) as caught:
        role_protocol.decode_go_helper_response(ts_doc)
    assert caught.value.fault is ComparatorFault.HELPER_OUTPUT_INVALID

    try:
        with pytest.raises(ComparatorUnavailable) as caught:
            role_protocol.decode_ts_helper_response(go_doc)
    except NotImplementedError as exc:
        pytest.fail(f"{_UNIMPLEMENTED}: {exc}")
    assert caught.value.fault is ComparatorFault.HELPER_OUTPUT_INVALID


def test_the_request_encoder_is_the_documented_document() -> None:
    """`encode_ts_helper_request` is the contract of its Go twin, one schema over.

    RED TODAY.

    Small, and here because the duplication is smaller and therefore more
    tempting than the decoder's. `ensure_ascii=True` is the one line with an
    argument behind it: a blob that is not valid UTF-8 must turn into a bad
    FILE, not into an environment fault, and a non-ASCII-escaping encoder makes
    the subprocess boundary decide which.

    Green when: the document has exactly the fields of `TsHelperRequest`,
    carries the TS schema, is pure ASCII, and passes source through verbatim
    including BOM and CRLF.
    Falsify: drop `ensure_ascii` — the ASCII assertion reddens. Normalise line
    endings — the verbatim assertion reddens, and in production two revisions
    that differ only in line endings would silently agree.
    """
    source = "﻿export const s = 'café';\r\nexport const t: number = 1;\r\n"
    try:
        encoded = role_protocol.encode_ts_helper_request(_TSX, source)
    except NotImplementedError as exc:
        pytest.fail(f"{_UNIMPLEMENTED}: {exc}")

    assert encoded.isascii(), (
        "the request document must be pure ASCII: a blob that is not valid "
        "UTF-8 must read as a bad FILE, not as an environment fault"
    )
    document = json.loads(encoded)
    assert set(document) == {"schema", "path", "source"}, (
        f"the request carries {sorted(document)}, not exactly the fields of "
        "TsHelperRequest"
    )
    assert document["schema"] == role_protocol.TS_HELPER_SCHEMA
    assert document["path"] == _TSX, (
        "`path` selects the parse DIALECT and must travel verbatim"
    )
    assert document["source"] == source, (
        "source travels verbatim, BOM and CRLF included; the revisions being "
        "compared are git blobs and a normalising encoder would make two "
        "different files agree"
    )


# --------------------------------------------------------------------------- #
# 11 — WHAT IS RECORDED RATHER THAN REFUSED
#
# GREEN TODAY.
#
# The largest hole in this contract is cross-file declaration merging, and the
# operator ruling is that it is RECORDED AND ACCEPTED, not fixed here. So these
# seals do not assert a refusal the design does not implement — a seal against
# behaviour nothing produces is a seal against nothing, and it would go green
# the day someone deleted the comparator.
#
# What they assert instead is that the limit is KNOWN: the protocol rule that
# creates it still holds and is measured, and the limitation is still written
# down where the next reader meets it. That is the honest instrument, and it is
# the one that reddens if someone quietly "fixes" the bypass without saying so
# — because then the recorded text and the behaviour disagree.
# --------------------------------------------------------------------------- #


def test_the_new_file_bypass_is_real_and_is_measured_on_the_comparator_that_exists() -> (
    None
):
    """A new file has no base revision, so every symbol in it is ADDED.

    GREEN TODAY, measured against the Python comparator.

    This is the mechanism of the bypass, and it is a PROTOCOL rule rather than
    a comparator rule — decided once in `compare_signatures` for every
    language, which is why it can be measured today on Python and why closing
    it is a change to `_compare_branch_signatures` and not to a comparator.

    In TypeScript the consequence is first-class rather than incidental.
    Declaration merging and module augmentation mean a body agent can widen a
    sealed interface from a second file — `interface Bet { newField: string }`
    in any file that imports it into scope, or `declare module './bet' { … }`
    outright — and the gate compares one file at a time, so the widening
    arrives as an added symbol in a file with no base revision.

    Green when: a new file is CHECKED with no changes, and an added symbol in
    an existing file is not a change while a removed one is.
    Falsify: rule an added symbol a change — this reddens, and so does the
    "class method added" ruling and Python's "a body may add private helpers".
    That is the cost of closing this bypass at the comparator level, which is
    why the closure belongs one level up.
    """
    new_file = compare_signatures("pkg/m.py", None, "def f(a):\n    pass\n")
    assert new_file.status is SignatureCheckStatus.CHECKED
    assert not new_file.changes, (
        "a file that did not exist at base has no scaffolded signature to "
        "preserve — this is the rule the cross-file merging bypass rides on"
    )

    added = compare_signatures(
        "pkg/m.py", "def f(a):\n    pass\n", "def f(a):\n    pass\n\n\ndef g(b):\n    pass\n"
    )
    assert not added.changes, "an added symbol is not a change"

    removed = compare_signatures("pkg/m.py", "def f(a):\n    pass\n", "")
    assert removed.changes, "a removed symbol IS a change"


def test_the_limits_of_this_design_are_still_written_down() -> None:
    """The named gaps are still named, in the module, where the next reader is.

    GREEN TODAY.

    This is the instrument this repository already uses for a limit that is
    accepted rather than closed: the limitation is stated in the contract, and
    a seal pins the sentence so that "the code is the contract" cannot be the
    way it quietly stops being true. `test_neither_finding_is_a_question_for_p4`
    in the Go file is the same shape.

    It is deliberately NOT a seal that the bypass is refused. The design does
    not refuse it, the operator has recorded and accepted that, and a seal
    asserting a refusal would either be red forever against a decision already
    taken or — worse — green because it asserted nothing.

    The four sentences pinned here are the four costs a reader must not
    discover by being caught out: the cross-file bypass, unread inference,
    absent type identity, and the uncovered extensions.

    Green when: all four are still in the module's own prose.
    Falsify: delete the cross-file paragraph from the D4 header — the first
    assertion reddens, and that is the point: if the bypass is ever closed, the
    paragraph changes and this seal is where somebody has to say so out loud.
    """
    source = _prose(_role_protocol_source())

    recorded = {
        "the cross-file declaration merging bypass": (
            "A NEW file has no base revision, so every symbol in it is an "
            "ADDED symbol, and an added symbol is not a change."
        ),
        "where its closure belongs": (
            "Closing it needs a whole-diff comparison rather than a per-file "
            "one"
        ),
        "unread inference": "Inferred types are not read.",
        "absent type identity": "No type identity.",
    }
    for label, sentence in recorded.items():
        assert _prose(sentence) in source, (
            f"the record of {label} is gone from role_protocol.py. This limit "
            "is ACCEPTED, not closed, and an accepted limit that stops being "
            "written down is an undiscovered defect the next reader pays for"
        )


def test_the_typescript_design_adds_no_seventh_comparator_fault() -> None:
    """Six faults, and every TypeScript failure maps onto them.

    GREEN TODAY.

    `tests/test_role_protocol_faults.py` hard-pins the count, and adding a
    member fails COLLECTION for the whole suite — so this seal is not the
    tripwire. What it adds is the D4-specific claim: the fault the scaffold
    refused to add, `PARSER_UNTRUSTED`, is unreachable BY CONSTRUCTION under
    the resolution rule, because the resolution never looks inside the tree
    under judgement. An enum member for an unreachable state is vacuity.

    The digest ruling in section 2 is where this claim was most at risk — a
    parser that fails its digest is a new *situation* — and it is answered
    there without a new member: a parser whose bytes are not the floored ones
    is this build's own apparatus being wrong, which is what HELPER_MISSING
    already names.

    Green when: the set is exactly the six, and every one is blocking.
    Falsify: add `PARSER_UNTRUSTED` — this reddens, and so does the whole
    suite's collection, which is the louder signal and the reason that member
    would have to be a P4 commit.
    """
    faults = {f.name for f in ComparatorFault}
    assert faults == {
        "TOOLCHAIN_MISSING",
        "TOOLCHAIN_UNUSABLE",
        "HELPER_MISSING",
        "HELPER_FAILED",
        "HELPER_TIMEOUT",
        "HELPER_OUTPUT_INVALID",
    }, f"the fault set moved: {sorted(faults)}"
    assert "PARSER_UNTRUSTED" not in faults, (
        "under the resolution rule, 'the parser I found is inside the tree "
        "under judgement' is unreachable by construction; a member for an "
        "unreachable state is the vacuity this codebase keeps paying for"
    )
    for fault in ComparatorFault:
        assert role_protocol.signature_status_for_fault(fault) is (
            SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
        ), f"{fault.value} stopped being blocking"


# --------------------------------------------------------------------------- #
# 12 — THE SEAL ON THIS FILE ITSELF
#
# GREEN TODAY.
# --------------------------------------------------------------------------- #


def test_this_file_cannot_go_green_by_the_comparator_being_absent() -> None:
    """`_ts_changed` fails on absence. It does not skip and it does not xfail.

    GREEN TODAY, and it is the seal that makes every red row above mean what it
    says.

    The failure mode being refused is specific: a helper that turned "the
    comparator could not answer" into a skip would make this entire file green
    on every machine that has no vendored parser — which is every machine — and
    green over 996 files is a certificate issued for asking nothing. That is
    the vacuity unit D4 exists to prevent, and it would arrive as a
    one-line kindness in a helper nobody re-reads.

    The two prefixes are asserted distinct because they carry the diagnosis a
    reader needs from a failure list: `NOT IMPLEMENTED` means unit D4 is still
    a contract, `NO TRUSTED PARSER` means it was built and nothing was
    vendored. Collapsing them loses the difference between "P3 has not started"
    and "P4's vendoring commit is missing".

    Green when: absence produces `Failed`, never `Skipped`.

    Falsify: change either `pytest.fail` in `_ts_changed` to `pytest.skip`.
    Measured in a clone (mutation M13): replacing all fourteen `pytest.fail`
    calls in this file turns **75 red rows green-by-disappearance** and leaves
    ten skips in their place. That number is the size of the certificate this
    seal refuses to issue.

    WHY IT IS WRITTEN WITH `except BaseException` AND NOT `pytest.raises`.
    The first version used `pytest.raises(Failed)`, and M13 showed it could not
    redden: `pytest.skip` raises `Skipped`, which is a `BaseException` and not
    a `Failed`, so it propagated straight out of the assertion and SKIPPED this
    seal too. A guard that its own mutation switches off is worse than no
    guard, because the skip count is the only trace it leaves. Catching the
    base class and asserting the TYPE is what makes the promise self-enforcing.
    """

    def _absent(before, after, path=_TS):
        raise NotImplementedError("D4 P1 scaffold: contract only")

    class _Unavailable:
        status = SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
        detail = "helper-missing: nothing vendored"
        changes = ()

    for label, compare, expected in (
        ("an unimplemented comparator", _absent, _UNIMPLEMENTED),
        ("an absent parser", lambda *a, **k: _Unavailable(), _NO_PARSER),
    ):
        try:
            _ts_changed(compare, "a", "b")
        except Failed as exc:
            assert expected in str(exc), (
                f"{label} failed without the {expected!r} marker, so a reader "
                f"of a failure list cannot tell which red state it is: {exc}"
            )
        except BaseException as exc:  # noqa: BLE001 - Skipped is a BaseException
            raise AssertionError(
                f"{label} produced {type(exc).__name__}, not a test FAILURE. "
                "A comparator that cannot answer must never turn this file "
                "green: with no vendored parser that would be every machine "
                "in the world, and green over 996 files is a certificate "
                "issued for asking nothing"
            ) from exc
        else:
            raise AssertionError(
                f"{label} returned an answer. `_ts_changed` must not "
                "manufacture one — a default of False would make every "
                "silent row in this file pass without a comparator"
            )

    assert _UNIMPLEMENTED != _NO_PARSER, (
        "the two red states must stay distinguishable in a failure list: one "
        "says P3 has not started, the other says P4's vendoring is missing"
    )


# --------------------------------------------------------------------------- #
# 13 — TRAP 1 AT THE FINGERPRINT LEVEL: the RENDERING grammar's forgeability
#
# GREEN TODAY, and red under the mutations named row by row. Added by the P2
# second pass, 2026-08-10.
#
# WHY THIS SECTION EXISTS AND WHY SECTION 3 IS NOT IT
# ---------------------------------------------------
# Section 3 seals the SYMBOL-KEY grammar — `ts_symbol_key`, the `/`-joined
# segment list — against a member name that spells a separator. It is a good
# seal and it is only half the surface. A symbol has TWO author-reachable
# strings: its key, and its FINGERPRINT, and the fingerprint has a grammar of
# its own, invented in `main.cjs` and recorded nowhere else. Nothing sealed it.
#
# The body author disclosed the hole against its own interest and measured it:
# mutations that each remove one anti-forgery device redden ZERO of the 151 rows
# above. That was re-measured for this commit and the count is confirmed at zero
# for all NINE mutations named below (M1, M2, M2b, M3, M4, M4b, M5, M6, M7). A
# device no seal defends is a device the next refactor deletes for being
# unreachable.
#
# THE GO DEFECT, RESTATED, BECAUSE IT IS THE THING BEING PREVENTED
# ----------------------------------------------------------------
# Go shipped `embedded T` as an embed marker and a struct field named `embedded`
# forged it: "no marker" was spelled by the ABSENCE of a word in a column a name
# occupies. TypeScript is a far worse language to try this in, because a member
# name is not required to be an identifier: `{ "a;b": string }`,
# `{ "content-type": string }`, `{ 1: string }`, `{ [Symbol.iterator](): void }`
# and `#private` are all ordinary code, and `; + [ ] :` is most of the
# separator alphabet of the fingerprint grammar.
#
# THE PROPERTY, stated once: **no member name, string literal or type-expression
# text may forge a structural element of a rendered fingerprint.** Two different
# declarations may not render the same bytes.
#
# HOW EVERY ROW BELOW IS KEPT NON-VACUOUS
# ----------------------------------------
# This unit has already shipped two vacuous seals — one that passed with the
# defect present because an error string happened to contain the substring it
# searched for, and one whose pass condition was satisfiable by executing
# nothing. So every row here obeys three rules:
#
#   1. IT NAMES ITS MUTATION, and that mutation was APPLIED to a `cp -a` clone
#      (`.git` file removed, `git init` fresh, `__pycache__` cleared between
#      runs because CPython keys bytecode on `(mtime_seconds, size)` and a
#      same-size edit restored inside one second is served from cache). Red was
#      observed, not argued.
#   2. IT CARRIES ITS CONTROL IN THE SAME CALL. The forging input and the benign
#      twin it forges are judged together. A green bought by the comparator
#      answering `{}`, or by every name being quoted including the ones that
#      must not be, fails the control half.
#   3. IT SAYS WHERE THE INPUT COMES FROM. Some of these fixtures are ordinary
#      production TypeScript and the row says so; some are adversarial and the
#      row says THAT, plainly, rather than dressing an attack up as a soak
#      finding.
#
# WHAT THIS SECTION COULD NOT SEAL — see
# `test_the_absolute_path_rule_cannot_be_sealed_on_this_machine` at the end. It
# is the one hole this pass leaves open, and it is open for a reason no seal on
# this machine can close.
# --------------------------------------------------------------------------- #

#: THE FORGERIES. Each row is (label, forging source, benign twin, mutation).
#:
#: The recipe is the one section 3's `a/s:b` row uses, and it is worth stating,
#: because it is what makes these rows collisions rather than merely ugly names.
#: A member always renders `[kind][modifiers]<tag>:<name>…`, so a forger can only
#: impersonate a member list whose FIRST member carries the forger's own kind and
#: tag. Every forger below is therefore a non-identifier-named member — tag `s` —
#: impersonating a list of non-identifier-named members.
#:
#: PROVENANCE, stated per side rather than in aggregate:
#:   * The TWINS are ordinary production TypeScript. Quoted kebab-case members
#:     are what every HTTP-header, CSS-property and JSON-schema type is made of
#:     (`{ "content-type": string }`), and the primary target has them.
#:   * The FORGERS are adversarial. They are legal TypeScript — any string is a
#:     legal member name — but nothing writes them by accident. Their job is the
#:     same as `a/s:b`'s in section 3: to make a device falsifiable. Without a
#:     row built to collide, the device can be deleted with nothing going red,
#:     which is precisely the state this section found.
_FORGED_FINGERPRINTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "a member name forges the member separator, so two members read as one",
        'export interface I { "content-type:string;[prop][]s:x-request-id": number }\n',
        'export interface I { "content-type": string; "x-request-id": number }\n',
        "M2",
    ),
    (
        "a member name forges a whole extra method into the interface",
        'export interface I { "a-b():void;[method][]s:c-d"(): number }\n',
        'export interface I { "a-b"(): void; "c-d"(): number }\n',
        "M2",
    ),
    (
        "a member name forges the `+` that folds an overload set",
        'export interface I { "a-b:string+[prop][]s:a-b": number }\n',
        'export interface I { "a-b": string; "a-b": number }\n',
        "M2",
    ),
    (
        "a string literal type forges the `,` between two tuple elements",
        'export type T = ["x),lit(y"];\n',
        'export type T = ["x", "y"];\n',
        "M2b",
    ),
)


@pytest.mark.parametrize(
    "label, forger, twin, mutation",
    _FORGED_FINGERPRINTS,
    ids=[r[0] for r in _FORGED_FINGERPRINTS],
)
def test_a_member_name_cannot_forge_a_structural_element_of_a_fingerprint(
    label: str, forger: str, twin: str, mutation: str, compare_ts
) -> None:
    """Trap 1, at the level section 3 does not reach: the RENDERED bytes.

    GREEN TODAY. Red under the mutation each row names.

    Two declarations that mean different things to every consumer must not
    render the same fingerprint. The twin declares two members; the forger
    declares ONE, whose name contains the bytes the renderer uses to separate
    the twin's two. If those bytes are not quoted, a body author can delete a
    member of a published interface and the gate reports no change — which is
    the Go defect exactly, transplanted into a language where the member
    position accepts arbitrary text.

    Green when: the two files fingerprint differently AND the edit from the twin
    to the forger is reported as a change by the live comparator.

    Falsify — MEASURED, in a `cp -a` clone with a fresh `git init`:

      * **M2** — in `renderAtom`, drop the `JSON.stringify` from both quoting
        arms, so a tag's text is emitted bare::

            return `${tag}:${text}`;

        Rows 1-3 then render byte-identically to their twins and go red. Row 4
        is untouched, because a tuple's literal text is quoted by `renderExpr`
        and not by `renderAtom` — which is why row 4 exists and names M2b.
      * **M2b** — in `renderExpr`, return `node.text` rather than
        `JSON.stringify(node.text)` for `StringLiteral` /
        `NoSubstitutionTemplateLiteral`. Row 4 goes red; rows 1-3 do not.

    Both mutations redden ZERO of the 151 rows that predate this section, which
    is the measurement this section was written to answer.

    THE CONTROLS, and why a bare inequality would not have been one. Asserting
    only `forger != twin` is satisfiable by a comparator that answers `{}` to
    one file and something to the other, and by a comparator that faults on one.
    So the symbol SETS are asserted equal first — both files declare exactly one
    top-level name — and both are asserted non-empty. The pair is judged in this
    one call and neither half means anything alone.
    """
    forged = _fingerprints(_TS, forger)
    benign = _fingerprints(_TS, twin)

    assert forged and benign, (
        f"{label}: one side fingerprinted to nothing ({forged} vs {benign}). An "
        "empty answer passes every inequality in this file for free"
    )
    assert set(forged) == set(benign), (
        f"{label}: the two revisions declare the same top-level name and must "
        f"produce the same symbol SET; got {sorted(forged)} vs {sorted(benign)}"
    )
    assert forged != benign, (
        f"{label}: a member NAME forged a structural element of the rendered "
        "fingerprint, so two different declarations render the same bytes. That "
        "is the Go embed-marker defect in the one position TypeScript makes "
        "trivially reachable — a member name is not required to be an "
        "identifier. Text the parser has not certified an identifier must be "
        "JSON-quoted; a JSON string is self-delimiting and no author-chosen "
        "character can reach a structural position from inside one"
    )
    assert _ts_changed(compare_ts, twin, forger) is True, (
        f"{label}: the live comparator reported NO CHANGE for an edit that "
        "removes a member from a published interface. This is the direction "
        "that clears a branch, and it clears it silently"
    )


#: Member names the parser will NOT certify as identifiers, so every one of them
#: must reach the fingerprint inside a JSON string. Each is legal TypeScript in
#: the member position.
#:
#: The first four are the body's own named fixtures. `content-type` is the
#: production case and it is not exotic: quoted kebab-case members are what
#: HTTP-header, CSS-property and JSON-schema types are made of. The rest are
#: chosen for the separator each one reaches: `;` and `+` join members, `[` and
#: `]` delimit the two slots, `:` separates tag from text and name from type,
#: `/` is the KEY separator, `"` and `\\` are the JSON string's own delimiters,
#: and a newline and a space are the two characters a hand-rolled quoting scheme
#: forgets first.
_NAMES_THE_PARSER_DID_NOT_CERTIFY: tuple[str, ...] = (
    "a;b",
    "[prop][]i:c",
    "content-type",
    "k:empty",
    "a/b",
    "a+b",
    "a{b}c",
    "a b",
    "1abc",
    "i:x",
    'a"b',
    "a\\b",
    "a\nb",
)


@pytest.mark.parametrize("name", _NAMES_THE_PARSER_DID_NOT_CERTIFY)
def test_text_the_parser_did_not_certify_an_identifier_is_json_quoted(
    name: str,
) -> None:
    """Rule 1 of the rendering grammar, sealed as a property over the text.

    GREEN TODAY. Red under M2.

    The rule `main.cjs` states is: bare text is emitted ONLY when the parser has
    told us it is an identifier, and everything else is `JSON.stringify`d. A
    JSON string is self-delimiting — it begins and ends with `"` and contains no
    unescaped `"` or `\\` — so no author-chosen character can reach a structural
    position from inside one. That rule had no seal.

    This is the general form of the forgery table above: rather than one
    hand-built collision per separator, it asserts the invariant that makes
    every such collision impossible at once.

    Green when: the hostile name appears in the fingerprint as `s:` followed by
    its JSON encoding, AND — in the same call, on the same file — the ordinary
    member named `plain` appears BARE as `i:plain`.

    THE CONTROL IS THE SECOND HALF AND IT IS NOT DECORATION. A renderer that
    quoted everything, including certified identifiers, would satisfy the first
    assertion on every row while breaking the `{foo}` / `{"foo"}` fold that
    `test_quoting_a_member_name_is_not_a_signature_change` depends on. Both
    halves are asserted here, because a seal that can be passed by over-quoting
    is a seal that moves the defect one test to the left.

    Falsify: **M2** — drop `JSON.stringify` from both arms of `renderAtom`.
    Measured red on every row of this table, with the `i:plain` control still
    green, which is the pairing doing its job. M2 reddens none of the 151 rows
    that predate this section.

    A MEASUREMENT WORTH RECORDING, because it corrects the obvious reading of
    the body's report. The body named `[prop][]i:c` as a needed fixture. It is
    in this table and it belongs here — but it does NOT collide with the member
    `c`, not even under M2, because the forger lands on tag `s` and `c` lands on
    tag `i`, and the LEADING tag is what is read. The tag split is a second,
    independent device. That is why the collision rows above are built out of
    non-identifier-named twins rather than out of this fixture: a row that
    cannot collide cannot falsify anything, and this file has already shipped
    two seals that could not fail.
    """
    source = f"export interface I {{ {json.dumps(name)}: string; plain: string }}\n"
    fingerprints = _fingerprints(_TS, source)

    assert set(fingerprints) == {"i:I"}, (
        f"a member named {name!r} moved the SYMBOL SET to {sorted(fingerprints)}; "
        "an interface is one symbol whatever its members are called"
    )
    rendered = fingerprints["i:I"]

    assert f"s:{json.dumps(name)}" in rendered, (
        f"a member named {name!r} did not reach the fingerprint inside a JSON "
        f"string. It rendered as {rendered!r}. Text the parser has not certified "
        "an identifier must be quoted, or the member position — which accepts "
        "ARBITRARY text in TypeScript — becomes a way to write the renderer's "
        "own separators into a fingerprint"
    )
    assert "i:plain:string" in rendered, (
        "the control half: a member the parser DID certify an identifier must "
        f"render bare, and {rendered!r} does not contain `i:plain:string`. "
        "Quoting everything would pass the assertion above and break the "
        "`{foo}`/`{\"foo\"}` fold, which is the same defect one test to the left"
    )


#: Class members with and without modifiers. Every one is ordinary production
#: TypeScript; the last row is the Go defect's exact TypeScript twin, and the
#: contract at `main.cjs` rule 2 prints both halves of it by name.
_MEMBER_SHAPES: tuple[tuple[str, str, str], ...] = (
    ("a plain property", "export class C { x: number = 1; }\n", "[prop][]i:x:number"),
    (
        "a static property",
        "export class C { static x: number = 1; }\n",
        "[prop][static]i:x:number",
    ),
    (
        "a readonly property",
        "export class C { readonly x: number = 1; }\n",
        "[prop][readonly]i:x:number",
    ),
    ("a plain method", "export class C { m(): void {} }\n", "[method][]i:m():void"),
    (
        "a static async method",
        "export class C { static async m(): Promise<void> {} }\n",
        "[method][static,async]i:m():i:Promise<void>",
    ),
    (
        "a getter",
        "export class C { get g(): number { return 1; } }\n",
        "[get][]i:g():number",
    ),
    (
        "a constructor",
        "export class C { constructor(a: string) {} }\n",
        "[ctor][]([]i:a:string):@inferred",
    ),
    (
        "a property NAMED static — the Go defect's TypeScript twin",
        "export class C { static: number = 1; }\n",
        "[prop][]i:static:number",
    ),
)


@pytest.mark.parametrize(
    "label, source, expected", _MEMBER_SHAPES, ids=[r[0] for r in _MEMBER_SHAPES]
)
def test_every_optional_marker_lives_in_an_always_present_bracket_slot(
    label: str, source: str, expected: str
) -> None:
    """Rule 2 of the rendering grammar: `[]` when empty, never omitted.

    GREEN TODAY. Red under M1.

    This is the device that is the LITERAL repair of the Go defect. In Go, "no
    marker" was spelled by the absence of a word in a column a name occupies, so
    `type S struct{embedded embedded}` and an embed of that type rendered
    identically. Here "no marker" is spelled `[]`, and `[` cannot appear in a
    TypeScript identifier, so `class C { static: number }` renders
    `[prop][]i:static:number` and `class C { static x: number }` renders
    `[prop][static]i:x:number`.

    Green when: each member renders EXACTLY the documented bytes, and every
    member sub-symbol of the class has both slots — `[kind][modifiers]` — with
    the modifier slot present even when it holds nothing.

    Falsify: **M1** — make `slot()` omit itself when empty and drop its brackets
    when it does not::

        function slot(words) {
          return words.length ? `${words.join(' ')} ` : '';
        }

    Measured: every row of this table goes red, and M1 reddens ZERO of the 151
    rows that predate this section.

    AN HONEST LIMIT ON WHAT THIS ROW PROVES, recorded because the alternative is
    a seal that claims more than it measured. Under M1 the two halves of the Go
    fixture STILL do not converge — `[prop]i:static:number` and
    `[prop]static i:x:number` differ — because every member name is prefixed by
    its tag (`i:` / `s:`), which is rule 1's device and not rule 2's. So on the
    tree as it stands, rule 2 is defence in depth rather than the load-bearing
    guard, and no fixture found on this machine turns M1 alone into a collision.
    It is sealed anyway, and sealed as EXACT BYTES rather than as a collision,
    because that is the honest shape of the claim: the contract prints these
    strings, the renderer must emit them, and a device deleted for being
    unreachable is a device that is not there the day rule 1 is weakened. M1 and
    M2 together are the Go defect restored in full.

    **P4, 2026-08-10 — UPHELD, and the limit above is upgraded from an absence of
    evidence to a reason.** The disputed question was whether defence in depth
    sealed as exact bytes overstates what the row proves. It does not, and the
    two halves of that answer are worth separating.

    First, the negative result is not "we looked and did not find one". It is
    structural, and it can be stated: under M1 the modifier column is followed
    either by a tag-prefixed atom or by a keyword from a closed literal set
    (`fn`, `class`, `new`, `function`, `interface`, `type`, `enum`, `namespace`,
    `export`), and the column's own contents come from `MODIFIER_WORDS`, a table
    keyed by `ts.SyntaxKind`. So there is **no author-controlled text in that
    column at all**, and a name cannot reach it whatever it is spelled. M1 alone
    is therefore not merely un-forged on this machine, it is unforgeable — and it
    becomes forgeable the moment rule 1's tag prefix is what weakens, which is
    the precise contingency the row is held against. That is a stronger claim
    than the seal author felt entitled to make and it is the same conclusion.

    Second, EXACT BYTES is the right instrument here rather than an over-pin,
    because these bytes are not an implementation detail this row discovered:
    `main.cjs` rule 2 PRINTS `[prop][]i:static:number` and
    `[prop][static]i:x:number` in its header, and the header is the only record
    of the rendering grammar anywhere. A row that asserted only the shape would
    let the contract and the renderer drift apart while staying green. And the
    brittleness objection cuts the other way: the grammar IS the wire format, so
    a change to these bytes is a change that must bump `SCHEMA` — `main.cjs` says
    so at the constant — and eight loud red rows are the correct way to make that
    conversation happen rather than a cost to be engineered away.
    """
    import re

    fingerprints = _fingerprints(_TS, source)
    members = {k: v for k, v in fingerprints.items() if k.startswith("i:C/")}

    assert members, (
        f"{label}: the class produced no member sub-symbols at all "
        f"({sorted(fingerprints)}). A class member is a sub-symbol by the "
        "contract, and an answer with no members passes every byte assertion "
        "below by having nothing to assert on"
    )
    assert expected in fingerprints.get("i:C", ""), (
        f"{label}: the class fingerprint {fingerprints.get('i:C')!r} does not "
        f"contain the documented rendering {expected!r}. Rule 2 of the grammar "
        "is that every optional marker lives in an ALWAYS-PRESENT bracket slot, "
        "`[]` when empty; omitting the empty slot is how Go shipped a marker a "
        "field name could spell"
    )
    two_slots = re.compile(
        r"^\[(?:prop|method|get|set|ctor|call|new|index)\]\[[a-z,]*\]"
    )
    for key, text in members.items():
        assert two_slots.match(text), (
            f"{label}: the member {key} rendered as {text!r}, which does not "
            "open with a kind slot followed by a modifier slot. Both slots are "
            "unconditional — the modifier slot is `[]` when there are no "
            "modifiers — and that is what stops a name occupying the column a "
            "marker would otherwise have occupied"
        )


def test_quoting_a_member_name_is_not_a_signature_change(compare_ts) -> None:
    """`{ foo }` and `{ "foo" }` are ONE member, and the fold must say so.

    GREEN TODAY. Red under M3.

    This is the third device the body measured as undefended, and it is the one
    whose failure is a FALSE POSITIVE rather than a false negative — which makes
    it the one most likely to ship, because a gate that over-reports looks
    conservative right up until the 996-file repository it guards stops being
    read.

    The input is ordinary production churn, not an attack: Prettier's
    `quoteProps` setting (`"as-needed"`, `"consistent"`, `"preserve"`) rewrites
    exactly this, in bulk, across every object type in a repository, and
    switching it is a one-line change to a config file that no reviewer reads as
    a signature edit. TypeScript agrees the two are one member — `{ foo }` and
    `{ "foo" }` are the same property — so a comparator that disagrees is simply
    wrong, not merely noisy.

    Green when: quoting a member name is silent, AND — in the same seal — the
    partner edit that changes the member's TYPE under the same quoting is still
    caught.

    THE PARTNER IS THE ANTI-VACUITY DEVICE, by the argument section 6 makes:
    "quoting is silent" is satisfied by a renderer that drops member names
    entirely, which would make the retype silent too. The two are asserted
    together and neither means anything alone.

    Falsify: **M3** — in `nameAtomOf`, drop the `isIdentifierText` guard on the
    string-literal arm so a quoted name always lands on the `s` tag::

        return segment('s', node.text);

    Measured: the silent half goes red (`i:foo` becomes `s:"foo"`), the partner
    half stays green, and M3 reddens ZERO of the 151 rows that predate this
    section.
    """
    bare = "export interface I { foo: string }\n"
    quoted = 'export interface I { "foo": string }\n'
    retyped = 'export interface I { "foo": number }\n'

    assert _ts_changed(compare_ts, bare, quoted) is False, (
        "quoting a member name was reported as a signature change. `{ foo }` "
        'and `{ "foo": … }` are the same member to TypeScript, and the rewrite '
        "between them is what Prettier's `quoteProps` does in bulk. A gate that "
        "reports a contract change for a formatter setting reports it across "
        "every object type at once, and is not read again"
    )
    assert _ts_changed(compare_ts, quoted, retyped) is True, (
        "the partner half: retyping a quoted member was silent too. A "
        "normalisation that reaches this row is deletion — the member name, or "
        "the member itself, went out with the quotes"
    )


def test_quoting_a_class_member_name_does_not_move_its_symbol_key() -> None:
    """The fold is the IDENTITY, so quoting may not move a KEY either.

    GREEN TODAY. Red under M3.

    Separate from the seal above because it fails one level down and fails
    worse. A class member is a sub-symbol, so its name is part of a KEY. If
    quoting moves `i:C/i:m` to `i:C/s:m`, the comparator does not report "a
    member changed" — it reports one symbol REMOVED and another ADDED, and
    removal is the blocking direction. Prettier's `quoteProps` would then block
    every branch that touched it, for a rewrite that changes nothing.

    Green when: the two spellings produce identical symbol MAPS — same keys,
    same fingerprints — and the retype partner still moves the fingerprint while
    keeping the key.

    Falsify: **M3**, as above. Measured: the key becomes `i:C/s:m` and the first
    assertion reddens, while the partner half stays green.
    """
    bare = _fingerprints(_TS, "export class C { m(): void {} }\n")
    quoted = _fingerprints(_TS, 'export class C { "m"(): void {} }\n')
    retyped = _fingerprints(_TS, 'export class C { "m"(): number { return 1; } }\n')

    assert bare and quoted, (
        f"one spelling fingerprinted to nothing ({bare} vs {quoted}); two empty "
        "answers are equal, which would pass the assertion below for free"
    )
    assert bare == quoted, (
        "quoting a class member's name moved its SYMBOL KEY. That is not "
        "reported as a changed member — it is reported as one symbol removed and "
        f"another added, and removed is the direction that blocks. {bare} vs "
        f"{quoted}"
    )
    assert set(quoted) == set(retyped), (
        "the partner half: changing a member's RETURN TYPE moved the symbol set, "
        "so the key is carrying something other than the member's name"
    )
    assert quoted != retyped, (
        "the partner half: changing a member's return type was silent. A "
        "renderer that made the quoting seal above pass by dropping member names "
        "would also pass that seal, which is why both are asserted here"
    )


def test_a_private_name_and_a_string_literal_of_the_same_spelling_stay_two_members(
    compare_ts,
) -> None:
    """`#secret` and `"#secret"` are DIFFERENT members and must not fold.

    GREEN TODAY. Red under M7.

    Found while measuring this section rather than named in the body's report,
    and it is the sharpest of the tag-split cases. `#secret` is not identifier
    text, so it reaches `renderAtom` quoted — but under tag `i`, deliberately,
    because a string-literal member spelled `"#secret"` is a different member and
    belongs on `s`. Route the private identifier through `segment('s', …)` and
    the two acquire the SAME KEY, and the fold that exists to make declaration
    merging representable silently swallows one of them: the class loses a
    member from its symbol set with no error anywhere.

    Provenance: private fields are ordinary production TypeScript and the primary
    target has them. The pairing with a string-literal `"#secret"` in the same
    class is adversarial, and this row says so — its job is to make the tag split
    falsifiable, exactly as the forgery table's forgers do.

    Green when: the class has three symbols — itself and both members — with
    distinct keys, and deleting the private field is still caught.

    Falsify: **M7** — in `nameAtomOf`, replace the `PrivateIdentifier` arm's
    `['i', node.text]` with `segment('s', node.text)`. Measured: the two members
    collapse into the single key `i:C/s:#secret` joined by `+`, this seal
    reddens, and M7 reddens ZERO of the 151 rows that predate this section.
    """
    both = 'export class C {\n  #secret: number = 1;\n  "#secret": string = "x";\n}\n'
    without_private = 'export class C {\n  "#secret": string = "x";\n}\n'

    fingerprints = _fingerprints(_TS, both)
    assert set(fingerprints) == {"i:C", "i:C/i:#secret", "i:C/s:#secret"}, (
        'a private `#secret` and a string-literal member `"#secret"` are two '
        "different members of one class and must key differently. They produced "
        f"{sorted(fingerprints)}. Sharing a key means the overload fold merges "
        "them and the class quietly loses a member — the fold exists to make "
        "declaration merging representable, not to hide members"
    )
    assert _ts_changed(compare_ts, both, without_private) is True, (
        "the control half: deleting the private field was silent, so the two "
        "members were never separately represented in the first place"
    )


#: The three positions the EMPTY name reaches, all legal, all found by the soak
#: in real code rather than by reading — `main.cjs` records the finding at
#: `segment()`. Each lands on the `k:empty` slot.
_THE_EMPTY_NAME: tuple[tuple[str, str, str], ...] = (
    (
        "an interface member with an empty name",
        'export interface I { "": number }\n',
        "i:I",
    ),
    ("an ambient module with an empty name", 'declare module "" {}\n', "k:empty"),
    (
        "a star re-export from an empty specifier",
        'export * from "";\n',
        "k:export/k:star/k:empty",
    ),
)


@pytest.mark.parametrize(
    "label, source, key", _THE_EMPTY_NAME, ids=[r[0] for r in _THE_EMPTY_NAME]
)
def test_the_empty_name_is_representable_rather_than_a_helper_bug(
    label: str, source: str, key: str
) -> None:
    """`interface I { "": number }` compiles, so the gate may not fault on it.

    GREEN TODAY. Red under M6.

    `ts_symbol_key` refuses an empty segment text, correctly — a key built from a
    bug matches nothing across revisions. But an empty NAME is not a bug, it is
    legal TypeScript, and all three shapes above were found by the soak in real
    code. Before the `segment()` guard the helper threw and the caller reported
    HELPER_FAILED: the gate switching ITSELF OFF on ordinary compiling code,
    which is the worse of the two ways to be wrong, because a fault is not a
    lenient answer — it is no answer, over the whole file.

    Green when: each shape fingerprints without a fault, at its `k:empty` key.

    Falsify: **M6** — remove the guard, so `segment()` is the identity::

        function segment(tag, text) { return [tag, text]; }

    Measured: all three rows raise `ComparatorUnavailable(helper_failed: empty
    text for a s segment)` and `_fingerprints` fails them with the `NO TRUSTED
    PARSER` marker. M6 reddens ZERO of the 151 rows that predate this section —
    which is to say the guard that stops the gate faulting on legal code had no
    seal at all.

    RULING REQUEST — **GRANTED, P4, 2026-08-10.** The word is written. The seal
    author's argument is the ruling's argument and is not restated here: it is at
    `TS_KEY_TAGS`, which now lists `empty` among the keyword slots and carries
    the reason the slot is `k` and the reason it cannot be forged, and at
    `TypeScriptSignatureFingerprinter`'s key-position list, which now names the
    position. **The TAG SET is untouched and stays closed at `{i,s,c,k}`** —
    sealed shut by
    `test_a_key_built_from_a_helper_bug_is_refused_rather_than_returned` — and
    that is the whole distinction the ruling turns on: the word list has always
    been open, because an open word list is what a keyword slot IS, while an open
    tag set would put a forgeable prefix at offset 0 of a segment.

    Nothing in this row changed. It pinned the right behaviour before the ruling
    and pins it after; what changed is that it now pins behaviour the contract
    requires instead of behaviour the contract was silent about.
    """
    fingerprints = _fingerprints(_TS, source)
    assert key in fingerprints, (
        f"{label}: {key!r} is not among {sorted(fingerprints)}. The empty name is "
        "legal TypeScript in this position and the gate may not fault on it: a "
        "fault is not a conservative answer, it is no answer over the whole file"
    )

    # The forgery half of the ruling request, judged in the same call so that a
    # green above cannot be bought by `k:empty` swallowing its neighbours.
    named_empty = _fingerprints(_TS, "export interface I { empty: number }\n")
    spelled = _fingerprints(_TS, 'export interface I { "k:empty": number }\n')
    unnamed = _fingerprints(_TS, 'export interface I { "": number }\n')
    assert len({named_empty["i:I"], spelled["i:I"], unnamed["i:I"]}) == 3, (
        "a member named `empty`, a member spelled `k:empty` and a member with NO "
        "name must render three different ways. They rendered "
        f"{named_empty['i:I']!r}, {spelled['i:I']!r} and {unnamed['i:I']!r}. The "
        "`k` tag exists so that a position no identifier can name is a position "
        "no identifier can FORGE"
    )


def test_export_equals_keeps_its_own_slot_and_never_the_default_one() -> None:
    """`export = X` and `export default X` are two different promises.

    GREEN TODAY. Red under M5.

    They are not interchangeable, and the difference is load-bearing for every
    importer: `export = X` is the CommonJS-shaped export that
    `import X = require('m')` and `import * as X` consume, `export default X` is
    the ES one. Swapping them breaks every consumer — at build time for some and
    at run time for the rest, depending on `esModuleInterop`. They must not share
    a key, or the swap reads as one symbol whose fingerprint moved rather than as
    what it is: one promise withdrawn and a different one made.

    Green when: `export = X` keys `k:export`, `export default X` keys
    `k:default`, a named export keys `k:export/i:b`, and an ambient module NAMED
    "export" keys `s:export` — four distinct positions, none reachable from
    another.

    Falsify: **M5** — in the `ExportAssignment` arm of `collectStatement`, key
    both forms `['k', 'default']`. Measured: `export = X` moves to `k:default`,
    the first assertion reddens, and M5 reddens ZERO of the 151 rows that predate
    this section.

    RULING REQUEST — **GRANTED, P4, 2026-08-10: the contract gains the sentence
    rather than this row losing itself.** The seal author was right that the row
    pinned an unruled accident, and right to say so instead of leaving it to be
    discovered; the question P4 had to answer is whether the accident was the
    RIGHT answer, because a row pinning correct-but-unruled behaviour and a row
    pinning a bug look identical from here.

    It is the right answer, and the reason is that `export = X` does not export a
    NAME out of the module's surface — it REPLACES the surface, the module *is*
    `X` — so the symbol it should own is the export-surface subtree root itself,
    with nothing under it, which is exactly the bare `k:export`. No other key is
    true of it: `k:export/i:X` would claim a named export that does not exist,
    and `k:default` is the other export form and the one thing it must never be
    confused with. `TypeScriptSignatureFingerprinter`'s key-position list and its
    export-surface bullet now both name it, with the importer-breakage argument
    this docstring makes.

    Nothing in this row changed.
    """
    equals = _fingerprints(_TS, "declare const X: number;\nexport = X;\n")
    default = _fingerprints(_TS, "const X: number = 1;\nexport default X;\n")
    named = _fingerprints(_TS, "declare const b: number;\nexport { b };\n")
    module = _fingerprints(_TS, 'declare module "export" {}\n')

    assert "k:export" in equals and "k:default" not in equals, (
        "`export = X` must key `k:export` and must never reach the anonymous "
        f"default slot; it produced {sorted(equals)}. The two export forms are "
        "different promises to every importer, and a shared key reports the swap "
        "between them as one symbol changing rather than as one promise being "
        "withdrawn and another made"
    )
    assert "k:default" in default and "k:export" not in default, (
        f"`export default X` must key `k:default`; it produced {sorted(default)}"
    )
    assert "k:export/i:b" in named, (
        f"`export {{ b }}` must key `k:export/i:b`; it produced {sorted(named)}"
    )
    assert "s:export" in module and "k:export" not in module, (
        'an ambient module NAMED "export" must land on the `s` tag and must not '
        f"forge the keyword slot; it produced {sorted(module)}"
    )


def test_the_helper_environment_drops_every_node_and_npm_variable() -> None:
    """The environment scrub — a gate input the operator's shell can reach.

    GREEN TODAY. Red under M4.

    A different class from the three devices above: this is not a forgery, it is
    an ENVIRONMENT-CONTROLLED INPUT to the program that decides what a branch's
    signatures are. `NODE_OPTIONS` can carry `--require`, which executes
    arbitrary code before the helper's first line; `NODE_PATH` is a module search
    root taken from the environment, and this unit's whole rule is that search
    roots come from `__file__`. A shell that exports either for an unrelated
    project silently joins the trusted base.

    The contract writes the strip as a PREFIX rule rather than a list of the
    dangerous names, and that choice is what is sealed: `NODE_A_FUTURE_ONE` is in
    the table below and there is no list it could appear on.

    Green when: every `NODE_*` and `NPM_CONFIG_*` variable is gone, AND — in the
    same call — `PATH`, `HOME` and an unrelated variable survive.

    THE SURVIVORS ARE THE CONTROL, AND WITHOUT THEM THIS SEAL IS VACUOUS.
    `return {}` strips every dangerous variable and passes the first half
    perfectly, while breaking the helper on every machine (`node` is found on
    `PATH`, exactly as `go` is). Asserting only the removals is asserting that
    the function is destructive, not that it is correct.

    Falsify: **M4** — replace the comprehension in `_node_toolchain_environment`
    with `return dict(os.environ)`. Measured red, and M4 reddens ZERO of the 151
    rows that predate this section: the scrub described in four contract
    paragraphs had no executable seal anywhere.
    """
    import os

    hostile = {
        "NODE_OPTIONS": "--require /tmp/evil.js",
        "NODE_PATH": "/repo/node_modules",
        "NODE_EXTRA_CA_CERTS": "/tmp/ca.pem",
        "NODE_A_FUTURE_ONE": "whatever it turns out to do",
        "NPM_CONFIG_PREFIX": "/tmp/npm",
        "NPM_CONFIG_REGISTRY": "http://127.0.0.1:1/",
    }
    survivors = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/home/someone",
        "EVENPLAY_UNRELATED": "kept",
    }

    saved = os.environ
    try:
        os.environ = dict(hostile, **survivors)  # type: ignore[assignment]
        scrubbed = role_protocol._node_toolchain_environment()
    finally:
        os.environ = saved  # type: ignore[assignment]

    for name in hostile:
        assert name not in scrubbed, (
            f"{name} survived into the environment the helper runs under. The "
            "strip is a PREFIX rule — every `NODE_*` and every `NPM_CONFIG_*` — "
            "rather than a list of the dangerous ones, because the helper needs "
            "none of them and a future one has to be closed in advance rather "
            "than discovered"
        )
    for name, value in survivors.items():
        assert scrubbed.get(name) == value, (
            f"{name} was stripped along with the dangerous variables. `node` is "
            "found on PATH exactly as `go` is, and a function that returns an "
            "empty environment passes every removal assertion above while making "
            "the helper unrunnable — which is the vacuous way to pass this seal"
        )


def test_the_helper_process_is_actually_given_the_scrubbed_environment() -> None:
    """The scrub is plumbed into the subprocess, not merely computed.

    GREEN TODAY. Red under M4b.

    The seal above proves the function is correct. It does not prove anything
    calls it, and a correct function nobody calls is exactly the shape of defect
    this unit keeps finding: `_run_ts_helper` is the only place the property
    becomes real, and `env=` there is one token wide.

    The `cwd` is asserted in the same call and for the reason it is set: Node
    resolves `require` by walking UP from the requiring file and, for some
    lookups, from the CWD, and it reads `package.json` from ancestor directories
    to decide CommonJS-versus-ESM. Left at the judged checkout, the ancestor
    chain is the branch's — the untrusted-parser problem arriving by a second
    door.

    Green when: `subprocess.run` is called with the scrubbed mapping and with
    `cwd` set to the parser's own directory.

    Falsify: **M4b** — change `env=_node_toolchain_environment()` to `env=None`
    and `cwd=str(directory)` to `cwd=None` in `_run_ts_helper`. Measured red, and
    M4b reddens ZERO of the 151 rows that predate this section.
    """
    import os
    import subprocess

    captured: dict[str, object] = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout=b"{}", stderr=b"")

    saved_run = subprocess.run
    saved_environ = os.environ
    directory = Path("/nonexistent/parser/home")
    try:
        os.environ = dict(  # type: ignore[assignment]
            {"NODE_OPTIONS": "--require /tmp/evil.js", "NODE_PATH": "/repo/nm"},
            PATH="/usr/bin",
        )
        subprocess.run = _fake_run  # type: ignore[assignment]
        role_protocol._run_ts_helper("node", directory, _TS, "export const a = 1;\n")
    finally:
        subprocess.run = saved_run  # type: ignore[assignment]
        os.environ = saved_environ  # type: ignore[assignment]

    assert captured.get("args"), (
        "`_run_ts_helper` never reached `subprocess.run` at all, so every "
        "assertion below would be checking a mapping nobody built. A pass "
        "condition satisfiable by executing nothing is the second vacuous seal "
        "this unit has already shipped"
    )
    env = captured.get("env")
    assert isinstance(env, dict), (
        f"the helper subprocess was launched with env={env!r}, which means it "
        "INHERITS the operator's environment. `NODE_OPTIONS` in an inherited "
        "environment executes arbitrary code before the helper's first line, and "
        "the helper is the program that decides what a branch's signatures are"
    )
    assert "NODE_OPTIONS" not in env and "NODE_PATH" not in env, (
        f"the scrub is computed but not plumbed: the process was given {sorted(env)}"
    )
    assert env.get("PATH") == "/usr/bin", (
        "the process was given an environment with no PATH; `node` is found on "
        "PATH, so that would be a helper which cannot run rather than a helper "
        "which runs safely"
    )
    assert captured.get("cwd") == str(directory), (
        f"the helper's cwd was {captured.get('cwd')!r}, not the parser's own "
        "directory. Node reads `package.json` from ancestor directories and "
        "resolves some lookups from the CWD; left at the judged checkout the "
        "ancestor chain is the branch's, which restores the untrusted-parser "
        "problem by a second door"
    )


def test_the_forgery_tables_are_intact_and_every_row_is_a_real_probe() -> None:
    """A structural seal on this section's own tables.

    GREEN TODAY.

    The argument `test_the_normalisation_tables_are_paired_and_rule_both_ways`
    makes for section 6, and it earns its place for the same reason: a table that
    quietly loses rows still runs, still reports green for whatever survives, and
    stops proving what the section claims. The specific failure refused here is a
    forger row edited until it no longer forges — the fastest way to make a red
    row green is to make it stop asking.

    Green when: no forger equals its twin, no duplicate labels, every hostile
    name is genuinely non-identifier text, the member-shape table rules the empty
    slot in BOTH directions, and every mutation a row names is one this section
    claims to have measured.
    """
    labels = [row[0] for row in _FORGED_FINGERPRINTS]
    assert len(labels) == len(set(labels)), f"duplicate forgery labels: {labels}"
    measured = {"M1", "M2", "M2b", "M3", "M4", "M4b", "M5", "M6", "M7"}
    for label, forger, twin, mutation in _FORGED_FINGERPRINTS:
        assert forger != twin, (
            f"{label}: the forger and its twin are the same text, so the row "
            "proves nothing"
        )
        assert mutation in measured, (
            f"{label}: names the mutation {mutation!r}, which is not one this "
            "section measured. A falsifier nobody ran is a claim, not a seal"
        )

    assert len(set(_NAMES_THE_PARSER_DID_NOT_CERTIFY)) == len(
        _NAMES_THE_PARSER_DID_NOT_CERTIFY
    ), "duplicate hostile member names"
    for name in _NAMES_THE_PARSER_DID_NOT_CERTIFY:
        assert not name.isidentifier(), (
            f"{name!r} is plain identifier text, so it normalises to the `i` tag "
            "and the quoting assertion it sits in cannot fail"
        )

    shapes = [row[0] for row in _MEMBER_SHAPES]
    assert len(shapes) == len(set(shapes)), f"duplicate member shapes: {shapes}"
    assert any("[]" in row[2] for row in _MEMBER_SHAPES) and any(
        "][" in row[2] and "[]" not in row[2] for row in _MEMBER_SHAPES
    ), (
        "the member-shape table must contain BOTH a member with no modifiers and "
        "a member with some, or the always-present-slot rule is asserted in only "
        "one direction and an unconditional `[]` would pass it"
    )


def test_the_absolute_path_rule_is_still_explained_where_a_reader_meets_it() -> None:
    """The header paragraph that says WHY the parser is addressed absolutely.

    GREEN TODAY, and it is a seal on the RECORD rather than on the property.

    `main.cjs` requires the parser as `path.join(__dirname, 'typescript.js')` and
    never as `require('typescript')`, and that is the central security property
    of unit D4: `require('typescript')` walks up from the requiring file looking
    for a `node_modules`, and a branch that edited its own
    `node_modules/typescript/lib/typescript.js` to drop a modifier would be
    choosing the program that decides what its signatures are.

    THIS ROW USED TO SAY THAT PROPERTY COULD NOT BE SEALED, AND IT WAS RIGHT
    UNTIL THE P4 ADJUDICATION OF 2026-08-10. The seal author recorded the hole
    rather than papering over it: the body's measurement of 53 rows reddening
    under `require('typescript')` was an ARTIFACT of this machine having no
    ambient `typescript` on the resolution path, so the mutant simply failed to
    load. On a machine that HAS one the mutant would resolve, run, and go green
    with the defect present. A falsification that depends on the alternative
    parser being absent is not a falsification of the parser being untrusted.

    **The hole is closed and the seal is section 14.** P4 ruled for the change
    the seal author proposed: `--probe` now reports `parser`, the filename Node
    resolved for the module the helper is actually holding, and
    `_probe_node_and_parser` compares it against the vendored file by IDENTITY.
    Section 14 manufactures the hostile machine — an ambient `node_modules/
    typescript` reporting the same version — and measures the refusal, so the
    property is falsifiable HERE and on every machine.

    What survives in this row is the documentation half, and it is worth keeping
    on its own merits: the header is where a reader learns why the rule exists,
    and section 14 seals the mechanism without teaching anybody the reason.

    Green when: the header still names the rule and both halves of it.
    Falsify: delete the paragraph. (Deleting the RULE is section 14's job.)
    """
    helper = _prose(
        Path(role_protocol.__file__)
        .with_name("ts_signature_fingerprint")
        .joinpath("main.cjs")
        .read_text(encoding="utf-8")[:6000]
    )
    assert _prose("WHY THE PARSER IS REQUIRED BY ABSOLUTE PATH") in helper, (
        "the helper stopped explaining why it addresses its parser absolutely. "
        "Section 14 seals that the rule HOLDS; this paragraph is the only place "
        "that says why it exists, and a mechanism whose reason is unwritten is "
        "the mechanism the next refactor removes for being unexplained"
    )
    assert _prose("typescript.js") in helper and _prose("require('typescript')") in helper, (
        "the header no longer names both halves of the rule — the absolute path "
        "it uses, and the resolution it refuses"
    )


# --------------------------------------------------------------------------- #
# 14 — WHICH PARSER ACTUALLY RAN, ANSWERED BY IDENTITY
#
# GREEN TODAY. Added by the P4 adjudication, 2026-08-10, together with the
# production change it rules for (task #15).
#
# WHY THIS SECTION EXISTS
# -----------------------
# Everything unit D4 does to keep the branch from choosing its own parser was,
# until this section, unfalsifiable:
#
#   * `ts_parser_home` proves a file EXISTS at a computed path (section 1);
#   * `TS_VENDORED_PARSER_SHA256` proves BYTES ON DISK at that path (section 2);
#   * `--probe` proved a VERSION STRING.
#
# None of those says which file the helper process loaded. The seal author
# found this and stated it precisely: mutating `main.cjs` to
# `require('typescript')` reddens 53 rows on THIS machine only, because nothing
# ambient resolves here, and on a laptop with a global install, a CI image with
# hoisted `node_modules`, or the primary target checkout — which vendors
# TypeScript — the mutant resolves, runs, and goes green with the defect
# present. The digest would still pass: it would be vouching for bytes nobody
# loaded. The version would still pass too, and that is the part that kills any
# cheaper fix — measured below, the ambient copy reports the SAME `5.9.3`.
#
# THE RULING, AND WHAT IT COST
# ----------------------------
# P4 ruled for the change the seal author proposed. `--probe` now reports
# `parser`: the filename NODE resolved for the module object the helper holds,
# read out of the loader's own `module.children` rather than recomputed from
# the specifier — recomputing would seal nothing, since a mutant that changed
# the specifier and left the computation alone would report a path it did not
# load. `_probe_node_and_parser` compares it against the vendored file by
# identity and refuses anything else, as TOOLCHAIN_UNUSABLE and not a seventh
# fault: the trusted parser is present and its digest matched, so this is a
# runtime that loaded the wrong thing, not a missing helper.
#
# HOW THESE ROWS AVOID THE TRAP THAT MADE THE OLD ONES UNFALSIFIABLE
# -------------------------------------------------------------------
# By MANUFACTURING the machine instead of hoping for it. Each row builds a
# checkout that has an ambient `node_modules/typescript` on the resolution
# path — the exact machine the hole describes — and every row carries its
# control on the same manufactured machine, so a refusal cannot be bought by
# the temporary directory being odd. The stub reports `5.9.3` deliberately:
# a row that let the ambient copy report a different version would be sealing
# the version check that already existed.
# --------------------------------------------------------------------------- #


#: The shipped parser directory. Read through `role_protocol` rather than
#: hard-coded, so a rename of `TS_HELPER_PACKAGE_DIR` moves this with it.
def _vendored_dir() -> Path:
    return Path(role_protocol.__file__).with_name(role_protocol.TS_HELPER_PACKAGE_DIR)


#: The one line in `main.cjs` this section mutates. Asserted present rather
#: than assumed: a rewritten helper must redden this section loudly rather than
#: have its mutation silently not apply, which is how a falsifier stops
#: falsifying.
_THE_ABSOLUTE_REQUIRE = "const ts = require(path.join(__dirname, 'typescript.js'));"

#: An ambient TypeScript that is NOT the vendored one and says it is 5.9.3 —
#: the same release this build pins. That equality is the point of the stub:
#: it is what makes the pre-existing version check provably unable to separate
#: the two copies. `--probe` reads `ts.version` and, at module load, a handful
#: of `ts.SyntaxKind` members, so the proxy answers everything else with 0.
_AMBIENT_PARSER_STUB = """'use strict';
module.exports = new Proxy({ version: '5.9.3' }, {
  get(target, key) {
    if (key in target) return target[key];
    return new Proxy({}, { get: () => 0 });
  },
});
"""


def _a_machine_with_an_ambient_typescript(
    root: Path, *, require_line: str | None = None, probe_line: str | None = None
) -> Path:
    """A parser directory with a hostile `node_modules/typescript` beside it.

    The vendored parser is PRESENT (symlinked, so its resolved path is the real
    one) and correct — that is what makes the negative rows say something: the
    trusted parser is there and passes every existing check, and the helper
    loaded somebody else's anyway.
    """
    root.mkdir(parents=True, exist_ok=True)
    source = (_vendored_dir() / role_protocol.TS_HELPER_ENTRY_POINT).read_text(
        encoding="utf-8"
    )
    assert source.count(_THE_ABSOLUTE_REQUIRE) == 1, (
        "`main.cjs` no longer contains the line this section mutates "
        f"({_THE_ABSOLUTE_REQUIRE!r}). A falsifier that does not apply is not a "
        "falsifier, and every negative row below would pass by doing nothing"
    )
    if require_line is not None:
        source = source.replace(_THE_ABSOLUTE_REQUIRE, require_line)
    if probe_line is not None:
        old = "        parser: loadedParserPath(),\n"
        assert source.count(old) == 1, (
            "the probe no longer reports `parser` at all; the identity check "
            "this section seals has been removed from the helper side"
        )
        source = source.replace(old, probe_line)
    (root / role_protocol.TS_HELPER_ENTRY_POINT).write_text(source, encoding="utf-8")

    link = root / role_protocol.TS_VENDORED_PARSER
    if not link.exists():
        link.symlink_to(_vendored_dir() / role_protocol.TS_VENDORED_PARSER)

    ambient = root / "node_modules" / "typescript"
    ambient.mkdir(parents=True, exist_ok=True)
    (ambient / "package.json").write_text(
        '{"name":"typescript","version":"5.9.3","main":"index.js"}\n', encoding="utf-8"
    )
    (ambient / "index.js").write_text(_AMBIENT_PARSER_STUB, encoding="utf-8")
    return root


def test_the_probe_says_which_parser_node_actually_loaded(tmp_path: Path) -> None:
    """`--probe` reports the loaded parser, and it is the vendored file.

    GREEN TODAY. Red under M8a.

    The positive direction, measured against the SHIPPED directory rather than
    a manufactured one, because the thing being asserted is that the real gate
    path loads the real parser. The two pre-existing fields are asserted in the
    same call: this ruling ADDS a field and may not quietly remove the version
    checks that were already there.

    Green when: `--probe` exits 0, its document carries `node`, `typescript` and
    `parser`, `parser` resolves to the vendored `typescript.js`, and
    `_probe_node_and_parser` accepts the shipped directory.

    Falsify: **M8a** — drop `parser` from the probe document. Measured: **88
    rows red**, which is every execution seal in this file plus all three of
    section 14, because `_probe_node_and_parser` then refuses every TypeScript
    file on the machine. That is the correct blocking answer to "which parser
    ran is unknown" and it is worth naming as the shape it is: a helper that
    stops answering this question takes the whole comparator down rather than
    quietly clearing branches.
    """
    import subprocess

    try:
        directory = role_protocol.ts_parser_home()
    except ComparatorUnavailable as exc:
        pytest.fail(f"{_NO_PARSER}: {exc.fault.value}: {exc.message}")

    entry = directory / role_protocol.TS_HELPER_ENTRY_POINT
    probe = subprocess.run(
        [shutil.which("node") or "node", str(entry), "--probe"],
        capture_output=True,
        cwd=str(directory),
        env=role_protocol._node_toolchain_environment(),
    )
    assert probe.returncode == 0, (
        f"`node main.cjs --probe` exited {probe.returncode}: {probe.stderr!r}"
    )
    reported = json.loads(probe.stdout.decode("utf-8"))

    assert set(reported) >= {"node", "typescript", "parser"}, (
        f"the probe document is {reported!r}. `parser` is what makes the "
        "untrusted-parser property checkable at all, and `node` and "
        "`typescript` are the version checks that existed before it — this "
        "ruling adds a field and removes nothing"
    )
    assert reported["typescript"] == role_protocol.TS_VENDORED_PARSER_VERSION, (
        f"the loaded parser reports {reported['typescript']!r}, not the pinned "
        f"{role_protocol.TS_VENDORED_PARSER_VERSION!r}"
    )
    assert (
        Path(reported["parser"]).resolve()
        == (directory / role_protocol.TS_VENDORED_PARSER).resolve()
    ), (
        f"the helper loaded {reported['parser']!r}, not the vendored parser at "
        f"{str(directory / role_protocol.TS_VENDORED_PARSER)!r}"
    )

    # And the caller accepts it — the property is only real where it is checked.
    assert role_protocol._probe_node_and_parser(directory), (
        "`_probe_node_and_parser` did not return the `node` it probed"
    )


def test_a_helper_that_loaded_an_ambient_parser_is_refused_by_identity(
    tmp_path: Path,
) -> None:
    """**THE ROW THAT CLOSES THE HOLE.** Both halves, on one hostile machine.

    GREEN TODAY. Red under M8b.

    This is the machine the seal author could not reach and therefore could not
    seal against: a checkout with an ambient `node_modules/typescript` on the
    resolution path. It is manufactured here rather than waited for, so the
    property is falsifiable on every machine and not only on one that happens
    to have a global TypeScript installed.

    THE CONTROL IS ON THE SAME MACHINE AND WITHOUT IT THIS ROW IS VACUOUS. An
    unmutated `main.cjs`, in the same directory, with the same hostile
    `node_modules` one level down, must be ACCEPTED. Otherwise a refusal bought
    by the temporary directory being unusual for any reason at all would read as
    the security property holding.

    AND THE VERSIONS ARE COMPARED, which is the row's second job: the ambient
    stub reports `5.9.3`, the same release this build pins, and both probes
    report it. That is the measurement that says the pre-existing version check
    could never have caught this — a version string is equally true of the
    untrusted copy — so the identity check is doing work no cheaper check does.

    Green when: the mutant is refused with TOOLCHAIN_UNUSABLE naming the file it
    loaded, the honest twin on the same machine is accepted, and the two report
    the same `typescript` version.

    Falsify: **M8b** — neuter the identity comparison in
    `_probe_node_and_parser` (`if False and loaded != expected:`). Measured:
    **exactly one row red, this one** — the mutant is accepted and the other 189
    rows in this file stay green. That count is the finding, not a footnote: it
    says nothing else in this suite can see an untrusted parser being loaded,
    which is precisely the state the seal author reported and this row ends.
    """
    import subprocess

    node = shutil.which("node")
    assert node, "`node` is not on PATH; this row cannot measure what it claims"

    honest = _a_machine_with_an_ambient_typescript(tmp_path / "honest")
    mutant = _a_machine_with_an_ambient_typescript(
        tmp_path / "mutant", require_line="const ts = require('typescript');"
    )

    def _probe_document(directory: Path) -> dict:
        probe = subprocess.run(
            [node, str(directory / role_protocol.TS_HELPER_ENTRY_POINT), "--probe"],
            capture_output=True,
            cwd=str(directory),
            env=role_protocol._node_toolchain_environment(),
        )
        assert probe.returncode == 0, (
            f"the probe in {directory} exited {probe.returncode}: {probe.stderr!r}. "
            "The mutant must RESOLVE AND RUN here — a mutant that fails to load "
            "is the artifact this whole section exists to stop relying on"
        )
        return json.loads(probe.stdout.decode("utf-8"))

    honest_doc = _probe_document(honest)
    mutant_doc = _probe_document(mutant)

    assert honest_doc["typescript"] == mutant_doc["typescript"], (
        f"the honest helper reported TypeScript {honest_doc['typescript']!r} and "
        f"the mutant reported {mutant_doc['typescript']!r}. The stub is meant to "
        "claim the SAME version as the vendored parser, because that is what "
        "proves a version check cannot separate the two copies. With different "
        "versions this row would be re-sealing the check that already existed"
    )
    loaded_by_mutant = Path(mutant_doc["parser"]).resolve()
    assert loaded_by_mutant != Path(honest_doc["parser"]).resolve(), (
        f"both helpers reported loading {mutant_doc['parser']!r}, so the mutation "
        "did not take effect and the refusal below would prove nothing"
    )

    # The control: same machine, same ambient node_modules, honest require.
    assert role_protocol._probe_node_and_parser(honest), (
        "the UNMUTATED helper was refused on this machine. Then the refusal "
        "below is not the identity check working, it is the manufactured "
        "directory being rejected for some unrelated reason, and this row would "
        "be certifying nothing"
    )

    with pytest.raises(ComparatorUnavailable) as caught:
        role_protocol._probe_node_and_parser(mutant)

    assert caught.value.fault is ComparatorFault.TOOLCHAIN_UNUSABLE, (
        f"a helper that loaded an untrusted parser was refused as "
        f"{caught.value.fault.value}. The vendored parser is present and its "
        "digest matches — the failure is a runtime that loaded something else, "
        "which is a toolchain present and unusable, and this design adds no "
        "seventh fault"
    )
    assert mutant_doc["parser"] in caught.value.message, (
        f"the refusal does not name the file that was actually loaded; it said "
        f"{caught.value.message!r}. An operator reading this must be able to see "
        "WHICH parser ran, because that is the whole finding"
    )


def test_a_probe_that_will_not_say_which_parser_it_loaded_is_refused(
    tmp_path: Path,
) -> None:
    """A helper that stops answering the question is refused, not trusted.

    GREEN TODAY. Red under M8c.

    The identity check has two sides and the seal above only exercises one. If
    the helper simply stops reporting `parser` — the natural shape of somebody
    removing the check from the side that is not `role_protocol` — then a caller
    that treated a missing field as "nothing to compare" would be back to the
    state this ruling closed, with a `--probe` document that looks fine.

    So the default for "which parser ran is unknown" is a FAULT. Both spellings
    of unknown are ruled: the key absent, and the key present as `null` — which
    is what `main.cjs` itself emits if it cannot find the loaded module in the
    loader's records, deliberately, rather than guessing the path it meant to
    load.

    Green when: both spellings raise TOOLCHAIN_UNUSABLE.

    Falsify: **M8c** — let a missing `parser` default to the path that was
    expected: `reported.get("parser") or str(expected)`. That is the realistic
    shape of the fail-open, because it is what a reader tidying an "unnecessary"
    branch would write. Measured: **exactly one row red, this one.**
    """
    for label, probe_line in (
        ("the key absent", ""),
        ("the key null", "        parser: null,\n"),
    ):
        directory = _a_machine_with_an_ambient_typescript(
            tmp_path / label.replace(" ", "-"), probe_line=probe_line
        )
        with pytest.raises(ComparatorUnavailable) as caught:
            role_protocol._probe_node_and_parser(directory)
        assert caught.value.fault is ComparatorFault.TOOLCHAIN_UNUSABLE, (
            f"{label}: a probe that does not say which parser it loaded was "
            f"accepted as {caught.value.fault.value}. 'Unknown' may not be a "
            "pass: `require('typescript')` resolves on any machine with a "
            "hoisted node_modules, including the target checkout"
        )
