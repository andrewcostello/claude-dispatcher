"""Known-red register: rows a SEALS task committed RED by design (D-68).

The mechanical gate runs the whole suite and judges on exit code, but the
scaffold-first protocol leaves rows red between a seals task (P2) and its body
(P3). Without this register every task dispatched in that window fails a gate it
cannot satisfy. Rationale and the wave-1 measurements are in DECISIONS.md D-68.

Four constraints a future change must not break:

  * NO TEST-OUTPUT PARSING. Row identity comes from a declared entry, never from
    a report. Suppression is `--deselect`; confirming a row is red is a targeted
    run. Every judgement stays exit-code-only (D-58 — two shipped false greens).
  * AN ENTRY NEVER EXCUSES ITS OWN BODY. `body_task` still sees the rows red;
    greening them is its deliverable.
  * FAIL TOWARD RED. A `--deselect` matching no test is not an error, so a stale
    entry leaves the row running. Never replace this with a skip or a marker.
  * EXCLUSIONS TRAVEL AS A FILE PATH, not as arguments. The test command is
    arbitrary shell and cannot be safely appended to; see EXCLUSION_ENV.

Entries are hand-written and reviewed in a diff. Auto-registration from a seals
summary is deliberately NOT built yet — it is the half that could invent a
suppression nobody read.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

# Tracked, so a suppression is reviewed in a diff. Deliberately not `docs/runs/`
# (gitignored, per-run) nor the task row (rewritten mid-run, dies with the
# worktree).
REGISTER_RELPATH = "config/known-red.yaml"

# Names a FILE of node ids, one per line; the repo builds its own argv with
# `while IFS= read -r row`. Two rejected designs and why (pre-rendered args
# cannot survive shell expansion; an IFS-newline split cannot be written inside
# a YAML block scalar) are in commit d4b942c. Do not switch to passing the rows
# in the variable itself.
EXCLUSION_ENV = "DISPATCHER_KNOWN_RED_FILE"

#: Basename of the rows file, written into the task's run-artifact directory.
ROWS_FILENAME = "known-red-rows.txt"


class ExclusionStyle(str, Enum):
    """How a repo spells "run the suite but not these rows".

    `go test` needs its own member (a `-run` regex, not per-row); until it has
    one, a Go repo with active entries is UNSUPPORTED_STYLE, never a no-op.

    The two members deliver DIFFERENT FILE CONTENTS, because the runners differ
    in what they can be handed (see `rows_payload`): pytest takes one node id
    per row, vitest takes a single pattern covering all of them.
    """

    PYTEST_DESELECT = "pytest-deselect"
    VITEST_NAME_PATTERN = "vitest-name-pattern"


class RegisterFault(str, Enum):
    """Named ways the register can fail to apply. All BLOCK rather than degrade:
    a silently dropped exclusion means the task pays for rows it cannot fix
    while the operator believes it was handled.
    """

    UNSUPPORTED_STYLE = "known_red_unsupported_style"
    COMMAND_IGNORES_EXCLUSIONS = "known_red_command_ignores_exclusions"


class RegisterError(ValueError):
    """Register exists but is unreadable. Fails CLOSED — never read as empty,
    or the file on disk would claim entries that are not in force.
    """


@dataclass(frozen=True)
class KnownRedEntry:
    """One unit's deliberate red rows.

    `body_task` is load-bearing twice: it retires the entry when Done, and it is
    the one gate these rows are NOT hidden from.
    """

    rows: tuple[str, ...]
    seals_task: str
    body_task: str
    reason: str
    registered_at_sha: str = ""

    def applies_to(self, task_key: str, *, done_keys: frozenset[str]) -> bool:
        """True iff these rows should be hidden from ``task_key``.

        False when it IS the body (the rows are its deliverable), or the body is
        Done (retired for everyone).
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
    """What to hand one task's gate. A non-None ``fault`` means BLOCK; ``rows``
    stays populated so the block can name what went unapplied.
    """

    rows: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    fault: RegisterFault | None = None
    detail: str = ""

    @property
    def applied(self) -> bool:
        """True only when rows will actually reach the test command. Requires
        ``env``, so a suppression that never happened is not logged as though it
        did.
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
    """Read the register. Absent file = empty register (every repo's starting
    state). Present but unreadable raises :class:`RegisterError`.
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
    """Rows to hide from ``task_key``'s gate, de-duplicated. Order is stable
    (first registration wins) so journal payloads diff across runs.
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


def rows_payload(rows: Iterable[str], *, style: ExclusionStyle) -> str:
    """Contents of the rows file. Data, never arguments — see
    :data:`EXCLUSION_ENV`.

    The contents are style-specific because the runners are:

      * PYTEST_DESELECT — one node id per line; the repo loops and emits one
        ``--deselect`` per row.
      * VITEST_NAME_PATTERN — ONE ready-built regex, because vitest excludes by
        pattern and building that pattern means regex-escaping arbitrary test
        names. A repo cannot do that safely in shell, so the dispatcher renders
        it and the repo only interpolates.

    ``style`` is required: a payload written in the other style parses as a
    valid file and excludes nothing, which is a silent fail-open.
    """
    rows = tuple(rows)
    if not rows:
        return ""
    if style is ExclusionStyle.VITEST_NAME_PATTERN:
        return f"{name_pattern(rows)}\n"
    body = "\n".join(rows)
    return f"{body}\n"


def write_rows_file(
    rows: Iterable[str], *, directory: Path, style: ExclusionStyle,
) -> Path:
    """Write the rows file into ``directory`` (created if absent) and return it."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ROWS_FILENAME
    path.write_text(rows_payload(rows, style=style), encoding="utf-8")
    return path


def deselect_args(rows: Iterable[str]) -> str:
    """Render ``rows`` as shell-quoted pytest ``--deselect`` arguments.

    NOT for :data:`EXCLUSION_ENV`. For callers that exec a shlex-split list, and
    to document the canonical pytest spelling. Quoting matters: parametrised ids
    contain spaces, e.g. ``...::test_slot[a plain property]``.
    """
    return " ".join(f"--deselect {shlex.quote(r)}" for r in rows)


#: Characters that carry meaning in a JavaScript regular expression. Python's
#: `re.escape` is not usable here: it escapes `&`, `~`, `#` and space, which are
#: identity escapes JS accepts only outside unicode mode, so a pattern built
#: with it is one `new RegExp(p, "u")` away from a SyntaxError that would fail
#: the gate OPEN by matching nothing.
_JS_REGEX_SPECIAL = set(r"^$\.*+?()[]{}|/")


def _js_regex_escape(text: str) -> str:
    return "".join(f"\\{c}" if c in _JS_REGEX_SPECIAL else c for c in text)


def name_pattern(rows: Iterable[str]) -> str:
    """Render ``rows`` as one vitest ``--testNamePattern`` regex.

    A row is a test's FULL name — its `describe` names and its own, joined by
    single spaces, which is what vitest matches against.

    Anchored with `$` inside the lookahead so a row excludes only its own exact
    name: unanchored, a registered "loads a user" would also suppress "loads a
    user with no email", hiding a row nobody registered. That is the fail-open
    this register exists to refuse.
    """
    alternatives = "|".join(_js_regex_escape(r) for r in rows)
    return f"^(?!(?:{alternatives})$)"


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

    ``style`` is None when the repo declared none. ``test_command`` must PLACE
    :data:`EXCLUSION_ENV` itself — the dispatcher cannot inject into arbitrary
    shell safely.
    """
    rows = rows_for_task(register, task_key=task_key, done_keys=done_keys)
    if not rows:
        # Byte-identical to pre-register behaviour. Not a fault even with no
        # declared style: an empty active register needs no mechanism.
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
        # Decision without delivery: `applied` stays False (see the property).
        return Exclusions(
            rows=rows,
            detail=f"{len(rows)} registered known-red row(s), no rows_dir given",
        )

    path = write_rows_file(rows, directory=rows_dir, style=style)
    return Exclusions(
        rows=rows,
        env={EXCLUSION_ENV: str(path)},
        detail=f"excluded {len(rows)} registered known-red row(s) via {path}",
    )
