"""The known-red register — the P2→P3 window as a NAMED state (D-68).

The defect
----------
The mechanical gate runs the WHOLE repo suite and judges on exit code alone
(``mechanical_verify.MechanicalVerifyResult.passed`` is ``exit_code == 0``).
The scaffold-first protocol DELIBERATELY produces red rows: P2 commits seals
that must fail, P3 makes them pass. So between a seals task merging and its
body merging, the integration branch is red BY DESIGN.

Measured live in dogfood wave 1 (D-68): DF-1-4 (adjudicate) failed the
mechanical gate twice, spawned a fix-the-tests agent, and cascaded
``claude@default → claude@high`` on three rows belonging to DF-5-2 — a
different unit, which DF-1-4 had changed nothing to affect. Per affected task:
one wasted agent spawn (which CANNOT fix another unit's seals — the only route
to green is weakening them, the defect the protocol exists to prevent), plus a
cascade rung at higher effort, plus a second full suite run.

``role_protocol._SUITE_EXPECTATIONS`` is why this is not a seals-only problem:

    SCAFFOLD   GREEN       BODIES     GREEN
    SEALS      UNJUDGED    ADJUDICATE GREEN

SEALS is immune to its OWN red rows (D-58). Three of the four roles are not
immune to ANYONE ELSE'S. With three units in flight, every body and every
adjudicate pays for the other units' windows.

D-70 makes it worse: a preserved branch freezes those rows in, and merging the
body does not reach them, so the tax outlives the window.

Why this design reads no test output
------------------------------------
D-58 records the standing refusal: *"the reason that gate refuses to parse test
output is that this project has twice shipped a false green from doing so."*
That refusal is PRESERVED here, and it is the reason the register holds row
IDs rather than deriving them.

Every judgement in the chain stays exit-code-only:

  * suppressing a known-red row is ``pytest --deselect <nodeid>`` — the suite's
    exit code is still the whole verdict;
  * confirming a row genuinely belongs in the register is a TARGETED run of
    that row, whose exit code is the whole answer;
  * retiring an entry is the body task's own gate going green on the full
    suite, exit code again.

Nothing in this module parses a test report, and nothing should be added that
does without re-opening D-58's ruling.

The two properties that make this safe rather than a suppression hole
--------------------------------------------------------------------
1. **An entry never excuses its own body.** :func:`rows_for_task` skips an
   entry whose ``body_task`` is the task being gated. The whole point of the
   unit is that P3 turns those rows green, so the one task that must still see
   them red is P3 itself. A register that excused the body would let a unit
   land with its seals permanently suppressed — the vacuous seal, one tier up.

2. **A stale or misspelled entry hides nothing.** pytest does not error on a
   ``--deselect`` that matches no test: the row simply still runs. Measured::

       suite, no register                              -> exit 1
       suite, real known-red row deselected            -> exit 0  (1 deselected)
       suite, TYPO'd nodeid deselected                 -> exit 1  (fails safe)

   The mechanism fails TOWARD red. That direction is the whole reason
   ``--deselect`` was chosen over a marker, a skip, or a conftest hook: the
   failure mode of a bad entry is a red gate someone must explain, never a
   green one nobody notices.

What is NOT decided here, and is deliberately left to the operator
-----------------------------------------------------------------
**Who fills the register.** Entries are written BY HAND and reviewed in a diff.
Auto-registration — deriving a seals task's red rows from its summary and
verifying them at merge — is a further unit, and it is deliberately not built
first: it is the half that could invent a suppression nobody read. A tracked
file that a human adds three lines to, and that shows up in ``git diff``, is
the conservative starting point. See :data:`REGISTER_RELPATH`.

Consequently this module does not decide WHETHER a row deserves an entry. It
decides which registered rows apply to which task, renders the exclusion, and
NAMES every way the arrangement can be wrong.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

# The register lives in the repository, TRACKED, and is reviewed in a diff.
# Not in `docs/runs/` (gitignored, and per-run), not on the task row (which is
# rewritten by the dispatcher mid-run, and which does not survive a worktree
# being deleted). A suppression that no reviewer ever sees is the failure this
# placement is chosen against.
REGISTER_RELPATH = "config/known-red.yaml"

# The repo's test command receives the exclusion through the environment rather
# than by string surgery on the command itself. The command in
# `.dispatcher.yaml` is ARBITRARY SHELL — here it is a multi-line script that
# resolves an interpreter before invoking pytest — so appending arguments to it
# is not generally valid. Handing the repo a variable and requiring the repo to
# place it is the same contract `DISPATCHER_TEST_PYTHON` already uses.
#
# THE VARIABLE CARRIES A FILE PATH, NOT THE ROWS, and both halves of that are
# corrections found by wiring it up rather than by reasoning about it.
#
# Attempt 1 — a pre-rendered argument string
# (``--deselect 'a.py::t[x y]' --deselect b.py::t``) is broken in exactly the
# case the quoting exists for: the shell does NOT re-parse quotes after
# expanding a variable, so an unquoted ``$VAR`` splits on whitespace and a
# parametrised id arrives as the two literal words ``--deselect 'a.py::t[x`` and
# ``y]'``; quoting the expansion passes the whole string as ONE argument, which
# pytest rejects. No spelling survives both, short of ``eval``.
#
# Attempt 2 — newline-separated ids in the variable, split by the repo with
# ``IFS`` set to a newline. Correct in shell, and MEASURED WORKING under dash —
# but unwritable in the place it has to live: setting ``IFS`` to a newline needs
# a literal newline inside the shell string, and a line holding a bare ``"`` at
# column 0 TERMINATES the YAML block scalar that holds the test command. It made
# `.dispatcher.yaml` unparseable.
#
# So the variable names a FILE holding one node id per line, and the repo reads
# it with ``while IFS= read -r row``. That is pure POSIX (dash included), needs
# no arrays, no herestring, no ``IFS`` gymnastics and no ``eval``; ``IFS= read
# -r`` preserves spaces and backslashes in a row exactly. Newline is a safe
# record separator because a pytest node id cannot contain one, and the file is
# a durable artifact an operator can read after the fact — which the journal
# payload alone does not give for a run that has already been cleaned up.
EXCLUSION_ENV = "DISPATCHER_KNOWN_RED_FILE"

#: Basename of the rows file, written into the task's run-artifact directory.
ROWS_FILENAME = "known-red-rows.txt"


class ExclusionStyle(str, Enum):
    """How a repo spells "run the suite but not these rows".

    One member today. ``go test`` has no per-row exclusion of this shape (its
    nearest equivalent is a ``-run`` regex, which is a different and clumsier
    contract), so the Go repo will need its own member — and until it has one,
    a Go repo with a non-empty active register is
    :attr:`RegisterFault.UNSUPPORTED_STYLE` rather than a silent no-op.
    """

    PYTEST_DESELECT = "pytest-deselect"


class RegisterFault(str, Enum):
    """The named ways the register can fail to apply.

    Every one of these BLOCKS rather than degrading. An exclusion that was
    meant to apply and silently did not is the unnamed state this project
    refuses on principle — and here it has teeth in both directions: the task
    pays for rows it cannot fix, and the operator believes the register handled
    it.
    """

    UNSUPPORTED_STYLE = "known_red_unsupported_style"
    COMMAND_IGNORES_EXCLUSIONS = "known_red_command_ignores_exclusions"


class RegisterError(ValueError):
    """The register file exists but cannot be read as one.

    Fail CLOSED: a malformed register is never treated as an empty one. An
    empty register suppresses nothing, which is a safe state to be in by
    accident; a malformed register that READS as empty would silently restore
    the D-68 tax while the file on disk claims otherwise.
    """


@dataclass(frozen=True)
class KnownRedEntry:
    """One unit's deliberate red rows.

    ``body_task`` is the load-bearing field: it is both the retirement
    condition (the entry dies when that task is Done) and the exemption
    (that task is the one gate these rows are NOT hidden from).
    """

    rows: tuple[str, ...]
    seals_task: str
    body_task: str
    reason: str
    registered_at_sha: str = ""

    def applies_to(self, task_key: str, *, done_keys: frozenset[str]) -> bool:
        """True iff this entry's rows should be hidden from ``task_key``.

        False in exactly two cases, and they are different reasons:
          * ``task_key`` IS the body — the rows are its deliverable;
          * the body is Done — the entry has retired for everyone.
        """
        if self.body_task == task_key:
            return False
        if self.body_task in done_keys:
            return False
        return True


@dataclass(frozen=True)
class Register:
    """The parsed register. ``entries`` is empty when the file is absent."""

    entries: tuple[KnownRedEntry, ...] = ()
    path: Path | None = None

    @property
    def is_empty(self) -> bool:
        return not self.entries


@dataclass(frozen=True)
class Exclusions:
    """What to hand one task's gate, and why.

    ``fault`` non-None means the caller must BLOCK: there were rows to exclude
    and the arrangement could not deliver them. ``rows`` is still populated in
    that case so the block's detail can name what went unapplied.
    """

    rows: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    fault: RegisterFault | None = None
    detail: str = ""

    @property
    def applied(self) -> bool:
        """True only when rows will actually reach the test command.

        Requires ``env``, not just ``rows``: a decision with no delivery is not
        an application, and reporting one as applied is how a suppression that
        never happened gets logged as though it did.
        """
        return bool(self.rows) and self.fault is None and bool(self.env)


def _as_entry(raw: object, *, index: int, path: Path) -> KnownRedEntry:
    if not isinstance(raw, dict):
        raise RegisterError(
            f"{path}: entries[{index}] is {type(raw).__name__}, expected a mapping"
        )
    missing = [k for k in ("rows", "seals_task", "body_task", "reason") if k not in raw]
    if missing:
        raise RegisterError(
            f"{path}: entries[{index}] is missing required key(s): "
            f"{', '.join(missing)}"
        )
    rows = raw["rows"]
    if not isinstance(rows, list) or not rows:
        raise RegisterError(
            f"{path}: entries[{index}].rows must be a non-empty list of pytest "
            "node ids"
        )
    for r in rows:
        if not isinstance(r, str) or not r.strip():
            raise RegisterError(
                f"{path}: entries[{index}].rows holds a non-string or blank row"
            )
    for key in ("seals_task", "body_task", "reason"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise RegisterError(
                f"{path}: entries[{index}].{key} must be a non-blank string"
            )
    return KnownRedEntry(
        rows=tuple(str(r).strip() for r in rows),
        seals_task=str(raw["seals_task"]).strip(),
        body_task=str(raw["body_task"]).strip(),
        reason=str(raw["reason"]).strip(),
        registered_at_sha=str(raw.get("registered_at_sha") or "").strip(),
    )


def load(repo_root: str | Path) -> Register:
    """Read the register from ``repo_root``.

    An ABSENT file is an empty register — that is the state every repo starts
    in and it must behave exactly as the dispatcher did before this module
    existed. A PRESENT but unreadable file raises (:class:`RegisterError`).
    """
    path = Path(repo_root) / REGISTER_RELPATH
    if not path.exists():
        return Register(entries=(), path=None)

    from . import yaml_io  # one YAML entrypoint for the whole package

    try:
        doc = yaml_io.load(path)
    except Exception as exc:  # noqa: BLE001 - re-raised as the module's own type
        raise RegisterError(f"{path}: not parseable as YAML: {exc}") from exc

    if doc is None:
        return Register(entries=(), path=path)
    if not isinstance(doc, dict):
        raise RegisterError(
            f"{path}: top level is {type(doc).__name__}, expected a mapping"
        )

    raw_entries = doc.get("entries")
    if raw_entries is None:
        return Register(entries=(), path=path)
    if not isinstance(raw_entries, list):
        raise RegisterError(
            f"{path}: `entries` is {type(raw_entries).__name__}, expected a list"
        )

    entries = tuple(
        _as_entry(raw, index=i, path=path) for i, raw in enumerate(raw_entries)
    )
    return Register(entries=entries, path=path)


def rows_for_task(
    register: Register,
    *,
    task_key: str,
    done_keys: Iterable[str] = (),
) -> tuple[str, ...]:
    """The registered rows to hide from ``task_key``'s gate, de-duplicated.

    Order is stable (first registration wins) so the rendered command is
    reproducible and a journal payload can be diffed across runs.
    """
    done = frozenset(done_keys)
    seen: set[str] = set()
    out: list[str] = []
    for entry in register.entries:
        if not entry.applies_to(task_key, done_keys=done):
            continue
        for row in entry.rows:
            if row not in seen:
                seen.add(row)
                out.append(row)
    return tuple(out)


def rows_payload(rows: Iterable[str]) -> str:
    """The CONTENTS of the rows file: one node id per line, trailing newline.

    Data, not arguments — see the note on :data:`EXCLUSION_ENV` for the two
    designs this replaced and why each failed.
    """
    body = "\n".join(rows)
    return f"{body}\n" if body else ""


def write_rows_file(rows: Iterable[str], *, directory: Path) -> Path:
    """Write the rows file into ``directory`` and return its path.

    The directory is created if absent — a gate must not fail because a run
    artifact directory had not been made yet.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ROWS_FILENAME
    path.write_text(rows_payload(rows), encoding="utf-8")
    return path


def deselect_args(rows: Iterable[str]) -> str:
    """Render ``rows`` as pytest ``--deselect`` arguments, SHELL-QUOTED.

    NOT used to build :data:`EXCLUSION_ENV` — see the note there. This renders
    the canonical pytest spelling for a caller that will hand the result to a
    shell as literal command text, or split it with ``shlex`` and exec a list.
    It is what documents "what the repo is expected to do with the rows", and
    the seals use it to drive real pytest.

    Quoting is not cosmetic. Parametrised node ids routinely carry spaces and
    brackets — wave 1's own flake was
    ``...::test_every_optional_marker_lives_in_an_always_present_bracket_slot[a
    plain property]``.
    """
    return " ".join(f"--deselect {shlex.quote(r)}" for r in rows)


def resolve(
    register: Register,
    *,
    task_key: str,
    done_keys: Iterable[str] = (),
    style: ExclusionStyle | None,
    test_command: str | None,
    rows_dir: Path | None = None,
) -> Exclusions:
    """Decide what one task's gate should exclude, or name why it cannot.

    ``style`` is the repo's declared exclusion mechanism (None when the repo
    declared none). ``test_command`` is the repo's verbatim test command, which
    must PLACE the variable — the dispatcher cannot place it safely itself,
    because the command is arbitrary shell.
    """
    rows = rows_for_task(register, task_key=task_key, done_keys=done_keys)
    if not rows:
        # Nothing to hide. Byte-identical to the pre-register behaviour, and
        # deliberately not a fault even when the repo declared no style: a repo
        # with an empty active register needs no mechanism.
        return Exclusions()

    if style is None:
        return Exclusions(
            rows=rows,
            fault=RegisterFault.UNSUPPORTED_STYLE,
            detail=(
                f"{len(rows)} row(s) are registered known-red and must be "
                f"excluded from {task_key}'s gate, but this repo's "
                f"`.dispatcher.yaml` declares no `test_exclusion:` style. "
                "Refusing to run the gate rather than let the task be judged "
                "against another unit's deliberate red rows (D-68). Rows: "
                + ", ".join(rows)
            ),
        )

    if not test_command or EXCLUSION_ENV not in test_command:
        return Exclusions(
            rows=rows,
            fault=RegisterFault.COMMAND_IGNORES_EXCLUSIONS,
            detail=(
                f"`.dispatcher.yaml` declares `test_exclusion: {style.value}` "
                f"but its `test:` command never references ${EXCLUSION_ENV}, "
                f"so the {len(rows)} registered exclusion(s) would be silently "
                "dropped and the gate would go red on rows this task cannot "
                "fix. Place the variable in the test command."
            ),
        )

    if rows_dir is None:
        # Callers that only want the decision (and the tests below) may omit the
        # directory. Reported as applied with no env rather than as a fault: the
        # decision is complete, the delivery is the caller's half.
        return Exclusions(
            rows=rows,
            detail=f"{len(rows)} registered known-red row(s), no rows_dir given",
        )

    path = write_rows_file(rows, directory=rows_dir)
    return Exclusions(
        rows=rows,
        env={EXCLUSION_ENV: str(path)},
        detail=f"excluded {len(rows)} registered known-red row(s) via {path}",
    )
