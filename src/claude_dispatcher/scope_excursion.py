"""Did this task change files it does not own, and how badly.

Measured 2026-09-04, WAL-HOLD-3: a BODIES task for the `hold` unit deleted
`wallet/v2/ledger/body.go` (378 lines) and rewrote `ledger/ledger.go`, then
passed its verifier AND its four-seat panel and reached Awaiting Review. Only
the merge ORDER saved the ledger unit's implementation — had HOLD-3 merged
first, 378 lines would have gone with it and the ledger's own merge would have
looked like the conflict.

Nothing asked the question. The panel judges code quality; the verifier judges
completeness against the contract. Neither asks whether the diff reaches
outside the task.

DIRECTION IS THE WHOLE DESIGN. A blanket path deny (`immutable_paths:`) exists
already and is the wrong tool here: it is add-only with no negation form, so it
refuses the missing import and the call-site rename that follows from a
signature the task legitimately owns — it stops the harm by also stopping the
help. Operator ruling 2026-09-04: "I don't want to be so rigid it stops simple
fixes that were necessary."

So an excursion's severity comes from what it DID, not merely from where:

    foreign delete   destroys another unit's work        -> BLOCK
    foreign modify   may be necessary and minimal        -> REVIEW
    foreign add      a call site, an import              -> NOTE

Only BLOCK and REVIEW cost anything, and a conforming task produces neither, so
the common case is free.

A BLOCK here is NOT a quality failure and must never feed the effort/model
cascade: escalating re-implements the same task three times to arrive at the
same question, and if a later rung happens not to reach outside, the block
clears silently and the evidence that an agent WANTED to disappears. That
evidence is the signal the deviation model exists to surface. Blocked rows go
to adjudication instead.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Sequence


class Severity(IntEnum):
    """IntEnum because the verdict IS `max` over the diff's excursions, and a
    plain Enum is unordered -- `max` raises on it rather than comparing."""

    NONE = 0
    NOTE = 1
    REVIEW = 2
    BLOCK = 3


#: git's `--name-status` letters this module acts on. Anything else (T, U, and
#: the R/C pairs, which `--no-renames` already decomposes into A+D) is treated
#: as a modify: unknown-but-present is the conservative reading, and silently
#: dropping a letter would let an excursion through.
_DELETE = "D"
_ADD = "A"

_SEVERITY_BY_CHANGE = {_DELETE: Severity.BLOCK, _ADD: Severity.NOTE}


@dataclass(frozen=True)
class Excursion:
    path: str
    change: str

    @property
    def severity(self) -> Severity:
        return _SEVERITY_BY_CHANGE.get(self.change, Severity.REVIEW)


@dataclass(frozen=True)
class ExcursionReport:
    excursions: tuple[Excursion, ...]
    severity: Severity

    @property
    def blocking(self) -> tuple[Excursion, ...]:
        return tuple(e for e in self.excursions if e.severity is Severity.BLOCK)

    def reason(self) -> str:
        """One line per excursion, worst first — this reaches a human as the
        row's blocked_reason, so it names paths rather than counts."""
        ordered = sorted(
            self.excursions, key=lambda e: (-e.severity.value, e.path),
        )
        return "; ".join(f"{e.change} {e.path}" for e in ordered)


def owns_path(path: str, owns: Sequence[str]) -> bool:
    """Whether `path` is inside the task's declared ownership.

    Two spellings, because a unit is a DIRECTORY and a glob is not a good way
    to say so: an entry ending in `/` or `/**` is a directory prefix, anything
    else is an fnmatch pattern.

    The prefix form compares against the trailing slash deliberately. `hold`
    and `holdings` share a prefix, so a bare `startswith("…/hold")` would call
    every file under `holdings/` owned — the excursion this module exists to
    catch would be invisible in exactly the repos that name units this way.
    """
    for entry in owns:
        spec = entry.strip()
        if not spec:
            continue
        if spec.endswith("/**"):
            spec = spec[:-2]
        if spec.endswith("/"):
            if path.startswith(spec):
                return True
            continue
        if fnmatch.fnmatchcase(path, spec):
            return True
    return False


def classify(
    name_status: Iterable[tuple[str, str]], owns: Sequence[str],
) -> ExcursionReport:
    """Classify one task's diff against what it declared it owns.

    `name_status` is (change_letter, path) as `git diff --name-status
    --no-renames` reports it.

    An EMPTY `owns` means the task declared no ownership, which is not the same
    as owning nothing: it is opt-in, so nothing is judged. Every worklist that
    predates this keeps running, and the check turns on per row.
    """
    if not list(owns):
        return ExcursionReport(excursions=(), severity=Severity.NONE)

    found = [
        Excursion(path=path, change=change)
        for change, path in name_status
        if not owns_path(path, owns)
    ]
    worst = max((e.severity for e in found), default=Severity.NONE)
    return ExcursionReport(excursions=tuple(found), severity=worst)
