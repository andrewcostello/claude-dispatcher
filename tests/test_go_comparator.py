"""D2 seals (P2): the Go comparator is READ CORRECTLY, not merely unreadable.

WHY THIS FILE EXISTS
--------------------
`GoSignatureFingerprinter` is implemented and `tests/` did not touch it. The
body author measured the hole and stated it exactly: dropping parameter names
from the Go fingerprint — the precise defect `GO_SIGNATURE_EDIT_RULINGS` exists
to forbid — left the suite at 1630 passed unenrolled, and *enrolled* produced
the same failures as the unmutated tree and not one more. (That measurement said
EIGHT; P4 re-measured on 2026-08-10 and it is NINE, the ninth being this file's
own section 0 — the count does not change the argument.) Those seals pin Go as
UNREADABLE; `tests/test_role_protocol_faults.py` pins a fault as not-a-language
using a stub comparator that raises. Neither class can notice a comparator that
runs and answers WRONG, and the target repo is 2,288 Go files.

This file is the missing half: every seal here drives the REAL helper — a real
`go build`, a real subprocess, a real `go/ast` parse — and asserts the answer.

WHY NOTHING HERE ENROLS GO
--------------------------
`GO_SUPPORT` was in `PENDING_COMPARATORS` when this file was written, and
enrolling it reddened nine seals a seal author may not amend; that is a later,
separate step and it is the body author's commit, not this file's. So the seals
drive `GoSignatureFingerprinter.fingerprints` directly, and reach
`compare_signatures` only through the `compare_go` fixture, which monkeypatches
`COMPARATORS` for the duration of one test — the same registry seam
`tests/test_role_protocol_faults.py` already uses, restored by pytest before the
next test runs. Nothing here calls `check_branch`.

P4, 2026-08-10: this file is now indifferent to whether the row is enrolled, and
that is deliberate. The fixture PREPENDS the row rather than replacing the
tuple, so it supplies Go before enrolment and shadows it with the same object
after; `test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees` (which
was `test_go_is_still_not_enrolled`) pins the registry's internal consistency
instead of pinning one transient state of it. Every other seal below is
unchanged, and none of them was measured against the enrolled tree differently
from the pending one.

THE VACUITY TRAPS, AND WHAT IS DONE ABOUT EACH
----------------------------------------------
1. *A table where every row is a CHANGE* is satisfied by a comparator that
   answers "changed" to everything — a gate nobody can pass. `_SILENT` is a
   third of this file and `test_the_table_rules_both_ways` refuses a table that
   lost its silent half.
2. *A table where every row is SILENT* is satisfied by a comparator that always
   returns `{}`. Same seal, other direction, and
   `test_an_empty_answer_and_a_real_one_are_distinguishable` pins that a file
   with declarations does not fingerprint as one without.
3. *Asserting on the rulings dataclass rather than on the comparator.*
   `test_role_protocol_faults.py` already does the dataclass half (rows differ,
   both answers present, Python analogues agree). This file feeds every row's
   `before`/`after` to the live Go comparator, which is the thing that was
   never measured.
4. *A seal that cannot fail.* Each seal's docstring names the mutation that
   reddens it, and every one of those mutations was applied to a throwaway
   clone of the helper and confirmed red — see the report accompanying this
   commit for the matrix.

WHAT THIS FILE COSTS
--------------------
The helper is built ONCE per process (`_warm_helper`), after which a file
revision costs 0.76 ms (measured). The fault arms deliberately rebuild — that
is what they are testing — and account for nearly all of this file's runtime.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from claude_dispatcher import role_protocol
from claude_dispatcher.role_protocol import (
    ComparatorFault,
    ComparatorUnavailable,
    GoSignatureEditRuling,
    GoSignatureFingerprinter,
    Language,
    SignatureCheckStatus,
    SourceUnparseable,
    compare_signatures,
)


_FP = GoSignatureFingerprinter()

#: Any path is fine — the helper is contractually forbidden to open it, and
#: `Request.Path` is used for messages only. Kept realistic so a failure message
#: reads like one from the gate.
_PATH = "internal/store/store.go"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module", autouse=True)
def _warm_helper():
    """Build the helper once for the whole module.

    Not an optimisation with a nice-to-have attached: `_GO_HELPER_PREPARED` is
    the reason a 200-file Go branch costs 0.3s instead of 24s, and a file that
    rebuilt per test would be both slow and a different code path from the one
    the gate runs.
    """
    role_protocol._GO_HELPER_PREPARED = None
    role_protocol._go_helper_binary()
    yield
    role_protocol._GO_HELPER_PREPARED = None


@pytest.fixture(autouse=True)
def _restore_comparator_globals():
    """Put every module global these seals can dirty back afterwards.

    The fault arms reach into `role_protocol` on purpose — that is the only way
    to drive TOOLCHAIN_MISSING on a machine that HAS a toolchain — and a leak
    would silently break the rest of the suite in file order, which is the
    worst kind of red. Restoring the PREPARED tuple rather than clearing it
    keeps the warm binary for the next test.
    """
    saved = {
        name: getattr(role_protocol, name)
        for name in (
            "_GO_HELPER_PREPARED",
            "GO_HELPER_PACKAGE_DIR",
            "go_helper_source_dir",
            "_HELPER_TIMEOUT_SECONDS",
            "COMPARATORS",
        )
    }
    yield
    for name, value in saved.items():
        setattr(role_protocol, name, value)


@pytest.fixture
def compare_go(monkeypatch: pytest.MonkeyPatch):
    """`compare_signatures` with the real Go row registered FOR THIS TEST ONLY.

    Registering is not enrolling: this fixture leaves the shipped `COMPARATORS`
    tuple unchanged on disk, whatever it holds, and
    `test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees` pins that
    the registry and the lookup agree either way. What this buys is that
    the ruled answers are measured through the real protocol — added-is-not-a-
    change, removed-is, status CHECKED — instead of through a re-implementation
    of those rules living in this file, which would be a second copy of the
    thing under test.
    """
    monkeypatch.setattr(
        role_protocol,
        "COMPARATORS",
        (role_protocol.GO_SUPPORT,) + role_protocol.COMPARATORS,
        raising=True,
    )

    def _compare(before: str | None, after: str | None, path: str = _PATH):
        return compare_signatures(path, before, after)

    return _compare


def _changed(compare, before: str, after: str) -> bool:
    result = compare(before, after)
    assert result.status is SignatureCheckStatus.CHECKED, (
        f"the comparator did not even read these two revisions: {result.detail}"
    )
    return bool(result.changes)


# --------------------------------------------------------------------------- #
# 0 — the precondition this whole file rests on
# --------------------------------------------------------------------------- #


def test_the_go_row_is_in_exactly_one_registry_and_the_lookup_agrees() -> None:
    """The Go row is enrolled or pending, never both and never neither, and what
    the gate actually READS says the same thing.

    Every seal below registers Go through the `compare_go` fixture, so this
    file's answers do not depend on which of the two states the shipped registry
    is in. What this row pins is that the two registries and the lookup cannot
    DISAGREE: `PENDING_COMPARATORS` is the named state for "written but not
    live" (`skills/explicit-state.md`), and a pending row that
    `support_for_path` nevertheless returns — or an enrolled row it does not —
    is coverage reported that does not exist, in exactly the direction that
    reads as safe.

    Green when: membership is exclusive and `support_for_path` and
    `enrolled_languages` both follow `COMPARATORS` alone.
    Falsify: make `support_for_path` consult `PENDING_COMPARATORS` as well as
    `COMPARATORS` — `readable` goes True while `enrolled` is False and the
    second assertion reddens. Derive `enrolled_languages` from both tuples —
    the third reddens. Drop the row from both tuples — the first reddens. This
    cannot be satisfied by two different behaviours: for any one registry there
    is exactly one set of answers that passes.

    AMENDED AND RENAMED by P4 on 2026-08-10, and by P4 only. It was
    `test_go_is_still_not_enrolled` and it asserted `GO_SUPPORT in
    PENDING_COMPARATORS` and `not in COMPARATORS` outright — a tripwire whose
    stated job was to make an enrolment "visible from HERE rather than as eight
    confusing failures elsewhere". **It is the NINTH seal that reddens on
    enrolment**, and no earlier count had it: it postdates the checklist at
    `GO_SUPPORT`, and it is not a stale-probe seal but a seal on a project state
    the operator has now decided to leave.

    Its tripwire job is discharged rather than deleted: the eight confusing
    failures elsewhere are gone — they were re-languaged in the same commit — so
    enrolment is now a reviewable one-commit body change with no seal edits in
    it, which is the visibility the operator asked for and a louder signal than
    a red test in a file about something else.

    What is KEPT is the part that outlives any particular enrolment, and the
    keeping was MEASURED rather than argued (2026-08-10, each mutation applied
    to a `cp -a` clone with `__pycache__` cleared, whole suite run, clone
    discarded). With the row PENDING, each of these reddens this seal and
    NOTHING ELSE in the suite, so all three properties the old row carried are
    still carried, and by nothing else:

      * `support_for_path` iterating `COMPARATORS + PENDING_COMPARATORS` — a
        pending row answering a lookup, which is coverage that does not exist;
      * `enrolled_languages` derived from both tables — the same lie in the
        report instead of the dispatch;
      * the row dropped from both tables — the state with no name.

    And with the row ENROLLED, where the old seal would have been deleted
    rather than amended, this one still bites: `enrolled_languages` filtered to
    drop the enrolled Go row reddens it (measured; the same mutation is
    correctly GREEN while the row is pending, which is why it has to be judged
    against the registry rather than against a fixed expected answer).

    A THIRD registry state is refused upstream and deliberately not re-asserted
    here: `GO_SUPPORT` in BOTH tuples cannot reach this seal at all, because
    `validate_registry(COMPARATORS, PENDING_COMPARATORS)` runs at import and
    raises `RoleProtocolError` on the duplicate language. Measured 2026-08-10 —
    adding the row to `COMPARATORS` without removing it from
    `PENDING_COMPARATORS` fails collection for the whole suite. Enrolment is
    therefore a two-line MOVE, not the one-line addition the checklist at
    `GO_SUPPORT` used to claim.
    """
    enrolled = role_protocol.GO_SUPPORT in role_protocol.COMPARATORS
    pending = role_protocol.GO_SUPPORT in role_protocol.PENDING_COMPARATORS
    assert enrolled != pending, (
        "the Go row is in both registries or in neither; 'scaffolded but not "
        "enrolled' is a named state and a row in two of them, or none, has no "
        f"name (enrolled={enrolled}, pending={pending})"
    )
    assert (role_protocol.support_for_path("cmd/x/main.go") is not None) is (
        enrolled
    ), (
        "what the gate READS disagrees with the registry it is supposed to be "
        "derived from — the direction that matters is a PENDING row answering "
        "a lookup, which reports coverage that does not exist"
    )
    assert (Language.GO in role_protocol.enrolled_languages()) is enrolled, (
        "`enrolled_languages` is the falsifiable statement of what this build "
        "covers; sourcing it from anything but `COMPARATORS` makes it prose"
    )


# --------------------------------------------------------------------------- #
# 1 — the rulings table, fed to the live comparator
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "ruling", role_protocol.GO_SIGNATURE_EDIT_RULINGS, ids=lambda r: r.name
)
def test_every_ruled_edit_gets_its_ruled_answer_from_the_live_comparator(
    ruling: GoSignatureEditRuling, compare_go
) -> None:
    """The acceptance criterion, MEASURED — the row that did not exist.

    `test_role_protocol_faults.py` checks this table three ways and none of
    them touches Go: the rows differ from each other, both answers are present,
    and the rows with a `python_analogue` agree with the PYTHON comparator. The
    Go comparator was never asked. It is asked here, with the table's own
    `before`/`after` sources, which the body author notes were written for
    exactly this.

    Parametrised over the live tuple, so a row added to the ruling is checked
    against the implementation the moment it is added.

    Green when: all four ruled edits come back with their ruled answer.
    Falsify: drop parameter names from `fieldSignature` in the helper — the
    rename and reorder rows go red, which is the defect the body author
    demonstrated the suite could not see.
    """
    assert _changed(compare_go, ruling.before, ruling.after) is ruling.is_a_change, (
        f"{ruling.name!r} is ruled "
        f"{'a change' if ruling.is_a_change else 'NOT a change'} and the live "
        f"Go comparator disagrees. The ruling is the acceptance criterion; "
        f"reopen it at GO_SIGNATURE_EDIT_RULINGS, not here"
    )


# --------------------------------------------------------------------------- #
# 2 — the ruled edits, and the boundary cases that make each ruling checkable
#
# `_SILENT` is honest body work the gate must permit. `_CHANGE` is contract
# movement it must catch. The two lists are asserted by the same seal so a
# comparator cannot satisfy this file by answering one way to everything.
# --------------------------------------------------------------------------- #

_SILENT: tuple[tuple[str, str, str], ...] = (
    (
        "reflowed across lines",
        "package m\nfunc F(a, b string) (int, error) { return 0, nil }\n",
        "package m\n\nfunc F(\n\ta string,\n\tb string,\n) (\n\tint,\n\terror,\n) "
        "{\n\treturn 0, nil\n}\n",
    ),
    (
        "func type reflowed",
        "package m\n\ntype H func(a int, b string) error\n",
        "package m\n\ntype H func(\n\ta int,\n\tb string,\n) error\n",
    ),
    (
        "map value type reflowed",
        "package m\n\nfunc F(m map[string]func(a int) error) {}\n",
        "package m\n\nfunc F(m map[string]func(\n\ta int,\n) error) {\n}\n",
    ),
    (
        "nested slice-of-struct reflowed",
        "package m\n\ntype S struct{ Xs []struct{ A int } }\n",
        "package m\n\ntype S struct {\n\tXs []struct {\n\t\tA int\n\t}\n}\n",
    ),
    (
        "comments edited",
        "package m\n\n// old words\nfunc F() {}\n",
        "package m\n\n// new words\n// on two lines\nfunc F() {}\n",
    ),
    (
        "comment added inside a struct",
        "package m\n\ntype S struct{ A int }\n",
        "package m\n\ntype S struct {\n\t// why A is here\n\tA int\n}\n",
    ),
    (
        "struct fields regrouped",
        "package m\n\ntype S struct{ A, B int }\n",
        "package m\n\ntype S struct {\n\tA int\n\tB int\n}\n",
    ),
    (
        "parameters regrouped",
        "package m\n\nfunc Move(src, dst string) {}\n",
        "package m\n\nfunc Move(src string, dst string) {}\n",
    ),
    (
        "interface method parameters regrouped",
        "package m\n\ntype I interface{ Do(a, b int) }\n",
        "package m\n\ntype I interface{ Do(a int, b int) }\n",
    ),
    (
        "body rewritten",
        "package m\n\nfunc F() int { return 0 }\n",
        "package m\n\nfunc F() int {\n\tx := 1\n\tfor range []int{} {\n\t\tx++\n\t}\n"
        "\treturn x\n}\n",
    ),
    (
        "exported declaration added",
        "package m\n\nfunc F() {}\n",
        "package m\n\nfunc F() {}\n\nfunc G(x int) error { return nil }\n",
    ),
    (
        "unexported helper added",
        "package m\n\nfunc F() {}\n",
        "package m\n\nfunc F() {}\n\nfunc h(x int) int { return x }\n",
    ),
    (
        "const edited",
        "package m\n\nconst A = 1\n\nfunc F() {}\n",
        "package m\n\nconst (\n\tA = 2\n\tB = 3\n)\n\nfunc F() {}\n",
    ),
    (
        "var edited",
        "package m\n\nvar A int = 1\n\nfunc F() {}\n",
        'package m\n\nvar A = "x"\n\nfunc F() {}\n',
    ),
    (
        "import added",
        "package m\n\nfunc F() {}\n",
        'package m\n\nimport "fmt"\n\nfunc F() { fmt.Println() }\n',
    ),
    (
        "build constraint added",
        "package m\n\nfunc F() {}\n",
        "//go:build linux\n\npackage m\n\nfunc F() {}\n",
    ),
    (
        "receiver variable renamed",
        "package m\n\ntype S struct{}\n\nfunc (s *S) Do() {}\n",
        "package m\n\ntype S struct{}\n\nfunc (svc *S) Do() {}\n",
    ),
)

_CHANGE: tuple[tuple[str, str, str], ...] = (
    (
        "same-type parameters reordered",
        "package m\n\nfunc Move(src, dst string) {}\n",
        "package m\n\nfunc Move(dst, src string) {}\n",
    ),
    (
        "parameter renamed",
        "package m\n\nfunc Move(src, dst string) {}\n",
        "package m\n\nfunc Move(source, target string) {}\n",
    ),
    (
        "parameter lost its name",
        "package m\n\nfunc F(s string) {}\n",
        "package m\n\nfunc F(string) {}\n",
    ),
    (
        "receiver became a pointer",
        "package m\n\ntype S struct{}\n\nfunc (s S) Do() {}\n",
        "package m\n\ntype S struct{}\n\nfunc (s *S) Do() {}\n",
    ),
    (
        "struct tag changed",
        'package m\n\ntype S struct {\n\tA int `json:"amount"`\n}\n',
        'package m\n\ntype S struct {\n\tA int `json:"amt"`\n}\n',
    ),
    (
        "struct tag added",
        "package m\n\ntype S struct {\n\tA int\n}\n",
        'package m\n\ntype S struct {\n\tA int `json:"a"`\n}\n',
    ),
    (
        "unexported function retyped",
        "package m\n\nfunc helper(a int) {}\n",
        "package m\n\nfunc helper(a string) {}\n",
    ),
    (
        "unexported type retyped",
        "package m\n\ntype cfg struct{ A int }\n",
        "package m\n\ntype cfg struct{ A string }\n",
    ),
    (
        "unexported field added",
        "package m\n\ntype S struct {\n\tA int\n}\n",
        "package m\n\ntype S struct {\n\tA int\n\tb string\n}\n",
    ),
    (
        "unexported field retyped",
        "package m\n\ntype S struct{ a int }\n",
        "package m\n\ntype S struct{ a string }\n",
    ),
    (
        "fields reordered",
        "package m\n\ntype S struct {\n\tA int\n\tB string\n}\n",
        "package m\n\ntype S struct {\n\tB string\n\tA int\n}\n",
    ),
    (
        "field embedded",
        "package m\n\ntype S struct {\n\tA int\n}\n",
        "package m\n\ntype S struct {\n\tReader\n\tA int\n}\n",
    ),
    (
        "blank padding field resized",
        "package m\n\ntype S struct{ _ [4]byte }\n",
        "package m\n\ntype S struct{ _ [8]byte }\n",
    ),
    (
        "variadic dropped",
        "package m\n\nfunc F(xs ...int) {}\n",
        "package m\n\nfunc F(xs []int) {}\n",
    ),
    (
        "result names dropped",
        "package m\n\nfunc F() (n int, err error) { return }\n",
        "package m\n\nfunc F() (int, error) { return 0, nil }\n",
    ),
    (
        "type constraint changed",
        "package m\n\nfunc F[T any](x T) {}\n",
        "package m\n\nfunc F[T comparable](x T) {}\n",
    ),
    (
        "type parameter renamed",
        "package m\n\nfunc F[T any](x T) {}\n",
        "package m\n\nfunc F[U any](x U) {}\n",
    ),
    (
        "generic type constraint changed",
        "package m\n\ntype L[T any] struct{ Xs []T }\n",
        "package m\n\ntype L[T comparable] struct{ Xs []T }\n",
    ),
    (
        "generic method parameter changed",
        "package m\n\ntype L[T any] struct{}\n\nfunc (l *L[T]) Add(x T) {}\n",
        "package m\n\ntype L[T any] struct{}\n\nfunc (l *L[T]) Add(x []T) {}\n",
    ),
    (
        "alias became a definition",
        "package m\n\ntype B struct{}\n\ntype A = B\n",
        "package m\n\ntype B struct{}\n\ntype A B\n",
    ),
    (
        "interface method retyped",
        "package m\n\ntype I interface{ Do(a int) }\n",
        "package m\n\ntype I interface{ Do(a string) }\n",
    ),
    (
        "interface gained a method",
        "package m\n\ntype I interface{ Do(a int) }\n",
        "package m\n\ntype I interface {\n\tDo(a int)\n\tMore()\n}\n",
    ),
    (
        "method named init retyped",
        "package m\n\ntype S struct{}\n\nfunc (s *S) init(a int) {}\n",
        "package m\n\ntype S struct{}\n\nfunc (s *S) init(a string) {}\n",
    ),
)


@pytest.mark.parametrize("name, before, after", _SILENT, ids=[r[0] for r in _SILENT])
def test_honest_body_work_is_silent(
    name: str, before: str, after: str, compare_go
) -> None:
    """The half of the gate that is not about catching anything.

    Every row here is work a body agent is HIRED to do, and every one of them
    must produce no change. This is the half a comparator that shouts "changed"
    at everything fails, and the half a reader is tempted to trade away when a
    false positive annoys them — so each row is a rule from the contract, not a
    sample: reformatting, comments, field regrouping, redundant result parens,
    body edits, added declarations, `const`/`var`, imports, build constraints,
    and the receiver's variable name.

    Two of these are load-bearing implementation details that look like
    tidy-ups, are sealed here so they cannot be "simplified" away, and cover
    DIFFERENT rows — which is worth stating, because the obvious pairing is
    wrong and was measured to be wrong:

      * The hand-rolled `structFields` / `fieldSignature` are what make
        `reflowed across lines`, `struct fields regrouped`, `parameters
        regrouped` and `interface method parameters regrouped` silent.
        go/printer preserves field GROUPING — `A, B int` and `A int; B int`
        print differently — and grouping is spelling, not contract. Because
        those two functions render each field's name and type separately, the
        source's line breaks never reach the output for a flat declaration.
      * `renderFset` being an EMPTY `token.FileSet` is what makes the last
        three rows silent — a func type, a map's value type, a struct inside a
        slice. Those are the shapes that FALL THROUGH to `render`, and there
        go/printer asks the file set for the line of every position; a file set
        that knows none reports line 0 for all of them and the printer emits
        one line. Give `render` the parse's real file set and only those rows
        redden, which is how the two mechanisms were told apart.

    Green when: none of these seventeen edits is reported as a change.
    Falsify: assign the real file set from `parser.ParseFile` to `renderFset`
    and the three fall-through reflow rows redden; replace
    `structFields`/`fieldSignature` with a plain `render` of the field list and
    the regroup rows redden; put `decl.Recv.List[0].Names` into the fingerprint
    and the receiver row reddens; emit `ast.ValueSpec` symbols from `GenDecl`
    and the `const`/`var` rows redden.
    """
    assert _changed(compare_go, before, after) is False, (
        f"{name!r} is honest body work and this gate reported it as a "
        f"signature change; a gate that blocks the work it exists to permit "
        f"is a gate that gets routed around"
    )


@pytest.mark.parametrize("name, before, after", _CHANGE, ids=[r[0] for r in _CHANGE])
def test_contract_movement_is_caught(
    name: str, before: str, after: str, compare_go
) -> None:
    """The half that catches, one row per ruled property.

    `same-type parameters reordered` is the row the whole parameter-name ruling
    rests on: `Move(src, dst string)` -> `Move(dst, src string)` is
    type-identical, compiles at every call site, and inverts the meaning of
    every one of them. It is indistinguishable in a syntactic single-file
    comparison from two renames, so `parameter renamed` is ruled the same way
    and the rename false positive is the PRICE of this catch, not a goal.

    `receiver became a pointer` is the boundary that keeps the receiver
    exception honest: the variable name is out, pointer-ness is in.
    `test_a_receiver_that_becomes_a_pointer_is_one_symbol_changed` pins the
    sharper half — that it is a CHANGE and not a remove-plus-add.

    The unexported rows are here because in-package `_test.go` seals bind to
    unexported identifiers, and because it is parity with the Python
    comparator's `_private` collection.

    Green when: all twenty-three edits are reported.
    Falsify (one per group): drop parameter names from `fieldSignature`;
    strip `*` in `funcSymbol`'s receiver fingerprint as well as in the key;
    drop `field.Tag` from `structFields`; skip `ast.IsExported`-negative names;
    sort struct fields before rendering; ignore `spec.Assign`; skip
    `typeParameters`.
    """
    assert _changed(compare_go, before, after) is True, (
        f"{name!r} moved the contract and this gate stayed silent. A missed "
        f"change is the direction this gate is NOT allowed to be wrong in"
    )


def test_the_table_rules_both_ways() -> None:
    """Neither half of the table above may be emptied.

    Without this, deleting `_SILENT` leaves a green file that a
    everything-is-a-change comparator passes, and deleting `_CHANGE` leaves one
    that a `return {}` comparator passes. Both are the failure this file was
    written to make impossible, so the shape of the evidence is itself sealed.

    Green when: both lists are populated and none of their names collide.
    Falsify: empty either tuple.
    """
    assert len(_SILENT) >= 10, "the silent half is what stops a shout-at-everything gate"
    assert len(_CHANGE) >= 10, "the change half is what stops a return-{} gate"
    names = [row[0] for row in _SILENT + _CHANGE]
    assert len(names) == len(set(names)), f"duplicate probe names: {names}"
    for _, before, after in _SILENT + _CHANGE:
        assert before != after, "a probe whose two revisions are equal proves nothing"


# --------------------------------------------------------------------------- #
# 3 — symbol KEYS: the half a change/no-change boolean cannot see
# --------------------------------------------------------------------------- #


def test_a_receiver_that_becomes_a_pointer_is_one_symbol_changed() -> None:
    """Value -> pointer receiver moves ONE symbol; it does not replace it.

    The boolean in section 2 is satisfied either way — a removed `S.Do` plus an
    added `*S.Do` also reads as "changed" — so the property is asserted on the
    keys. It matters because `compare_signatures` treats an ADDED symbol as not
    a change: if the two spellings keyed differently, the pointer version would
    be an addition and the value version a removal, and the report would say
    "removed" about a method that is still there.

    Green when: the symbol key is `S.Do` under both spellings and only the
    fingerprint moves.
    Falsify: return `render(expr)` from `receiverBaseName` instead of walking
    through `*`, `()` and type arguments — the key becomes `*S.Do` and this
    reddens while section 2 stays green.
    """
    value = _FP.fingerprints(_PATH, "package m\n\ntype S struct{}\n\nfunc (s S) Do() {}\n")
    pointer = _FP.fingerprints(_PATH, "package m\n\ntype S struct{}\n\nfunc (s *S) Do() {}\n")

    assert set(value) == set(pointer) == {"S", "S.Do"}, (
        f"the receiver spelling changed the symbol KEY: {set(value)} vs "
        f"{set(pointer)}. A key that moves reports a live method as removed"
    )
    assert value["S.Do"] != pointer["S.Do"]
    assert "*" in pointer["S.Do"] and "*" not in value["S.Do"], (
        "pointer-ness is IN the fingerprint even though the receiver's "
        "variable name is out"
    )


def test_the_symbol_keys_and_kinds_are_the_documented_grammar() -> None:
    """`Name`, `Recv.Name`, `Iface.Method` — and the kinds that report them.

    One realistic file, and the exact key set it must produce. This is the seal
    that notices a symbol silently disappearing: a comparator that stopped
    emitting interface methods, or unexported declarations, or methods, would
    keep every row in section 2 green for the edits that do not touch them and
    would quietly stop reading a third of the repo.

    `kind` is reportage and never compared, so it is checked here through
    `decode_go_helper_response` rather than through `fingerprints`, which drops
    it — the one place the field is worth pinning at all.

    Green when: the key set and the kind map are exactly these.
    Falsify: `continue` past `*ast.GenDecl` in `fingerprintFile`, or stop
    appending interface-method symbols in `typeSymbols`.
    """
    symbols = _FP.fingerprints(_PATH, _SAMPLE)
    assert set(symbols) == {
        "Config",
        "Alias",
        "Reader",
        "Reader.Read",
        "Reader.Close",
        "List",
        "List.Add",
        "Config.String",
        "Config.init",
        "Serve",
        "helper",
    }, f"the symbol set moved: {sorted(symbols)}"

    response = role_protocol.decode_go_helper_response(
        role_protocol._run_go_helper(
            role_protocol._go_helper_binary(), _PATH, _SAMPLE
        )
    )
    assert {s.symbol: s.kind for s in response.symbols} == {
        "Config": "type",
        "Alias": "type",
        "Reader": "type",
        "Reader.Read": "interface_method",
        "Reader.Close": "interface_method",
        "List": "type",
        "List.Add": "method",
        "Config.String": "method",
        "Config.init": "method",
        "Serve": "func",
        "helper": "func",
    }


def test_the_fingerprint_grammar_is_pinned_verbatim() -> None:
    """The whole grammar, written out, for the one file above.

    Sections 1-3 are behavioural: they catch a grammar change that alters an
    ANSWER. This catches one that does not — a renderer that starts emitting
    `func Serve(ctx context.Context, addrs []string)` for a variadic, say,
    where both revisions change together and every pair-wise seal stays green
    while the fingerprints of 2,288 files silently mean something new.

    That is not hypothetical: a fingerprint is only ever compared against
    another run of the SAME program, so an unversioned grammar change reads to
    a future reader as a branch that rewrote the world. `SchemaVersion` exists
    to be bumped when this seal reddens; reddening it is the point, and
    updating both together is the intended edit.

    Green when: the grammar is byte-for-byte what P3 shipped.
    Falsify: any edit to `signature`, `structFields`, `interfaceParts`,
    `results` or `typeFingerprint` that changes a rendering.
    """
    assert _FP.fingerprints(_PATH, _SAMPLE) == {
        "Config": (
            "type Config struct{Name string `json:\"name\"`; timeout int; "
            "_ [4]byte; Nested struct{A int; B int}}"
        ),
        "Alias": "type Alias = Config",
        "Reader": "type Reader interface{method Read; method Close; embedded error}",
        "Reader.Read": "func Read(p []byte) (n int, err error)",
        "Reader.Close": "func Close() (error)",
        "List": "type List[T comparable] struct{items []T}",
        "List.Add": "func (*List[T]) Add(item T) (ok bool)",
        "Config.String": "func (Config) String() (string)",
        "Config.init": "func (*Config) init()",
        "Serve": "func Serve(ctx context.Context, addrs ...string) (err error)",
        "helper": "func helper(a int, b int) (int)",
    }


def test_the_same_source_fingerprints_identically_twice() -> None:
    """Determinism, which the contract calls part of the protocol.

    A fingerprint is compared for equality across two invocations, so any
    nondeterminism — a map iteration, a path, a timestamp — reads as every
    symbol having changed, i.e. as a branch that rewrote the world. Two runs of
    a realistic file, byte for byte, including ORDER, because declaration order
    is the contract and `dict` preserves it.

    Green when: two runs agree, keys and values, in order.
    Falsify: build the symbol list from a Go `map` in `fingerprintFile`.
    """
    first = _FP.fingerprints(_PATH, _SAMPLE)
    second = _FP.fingerprints(_PATH, _SAMPLE)
    assert first == second
    assert list(first) == list(second), "declaration order is part of the answer"


# --------------------------------------------------------------------------- #
# 4 — the two findings that came out of soaking rather than reasoning
# --------------------------------------------------------------------------- #

_MANY_BLANKS = (
    "package m\n\n"
    "func _() {}\n\n"
    "func _() {}\n\n"
    "func _() {}\n\n"
    "type _ int\n\n"
    "type _ string\n\n"
    "func init() {}\n\n"
    "func init() {}\n\n"
    "func F() {}\n"
)


def test_several_blank_and_init_declarations_are_an_answer_not_a_broken_machine() -> None:
    """`func _()` and `func init` are excluded BY DESIGN, and it is correctness.

    This looks like a tidy-up and is not. A Go file may legally hold several of
    each — `stringer` emits one `func _()` compile-time assertion per constant
    block, and `crypto/tls/common_string.go` in GOROOT carries three — and a
    duplicate symbol key is `HELPER_OUTPUT_INVALID` at the caller. So a helper
    that emitted them would report ORDINARY GENERATED GO as a broken machine
    and leave the branch UNDETERMINED. Measured by the body author on GOROOT:
    11 files of 4,505 would have done it.

    Nothing is lost by the skip. The blank identifier cannot be referred to
    from anywhere by definition of the language; `func init` cannot either, and
    the spec fixes its signature at no parameters and no results, so its
    fingerprint is a constant that could never report a change.

    A METHOD named `init` is a different thing — referenceable, sealable by an
    in-package test, one per receiver — and is kept. That is asserted twice:
    the key `Config.init` in the section above, and the `method named init
    retyped` row in `_CHANGE`.

    Green when: the file fingerprints to exactly `{F}` and no fault is raised.
    Falsify: delete the `isBlank(d.Name) || isPackageInit(d)` guard in
    `fingerprintFile` — the helper emits duplicate `_` and `init` keys,
    `decode_go_helper_response` refuses the document, and this raises
    `ComparatorUnavailable(HELPER_OUTPUT_INVALID)` instead. Delete only the
    `decl.Recv == nil` clause of `isPackageInit` and the method-named-init
    seals redden instead, which is how the two halves stay distinguishable.
    """
    symbols = _FP.fingerprints(_PATH, _MANY_BLANKS)
    assert set(symbols) == {"F"}, (
        f"a legal Go file was read as {sorted(symbols)}; if `_` or `init` "
        f"appears here the next generated file is HELPER_OUTPUT_INVALID and "
        f"the branch is UNDETERMINED for a reason nobody can act on"
    )


def test_adding_another_blank_declaration_is_not_a_change(compare_go) -> None:
    """And the same file, edited, stays silent through the protocol.

    The seal above proves the symbols are absent; this proves the absence is
    worth something at the gate — regenerating a `stringer` file, which adds a
    `func _()`, must not block a bodies branch.

    Green when: adding a fourth `func _()` and a third `init` reports nothing.
    Falsify: the same guard deletion — this becomes a fault, not a pass.
    """
    more = _MANY_BLANKS.replace("func F() {}", "func _() {}\n\nfunc init() {}\n\nfunc F() {}")
    assert _changed(compare_go, _MANY_BLANKS, more) is False


def test_an_empty_answer_and_a_real_one_are_distinguishable() -> None:
    """"No symbols" is an ANSWER; it must not be how everything looks.

    The cheapest way to make every silent row in this file green is a
    fingerprinter that returns `{}`. A file that genuinely declares nothing
    must map to `{}` — that is the contract, and it is the one case where an
    empty mapping is correct — and a file that declares something must not.

    Green when: `package m` alone is `{}` and a file with a func is not.
    Falsify: `return nil, ""` from `fingerprintFile`.
    """
    assert _FP.fingerprints(_PATH, "package m\n") == {}
    assert _FP.fingerprints(_PATH, "package m\n\nfunc F() {}\n") != {}


# --------------------------------------------------------------------------- #
# 5 — the false positives that are ACCEPTED, sealed so the next reader meets
#     the tradeoff instead of "fixing" it
# --------------------------------------------------------------------------- #


def test_a_regrouped_deeply_nested_struct_is_an_accepted_false_positive(
    compare_go,
) -> None:
    """One level of nesting is normalised; deeper is not, and that is a choice.

    `typeFingerprint` renders struct and interface literals by hand so grouping
    is normalised, and everything else falls through to `render`. The recursion
    is therefore one level deep by construction: a struct inside a `[]` or a
    `map` keeps go/printer's grouping, so regrouping it reads as a change.

    This is a FALSE POSITIVE and never a false negative, which is the direction
    this gate is allowed to be wrong in. It costs one round trip or one ruling;
    the opposite error ships. Sealed rather than left to be discovered so that
    someone meeting the noise reads this before deciding it is a bug — and if
    they decide to fix it, this seal reddens and they must say so on purpose.

    Green when: regrouping the fields of a `[]struct{...}` is reported.
    Falsify: make `typeFingerprint` recurse through composite types.
    """
    assert _changed(
        compare_go,
        "package m\n\ntype S struct{ Xs []struct{ A, B int } }\n",
        "package m\n\ntype S struct {\n\tXs []struct {\n\t\tA int\n\t\tB int\n\t}\n}\n",
    ) is True

    # ...and the one-level case IS normalised, which is what makes the row
    # above a boundary rather than "nesting is broken".
    assert _changed(
        compare_go,
        "package m\n\ntype S struct{ N struct{ A, B int } }\n",
        "package m\n\ntype S struct {\n\tN struct {\n\t\tA int\n\t\tB int\n\t}\n}\n",
    ) is False


def test_an_import_alias_rename_is_an_accepted_false_positive(compare_go) -> None:
    """Renaming an import alias rewrites every `pkg.T` and every one reads.

    The comparator is deliberately single-file and does not run `go/types`, so
    `f.Stringer` and `g.Stringer` are different type expressions and it cannot
    know they resolve to the same type. Every signature mentioning the alias
    reports a change.

    This is the noisiest accepted false positive in the contract, and the
    parameter-name ruling cites it by name: if THIS noise is tolerable, a
    parameter rename — one symbol, one line — is. Sealing it keeps that
    argument honest, because an argument resting on a behaviour nothing
    measures is an argument resting on nothing.

    Green when: the alias rename is reported.
    Falsify: resolve imports (which would mean a second parser and a package
    load, i.e. the thing this whole unit refuses).
    """
    assert _changed(
        compare_go,
        'package m\n\nimport f "fmt"\n\nfunc F(s f.Stringer) {}\n',
        'package m\n\nimport g "fmt"\n\nfunc F(s g.Stringer) {}\n',
    ) is True


def test_redundant_parens_inside_a_type_are_reported_and_this_is_a_divergence(
    compare_go,
) -> None:
    """MEASURED, NOT RULED — see the dispute filed with this commit.

    The helper's `Symbol.Fingerprint` comment says fingerprints are "rendered
    through go/printer so gofmt-able differences, comments and redundant parens
    are not changes". Measured, that holds for the RESULT LIST — `func F()
    error` and `func F() (error)` agree. It does NOT hold for an
    `ast.ParenExpr` inside a type: go/printer preserves it, so
    `A int` -> `A (int)` is reported as a change.

    The result-list half is asserted below as CONTEXT and is deliberately not
    counted as a seal: go/parser gives both spellings the identical
    `ast.FieldList`, so no change to the renderer can make them differ and the
    assertion cannot fail. It is here because it is the sentence's one true
    case, and a reader comparing the two lines should see which is which.

    Nor is it self-correcting: `gofmt` removes the redundant parens around a
    RECEIVER type but leaves them on a struct field type (measured, go1.24.4),
    so a gofmt-clean file can carry them.

    It is a false positive, so the direction is safe, and it is sealed here
    with the divergence named rather than silently left to the next reader.
    If P4 rules that `render` should strip `ParenExpr`, this seal reddens and
    the contract sentence and the code agree for the first time.

    Green when: today's measured behaviour.
    Falsify: unwrap `*ast.ParenExpr` in `typeFingerprint`.
    """
    assert _changed(
        compare_go,
        "package m\n\ntype S struct{ A int }\n",
        "package m\n\ntype S struct{ A (int) }\n",
    ) is True

    # Context, not a seal — see the docstring. Identical ASTs, so unfalsifiable.
    assert _changed(
        compare_go,
        "package m\n\nfunc F() error { return nil }\n",
        "package m\n\nfunc F() (error) { return nil }\n",
    ) is False


# --------------------------------------------------------------------------- #
# 6 — the protocol half, on Go inputs
#
# The language-agnostic rules (added is not a change, removed is, a new file
# has nothing to preserve) are already sealed for Python. They are re-asserted
# here on GO inputs because the point of the registry is that a second row
# cannot answer a protocol question differently from the first, and because
# these are the rows that would go wrong if the Go fingerprinter returned its
# symbols in some other shape.
# --------------------------------------------------------------------------- #


def test_a_removed_go_symbol_is_a_change_and_an_added_one_is_not(compare_go) -> None:
    """Both directions, on one pair of revisions.

    Green when: deleting `S.B` is reported with `after` None and adding `S.C`
    is not reported at all.
    Falsify: make `compare_signatures` iterate over head symbols.
    """
    result = compare_go(
        "package m\n\ntype S struct{}\n\nfunc (s S) A() {}\n\nfunc (s S) B() {}\n",
        "package m\n\ntype S struct{}\n\nfunc (s S) A() {}\n\nfunc (s S) C() {}\n",
    )
    assert result.status is SignatureCheckStatus.CHECKED
    assert [(c.symbol, c.after) for c in result.changes] == [("S.B", None)]


def test_a_new_go_file_has_nothing_to_preserve_and_a_deleted_one_loses_all_of_it(
    compare_go,
) -> None:
    """The two one-sided revisions.

    Green when: base None is CHECKED with no changes; head None reports every
    base symbol with `after` None.
    Falsify: return the head symbols as changes for a new file.
    """
    assert compare_go(None, "package m\n\nfunc A() {}\n").changes == ()
    deleted = compare_go("package m\n\nfunc A() {}\n\nfunc b() {}\n", None)
    assert {c.symbol for c in deleted.changes} == {"A", "b"}
    assert all(c.after is None for c in deleted.changes)


def test_unparseable_go_is_a_fact_about_the_file_not_about_the_machine(
    compare_go,
) -> None:
    """`SourceUnparseable`, and the status that follows from it.

    The distinction is the one `ComparatorFault` exists for: the gate opened
    this file, read it, and the text is bad — so the remediation is "fix the
    branch", not "fix the image", and `unsupported_paths` stays EMPTY because
    the file was read rather than skipped.

    Green when: the fingerprinter raises `SourceUnparseable` (not
    `ComparatorUnavailable`), and `compare_signatures` reports
    UNCHECKED_UNPARSEABLE naming the revision.
    Falsify: make the helper `os.Exit(1)` on a parse error instead of returning
    a `parse_error` document at exit 0 — the answer becomes HELPER_FAILED, a
    broken machine, and this reddens on both counts.
    """
    with pytest.raises(SourceUnparseable) as raised:
        _FP.fingerprints(_PATH, "package m\n\nfunc ((\n")
    assert raised.value.path == _PATH
    assert "go:" in raised.value.message

    result = compare_go("package m\n\nfunc ((\n", "package m\n\nfunc A() {}\n")
    assert result.status is SignatureCheckStatus.UNCHECKED_UNPARSEABLE
    assert result.unsupported_paths == ()
    assert "at base" in result.detail


def test_the_helper_is_built_once_and_reused_for_every_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cost decision, sealed, because losing it is invisible.

    `go run .` compiles before each invocation: 59ms, which on a 200-file Go
    branch (400 invocations, base and head) is 24 seconds added to the
    post-implementer hot path. Building once and executing is 0.7ms. A
    refactor that dropped `_GO_HELPER_PREPARED` would change no answer, redden
    no other seal, and make the gate 80x slower — the class of regression that
    ships.

    Green when: forty file revisions cost exactly one build.
    Falsify: call `_build_go_helper()` from `fingerprints` instead of
    `_go_helper_binary()`.
    """
    builds = 0
    real_build = role_protocol._build_go_helper

    def counting_build():
        nonlocal builds
        builds += 1
        return real_build()

    monkeypatch.setattr(role_protocol, "_build_go_helper", counting_build)
    role_protocol._GO_HELPER_PREPARED = None
    for index in range(40):
        _FP.fingerprints(_PATH, f"package m\n\nfunc F{index}(a int) {{}}\n")
    assert builds == 1, f"the helper was built {builds} times for 40 revisions"


# --------------------------------------------------------------------------- #
# 7 — the fault arms, through the REAL fingerprinter
#
# `tests/test_role_protocol_faults.py` drives all six from a stub that raises,
# which is right for what it seals (the rank, the verdict, the status sets) and
# says nothing about whether the real code path can ever PRODUCE them. A fault
# nothing can reach is a fault nothing will report. Every arm below goes
# through `GoSignatureFingerprinter.fingerprints` with a real `go` on PATH.
# --------------------------------------------------------------------------- #


@pytest.fixture
def helper_module(tmp_path: Path):
    """Build a stand-in helper package on disk and point the resolver at it.

    `go_helper_source_dir` is replaced rather than the package directory being
    edited: these seals must never write into the tree under test, and a stray
    `go.mod` left behind by a crashed test would be a fault the next run cannot
    explain.
    """

    def _make(name: str, main: str, go_directive: str = "go 1.21") -> Path:
        directory = tmp_path / name
        directory.mkdir()
        (directory / "go.mod").write_text(f"module {name}\n\n{go_directive}\n")
        (directory / "main.go").write_text(main)
        role_protocol.go_helper_source_dir = lambda: directory
        role_protocol._GO_HELPER_PREPARED = None
        return directory

    return _make


def _fault_from_fingerprinting() -> ComparatorFault:
    with pytest.raises(ComparatorUnavailable) as raised:
        _FP.fingerprints(_PATH, "package m\n\nfunc F() {}\n")
    return raised.value.fault


def test_no_go_on_path_is_toolchain_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A CI image without Go must never clear a Go branch.

    This is the live fail-open the whole fault enum was written for: if a
    missing binary read as "no Go support here", a Go-only diff would be
    promoted to UNCHECKED_NO_SUPPORTED_FILE and the branch would be CLEAN — for
    as long as the image stayed broken, silently, for every Go branch.

    Green when: an empty PATH raises TOOLCHAIN_MISSING.
    Falsify: return `{}` from `fingerprints` when `shutil.which("go")` is None.
    """
    monkeypatch.setenv("PATH", str(tmp_dir_that_does_not_exist()))
    role_protocol._GO_HELPER_PREPARED = None
    assert _fault_from_fingerprinting() is ComparatorFault.TOOLCHAIN_MISSING


def tmp_dir_that_does_not_exist() -> Path:
    """A path guaranteed absent, for the empty-PATH arm."""
    return Path(tempfile.gettempdir()) / "claude-dispatcher-no-such-bin-dir"


def test_a_go_that_cannot_write_a_build_cache_is_toolchain_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On PATH is not the same as working.

    A container that dropped `$HOME` makes `go env GOCACHE` answer `off`, and a
    build cannot run without a cache. The measured behaviour, not a simulated
    one: `HOME`, `GOCACHE` and `XDG_CACHE_HOME` are removed and the real `go`
    is asked.

    Green when: TOOLCHAIN_UNUSABLE, distinct from TOOLCHAIN_MISSING (the binary
    is right there) and from HELPER_FAILED (the helper is fine).
    Falsify: delete the GOCACHE check from `_probe_go_toolchain` — the arm
    becomes HELPER_FAILED with a build error, which blames the helper for the
    machine.
    """
    for name in ("HOME", "GOCACHE", "XDG_CACHE_HOME"):
        monkeypatch.delenv(name, raising=False)
    role_protocol._GO_HELPER_PREPARED = None
    assert _fault_from_fingerprinting() is ComparatorFault.TOOLCHAIN_UNUSABLE


@pytest.mark.parametrize(
    "name, script",
    [
        ("the probe exits non-zero", 'echo "go: cannot determine GOROOT" >&2\nexit 2\n'),
        ("GOVERSION is not a version", 'echo "weird"\necho "/tmp/cache"\n'),
    ],
)
def test_a_go_whose_own_version_probe_fails_is_toolchain_unusable(
    name: str, script: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other two routes out of `_probe_go_toolchain`, with a fake `go`.

    `go env` is the one subprocess the probe gets, and it answers both of the
    probe's questions — so a `go` that fails it, or answers it with something
    that is not a version, cannot be compared against the helper's own
    directive and must not be trusted to clear a branch. Reaching these needs a
    `go` that misbehaves, which is a nine-line shell script on a `PATH` of its
    own: hermetic, and 3ms.

    Green when: both raise TOOLCHAIN_UNUSABLE — not TOOLCHAIN_MISSING (the
    binary is there and ran) and not HELPER_FAILED (the helper is untouched).
    Falsify: delete the `probe.returncode` check, or default `installed` to a
    version that always compares greater.
    """
    stub = tmp_path / "bin"
    stub.mkdir()
    binary = stub / "go"
    binary.write_text("#!/bin/sh\n" + script)
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(stub))
    role_protocol._GO_HELPER_PREPARED = None
    assert _fault_from_fingerprinting() is ComparatorFault.TOOLCHAIN_UNUSABLE


def test_a_go_older_than_the_helper_needs_is_toolchain_unusable(
    helper_module, tmp_path: Path
) -> None:
    """The second unusable arm, and the one that names the right party.

    A toolchain older than the syntax the helper is written against fails as a
    COMPILE error, and a compile error is HELPER_FAILED — which blames the
    helper for the age of the machine. `_probe_go_toolchain` refuses first.

    Driven with a COPY of the real helper whose `go.mod` declares an
    unreachable version, so the shipped `go.mod` is never written to.

    Green when: a `go 1.99` directive is refused as TOOLCHAIN_UNUSABLE before
    anything is compiled.
    Falsify: delete the version comparison from `_probe_go_toolchain`.
    """
    real = Path(role_protocol.__file__).parent / role_protocol.GO_HELPER_PACKAGE_DIR
    directory = helper_module("future", (real / "main.go").read_text(), "go 1.99")
    assert (directory / "main.go").read_text().startswith("// Command")
    assert _fault_from_fingerprinting() is ComparatorFault.TOOLCHAIN_UNUSABLE


def test_an_install_that_dropped_the_helper_is_helper_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A wheel without the non-Python asset is a broken install, not "no Go".

    The failure `tests/test_packaging.py` exists for, hit live twice on
    2026-07-13. Both guards in `go_helper_source_dir` are driven: the directory
    absent, and the directory present with the program missing — the second is
    the partial install, and it is the one a "does the directory exist" check
    would wave through.

    `GO_HELPER_PACKAGE_DIR` is resolved against the package directory, so the
    probes point at a tmp_path by relative traversal; nothing is written inside
    the installed package.

    Green when: both shapes raise HELPER_MISSING.
    Falsify: drop the `main.go`/`go.mod` check and keep only `is_dir()` — the
    partial-install arm becomes HELPER_FAILED at `go build`.
    """
    package = Path(role_protocol.__file__).parent

    monkeypatch.setattr(role_protocol, "GO_HELPER_PACKAGE_DIR", "not_shipped")
    role_protocol._GO_HELPER_PREPARED = None
    assert _fault_from_fingerprinting() is ComparatorFault.HELPER_MISSING

    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "main.go").write_text("package main\n\nfunc main() {}\n")
    monkeypatch.setattr(
        role_protocol, "GO_HELPER_PACKAGE_DIR", os.path.relpath(partial, package)
    )
    role_protocol._GO_HELPER_PREPARED = None
    with pytest.raises(ComparatorUnavailable) as raised:
        _FP.fingerprints(_PATH, "package m\n")
    assert raised.value.fault is ComparatorFault.HELPER_MISSING
    assert "go.mod" in raised.value.message, (
        "go.mod is an entry point too: it fixes the language version the parse "
        "runs under, and an install that dropped it must not reach `go build`"
    )


def test_a_helper_that_does_not_compile_is_helper_failed(helper_module) -> None:
    """A real `go build` failure, through the real build.

    Green when: a helper package that is not valid Go raises HELPER_FAILED.
    Falsify: ignore `built.returncode` in `_build_go_helper`.
    """
    helper_module("broken", "package main\n\nfunc main() { this is not go }\n")
    assert _fault_from_fingerprinting() is ComparatorFault.HELPER_FAILED


def test_a_helper_that_exits_non_zero_is_helper_failed(helper_module) -> None:
    """Exit status and document are separate channels.

    A non-zero exit means stdout is not read AT ALL, because a document from a
    run that failed is a partial answer and a partial answer manufactures
    removed symbols.

    Green when: a helper that compiles and exits 3 raises HELPER_FAILED.
    Falsify: parse stdout before checking `returncode` in `_run_go_helper`.
    """
    helper_module(
        "exiter",
        'package main\n\nimport "os"\n\nfunc main() { os.Exit(3) }\n',
    )
    assert _fault_from_fingerprinting() is ComparatorFault.HELPER_FAILED


def test_a_helper_that_hangs_is_helper_timeout(
    helper_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate that hangs is a gate that is not enforcing anything.

    The budget is shrunk to 0.25s AFTER the sleeper has been built, so the
    toolchain probe (which shares `_HELPER_TIMEOUT_SECONDS`) runs under the
    normal budget and this seal cannot go green for the wrong reason on a
    loaded box. The child really is a compiled Go program that really does
    block; only the deadline is short.

    Green when: the run raises HELPER_TIMEOUT, and there is no retry and no
    degraded mode.
    Falsify: catch `TimeoutExpired` in `_run_go_helper` and return `{}` — the
    fallback that reports a pass nobody earned.
    """
    helper_module(
        "sleeper",
        'package main\n\nimport "time"\n\nfunc main() { time.Sleep(30 * time.Second) }\n',
    )
    role_protocol._go_helper_binary()
    monkeypatch.setattr(role_protocol, "_HELPER_TIMEOUT_SECONDS", 0.25)
    assert _fault_from_fingerprinting() is ComparatorFault.HELPER_TIMEOUT


def test_a_build_that_does_not_finish_is_helper_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The BUILD has its own budget, and blowing it is also HELPER_TIMEOUT.

    `_HELPER_BUILD_TIMEOUT_SECONDS` is separate from the per-file budget
    because it bounds different work — a cold Go build cache is a different
    order of magnitude — and the seal above only exercises the per-file one. A
    build that never returns is the same failure as a run that never returns: a
    gate that hangs is not enforcing anything.

    The REAL helper is built, under a budget no build can meet.

    Green when: HELPER_TIMEOUT, and specifically not HELPER_FAILED — the
    distinction is "the machine is stuck" versus "the program is broken", and
    they send a reader to different places.
    Falsify: let the `TimeoutExpired` from `go build` fall through to the
    generic non-zero-exit branch.
    """
    monkeypatch.setattr(role_protocol, "_HELPER_BUILD_TIMEOUT_SECONDS", 0.001)
    role_protocol._GO_HELPER_PREPARED = None
    assert _fault_from_fingerprinting() is ComparatorFault.HELPER_TIMEOUT


def test_a_helper_binary_that_cannot_be_executed_is_helper_failed(
    tmp_path: Path,
) -> None:
    """The `OSError` route out of `_run_go_helper`, which nothing else reaches.

    A build can succeed and leave something the kernel will not exec — a
    noexec mount, a stripped wheel, a partially written file. It is the helper
    that is broken, so it is HELPER_FAILED, and it must not escape as a bare
    `PermissionError` from a function documented to raise only
    `ComparatorError`: `ComparatorUnavailable` is deliberately not a
    `RoleDiffError`, and an OSError leaking past here would be caught by the
    git handlers and reported as a failed diff read.

    Green when: a non-executable "binary" raises HELPER_FAILED.
    Falsify: delete the `except OSError` clause in `_run_go_helper`.
    """
    not_a_binary = tmp_path / "not-a-binary"
    not_a_binary.write_text("this is not an executable\n")
    role_protocol._GO_HELPER_PREPARED = (not_a_binary, None)
    assert _fault_from_fingerprinting() is ComparatorFault.HELPER_FAILED


@pytest.mark.parametrize(
    "name, printed",
    [
        ("empty stdout", None),
        ("wrong schema", '{"schema":"some/other/v9","symbols":[]}'),
        (
            "duplicate symbol key",
            '{"schema":"claude-dispatcher/go-signature-fingerprint/v1",'
            '"symbols":[{"symbol":"F","fingerprint":"a","kind":"func"},'
            '{"symbol":"F","fingerprint":"b","kind":"func"}]}',
        ),
    ],
)
def test_a_helper_document_that_cannot_be_trusted_is_helper_output_invalid(
    name: str, printed: str | None, helper_module
) -> None:
    """Three ways the document is wrong, all faults and none a partial read.

    Each of these would otherwise produce a fingerprint set missing symbols,
    and a MISSING symbol is reported as a REMOVED one — so a half-understood
    response manufactures violations, and one that dropped everything
    manufactures a pass.

    `empty stdout` is the sharpest: "the helper returned no symbols" clears one
    file and "the helper returned nothing" would clear every branch. The wrong
    schema is refused rather than best-effort read, because fingerprints are
    compared across two runs and a grammar change would read as a rewrite. The
    duplicate key is the one that makes `isBlank`/`isPackageInit` correctness
    rather than tidiness — see section 4.

    Green when: all three raise HELPER_OUTPUT_INVALID.
    Falsify: `return {}` for empty stdout; drop the `schema` comparison; drop
    the `seen` set from `decode_go_helper_response`.
    """
    if printed is None:
        main = "package main\n\nfunc main() {}\n"
    else:
        main = (
            "package main\n\n"
            'import "fmt"\n\n'
            f"func main() {{ fmt.Println(`{printed}`) }}\n"
        )
    helper_module("invalid_" + name.replace(" ", "_"), main)
    assert _fault_from_fingerprinting() is ComparatorFault.HELPER_OUTPUT_INVALID


def test_a_fault_is_not_an_unreadable_language_even_on_the_real_path(
    monkeypatch: pytest.MonkeyPatch, compare_go
) -> None:
    """The fail-open, closed at the seam the real comparator actually uses.

    `test_role_protocol_faults.py` seals this with a stub that raises. Here the
    real fingerprinter faults for a real reason — no `go` on PATH — and the
    comparison must still refuse to name the path as one nobody can read: a
    Go-only diff whose paths landed in `unsupported_paths` is promoted to
    UNCHECKED_NO_SUPPORTED_FILE and the branch is CLEAN.

    Green when: the status is UNCHECKED_COMPARATOR_UNAVAILABLE, the detail
    names the fault, and `unsupported_paths` is empty.
    Falsify: put `path` into `unsupported_paths` in
    `_comparator_unavailable_comparison`.
    """
    monkeypatch.setenv("PATH", str(tmp_dir_that_does_not_exist()))
    role_protocol._GO_HELPER_PREPARED = None

    result = compare_go("package m\n\nfunc A() {}\n", "package m\n\nfunc A(x int) {}\n")

    assert result.status is SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    assert result.unsupported_paths == (), (
        "a machine without a toolchain is not a language nobody can read; "
        "naming the path here hands every Go branch a clean bill of health"
    )
    assert ComparatorFault.TOOLCHAIN_MISSING.value in result.detail
    assert result.changes == ()


# --------------------------------------------------------------------------- #
# the sample file, at the bottom because it is long and referenced twice
# --------------------------------------------------------------------------- #

_SAMPLE = '''package m

import "context"

// Doc comment.
const Version = "1"

var registry = map[string]int{}

type Config struct {
	Name    string `json:"name"`
	timeout int
	_       [4]byte
	Nested  struct{ A, B int }
}

type Alias = Config

type Reader interface {
	Read(p []byte) (n int, err error)
	Close() error
	error
}

type List[T comparable] struct{ items []T }

func (l *List[T]) Add(item T) (ok bool) { return true }

func (c Config) String() string { return c.Name }

func (c *Config) init() {}

func Serve(ctx context.Context, addrs ...string) (err error) { return nil }

func helper(a, b int) int { return a + b }

func init() {}

func _() {}
'''
