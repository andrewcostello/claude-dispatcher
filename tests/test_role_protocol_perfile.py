"""D1 seals: the signature gate is judged PER FILE, not all-or-nothing.

THE RULING (operator, 2026-08-09, the ruling after I6). Each changed path is
judged by whether its language is supported. Supported files are compared and
their changes decide the verdict. Unsupported files are **named** and do not
block.

What it replaces. `_compare_branch_signatures` aggregates all-or-nothing: one
`.go` beside one `.py` is a PARTIAL check, reports
UNCHECKED_UNSUPPORTED_LANGUAGE, and `check_branch` maps that to UNDETERMINED on
BODIES with no override. The I6 ruling carved out only the diff with NO
supported file in it and explicitly left the mixed case refused ("a question for
a fresh ruling (a per-file verdict, or a Go comparator), not something to be
settled by widening this one"). This is that fresh ruling, and it is the
per-file verdict.

Why the mixed case could not be left. Measured composition of the two target
repositories:

    evenplay-mono   2,288 Go   996 TS+TSX   781 SQL   316 Java   0 Python
    awevana           231 Go    75 TS+TSX     8 Python

so a mixed diff is the ORDINARY shape, not the exotic one, and SQL and Java will
realistically never be covered — there will always be a file in a real branch
that nobody can read. Under the all-or-nothing aggregate that is a permanent
refusal on most real work. The consequence the operator chose the per-file rule
for: every comparator added later is a MONOTONIC improvement. Enrolling Go turns
`unsupported_paths` entries into compared files and can only turn a CLEAN into a
VIOLATION for a real finding; it can never newly block a class of branch.

WHAT THIS RULING DOES NOT TOUCH, and what these seals therefore defend rather
than relax:

  * **The naming discipline is now the only thing between a CLEAN verdict and a
    silent one.** `unsupported_paths` names exactly the skipped paths in diff
    order, and the verdict's own `detail` — the line `_print_report` puts on
    stdout and the only line a caller that logs the verdict keeps — carries
    those paths and the language reason. A prose-only seal is satisfied equally
    by an honest report and by dumping every changed path, so every row below
    pins the naming on a MIXED diff, where those two answers differ, and
    requires the COMPARED file to be absent from the unread report.
  * **UNCHECKED_NO_SUPPORTED_FILE and NOT_APPLICABLE stay distinct**, and
    neither absorbs the mixed case. Before this ruling the verdict separated
    them (CLEAN vs UNDETERMINED); now all three clear, so the STATUS is the only
    place the difference can live and the temptation to collapse them is new.
    Sealed in `test_read_nothing_read_some_and_no_duty_stay_three_states`.
  * **A comparator FAULT is not an unsupported language.** A missing toolchain
    or a broken helper absorbed into "nobody can read this" is a broken CI image
    clearing every branch — the failure mode the whole discipline exists to
    prevent. Nothing in this ruling touches faults;
    `test_a_comparator_fault_is_not_an_unreadable_language` makes sure nothing
    here accidentally licenses the conflation.
  * **An unparseable SUPPORTED file still refuses.** "I can read this language
    and this file is broken" is not "I cannot read this language", and the
    per-file rule does not rescue it.

WHY THE UNREADABLE PROBES BELOW ARE `.sql`, `.java` AND `.md`, AND NOT `.go`.
Every existing seal in this unit uses a Go file as its stand-in for "a language
this gate cannot read", which was the obvious choice when nothing was going to
change. It is now the wrong one, and this was MEASURED rather than argued
(2026-08-09, against a throwaway clone carrying both this ruling and a stub Go
comparator that moves `.go` from unsupported to supported and finds nothing):
enrolling Go reddens EIGHT existing seals, and the first draft of this file
reddened SIX of its own nine rows for the same reason. Those are false alarms —
the behaviour would be correct and the probe merely stale — and a suite that
cries wolf at the first comparator is a suite that gets its assertions deleted
by the person landing the comparator.

The whole point of the per-file ruling is that comparators can be added later,
so a seal about unreadability must be written in a language that will still be
unreadable then. Go is 2,288 files and is the obvious first enrolment. SQL (781)
and Java (316) have no plausible signature comparator in this codebase — there
is no scaffolded-stub discipline in a migration or a POJO to preserve — and a
`.md` file has no signatures at all. So these rows probe with those, and they
survive the improvement they exist to enable. The measurement, and the same
recommendation applied to the existing Go-probing seals, is P4's to act on; it
is applied here because these rows are this author's to write.

NON-VACUITY TECHNIQUE, as everywhere in this effort: the benign twin, judged in
the SAME call, so a row proves the DIFFERENCE it claims and not merely an
answer. The load-bearing row is
`test_an_unreadable_file_does_not_mask_a_widened_python_signature` — a mutation
that returns CLEAN unconditionally reddens it, one that returns VIOLATION
unconditionally reddens its twin, and one that returns UNDETERMINED
unconditionally reddens both. No row is parametrized over a comprehension across
the constant it pins: every path list and every expected tuple is written out.

WHAT THESE SEALS DO **NOT** PIN, deliberately:

  * which `SignatureCheckStatus` a mixed diff reports. It must not be CHECKED
    (I5: a file nobody compared is not a checked signature) and must not be
    UNCHECKED_NO_SUPPORTED_FILE (the gate examined something). Between those,
    keeping UNCHECKED_UNSUPPORTED_LANGUAGE and removing it from the blocking set
    is the obvious shape, and so is a new member; the choice is the fixer's.
  * the private name of the blocking set. `_BODIES_BLOCKING_SIGNATURE_STATUSES`
    exists today; whether the per-file rule empties it, deletes it, or moves the
    decision into the aggregate is not sealed here.
  * whether a Go/SQL/Java comparator ever lands. This ruling is about the
    VERDICT for a file nobody can read, not about reading it.

EXISTING SEALS THIS RULING CONTRADICTS — reported to P4, untouched here. A seal
author does not amend a seal. MEASURED, by turning the rows below green against
a throwaway reference implementation in a clone and running the whole suite:
exactly ONE existing seal fails, and it fails on exactly one of its assertions.

    tests/test_role_protocol_inputs.py
      ::test_the_paths_named_unread_are_the_skipped_ones_not_the_whole_diff
      the line `assert mixed.verdict is DiffVerdict.UNDETERMINED`

It requires UNDETERMINED for the very input row 1 below requires CLEAN for. Its
own docstring names the assertion as deliberate ("the operator's rule 4 ... it
is pinned here"), and the I6 section header explains why it was left open, so
this is a genuine ruling-versus-ruling conflict and not an oversight. Everything
else in that seal — `unsupported_paths` being the Go file alone, the status
being neither CHECKED nor UNCHECKED_NO_SUPPORTED_FILE, and the all-Python
control — is still true under this ruling and must survive the amendment. Row 8
below re-pins the status distinction independently, so that if the amendment
takes the whole row out, the three-way separation is not lost with it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher.role_protocol import (
    DiffVerdict,
    Role,
    SignatureCheckStatus,
    built_in_policy,
    check_branch,
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


def _run_stub(
    changed: list[str],
    blobs: dict[str, str] | None = None,
    *,
    fault_on: tuple[str, ...] = (),
):
    """A git seam answering only the reads this module may do.

    Modelled on `_run_stub` in `test_role_protocol_inputs.py` and answering the
    same four commands, so a row here and a row there cannot disagree about what
    git was allowed to say. `blobs` is keyed `"<ref>:<path>"` exactly as git
    spells it, so a stub answer cannot be mistaken for a different revision. An
    unscripted command raises, so a seal cannot pass on a read it never
    modelled. `merge-base` and `rev-parse` answer with the ref they were handed:
    the base has not advanced and the refs do not move, because these rows are
    about which files were READ and must not go red or green according to how I3
    and I4 were fixed.

    `fault_on` is the one addition. Every path in it makes the BLOB read raise
    `OSError` — a missing toolchain, a git that will not run, a helper that
    exploded. It models the failure that must never be absorbed into "nobody can
    read this language", and it is spelled as an exception out of the seam
    rather than as a git error code so it cannot be confused with "absent from
    that tree", which `file_text_at` already guarantees is the ONLY meaning of
    its None.
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
            _ref, _, path = spec.partition(":")
            if path and path in fault_on:
                raise OSError(
                    f"git could not be run to read {spec}: this is a FAULT in "
                    "the comparator's plumbing, not a language this gate "
                    "cannot read"
                )
            if spec in blobs:
                return _RunResult(0, blobs[spec], "")
            return _RunResult(
                128, "", f"fatal: path '{path}' does not exist in '{_ref}'"
            )
        raise AssertionError(f"unscripted git command: {argv}")

    return run


def _bodies(changed: list[str], blobs: dict[str, str] | None = None, **kwargs):
    """`check_branch` for BODIES over `changed`. The role under the gate."""
    return check_branch(
        "/x",
        "main",
        "feat/x",
        Role.BODIES,
        policy=built_in_policy(),
        run=_run_stub(changed, blobs, **kwargs),
    )


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repo on `main` whose base commit already carries the sealed stub."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text(_STUB_PY, encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base: the scaffolded stub"], repo)
    return repo


#: The scaffolded stub, the honest body that fills it in, and the widening a
#: body agent must not get away with. `_FILLED_PY` matters: without it the
#: CLEAN rows could be satisfied by a gate that reports CLEAN for any file it
#: did not have to look hard at.
_STUB_PY = "def f(a: int) -> None:\n    raise NotImplementedError\n"
_FILLED_PY = "def f(a: int) -> None:\n    return None\n"
_WIDENED_PY = "def f(a: int, b: int) -> None:\n    return None\n"
_BROKEN_PY = "def f(a: int -> None:\n"

#: base/head blobs for the three shapes above, so every row states which of them
#: it is using at the call site rather than three lines away.
_HONEST = {"main:src/app.py": _STUB_PY, "feat/x:src/app.py": _FILLED_PY}
_WIDENED = {"main:src/app.py": _STUB_PY, "feat/x:src/app.py": _WIDENED_PY}
_UNPARSEABLE = {"main:src/app.py": _STUB_PY, "feat/x:src/app.py": _BROKEN_PY}


def _unread(result) -> tuple[str, ...]:
    """`unsupported_paths`, or a marker no assertion can accidentally match."""
    return () if result.signature is None else result.signature.unsupported_paths


# --------------------------------------------------------------------------- #
# 1 — the ruling itself: an unreadable file beside a readable one does not block
# --------------------------------------------------------------------------- #


def test_one_unreadable_file_beside_a_readable_one_no_longer_blocks_the_branch(
) -> None:
    """The ordinary shape of the operator's tree: a body branch that changed one
    `.py` (honest work, signature untouched) and one `.sql`.

    Per the ruling the `.py` is compared, finds nothing, and decides the
    verdict; the `.sql` is NAMED and does not block. Both halves are sealed,
    because the verdict without the naming is the quiet-and-wrong CLEAN the I6
    ruling already refused once, one case wider.

    The naming is pinned on this MIXED diff and not on a wholly-unreadable one
    on purpose. Where every path is unsupported, "name the skipped paths" and
    "dump the whole diff" produce the same answer; here they differ, so
    `src/app.py` being ABSENT from the unread report is as much of the seal as
    `db/migrate/001_bay.sql` being present.

    Red now (measured against the built worktree, 2026-08-09):
    `verdict=UNDETERMINED` — `_compare_branch_signatures` reports
    UNCHECKED_UNSUPPORTED_LANGUAGE for the partial check and `check_branch` maps
    it through `_BODIES_BLOCKING_SIGNATURE_STATUSES`; and `result.detail` names
    no path at all, because today only UNCHECKED_NO_SUPPORTED_FILE gets the
    unread enumeration appended.
    Green when: CLEAN, with the SQL file named in `unsupported_paths` and in
    the verdict's own detail, and the language given as the reason.
    Falsify: the all-Python control in the same body is CLEAN with NOTHING
    named, so this cannot be satisfied by always reporting something unread;
    hand back `checked_paths` as the unread list and the `src/app.py`
    assertions go red; drop the detail and keep the field and the stdout half
    goes red.
    """
    mixed = _bodies(["src/app.py", "db/migrate/001_bay.sql"], _HONEST)
    all_python = _bodies(["src/app.py"], _HONEST)

    assert (mixed.verdict, all_python.verdict) == (
        DiffVerdict.CLEAN,
        DiffVerdict.CLEAN,
    ), (
        "a body branch that changed one Python file and one SQL file was "
        "refused for the SQL file, and no commit its author can write clears "
        f"it — nobody will ever write a SQL comparator: {mixed.detail}"
    )
    assert mixed.violations == ()
    assert mixed.signature is not None
    assert mixed.signature.changes == ()

    # The machine-readable half: the skipped path, alone, in diff order.
    assert _unread(mixed) == ("db/migrate/001_bay.sql",), (
        "the report must name the file the gate could not read and ONLY that "
        f"file: {_unread(mixed)}"
    )
    # The stdout half — the line `_print_report` prints as `detail:` and the
    # only line a caller that logs one line keeps.
    assert "db/migrate/001_bay.sql" in mixed.detail, (
        "the branch was cleared and the verdict's own detail does not say "
        f"which file nobody opened: {mixed.detail}"
    )
    assert "db/migrate/001_bay.sql" in mixed.signature.detail, mixed.signature.detail
    assert "languag" in mixed.detail.lower(), (
        "the detail names the unread path but not the REASON; 'nobody read "
        f"this' and 'this gate has no comparator for it' differ: {mixed.detail}"
    )
    assert "src/app.py" not in mixed.detail, (
        "the verdict's detail hands back the whole diff instead of the files "
        "that went unread; on a wholly-unreadable diff those two answers are "
        "identical, which is why the honest one is pinned HERE: "
        f"{mixed.detail}"
    )
    assert mixed.signature.status is not SignatureCheckStatus.CHECKED, (
        "one of the two changed files was never opened; 'changes is "
        "authoritative' is not true of this diff (I5)"
    )

    # The control. A diff the gate read in full has nothing to confess, so the
    # row above cannot be satisfied by always naming something.
    assert _unread(all_python) == (), (
        f"a fully-read diff named something as unread: {_unread(all_python)}"
    )
    assert all_python.signature is not None
    assert all_python.signature.status is SignatureCheckStatus.CHECKED
    assert "db/migrate/001_bay.sql" not in all_python.detail


# --------------------------------------------------------------------------- #
# 2 — the load-bearing row: the unreadable file must not mask a real finding
# --------------------------------------------------------------------------- #


def test_an_unreadable_file_does_not_mask_a_widened_python_signature() -> None:
    """The row a body author cannot satisfy by clearing everything.

    The SAME mixed diff twice, differing in exactly one thing: whether the
    Python file's sealed signature was widened. Per the ruling the supported
    files decide the verdict, so the widening is a VIOLATION and the presence of
    an unreadable SQL file next to it changes nothing — least of all into a
    pass. And the SQL file is STILL named, because a VIOLATION report that
    stopped confessing what it could not read would make the confession
    conditional on the verdict, which is how it goes missing on the branches that matter.

    Red now (measured against the built worktree, 2026-08-09), and the shape of
    the failure is worth stating precisely because it is what makes this the
    load-bearing row. The pair comes back
    `(VIOLATION, UNDETERMINED)`: the WIDENED half is already right, because
    `check_branch` weighs `violations or signature.changes` BEFORE it consults
    the blocking-status set, so a signature change already outranks the partial
    check. It is the HONEST half that is refused. So the danger this row guards
    is not that the fix forgets the finding — it is that a fix which implements
    "unsupported files do not block" by clearing the whole mixed case takes the
    finding down with it, and today's suite would not notice, because nothing
    outside this file judges a mixed diff whose Python half is dirty.
    `unsupported_paths` is `("db/migrate/001_bay.sql",)` on both halves today;
    those assertions are green and are here to STAY green.
    Green when: the pair is (VIOLATION, CLEAN) and both name the SQL file.
    Falsify: return CLEAN unconditionally — the first element goes red. Return
    VIOLATION unconditionally — the second goes red. Keep today's refusal —
    both go red. Weigh only the path globs and skip the signature half — the
    first goes red. Stop naming the unread file on a VIOLATION — the naming
    assertions go red while the verdict pair stays green, which is the exact
    half-fix this row exists to catch.
    """
    widened = _bodies(["src/app.py", "db/migrate/001_bay.sql"], _WIDENED)
    honest = _bodies(["src/app.py", "db/migrate/001_bay.sql"], _HONEST)

    assert (widened.verdict, honest.verdict) == (
        DiffVerdict.VIOLATION,
        DiffVerdict.CLEAN,
    ), (
        "the unreadable SQL file decided the verdict for both branches; a file "
        "nobody can read must not be able to mask a widened signature in a "
        f"file the gate DID read. widened={widened.detail!r} "
        f"honest={honest.detail!r}"
    )

    assert widened.signature is not None
    assert {
        (c.path, c.symbol) for c in widened.signature.changes
    } == {("src/app.py", "f")}, (
        "the finding must name the Python symbol whose contract was widened: "
        f"{[(c.path, c.symbol) for c in widened.signature.changes]}"
    )
    assert widened.violations == (), (
        "control on the fixture: neither changed path is forbidden by the "
        "BODIES table, so the VIOLATION above is the SIGNATURE half of the "
        f"gate and not a path glob: {[v.path for v in widened.violations]}"
    )

    # Still confessing, on the branch it just refused.
    assert _unread(widened) == ("db/migrate/001_bay.sql",), (
        "the gate refused this branch for a Python signature and stopped "
        "saying that it also never opened the SQL file; an author reading "
        "this report would fix the Python and believe the SQL was checked: "
        f"{_unread(widened)}"
    )
    assert "db/migrate/001_bay.sql" in widened.signature.detail, (
        widened.signature.detail
    )
    assert _unread(honest) == ("db/migrate/001_bay.sql",)


# --------------------------------------------------------------------------- #
# 3 — the per-file rule does not rescue a broken SUPPORTED file
# --------------------------------------------------------------------------- #


def test_a_broken_python_file_still_refuses_even_beside_an_unreadable_one(
) -> None:
    """"I can read this language and this file is broken" is not "I cannot read
    this language", and the per-file ruling touches only the second.

    The same mixed diff three times: the Python file broken with the `.sql`
    listed AFTER it, the Python file broken with the `.sql` listed BEFORE it, and
    the benign twin whose Python parses. The first two are UNDETERMINED — the
    gate opened the file it is responsible for and could not finish, which is
    the I5 refusal and is untouched here. The third is CLEAN.

    **Why the ordering appears in this row and not only in row 4.** Today the
    aggregate keeps the FIRST non-CHECKED status and `check_branch` decides from
    that one word. The cheapest possible per-file fix is to leave that alone and
    remove UNCHECKED_UNSUPPORTED_LANGUAGE from the blocking set — and under that
    fix a diff whose `.sql` sorts first reports "unsupported language" for a
    branch whose Python does not parse, and CLEARS it. A broken supported file
    rescued by an unreadable one sorting ahead of it is the ruling being used to
    buy exactly what it does not grant, so the second call is here and the
    status assertion covers both: the state must name the reason the branch was
    refused, not whichever file git happened to list first.

    The last assertion is the one that stops the two reasons being merged: the
    unparseable `.py` must NOT appear in `unsupported_paths`. That file was
    opened and read; the gate failed ON it rather than skipping it, and naming
    it as unsupported would send a reader off to write a Python comparator that
    already exists — and, worse, would put a file the gate failed on into the
    list of files the ruling says do not block.

    Red now (measured, 2026-08-09): `(UNDETERMINED, UNDETERMINED, UNDETERMINED)`
    — all three refuse, the third for the SQL file, so today this triple
    distinguishes nothing; and `broken_sql_first`'s status is already
    UNCHECKED_UNSUPPORTED_LANGUAGE rather than UNCHECKED_UNPARSEABLE, which is
    the order-dependence above, live and reachable today (it is harmless only
    because both statuses currently block).
    Green when: (UNDETERMINED, UNDETERMINED, CLEAN), both refusals named
    UNPARSEABLE, and the broken `.py` not named as unsupported.
    Falsify: extend the per-file pass to unparseable files — the first two
    elements go red. Keep the first-status-wins aggregate and shrink the
    blocking set — `broken_sql_first` goes CLEAN and both its rows go red.
    Absorb the unparseable file into `unsupported_paths` — the last equality
    goes red.
    """
    broken_py_first = _bodies(["src/app.py", "db/migrate/001_bay.sql"], _UNPARSEABLE)
    broken_sql_first = _bodies(["db/migrate/001_bay.sql", "src/app.py"], _UNPARSEABLE)
    parses = _bodies(["src/app.py", "db/migrate/001_bay.sql"], _HONEST)

    assert (
        broken_py_first.verdict,
        broken_sql_first.verdict,
        parses.verdict,
    ) == (
        DiffVerdict.UNDETERMINED,
        DiffVerdict.UNDETERMINED,
        DiffVerdict.CLEAN,
    ), (
        "a supported file the gate could not parse is a check that STARTED and "
        "could not finish, on the one role whose gate this is; the per-file "
        f"rule is about files nobody can read: {broken_py_first.detail!r} / "
        f"{broken_sql_first.detail!r} / {parses.detail!r}"
    )
    assert broken_py_first.signature is not None
    assert broken_sql_first.signature is not None
    assert (
        broken_py_first.signature.status,
        broken_sql_first.signature.status,
    ) == (
        SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
        SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
    ), (
        "the reported state must be the reason the branch was refused. "
        "'unsupported language' on a branch refused for a Python file that "
        "does not parse tells the author to go write a SQL comparator: "
        f"{broken_py_first.signature.status} / "
        f"{broken_sql_first.signature.status}"
    )
    assert _unread(broken_py_first) == ("db/migrate/001_bay.sql",), (
        "the unparseable Python file was opened and read; listing it among the "
        "paths this gate has no comparator for both misdirects the reader and "
        f"files it under the rule that says such paths do not block: "
        f"{_unread(broken_py_first)}"
    )
    assert _unread(broken_sql_first) == ("db/migrate/001_bay.sql",)


# --------------------------------------------------------------------------- #
# 4 — the verdict does not depend on where the unreadable path sorts
# --------------------------------------------------------------------------- #


def test_the_verdict_does_not_depend_on_where_the_unreadable_files_sort(
) -> None:
    """Today's aggregate is order-sensitive by construction — "the FIRST
    non-CHECKED status wins" — and the per-file rule must not inherit that. Git
    emits paths in its own order, so a branch whose SQL file happens to sort
    before its Python file must not get a different answer from the same branch
    with the files renamed.

    Two orders of the same three-file diff, run twice over: once with the Python
    signature untouched (both CLEAN) and once with it widened (both VIOLATION).
    All four are asserted as one tuple, so an implementation that gets one order
    right still reddens.

    Two unsupported files rather than one, because that is what makes the
    ORDER of `unsupported_paths` assertable: the ruling says diff order, and
    with a single skipped path every order is diff order. The two expected
    tuples below are reverses of each other, so a fix that sorts the list, or
    that emits it in policy order, or that de-duplicates through a set, reddens
    here and nowhere else.

    Red now (measured, 2026-08-09): `(UNDETERMINED, UNDETERMINED, VIOLATION,
    VIOLATION)` — the two widened rows already pass, for the reason recorded on
    row 2 (a signature change outranks the partial check), and the two clean
    rows are refused. The `unsupported_paths` equalities are already green,
    including the diff-order one, and are here to stay green: the aggregate
    appends in loop order today, and a per-file rewrite is exactly the change
    that could start sorting or de-duplicating them.
    Green when: (CLEAN, CLEAN, VIOLATION, VIOLATION) and the two orders are
    reported in the order git gave them.
    Falsify: sort `unsupported_paths` — one of the two equalities goes red.
    Let the first path decide the aggregate — the two orders disagree and the
    verdict tuple goes red.
    """
    sql_first_clean = _bodies(
        ["db/migrate/001_bay.sql", "src/app.py", "svc/Handler.java"], _HONEST
    )
    sql_last_clean = _bodies(
        ["svc/Handler.java", "src/app.py", "db/migrate/001_bay.sql"], _HONEST
    )
    sql_first_widened = _bodies(
        ["db/migrate/001_bay.sql", "src/app.py", "svc/Handler.java"], _WIDENED
    )
    sql_last_widened = _bodies(
        ["svc/Handler.java", "src/app.py", "db/migrate/001_bay.sql"], _WIDENED
    )

    assert (
        sql_first_clean.verdict,
        sql_last_clean.verdict,
        sql_first_widened.verdict,
        sql_last_widened.verdict,
    ) == (
        DiffVerdict.CLEAN,
        DiffVerdict.CLEAN,
        DiffVerdict.VIOLATION,
        DiffVerdict.VIOLATION,
    ), (
        "the verdict moved with the position of a file nobody read: "
        f"{sql_first_clean.detail!r} / {sql_last_clean.detail!r} / "
        f"{sql_first_widened.detail!r} / {sql_last_widened.detail!r}"
    )

    assert _unread(sql_first_clean) == ("db/migrate/001_bay.sql", "svc/Handler.java")
    assert _unread(sql_last_clean) == ("svc/Handler.java", "db/migrate/001_bay.sql"), (
        "the unread paths must come back in DIFF order — the order git "
        f"reported them — and not sorted: {_unread(sql_last_clean)}"
    )
    assert _unread(sql_first_widened) == ("db/migrate/001_bay.sql", "svc/Handler.java")
    assert _unread(sql_last_widened) == ("svc/Handler.java", "db/migrate/001_bay.sql")


# --------------------------------------------------------------------------- #
# 5 — several unreadable files: ALL named, none blocking
# --------------------------------------------------------------------------- #


def test_every_unreadable_file_is_named_and_not_one_of_them_blocks() -> None:
    """The realistic branch. SQL and Java have no comparator now and will not
    get one, so a real diff carries several unreadable files at once beside the
    Python the gate can actually read.

    Two things this row adds to row 1. First, `unsupported_paths` must hold ALL
    THREE, so a fix that reports the first skipped path — the natural shape if
    the aggregate keeps only the first refusal, which is exactly what it does
    today for the STATUS — reddens. Second, all three must reach the verdict's
    own detail, so an implementation that names one and counts the rest reddens
    too. The twin in the same body widens the signature and requires the three
    to still be named on a VIOLATION.

    The four paths are written out and the expected tuple is written out. The
    expected tuple is NOT derived from the input list by a comprehension:
    deleting a probe must redden this row, not silently shrink it.

    Red now (measured, 2026-08-09): `(UNDETERMINED, VIOLATION)` — the widened
    half already answers (row 2 records why) and the honest one is refused; and
    the CLEAN verdict's `detail` names nothing, because today only
    UNCHECKED_NO_SUPPORTED_FILE gets the unread enumeration appended.
    Green when: (CLEAN, VIOLATION) and all three unreadable paths in both
    channels of both results.
    Falsify: name only the first — the equality goes red. Count instead of
    listing — the detail loop goes red. Include `src/app.py` — the last
    assertion goes red.
    """
    changed = [
        "db/migrate/001_bay.sql",
        "docs/adr/0007.md",
        "src/app.py",
        "svc/Handler.java",
    ]
    expected_unread = (
        "db/migrate/001_bay.sql",
        "docs/adr/0007.md",
        "svc/Handler.java",
    )

    honest = _bodies(changed, _HONEST)
    widened = _bodies(changed, _WIDENED)

    assert (honest.verdict, widened.verdict) == (
        DiffVerdict.CLEAN,
        DiffVerdict.VIOLATION,
    ), (
        "three unreadable files did not stop being three unreadable files, but "
        "they must stop deciding the verdict; and the one readable file must "
        f"still decide it: {honest.detail!r} / {widened.detail!r}"
    )
    assert honest.violations == () and widened.violations == (), (
        "control on the fixture: none of these four paths is forbidden by the "
        "BODIES table, so the VIOLATION is the signature half"
    )

    assert _unread(honest) == expected_unread, (
        "every path this gate skipped for its language must be named, not just "
        f"the first one it hit: {_unread(honest)}"
    )
    assert _unread(widened) == expected_unread, (
        "the confession must not become conditional on the verdict: "
        f"{_unread(widened)}"
    )

    for path in expected_unread:
        assert path in honest.detail, (
            f"{path} went unread and the CLEAN verdict's own detail — the "
            f"line a caller keeps — does not mention it: {honest.detail}"
        )
    assert "src/app.py" not in honest.detail, (
        "the one file the gate DID read is being reported alongside the ones "
        f"it did not; that is a path dump, not a confession: {honest.detail}"
    )


# --------------------------------------------------------------------------- #
# 6 — the control: an all-supported diff behaves exactly as it does today
# --------------------------------------------------------------------------- #


def test_an_all_python_diff_is_judged_exactly_as_it_is_today() -> None:
    """The upper bound on the ruling, and the row that makes every CLEAN above
    worth something.

    Three all-Python diffs, one of each answer, in one call: honest work is
    CLEAN and CHECKED, a widened signature is a VIOLATION, and an unparseable
    head is UNDETERMINED. None of the three has anything to confess. All three
    are GREEN TODAY and must stay green — the per-file ruling is about files the
    gate cannot read, and it must not reach the ones it can.

    This is the row that forbids the two lazy fixes: "never report anything
    unread" (the second block goes red), and "stop blocking on any unchecked
    status" (the third block goes red — an unparseable Python file is not an
    unreadable language).

    Falsify: make the aggregate always CLEAN — the second and third blocks go
    red. Make it always name something — the `unsupported_paths` assertions go
    red. Report CHECKED for a diff nobody read — this row would not notice, but
    row 1 would.
    """
    honest = _bodies(["src/app.py"], _HONEST)
    widened = _bodies(["src/app.py"], _WIDENED)
    broken = _bodies(["src/app.py"], _UNPARSEABLE)

    assert (honest.verdict, widened.verdict, broken.verdict) == (
        DiffVerdict.CLEAN,
        DiffVerdict.VIOLATION,
        DiffVerdict.UNDETERMINED,
    ), (
        "a diff made entirely of files this gate CAN read must be judged "
        "exactly as it was before the per-file ruling: "
        f"{honest.detail!r} / {widened.detail!r} / {broken.detail!r}"
    )

    assert honest.signature is not None
    assert honest.signature.status is SignatureCheckStatus.CHECKED
    assert honest.signature.changes == ()

    assert widened.signature is not None
    assert widened.signature.status is SignatureCheckStatus.CHECKED
    assert {(c.path, c.symbol) for c in widened.signature.changes} == {
        ("src/app.py", "f")
    }

    assert broken.signature is not None
    assert broken.signature.status is SignatureCheckStatus.UNCHECKED_UNPARSEABLE

    assert (_unread(honest), _unread(widened), _unread(broken)) == ((), (), ()), (
        "a diff the gate read in full has nothing to confess; a fix that "
        "satisfies the naming rows above by always naming something reddens "
        "here"
    )


# --------------------------------------------------------------------------- #
# 7 — a comparator FAULT is not an unreadable language
#
# Nothing in the ruling touches faults; this row is here so nothing in the ruling
# accidentally licenses conflating them. A broken CI image clearing every branch
# is the failure mode the whole naming discipline exists to prevent, and the
# per-file rule is exactly the shape a careless fix would reach for: "anything I
# could not compare, name it and move on".
#
# The FAULT half of this row is already correct today. It is red only because its
# benign twin — the identical call with a working seam — is refused today for the
# mixed diff, so today the pair cannot tell a broken toolchain from a SQL file.
# That is precisely the confusion the row exists to forbid, and it is why the
# fault is sealed as a DIFFERENCE rather than as an answer.
# --------------------------------------------------------------------------- #


def test_a_comparator_fault_is_not_an_unreadable_language() -> None:
    """The same mixed diff twice, differing in exactly one thing: whether the
    blob read of the Python file explodes.

    The fault is UNDETERMINED — "I could not run" is not a verdict about the
    branch — and the file the gate failed to read must NOT be reported as a
    language this gate has no comparator for. That report would be a lie with
    consequences: `unsupported_paths` is precisely the list of things the ruling
    says do not block, so a fault filed there is a fault that clears the branch,
    and a git that will not run files EVERY path there.

    The twin is the identical call without the fault, and it is CLEAN — so this
    row proves the fault is the difference, not the fixture.

    Red now (measured, 2026-08-09), and for the reason this row is about: the
    FAULT half is already right — the seam raises, `file_text_at` wraps it in
    `RoleDiffError`, `check_branch` maps that to UNDETERMINED and attaches no
    signature — but the TWIN is UNDETERMINED too, because the mixed diff is
    refused. Today's gate gives a broken toolchain and an ordinary SQL file
    the same answer, so this pair distinguishes nothing at all; the ruling is what
    makes the distinction visible, and this row is what keeps it.
    Green when: (UNDETERMINED, CLEAN).
    Falsify: catch the read failure inside the per-file loop and treat it like
    an unsupported language — the verdict pair goes red AND `src/app.py`
    appears in the unread list, so the row fails twice over. Catch it and treat
    it as "the file is absent at base" — the pair goes red, which is the older
    and worse version of the same mistake (`file_text_at` already refuses to
    return None for a read error, for this reason).
    """
    faulted = _bodies(
        ["src/app.py", "db/migrate/001_bay.sql"], _HONEST, fault_on=("src/app.py",)
    )
    working = _bodies(["src/app.py", "db/migrate/001_bay.sql"], _HONEST)

    assert (faulted.verdict, working.verdict) == (
        DiffVerdict.UNDETERMINED,
        DiffVerdict.CLEAN,
    ), (
        "a comparator that could not RUN was answered with a verdict about the "
        f"branch: {faulted.detail!r}"
    )
    assert "src/app.py" not in _unread(faulted), (
        "a fault was filed as 'this gate has no comparator for that language' "
        "— the one list whose entries the ruling says do not block. A broken "
        f"toolchain would then clear every branch: {_unread(faulted)}"
    )


# --------------------------------------------------------------------------- #
# 8 — read nothing / read some / no duty: still three states
#
# Before this ruling the VERDICT separated them: a wholly-unreadable BODIES diff
# was CLEAN, a mixed one was UNDETERMINED, and a SCAFFOLD diff was CLEAN with no
# duty. Now all three clear, so the verdict can no longer tell them apart and the
# STATUS is the only place the difference can live. The temptation to collapse
# them is created BY this ruling, which is why the distinction is re-pinned here
# rather than left to the I6 rows — one of which P4 must amend for its verdict
# assertion and could carry this away with it.
# --------------------------------------------------------------------------- #


def test_read_nothing_read_some_and_no_duty_stay_three_states() -> None:
    """Three calls, three statuses, one verdict.

    `UNCHECKED_NO_SUPPORTED_FILE` is a fact about the LANGUAGE on a role that
    HAS the signature duty and could not discharge it at all. The mixed diff is
    a role that has the duty and discharged part of it — a different fact, and
    the one whose `unsupported_paths` is a strict subset of its changed paths.
    `NOT_APPLICABLE` is a fact about the ROLE: SCAFFOLD has no signature duty,
    so it has nothing to confess and confesses nothing.

    Red now: the mixed row's verdict. The three statuses are already correct
    today and are here so the amendment that makes the mixed verdict CLEAN
    cannot quietly make it the same STATE as the wholly-unreadable diff.
    Green when: all three verdicts are CLEAN and the three statuses are three.
    Falsify: implement the per-file rule by giving every diff containing an
    unreadable file the NO_SUPPORTED_FILE state — the mixed status assertion
    goes red, and so does the `unsupported_paths` subset check. Reuse
    NOT_APPLICABLE for the unreadable BODIES diff — the first inequality goes
    red.
    """
    nothing_readable = _bodies(["db/migrate/001_bay.sql", "svc/Handler.java"])
    mixed = _bodies(["src/app.py", "db/migrate/001_bay.sql"], _HONEST)
    no_duty = check_branch(
        "/x",
        "main",
        "feat/x",
        Role.SCAFFOLD,
        policy=built_in_policy(),
        run=_run_stub(["db/migrate/001_bay.sql", "svc/Handler.java"]),
    )

    assert (
        nothing_readable.verdict,
        mixed.verdict,
        no_duty.verdict,
    ) == (DiffVerdict.CLEAN, DiffVerdict.CLEAN, DiffVerdict.CLEAN), (
        f"{nothing_readable.detail!r} / {mixed.detail!r} / {no_duty.detail!r}"
    )

    assert nothing_readable.signature is not None
    assert mixed.signature is not None
    assert no_duty.signature is not None

    assert nothing_readable.signature.status is (
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
    )
    assert no_duty.signature.status is SignatureCheckStatus.NOT_APPLICABLE
    assert mixed.signature.status is not (
        SignatureCheckStatus.UNCHECKED_NO_SUPPORTED_FILE
    ), (
        "a diff in which one file WAS compared is not a diff with no supported "
        "file in it; now that both are CLEAN, the status is the only thing "
        "that still separates 'read nothing' from 'read some'"
    )
    assert mixed.signature.status is not SignatureCheckStatus.NOT_APPLICABLE, (
        "'bodies has no signature duty' is false; the duty exists and was "
        "half discharged"
    )

    # And the confessions differ in the way the states claim they do.
    assert _unread(nothing_readable) == ("db/migrate/001_bay.sql", "svc/Handler.java")
    assert _unread(mixed) == ("db/migrate/001_bay.sql",)
    assert _unread(no_duty) == ()


# --------------------------------------------------------------------------- #
# 9 — the whole ruling through the face CI actually runs
# --------------------------------------------------------------------------- #


def test_the_ci_face_clears_a_mixed_branch_and_still_names_the_unread_file(
    git_repo: Path,
) -> None:
    """Rows 1 and 2 end to end, through the real script, real git and a real
    checkout — because the harm is in CI and the benefit is an exit code.

    The branch fills in the sealed stub (an honest body: the signature is
    untouched, only the body changed) and adds a `.sql` file. This is the shape
    of nearly every branch on the operator's tree, and today
    `scripts/check_body_branch.sh` exits 3 on it forever.

    Red now: rc=3 and `UNDETERMINED` on stdout.
    Green when: rc=0, the headline says CLEAN, and stdout still says the SQL
    file was never read.
    Falsify: clear the branch without the confession — the rc assertion goes
    green and the naming assertions go red. Keep the refusal — the rc assertion
    goes red.

    The `>= 2` is the whole of the second assertion, not a slack bound.
    `_print_report` lists every changed path under "changed paths examined:"
    whatever happened to it, so ONE occurrence of the migration path is printed
    by a gate that read the file and by one that never opened it alike — that
    measurement is recorded on the I6 CI row in `test_role_protocol_inputs.py`
    and is unchanged here. The second occurrence has to come from a line that
    says it went unread. The `src/app.py` count is pinned at exactly one for the
    matching reason: the file the gate DID read must appear in the path listing
    and nowhere in the unread report, which is the mixed-diff distinction that
    the wholly-unreadable CI row cannot make.
    """
    src_root = Path(__file__).resolve().parent.parent / "src"
    _git(["checkout", "-q", "-b", "feat/x"], git_repo)
    (git_repo / "src" / "app.py").write_text(_FILLED_PY, encoding="utf-8")
    (git_repo / "db" / "migrate").mkdir(parents=True)
    (git_repo / "db" / "migrate" / "001_bay.sql").write_text(
        "ALTER TABLE bay ADD COLUMN real_money_capable boolean NOT NULL;\n",
        encoding="utf-8",
    )
    _git(["add", "."], git_repo)
    _git(
        ["commit", "-q", "-m", "an honest body, and a migration beside it"],
        git_repo,
    )

    script = (
        Path(__file__).resolve().parent.parent / "scripts" / "check_body_branch.sh"
    )
    proc = subprocess.run(
        ["bash", str(script), "main", "feat/x", "bodies"],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON": sys.executable, "PYTHONPATH": str(src_root)},
        timeout=180,
    )

    assert proc.returncode == 0, (
        "a bodies branch that did honest Python work and touched one SQL file "
        "is refused by the CI face, and no commit its author can write clears "
        f"it\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "check_body_branch: CLEAN role=bodies" in proc.stdout, proc.stdout
    assert proc.stdout.count("db/migrate/001_bay.sql") >= 2, (
        "the branch was cleared and the only mention of the SQL file is the "
        "bare path listing every run prints; nothing on stdout says that file "
        f"was never read\nstdout={proc.stdout}"
    )
    assert proc.stdout.count("src/app.py") == 1, (
        "the file the gate actually READ is being repeated alongside the ones "
        "it could not; on this mixed diff that is what separates an honest "
        f"report from a path dump\nstdout={proc.stdout}"
    )
