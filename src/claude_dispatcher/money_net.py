"""The money-path net: derived from the target repo's tracked table, or a
named absence. Never a second hand-list.

P1 of unit DF-5. The contract is DF-5-1's, the seals are DF-5-2's, and the
:func:`derive_money_net` body plus its wiring landed with DF-5-3 — by
different authors.

The defect, re-measured on this tree (2026-08-14)
-------------------------------------------------
``cli.DEFAULT_FINANCIAL_PATHS`` ships 24 globs. The authoritative table —
``.agent/risk-paths.json`` on evenplay-mono's ``fix/agent-config-money-paths``
branch (PR #1387's line, tip ``164d3a828``) — carries **74** unique financial
paths. **49 are absent from the fallback**, including, verbatim, five of the six the
task names: ``**/grpc_xwallet/**``, ``**/adapter/wallet/**``,
``.../internal/playerfunds/**``, ``store/liability*``, ``store/process_shot*``
(plus ``cmd/bay-session/process_shot*``); the sixth, ``bet_service.go``, is
caught upstream by ``cmd/bay-session/*bet*`` — also absent here.

Three further measurements, each of which rules out one tempting answer:

1. **The drift detector already exists and is green today.**
   ``pytest tests/test_default_financial_paths.py`` → 7 passed, 0 skipped, on
   the same tree where the drift is 49 globs wide. Its parity row compares
   the fallback against ``~/Project/evenplay-mono/.agent/risk-paths.json`` —
   a file that is **untracked** in that checkout (``git status`` says
   ``?? .agent/``) and frozen at the pre-#1387 table. A detector whose truth
   source is an unversioned mirror inherits the mirror's staleness: it is the
   hand-list bug with a file read in front of it, exactly as the
   recheck_min_severity precedent predicted for generators that degrade when
   they cannot see the consumer. So "hand-list + drift test" — the third
   option the task allows — is not a candidate: it is the shipped status quo,
   and it failed today.

2. **The fallback is cross-repo noise.** This very run
   (2026-08-14T14-58-45Z-tasks) dispatches claude-dispatcher tasks, and every
   implementer prompt — including the one that authored this file — carries
   ``FINANCIAL_PATHS`` naming evenplay-mono money paths. The fallback is
   injected into repos it does not describe; for every non-evenplay run it is
   noise presented as a safety net.

3. **The authoritative table's own rows refute the structural tests.** 14 of
   the 74 financial paths at tip are exact files with no wildcard
   (``tournament/service.go``, ``cmd/bay-session/main.go``, …). The shipped
   ``test_entries_are_normalised_globs`` asserts every entry contains ``*`` or
   ``?`` — it would reject the authoritative table's own rows. Transcription
   tests encode the transcriber's assumptions, not the source's.

The three required answers
--------------------------
**Where does the authoritative money table live when the target repo is not
checked out?** Nowhere. There is no off-repo authority, and none is needed:
under ``dispatcher run`` the target repo is always checked out — ``repo_root``
is the tree worktrees are cut from. The only real cases are "the run's base
ref carries the table" (derive from it) and "it does not" (a named absence —
which is today's truth for any run based on evenplay-mono ``main``, since
``.agent/risk-paths.json`` exists only on the agent-config branches). A
consumer genuinely without the checkout has no basis to answer the money
question and must say ABSENT, not recite a memory of another repo.

**What is the fallback FOR?** It was justified as cover for runs where the
``cmd/classify`` binary is absent. But the table is plain JSON tracked in the
target repo: reading it requires git, which every run already has — not the
binary. The binary's absence never justified a hand copy; it justified
reading the table directly.

**Derived list, fail-closed refusal, or drift detector?** Derived, with a
fail-closed named absence. Derive the net at run start from the tracked table
at the run's base ref. When the ref carries no readable table, the net is
ABSENT — folded to the universal glob so even a consumer that has never heard
of absence gates *more*, never less (see the fold grammar below). The drift
detector is ruled out by measurement 1; a bare refusal (abort the run) is
disproportionate when the classification contract is already ADD-only — the
honest fail-closed shape for an ADD-only net is "gate everything", not "run
nothing".

**Should the fallback exist at all? No.** ``DEFAULT_FINANCIAL_PATHS`` was
condemned (see :data:`CONDEMNED_SURFACES`) and retired with DF-5-3's body,
together with its parity test — there is no hand list left to keep in parity.
What replaces it is not a better list but a different kind of thing: a
:class:`MoneyNet` record whose provenance is structural.

Structural exclusions (the DF-1 precedent: illegal sources have no member)
--------------------------------------------------------------------------
:class:`MoneyNetSource` has members for the tracked table at the run's base
ref and for an explicit operator override. It has **no member** for a shipped
constant, an untracked working-tree file, or another checkout's mirror — the
three shapes this defect class has actually taken. A net from those sources
is unconstructible, not discouraged.

The fold (key names fixed now, so seals bind to real names)
-----------------------------------------------------------
The env key ``FINANCIAL_PATHS``, the prompt line ``- FINANCIAL_PATHS=``, and
the plan line ``  Financial paths: `` survive unchanged. What changes is the
value's provenance and its absent form:

* DERIVED → the comma-joined globs, byte-compatible with today's grammar;
  consumers of the comma list are unchanged.
* ABSENT → exactly ``**`` (:data:`ABSENT_ENV_VALUE`). CHOICE: the universal
  glob, not an empty string and not a sentinel word. An empty string is the
  dead-net bug (GO-0) by construction. A sentinel word ("UNAVAILABLE") is a
  glob that matches nothing, so an unaware matcher silently under-gates —
  the same bug wearing a uniform. ``**`` makes the ignorant reading and the
  informed reading agree: everything is money until the repo says otherwise.
  The human-facing detail rides in :meth:`MoneyNet.plan_value`, not the env.

Scope choices (each a CHOICE this scaffold makes on purpose)
------------------------------------------------------------
* Authority is the tracked blob at the run's **base ref** — ``git`` object
  access, never the working-tree file. The measured trap is precisely an
  untracked on-disk copy shadowing truth. Two runs on the same base must
  derive the same net; ``table_blob_sha`` is the freshness witness that lets
  a later reader check what was actually read.
* A parsed table with **zero** financial rules folds to ABSENT (detail names
  the ref), not to an empty DERIVED net. An empty comma string is the shape
  of the dead-glob bug; a repo that declares no money rules gets the
  fail-closed fold and a truthful reason, not silence. DERIVED therefore
  always carries at least one glob.
* ``--financial-paths`` / ``$FINANCIAL_PATHS`` survives as
  ``OPERATOR_OVERRIDE`` — an operator's explicit statement is provenance,
  not drift. Only the shipped *default* is condemned.
* Entry validation accepts exact-file rows (measurement 3). It enforces
  repo-relative forward-slash shape only — matching semantics belong to the
  consumer, not the record.
* Wiring landed with DF-5-3 in one commit with the body: ``run.py`` and
  ``orchestrator`` resolve the net at run start (operator override, else
  :func:`derive_money_net` against the run's base ref), and the condemned
  constant and its parity-test file retired in the same commit. A wired stub
  breaks every run; an unwired body is a silent no-op — the DF-3-1 rule.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

#: Where a repo that has a money table tracks it, relative to its root.
TABLE_RELPATH = ".agent/risk-paths.json"

#: The ABSENT fold of the net: the universal glob. See the module docstring
#: for why this — and not "" or a sentinel word — is the fail-closed value.
ABSENT_ENV_VALUE = "**"

#: Surfaces this contract condemned; DF-5-3 retired them in the same commit
#: that wired :func:`derive_money_net` in. The record stays: the seals bind
#: to it so the retirement cannot be quietly weakened or reverted.
CONDEMNED_SURFACES = (
    "claude_dispatcher.cli.DEFAULT_FINANCIAL_PATHS",
    "tests/test_default_financial_paths.py",
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class MoneyNetSource(Enum):
    """Where a derived net's globs came from.

    Deliberately has no member for a shipped constant, an untracked
    working-tree file, or another checkout's mirror — the three measured
    shapes of this defect class. Such a net cannot be represented.
    """

    #: The tracked blob ``TABLE_RELPATH`` at the run's base ref, read via git
    #: object access (never the working-tree file).
    TRACKED_TABLE = "tracked-table"

    #: An explicit ``--financial-paths`` / ``$FINANCIAL_PATHS`` value the
    #: operator stated for this run.
    OPERATOR_OVERRIDE = "operator-override"


class MoneyNetState(Enum):
    DERIVED = "derived"
    ABSENT = "absent"


def _validate_glob(entry: str) -> None:
    if not entry or not entry.strip():
        raise ValueError("money-net glob must be non-blank")
    if entry != entry.strip():
        raise ValueError(f"money-net glob {entry!r} has surrounding whitespace")
    if entry.startswith("/"):
        raise ValueError(f"money-net glob {entry!r} must be repo-relative")
    if "\\" in entry:
        raise ValueError(f"money-net glob {entry!r} must use forward slashes")
    if "," in entry:
        raise ValueError(
            f"money-net glob {entry!r} contains a comma — it would corrupt "
            "the comma-joined env fold"
        )
    if "" in entry.split("/"):
        raise ValueError(f"money-net glob {entry!r} has an empty path segment")
    # NO wildcard requirement: 14 of the authoritative table's 74 financial
    # rows are exact files (measurement 3 in the module docstring).


@dataclass(frozen=True)
class MoneyNet:
    """The money-path net a run injects, with named provenance or a named
    absence. Illegal shapes are unconstructible — a truthiness check can
    never mistake an absent net for a real one, and nothing can smuggle in a
    provenance the source enum does not name.
    """

    state: MoneyNetState
    #: DERIVED: at least one entry. ABSENT: must be empty.
    financial_globs: tuple[str, ...] = ()
    #: DERIVED: required. ABSENT: must be None.
    source: MoneyNetSource | None = None
    #: TRACKED_TABLE only: the ref whose tree carried the table.
    base_ref: str | None = None
    #: TRACKED_TABLE only: git blob SHA of the table actually read — the
    #: freshness witness a later reader can check against the ref.
    table_blob_sha: str | None = None
    #: ABSENT only: why there is no net. Mandatory and non-blank.
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.state is MoneyNetState.DERIVED:
            if self.source is None:
                raise ValueError("a DERIVED money net must name its source")
            if not self.financial_globs:
                raise ValueError(
                    "a DERIVED money net must carry at least one glob — a "
                    "table with no financial rules folds to ABSENT, not to "
                    "an empty net (the GO-0 shape)"
                )
            for entry in self.financial_globs:
                _validate_glob(entry)
            if self.detail is not None:
                raise ValueError("detail is the ABSENT state's field")
            if self.source is MoneyNetSource.TRACKED_TABLE:
                if not (self.base_ref or "").strip():
                    raise ValueError(
                        "a tracked-table net must name the base ref it was "
                        "derived from"
                    )
                if not _SHA_RE.match(self.table_blob_sha or ""):
                    raise ValueError(
                        "a tracked-table net must carry the 40-hex blob SHA "
                        "of the table it read (the freshness witness)"
                    )
            else:  # OPERATOR_OVERRIDE
                if self.base_ref is not None or self.table_blob_sha is not None:
                    raise ValueError(
                        "an operator override has no ref or blob provenance"
                    )
        else:  # ABSENT
            if not (self.detail or "").strip():
                raise ValueError(
                    "an ABSENT money net must say why (mandatory detail)"
                )
            if self.financial_globs:
                raise ValueError("an ABSENT money net carries no globs")
            if (
                self.source is not None
                or self.base_ref is not None
                or self.table_blob_sha is not None
            ):
                raise ValueError(
                    "an ABSENT money net has no source provenance — absence "
                    "is not a place globs come from"
                )

    # -- the fold: key names are fixed by the existing consumers ---------- #

    def env_value(self) -> str:
        """The value of ``FINANCIAL_PATHS`` (env and prompt line).

        DERIVED folds to the comma-joined globs — byte-compatible with the
        grammar every consumer already parses. ABSENT folds to ``**`` so an
        unaware glob matcher over-gates instead of under-gating.
        """
        if self.state is MoneyNetState.DERIVED:
            return ",".join(self.financial_globs)
        return ABSENT_ENV_VALUE

    def plan_value(self) -> str:
        """The human-facing ``Financial paths:`` line for the dispatch plan:
        provenance for a derived net, the reason for an absent one."""
        if self.state is MoneyNetState.ABSENT:
            return f"{ABSENT_ENV_VALUE} (fail-closed: {self.detail})"
        if self.source is MoneyNetSource.OPERATOR_OVERRIDE:
            return (
                f"{len(self.financial_globs)} glob(s) from --financial-paths "
                "(operator override)"
            )
        return (
            f"{len(self.financial_globs)} glob(s) from {TABLE_RELPATH}"
            f"@{self.base_ref} (blob {(self.table_blob_sha or '')[:12]})"
        )


def financial_globs_from_table(table_json: str) -> tuple[str, ...]:
    """Fold a risk-paths table to its financial globs, order-preserving and
    deduplicated — the pure half of the derivation, implemented now so the
    seals bind to real behavior.

    Raises :class:`ValueError` on any malformed table. A table that cannot
    be understood is not a smaller net — the caller folds the failure to
    ABSENT with the error named. Returns ``()`` for a well-formed table with
    no ``financial: true`` rules; per the contract the caller folds that to
    ABSENT too, never to an empty DERIVED net.
    """
    try:
        payload = json.loads(table_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"risk-paths table is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise ValueError("risk-paths table has no 'rules' list")
    out: list[str] = []
    for i, rule in enumerate(payload["rules"]):
        if not isinstance(rule, dict):
            raise ValueError(f"risk-paths rule #{i} is not an object")
        if not rule.get("financial"):
            continue
        paths = rule.get("paths")
        if not isinstance(paths, list) or not all(
            isinstance(p, str) for p in paths
        ):
            raise ValueError(
                f"financial rule #{i} has no 'paths' list of strings"
            )
        for path in paths:
            if path not in out:
                out.append(path)
    return tuple(out)


def money_net_from_override(value: str) -> MoneyNet:
    """Fold an explicit ``--financial-paths`` / ``$FINANCIAL_PATHS`` value to
    a net with ``OPERATOR_OVERRIDE`` provenance.

    An empty override folds to ABSENT (fail-closed): an operator typing
    ``--financial-paths ""`` gets the universal glob and a named reason,
    never the dead empty net (the GO-0 shape). A malformed override glob
    raises :class:`ValueError` — an operator's explicit statement is refused
    loudly, not folded away.
    """
    globs: list[str] = []
    for entry in value.split(","):
        entry = entry.strip()
        if entry and entry not in globs:
            globs.append(entry)
    if not globs:
        return MoneyNet(
            state=MoneyNetState.ABSENT,
            detail="--financial-paths override was empty",
        )
    return MoneyNet(
        state=MoneyNetState.DERIVED,
        financial_globs=tuple(globs),
        source=MoneyNetSource.OPERATOR_OVERRIDE,
    )


def derive_money_net(repo_root: Path, base_ref: str) -> MoneyNet:
    """Derive the run's money net from the tracked table at ``base_ref``.

    The mechanics as ruled by DF-5-1 (module docstring):

    * The blob is resolved with git object access —
      ``git -C repo_root rev-parse <base_ref>:.agent/risk-paths.json`` —
      and read with ``git cat-file blob <sha>``. NEVER the working-tree
      file: the measured trap is an untracked on-disk copy 49 globs stale.
    * Path absent at the ref (or no usable repo/ref at all) → ABSENT, detail
      naming the ref and :data:`TABLE_RELPATH`.
    * Unreadable or malformed table, or a table with zero financial rules →
      ABSENT, detail naming the failure (see
      :func:`financial_globs_from_table`).
    * Otherwise → DERIVED / TRACKED_TABLE with the globs, the ref, and the
      blob SHA.
    * There is no constant to fall back to on ANY branch of this function.
    """

    def _git(*argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo_root), *argv],
            capture_output=True,
            text=True,
        )

    def _absent(detail: str) -> MoneyNet:
        return MoneyNet(state=MoneyNetState.ABSENT, detail=detail)

    spec = f"{base_ref}:{TABLE_RELPATH}"
    rev = _git("rev-parse", "--verify", spec)
    if rev.returncode != 0:
        return _absent(
            f"no tracked {TABLE_RELPATH} at {base_ref} in {repo_root}: "
            f"{rev.stderr.strip() or 'git rev-parse failed'}"
        )
    blob_sha = rev.stdout.strip()
    if not _SHA_RE.match(blob_sha):
        return _absent(
            f"git rev-parse {spec} returned {blob_sha!r}, not a 40-hex blob "
            "SHA — no freshness witness, no net"
        )
    blob = _git("cat-file", "blob", blob_sha)
    if blob.returncode != 0:
        return _absent(
            f"unreadable {TABLE_RELPATH} blob {blob_sha[:12]} at {base_ref}: "
            f"{blob.stderr.strip()}"
        )
    try:
        globs = financial_globs_from_table(blob.stdout)
    except ValueError as exc:
        return _absent(f"{TABLE_RELPATH} at {base_ref} is malformed: {exc}")
    if not globs:
        return _absent(
            f"{TABLE_RELPATH} at {base_ref} declares zero financial rules"
        )
    try:
        return MoneyNet(
            state=MoneyNetState.DERIVED,
            financial_globs=globs,
            source=MoneyNetSource.TRACKED_TABLE,
            base_ref=base_ref,
            table_blob_sha=blob_sha,
        )
    except ValueError as exc:
        return _absent(
            f"{TABLE_RELPATH} at {base_ref} carries an illegal glob: {exc}"
        )
