"""D2 seals (P4): a comparator that could not RUN is not a language nobody can
read — sealed at the RANK, where `test_a_comparator_fault_is_not_an_unreadable_
language` seals it at the verdict.

WHY THIS FILE EXISTS SEPARATELY FROM THE PER-FILE SEALS
-------------------------------------------------------
`tests/test_role_protocol_perfile.py` already has a green row for this
distinction, and it is a good row: same mixed diff twice, differing only in
whether a read explodes, (UNDETERMINED, CLEAN). But its "fault" is a git blob
read that raises, which `check_branch` maps to UNDETERMINED *before any
signature status exists* — the result carries `signature is None`. It therefore
cannot say anything about `SignatureCheckStatus`, about
`_BODIES_BLOCKING_SIGNATURE_STATUSES`, or about where the fault sorts in
`_SIGNATURE_STATUS_PRECEDENCE`, and `_worst_signature_status` raises on any
status it was not taught to rank. Those are the three things the sixth member
introduced and the three things sealed here.

HOW A FAULT IS REACHED WITHOUT A GO TOOLCHAIN
---------------------------------------------
Through the registry seam: `COMPARATORS` is monkeypatched with a row whose
`fingerprinter.fingerprints` raises `ComparatorUnavailable`. Deliberately NOT by
patching `signature_status_for_fault`, `_comparator_unavailable_comparison` or
the frozensets — every one of those is under test here, and a seal that patches
the thing it is measuring measures nothing. Deliberately NOT by removing `go`
from PATH either: the fault must be reachable on a machine that HAS a toolchain,
or the seal is green for the wrong reason on half the fleet and stops testing
anything the day CI installs Go.

The patched row uses Go's own `.go` extension, so these seals are indifferent to
whether `GO_SUPPORT` is enrolled — before enrolment the row supplies the
language, after enrolment it overrides it, and in both cases the fingerprinter
that raises is the one written here. The UNREADABLE probes are `.sql`, `.java`
and `.md`, following the standing convention (a prior adjudicator's, for the
seals that must survive enrolment): they are languages with no comparator
planned here, 1,097 files of them in the target repo, so enrolling Go cannot
turn an "unreadable" probe readable underneath a seal.

THE VACUITY TRAP IN THIS UNIT
-----------------------------
It is `assert _SIGNATURE_STATUS_PRECEDENCE == (...)`. That pins the tuple and
proves nothing about a verdict: it is satisfied by a build where the fold is
never called, where the rank is read from a different tuple, or where
`check_branch` ignores the status entirely. Every rank row here is therefore
asserted through `check_branch` on a real mixed diff, and the tuple's SHAPE is
asserted only where the shape is itself the property (the exhaustiveness rows).
"""

from __future__ import annotations

import pytest

from claude_dispatcher import role_protocol
from claude_dispatcher.role_protocol import (
    ComparatorFault,
    ComparatorUnavailable,
    DiffVerdict,
    Language,
    LanguageSupport,
    Role,
    RoleProtocolError,
    SignatureCheckStatus,
    built_in_policy,
    check_branch,
    signature_status_for_fault,
)

_GO_SRC = "package m\n"
_PY_SRC = "def f(a):\n    pass\n"


# --------------------------------------------------------------------------- #
# The seam
# --------------------------------------------------------------------------- #


def _run_stub(changed: list[str], blobs: dict[str, str] | None = None):
    """A git seam answering only the reads the gate is allowed to do.

    `blobs` is keyed `"<ref>:<path>"`; an unmodelled blob answers exactly as
    git does for a path absent at a revision (rc 128 with the `does not exist`
    wording), which `file_text_at` reads as absence rather than as failure. An
    unscripted command raises, so no row here can pass on a read it never
    modelled.
    """
    blobs = blobs or {}

    def run(cmd, *_args, **_kwargs):
        argv = [str(c) for c in cmd]
        if "diff" in argv:
            return (0, "".join(p + "\n" for p in changed), "")
        if "merge-base" in argv:
            return (0, "main\n", "")
        spec = next((a for a in argv if ":" in a and not a.startswith("-")), None)
        if spec is not None:
            if spec in blobs:
                return (0, blobs[spec], "")
            ref, _, path = spec.partition(":")
            return (128, "", f"fatal: path '{path}' does not exist in '{ref}'")
        raise AssertionError(f"unscripted git command: {argv}")

    return run


def _faulting_row(fault: ComparatorFault) -> LanguageSupport:
    """A registry row for `.go` whose comparator exists and cannot run."""

    class _Unavailable:
        def fingerprints(self, path: str, text: str) -> dict[str, str]:
            raise ComparatorUnavailable(fault, f"probe fault on {path}")

    return LanguageSupport(
        language=Language.GO, extensions=(".go",), fingerprinter=_Unavailable()
    )


def _with_faulting_go(
    monkeypatch: pytest.MonkeyPatch,
    fault: ComparatorFault = ComparatorFault.TOOLCHAIN_MISSING,
) -> None:
    """Enrol the faulting `.go` row ALONGSIDE the real Python one.

    Python is kept enrolled on purpose: the mixed rows below need a file the
    gate genuinely reads, and a registry that dropped Python would make
    "nothing was compared" true for a second reason and hide which one the
    verdict came from.
    """
    monkeypatch.setattr(
        role_protocol,
        "COMPARATORS",
        (_faulting_row(fault), role_protocol.PYTHON_SUPPORT),
        raising=True,
    )


def _bodies(changed: list[str], blobs: dict[str, str] | None = None):
    return check_branch(
        "/x",
        "main",
        "feat/x",
        Role.BODIES,
        policy=built_in_policy(),
        run=_run_stub(changed, blobs),
    )


_GO_BLOB = {"main:cmd/x/main.go": _GO_SRC, "feat/x:cmd/x/main.go": _GO_SRC}
_PY_BLOB = {"main:src/app.py": _PY_SRC, "feat/x:src/app.py": _PY_SRC}


# --------------------------------------------------------------------------- #
# 1 — the rank, measured on the diff that needs it
# --------------------------------------------------------------------------- #


def test_a_fault_beside_an_unreadable_file_refuses_the_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mixed diff, and the whole reason UNCHECKED_COMPARATOR_UNAVAILABLE is
    ranked above UNCHECKED_UNSUPPORTED_LANGUAGE rather than below it.

    One `.go` whose comparator could not run, beside one `.sql` nobody can
    read. Neither the `examined` counter nor `unsupported_paths` decides this
    diff: `examined == 1` so nothing is promoted, and the `.sql` is legitimately
    named unread. What decides it is the FOLD, and the fold returns whichever
    status ranks worse. Rank the fault below the language status and the
    aggregate answers `unchecked_unsupported_language`, which clears BODIES —
    so a CI image with no `go` binary hands a clean bill of health to every
    branch that also happens to touch a SQL file.

    Green when: UNDETERMINED, reported as the FAULT and not as the language.
    Falsify (measured, 2026-08-09): move
    `SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE` to the end of
    `_SIGNATURE_STATUS_PRECEDENCE` — this row goes CLEAN and red. Both
    assertions matter: the verdict catches the fail-open, and the status
    catches a build that refuses for the right reason by accident while
    reporting the wrong one.
    """
    _with_faulting_go(monkeypatch)
    result = _bodies(["cmd/x/main.go", "db/migrate/001_bay.sql"], _GO_BLOB)

    assert result.verdict is DiffVerdict.UNDETERMINED, (
        "a comparator that could not run was cleared by an unreadable "
        f"neighbour sorting under it: {result.detail!r}"
    )
    assert result.signature is not None
    assert result.signature.status is (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    ), (
        "the branch was refused, but the report blames the language rather "
        f"than the machine: {result.signature.status!r}"
    )


def test_the_fault_outranks_an_unparseable_file_in_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other rank boundary. Both statuses BLOCK, so the verdict is
    UNDETERMINED either way and nothing fails open here — what the rank decides
    is which reason the report LEADS with, and that is a ruling rather than a
    forced consequence (P4, 2026-08-09; the argument is at
    `_SIGNATURE_STATUS_PRECEDENCE`, and a later unit may re-argue it without
    reopening the member).

    The ruling: the fault leads. An unparseable file was established by working
    apparatus; a fault says the apparatus did not run, so the completeness of
    the whole diff is in question and the owner of the fix is not the author.

    Green when: the status is the fault, and the unparseable file is STILL
    named in the details — the rank moves the headline, it does not drop the
    other finding.
    Falsify: swap the first two entries of `_SIGNATURE_STATUS_PRECEDENCE` — the
    status assertion goes red while the verdict stays UNDETERMINED, which is
    exactly the point of asserting the status here.
    """
    _with_faulting_go(monkeypatch)
    result = _bodies(
        ["cmd/x/main.go", "src/app.py"],
        dict(_GO_BLOB, **{"main:src/app.py": _PY_SRC, "feat/x:src/app.py": "def (:\n"}),
    )

    assert result.verdict is DiffVerdict.UNDETERMINED
    assert result.signature is not None
    assert result.signature.status is (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    )
    assert "src/app.py" in result.signature.detail, (
        "ranking the fault first dropped the unparseable file from the "
        f"report; the rank moves the headline, not the findings: "
        f"{result.signature.detail!r}"
    )


def test_the_fault_verdict_does_not_depend_on_where_the_go_file_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fold is commutative, so git's path order cannot decide this gate.

    The same two files in both orders. This is the property the ranked fold
    replaced "first non-CHECKED wins" to get, re-pinned for the new member
    because a rank added to the wrong END of the tuple is invisible to a
    single-order seal.

    Green when: both orders give the same verdict AND the same status.
    Falsify: make `_worst_signature_status` return `left` — one order goes
    CLEAN.
    """
    _with_faulting_go(monkeypatch)
    go_first = _bodies(["cmd/x/main.go", "db/migrate/001_bay.sql"], _GO_BLOB)
    sql_first = _bodies(["db/migrate/001_bay.sql", "cmd/x/main.go"], _GO_BLOB)

    assert go_first.signature is not None
    assert sql_first.signature is not None
    assert (go_first.verdict, go_first.signature.status) == (
        sql_first.verdict,
        sql_first.signature.status,
    ), "the verdict moved with the diff's path order"
    assert go_first.verdict is DiffVerdict.UNDETERMINED


# --------------------------------------------------------------------------- #
# 2 — the bookkeeping halves, sealed because they are STRUCTURAL
#
# Both are true today for free: `examined` is incremented before the comparison
# runs, and the aggregate extends `unsupported_paths` only from a language
# refusal. Neither is defended by a line that looks like a gate, so a P3 tidying
# the aggregate can undo either without noticing. Measured (2026-08-09): the
# `examined` half alone is a live fail-open on the mixed diff.
# --------------------------------------------------------------------------- #


def test_a_faulted_path_counts_as_examined_so_nothing_is_promoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The promotion to UNCHECKED_NO_SUPPORTED_FILE — which is CLEAN — fires
    when the loop examined NOTHING and skipped something for its language. A
    path whose comparator exists and faulted was not skipped for its language:
    the gate reached for it and the machine failed.

    Sealed on the MIXED diff, not the Go-only one. That is the correction P4
    measured (2026-08-09): on a Go-only diff, miscounting `examined` is
    harmless because `unsupported_paths` is empty and the promotion's other
    half cannot fire either — so a seal written against the Go-only case, which
    is the case the scaffold's contract argued from, is GREEN while the fault
    is being cleared on every mixed diff in the fleet. The `.sql` neighbour is
    what makes this row able to fail.

    Green when: UNDETERMINED, and the status is the fault rather than
    NO_SUPPORTED_FILE.
    Falsify (measured): decrement `examined` for a faulted comparison — this
    row goes CLEAN with `unchecked_no_supported_file`, and it is the only row
    in the suite that does.
    """
    _with_faulting_go(monkeypatch)
    result = _bodies(["cmd/x/main.go", "db/migrate/001_bay.sql"], _GO_BLOB)

    assert result.signature is not None
    assert result.signature.status is not (
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
    ), (
        "a diff in which the gate REACHED for a file was reported as a diff "
        "with no supported file in it — the state that clears the branch"
    )
    assert result.verdict is DiffVerdict.UNDETERMINED


def test_a_faulted_path_is_never_named_as_a_language_nobody_can_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`unsupported_paths` is the list of files skipped FOR THEIR LANGUAGE, and
    the 2026-08-09 ruling says entries there do not block. A fault filed among
    them is a broken machine wearing a permanent-fact costume.

    Measured (2026-08-09): breaking this half ALONE does not clear the branch —
    the rank and the `examined` counter still refuse it — so this row is sealed
    as a REPORTING requirement, not as the fail-open, and it is worth saying so
    rather than leaving a reader to assume the verdict depends on it. What it
    prevents is the report that sends an operator off to write a Go comparator
    when what they have is an unset PATH, and a future relaxation that reads
    "everything in unsupported_paths is fine" and finds a fault in there.

    Green when: the `.sql` is named and the `.go` is not.
    Falsify: have `_comparator_unavailable_comparison` return
    `unsupported_paths=(path,)` and have the aggregate union it — the first
    assertion goes red while the verdict stays UNDETERMINED.
    """
    _with_faulting_go(monkeypatch)
    result = _bodies(["cmd/x/main.go", "db/migrate/001_bay.sql"], _GO_BLOB)

    assert result.signature is not None
    assert "cmd/x/main.go" not in result.signature.unsupported_paths, (
        "an environment fault was filed as a language this gate cannot read: "
        f"{result.signature.unsupported_paths}"
    )
    assert "db/migrate/001_bay.sql" in result.signature.unsupported_paths, (
        "the genuinely unreadable neighbour stopped being named, so the row "
        "above could pass by naming nothing at all"
    )


# --------------------------------------------------------------------------- #
# 3 — the blocking classification, and the status -> verdict table as DATA
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "status, expected",
    [
        (SignatureCheckStatus.UNCHECKED_UNPARSEABLE, DiffVerdict.UNDETERMINED),
        (
            SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE,
            DiffVerdict.UNDETERMINED,
        ),
        (SignatureCheckStatus.UNCHECKED_UNSUPPORTED_LANGUAGE, DiffVerdict.CLEAN),
        (SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE, DiffVerdict.CLEAN),
        (SignatureCheckStatus.CHECKED, DiffVerdict.CLEAN),
    ],
)
def test_the_bodies_status_to_verdict_table_is_data_not_prose(
    status: SignatureCheckStatus, expected: DiffVerdict
) -> None:
    """`check_branch`'s docstring carries the status -> BODIES verdict table.
    This is that table, executable.

    It exists because the table ARRIVED WRONG: the D2 scaffold was branched
    before the per-file verdict landed and its table spelled both CLEAN rows as
    UNDETERMINED. Nothing caught that, because the table was prose. A
    specification table that disagrees with the code is worse than no table —
    it is the thing a reader reaches for instead of the code.

    Asserted through `_BODIES_BLOCKING_SIGNATURE_STATUSES`, which is the
    mechanism `check_branch` actually consults, so this cannot drift from the
    verdict without also drifting from the code. NOT_APPLICABLE has no row: it
    is unreachable on BODIES by construction (`check_branch` produces it only
    for a role with no signature duty), so a row for it would assert about a
    state this parametrisation cannot reach.

    Green when: every status classified as this table says.
    Falsify: add UNCHECKED_UNSUPPORTED_LANGUAGE to the blocking set (the
    pre-ruling behaviour) — its row goes red. Remove
    UNCHECKED_COMPARATOR_UNAVAILABLE from it — its row goes red, and that is
    the broken-CI-image fail-open.
    """
    blocking = status in role_protocol._BODIES_BLOCKING_SIGNATURE_STATUSES
    assert blocking is (expected is DiffVerdict.UNDETERMINED), (
        f"{status.value} is {'' if blocking else 'not '}in the BODIES blocking "
        f"set, but the ruled verdict for it is {expected.value}"
    )


def test_the_fault_status_is_unchecked_and_blocking_and_not_promotable() -> None:
    """The member's three set memberships, in the one place they can be read
    together — and the one it must NOT have.

    `_UNCHECKED_SIGNATURE_STATUSES` says the comparison did not run;
    `_BODIES_BLOCKING_SIGNATURE_STATUSES` says the branch is not cleared;
    `_SIGNATURE_STATUS_PRECEDENCE` says a per-file comparison can produce it.
    UNCHECKED_NO_SUPPORTED_FILE is the state it must never become, and that is
    asserted as a non-membership of the precedence tuple rather than as prose:
    a status the aggregate can promote INTO is one the fold ranks, and the
    promotion is the CLEAN path.

    Green when: all four hold.
    Falsify: drop the member from the blocking set — the second assertion goes
    red here and the mixed-diff rows above go CLEAN.
    """
    fault_status = SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE

    assert fault_status in role_protocol._UNCHECKED_SIGNATURE_STATUSES
    assert fault_status in role_protocol._BODIES_BLOCKING_SIGNATURE_STATUSES
    assert fault_status in role_protocol._SIGNATURE_STATUS_PRECEDENCE
    assert (
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
        not in role_protocol._SIGNATURE_STATUS_PRECEDENCE
    ), (
        "the aggregate's own whole-diff conclusion became a per-file rank; it "
        "is the CLEAN state, and a per-file status that can fold to it is a "
        "per-file status that can clear the branch"
    )


def test_the_fault_status_ranks_above_every_status_that_clears() -> None:
    """The rank's invariant, stated as the property rather than as the tuple.

    Written this way on purpose. `assert _SIGNATURE_STATUS_PRECEDENCE == (...)`
    would pin the literal and would have to be edited by whoever adds the
    seventh status — which is exactly the edit that should be forced to think.
    This says the thing that must stay true however the tuple grows: no status
    that CLEARS a bodies branch may outrank a status that BLOCKS one. A build
    that violates it has a clearing reason winning a fold against a blocking
    one, which is the 2026-08-09 fail-open in general form.

    Green when: every blocking status sorts ahead of every clearing status.
    Falsify: move UNCHECKED_COMPARATOR_UNAVAILABLE (or UNCHECKED_UNPARSEABLE)
    to the end of the tuple.
    """
    order = {s: i for i, s in enumerate(role_protocol._SIGNATURE_STATUS_PRECEDENCE)}
    blocking = role_protocol._BODIES_BLOCKING_SIGNATURE_STATUSES

    worst_clearing = max(
        (i for s, i in order.items() if s not in blocking), default=-1
    )
    best_clearing = min(
        (i for s, i in order.items() if s not in blocking), default=len(order)
    )
    worst_blocking = max((i for s, i in order.items() if s in blocking), default=-1)

    assert best_clearing > worst_blocking, (
        "a status that CLEARS a bodies branch outranks one that BLOCKS it, so "
        "the fold can answer 'clean' for a diff that contains a refusal: "
        f"{[s.value for s in role_protocol._SIGNATURE_STATUS_PRECEDENCE]}"
    )
    assert worst_clearing >= 0, "no clearing status is ranked at all"


# --------------------------------------------------------------------------- #
# 4 — the fault -> status mapping is TOTAL
# --------------------------------------------------------------------------- #


def test_every_comparator_fault_has_a_row_and_a_new_one_raises() -> None:
    """`signature_status_for_fault` is a table, not a `return`, and this is why.

    Every one of the six faults must map, and must map to the SAME status —
    they share a verdict and a remediation, and the fault itself carries the
    distinction. That is asserted by production, over the real enum, so a
    seventh fault added without a row reddens here rather than being absorbed
    at whatever the previous row said.

    The raise is asserted with a fault the table does not contain. It is
    reached through a stand-in rather than by deleting a row, because a seal
    must not need the module edited to exercise its own error path.

    Green when: all six map, and an unmapped fault raises RoleProtocolError.
    Falsify: replace the body with `return
    SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE` — the first half
    still passes and the raise assertion goes red, which is the whole argument
    for the table written out as a test.
    """
    produced = {signature_status_for_fault(f) for f in ComparatorFault}
    assert produced == {SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE}
    assert len(list(ComparatorFault)) == 6, (
        "a comparator fault was added or removed; the mapping above still "
        "covers the enum, but `ComparatorFault`'s own docstring rules what "
        "each member means and a new one needs that ruling too"
    )

    class _SeventhFault:
        value = "not_yet_ruled"

    with pytest.raises(RoleProtocolError, match="no row in the fault"):
        signature_status_for_fault(_SeventhFault())  # type: ignore[arg-type]


@pytest.mark.parametrize("fault", list(ComparatorFault))
def test_every_fault_reaches_the_gate_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, fault: ComparatorFault
) -> None:
    """Each of the six, end to end: raised by a fingerprinter, carried through
    `compare_signatures`, folded by the aggregate, and refused by
    `check_branch`.

    Parametrised over the live enum rather than over a written-out list, so a
    seventh fault is exercised here the moment it exists. The fault's own name
    must reach the report — the status carries the verdict and the fault
    carries the diagnosis, and an operator who cannot tell HELPER_TIMEOUT from
    TOOLCHAIN_MISSING has to guess which machine to look at.

    Green when: UNDETERMINED, with the fault's value in the detail.
    Falsify: drop the fault from the detail in
    `_comparator_unavailable_comparison` — all six rows go red.
    """
    _with_faulting_go(monkeypatch, fault)
    result = _bodies(["cmd/x/main.go"], _GO_BLOB)

    assert result.verdict is DiffVerdict.UNDETERMINED
    assert result.signature is not None
    assert result.signature.status is (
        SignatureCheckStatus.UNCHECKED_COMPARATOR_UNAVAILABLE
    )
    assert fault.value in result.signature.detail, (
        f"the report does not say WHICH environment failure happened: "
        f"{result.signature.detail!r}"
    )


# --------------------------------------------------------------------------- #
# 5 — the fault is not the language, on a diff of nothing but faults
# --------------------------------------------------------------------------- #


def test_a_wholly_faulted_diff_is_refused_where_a_wholly_unreadable_one_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pair the member exists for, at its starkest: two diffs of one file
    each, identical in every way except whether this gate HAS a comparator for
    the language.

    The unreadable one is CLEAN and names what it missed — the 2026-08-09
    ruling, unchanged and re-pinned here so a fix for the fault cannot take it
    away. The faulted one is UNDETERMINED. Reuse the language answer for the
    fault and these two collapse into one, which is a broken CI image clearing
    every Go branch it builds.

    The unreadable probe is `.sql`, not `.go`, so enrolling Go later cannot
    turn this row green for the wrong reason.

    Green when: (UNDETERMINED, CLEAN) with two different statuses.
    Falsify: map every `ComparatorFault` to
    UNCHECKED_UNSUPPORTED_LANGUAGE — the pair becomes (CLEAN, CLEAN) and both
    assertions go red.
    """
    _with_faulting_go(monkeypatch)
    faulted = _bodies(["cmd/x/main.go"], _GO_BLOB)
    unreadable = _bodies(["db/migrate/001_bay.sql"])

    assert (faulted.verdict, unreadable.verdict) == (
        DiffVerdict.UNDETERMINED,
        DiffVerdict.CLEAN,
    ), (
        "a machine that could not run the comparator was answered exactly as "
        f"a language nobody wrote one for: {faulted.detail!r} / "
        f"{unreadable.detail!r}"
    )
    assert faulted.signature is not None
    assert unreadable.signature is not None
    assert faulted.signature.status is not unreadable.signature.status


def test_a_fault_does_not_stop_the_other_roles_from_clearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The blocking classification is a BODIES rule and only a BODIES rule.

    Every other role has no signature obligation, so a fault must not become a
    new gate on work that never had one — the same boundary
    `_not_applicable_signature` draws for the language statuses. SCAFFOLD is
    the probe because it is the role that writes the contracts a fault would
    otherwise block from ever being written.

    Green when: SCAFFOLD is CLEAN with NOT_APPLICABLE while BODIES is refused
    on the identical diff.
    Falsify: widen step 5's `if role is Role.BODIES` to include SCAFFOLD —
    SCAFFOLD goes UNDETERMINED (measured).

    Note which mutation does NOT falsify this, because it says where the
    protection really lives: dropping the `role is Role.BODIES` term from the
    VERDICT guard changes nothing at all. By then the signature is already
    NOT_APPLICABLE, which is in no blocking set, so that term is redundant
    belt-and-braces. The load-bearing guard is the earlier one — the roles
    without a signature duty never run the comparison — and this row is
    pointed at that one.
    """
    _with_faulting_go(monkeypatch)
    scaffold = check_branch(
        "/x",
        "main",
        "feat/x",
        Role.SCAFFOLD,
        policy=built_in_policy(),
        run=_run_stub(["cmd/x/main.go"], _GO_BLOB),
    )
    bodies = _bodies(["cmd/x/main.go"], _GO_BLOB)

    assert scaffold.verdict is DiffVerdict.CLEAN
    assert scaffold.signature is not None
    assert scaffold.signature.status is SignatureCheckStatus.NOT_APPLICABLE
    assert bodies.verdict is DiffVerdict.UNDETERMINED
