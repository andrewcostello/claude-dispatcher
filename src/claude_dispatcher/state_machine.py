"""Declared state machines: exhaustive by construction, diagram generated (not drawn).

A design review that asks "is every state explicit?" is a model judgement, and it
does not converge — measured, 4/4/7 findings flat across rounds. The same question
asked of a DECLARATION is arithmetic.

So a module declares its machine as a module-level literal and this module checks
it and draws it. Read by AST and `ast.literal_eval`, never by importing: a gate
that imports the branch it is judging executes the code under judgement.

The diagram is GENERATED. A model-drawn diagram is prose, and prose describing a
world that does not exist has blocked this project three times (D-56, D-65,
D-72). A generated one cannot drift, and regenerating it is a gate: a diagram
that no longer reproduces means the machine changed without the declaration.

Declaration shape (all names are plain strings so the literal stays AST-safe;
they are cross-checked against real Enum members in the same file):

    STATE_MACHINE = {
        "name": "bet_confirmation",
        "state_enum": "BetState",
        "event_enum": "BetEvent",
        "initial": "ACCEPTED",
        "terminal": ["SETTLED", "REJECTED"],
        "transitions": [
            {"from": "ACCEPTED", "event": "ROTATION_ACTIVATES", "to": "AWAITING_TURN",
             "effects": ["awaiting_confirmation=TRUE"]},
        ],
        "rejections": [
            {"from": "AWAITING_TURN", "event": "PROCESS_SHOT",
             "error": "TurnConfirmationPending"},
        ],
    }

Totality, not enumeration. "Undefined must not be a silent no-op" is the rule;
spelling out every (state x event) pair is not the only way to satisfy it, and on a
real machine it is the wrong way. Tested against bay-session's confirmation/arming
machine: 9 states x 5 events with 10 meaningful edges, so full enumeration demanded
25 filler pairs. A declaration that is mostly filler stops being read.

So a machine is total if EITHER every non-terminal pair is declared, OR a
`default_rejection` is declared and covers the rest. Neither is the failure — that
is the silent no-op. The count the default absorbs is reported, so what it covers
is visible rather than hidden.

`groups` is optional and purely presentational: it reproduces the composite states
("Turn gate", "Shot gate") that make the reviewed bay-session diagram readable.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

DECLARATION_NAME = "STATE_MACHINE"


class Fault(str, Enum):
    """Named ways a declaration is unusable. Every one blocks; none degrades."""

    NO_DECLARATION = "state_machine_absent"
    MALFORMED = "state_machine_malformed"
    STATE_NOT_ENUM = "state_not_an_enum_member"
    EVENT_NOT_ENUM = "event_not_an_enum_member"
    UNKNOWN_NAME = "declaration_names_unknown_state_or_event"
    NON_EXHAUSTIVE = "state_event_pair_undefined"
    NO_TERMINAL = "no_terminal_state"
    DIAGRAM_STALE = "diagram_does_not_reproduce"


@dataclass(frozen=True)
class Transition:
    source: str
    event: str
    target: str
    effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rejection:
    source: str
    event: str
    error: str


@dataclass(frozen=True)
class Declaration:
    name: str
    state_enum: str
    event_enum: str
    initial: str
    terminal: tuple[str, ...]
    transitions: tuple[Transition, ...]
    rejections: tuple[Rejection, ...]
    #: Typed error for every (state x event) pair not declared above. None means
    #: the declaration must enumerate them all.
    default_rejection: str | None = None
    #: Presentational grouping: label -> member states.
    groups: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: State rejection edges point at. Declared rather than guessed: without it the
    #: generator synthesised a `Rejected` pseudo-state beside a declared `REJECTED`
    #: terminal, so one diagram carried two nodes meaning the same thing.
    rejection_state: str | None = None

    @property
    def states(self) -> tuple[str, ...]:
        seen = [self.initial]
        for t in self.transitions:
            for s in (t.source, t.target):
                if s not in seen:
                    seen.append(s)
        for r in self.rejections:
            if r.source not in seen:
                seen.append(r.source)
        for s in self.terminal:
            if s not in seen:
                seen.append(s)
        return tuple(seen)

    @property
    def events(self) -> tuple[str, ...]:
        seen: list[str] = []
        for e in [t.event for t in self.transitions] + [r.event for r in self.rejections]:
            if e not in seen:
                seen.append(e)
        return tuple(seen)


@dataclass(frozen=True)
class Report:
    faults: tuple[tuple[Fault, str], ...] = ()
    declaration: Declaration | None = None
    #: Pairs the `default_rejection` covers. Reported so a default cannot hide how
    #: much of the machine it is standing in for.
    defaulted_pairs: int = 0

    @property
    def ok(self) -> bool:
        return not self.faults

    def detail(self) -> str:
        if self.ok:
            extra = (f", {self.defaulted_pairs} pair(s) covered by the default "
                     "rejection") if self.defaulted_pairs else ""
            return f"declaration is total and enum-backed{extra}"
        return "; ".join(f"{f.value}: {why}" for f, why in self.faults)


def _enum_members(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    """Enum class name -> its member names, from the AST alone."""
    out: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
        if not bases & {"Enum", "StrEnum", "IntEnum", "Flag", "IntFlag"}:
            continue
        members = [
            t.id
            for stmt in node.body
            if isinstance(stmt, ast.Assign)
            for t in stmt.targets
            if isinstance(t, ast.Name)
        ]
        out[node.name] = tuple(members)
    return out


def parse(source: str) -> tuple[Declaration | None, str]:
    """Read the declaration literal. Returns (decl, why-not) — never raises."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, f"module does not parse: {exc}"
    raw = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == DECLARATION_NAME for t in node.targets
        ):
            try:
                raw = ast.literal_eval(node.value)
            except (ValueError, SyntaxError) as exc:
                return None, f"{DECLARATION_NAME} is not a literal: {exc}"
    if raw is None:
        return None, f"no module-level {DECLARATION_NAME} literal"
    if not isinstance(raw, dict):
        return None, f"{DECLARATION_NAME} is {type(raw).__name__}, expected a mapping"

    required = ("name", "state_enum", "event_enum", "initial", "terminal", "transitions")
    missing = [k for k in required if k not in raw]
    if missing:
        return None, f"missing key(s): {', '.join(missing)}"
    try:
        transitions = tuple(
            Transition(
                source=str(t["from"]), event=str(t["event"]), target=str(t["to"]),
                effects=tuple(str(e) for e in (t.get("effects") or [])),
            )
            for t in raw["transitions"]
        )
        rejections = tuple(
            Rejection(source=str(r["from"]), event=str(r["event"]), error=str(r["error"]))
            for r in raw.get("rejections") or []
        )
        dflt = raw.get("default_rejection")
        decl = Declaration(
            name=str(raw["name"]), state_enum=str(raw["state_enum"]),
            event_enum=str(raw["event_enum"]), initial=str(raw["initial"]),
            terminal=tuple(str(s) for s in raw["terminal"]),
            transitions=transitions, rejections=rejections,
            default_rejection=str(dflt) if dflt else None,
            rejection_state=(str(raw["rejection_state"])
                             if raw.get("rejection_state") else None),
            groups=tuple(
                (str(k), tuple(str(v) for v in vs))
                for k, vs in (raw.get("groups") or {}).items()
            ),
        )
    except (KeyError, TypeError) as exc:
        return None, f"malformed entry: {exc}"
    return decl, ""


def check(source: str) -> Report:
    """Verify the declaration against the module's real enums, and that every
    (non-terminal state x event) pair is defined or explicitly rejected.
    """
    decl, why = parse(source)
    if decl is None:
        fault = Fault.NO_DECLARATION if "no module-level" in why else Fault.MALFORMED
        return Report(faults=((fault, why),))

    faults: list[tuple[Fault, str]] = []
    enums = _enum_members(ast.parse(source))

    states = enums.get(decl.state_enum)
    if states is None:
        faults.append((Fault.STATE_NOT_ENUM,
                       f"no Enum class {decl.state_enum!r} in this module"))
    events = enums.get(decl.event_enum)
    if events is None:
        faults.append((Fault.EVENT_NOT_ENUM,
                       f"no Enum class {decl.event_enum!r} in this module"))

    if states is not None:
        unknown = sorted(set(decl.states) - set(states))
        if unknown:
            faults.append((Fault.UNKNOWN_NAME,
                           f"state(s) not in {decl.state_enum}: {', '.join(unknown)}"))
    if events is not None:
        unknown = sorted(set(decl.events) - set(events))
        if unknown:
            faults.append((Fault.UNKNOWN_NAME,
                           f"event(s) not in {decl.event_enum}: {', '.join(unknown)}"))

    if not decl.terminal:
        faults.append((Fault.NO_TERMINAL,
                       "no terminal state: a machine that never ends cannot be "
                       "shown to complete"))

    gaps: list[tuple[str, str]] = []
    if states is not None and events is not None and not faults:
        defined = {(t.source, t.event) for t in decl.transitions}
        defined |= {(r.source, r.event) for r in decl.rejections}
        gaps = sorted(
            (s, e) for s in states if s not in decl.terminal for e in events
            if (s, e) not in defined
        )
        if gaps and not decl.default_rejection:
            shown = ", ".join(f"{s} x {e}" for s, e in gaps[:8])
            more = f" (+{len(gaps) - 8} more)" if len(gaps) > 8 else ""
            faults.append((
                Fault.NON_EXHAUSTIVE,
                f"{len(gaps)} (state x event) pair(s) are neither declared nor "
                f"covered: {shown}{more}. Either declare them, or declare a "
                "`default_rejection` so the machine is total by construction. "
                "Undefined must not be a silent no-op",
            ))
    return Report(faults=tuple(faults), declaration=decl,
                  defaulted_pairs=len(gaps) if decl.default_rejection else 0)


def _mermaid_id(label: str) -> str:
    """A safe mermaid node id. `(`, `+` and spaces are not valid in one, and a
    group label like "Turn gate (ROTATION + on_turn)" produced an unparseable
    diagram until this existed.
    """
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in label)
    return safe.strip("_") or "group"


def to_mermaid(decl: Declaration) -> str:
    """A normalised `stateDiagram-v2`. Deterministic: same declaration, same bytes.

    Shape follows the reviewed bay-session diagram — the event on the edge, the
    field effects under it, and rejections as edges to a single `Rejected`
    pseudo-state labelled with the TYPED error, so a reader sees what the machine
    refuses and with what.
    """
    lines = ["stateDiagram-v2", f"    %% {decl.name} (generated — do not edit)",
             f"    [*] --> {decl.initial}"]
    for label, members in sorted(decl.groups):
        lines.append(f'    state "{label}" as {_mermaid_id(label)} {{')
        for m in sorted(members):
            lines.append(f"        {m}")
        lines.append("    }")
    for t in sorted(decl.transitions, key=lambda x: (x.source, x.event, x.target)):
        label = t.event
        if t.effects:
            label += "\\n" + "\\n".join(sorted(t.effects))
        lines.append(f"    {t.source} --> {t.target}: {label}")
    sink = decl.rejection_state or "Rejected"
    for r in sorted(decl.rejections, key=lambda x: (x.source, x.event)):
        lines.append(f"    {r.source} --> {sink}: {r.event}\\n{r.error}")
    for s in sorted(decl.terminal):
        lines.append(f"    {s} --> [*]")
    if (decl.rejections or decl.default_rejection) and not decl.rejection_state:
        lines.append("    Rejected --> [*]")
    if decl.default_rejection:
        lines.append(f"    %% every undeclared (state x event) rejects: "
                     f"{decl.default_rejection}")
    return "\n".join(lines) + "\n"


def diagram_is_current(source: str, committed: str) -> bool:
    """True iff ``committed`` is exactly what this declaration generates.

    Byte comparison on purpose: a diagram that "mostly" matches is a diagram
    someone edited, which is the drift this exists to make impossible.
    """
    decl, _ = parse(source)
    if decl is None:
        return False
    return to_mermaid(decl) == committed


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] not in ("check", "diagram"):
        print("usage: state_machine check|diagram <file.py>", file=sys.stderr)
        return 2
    src = Path(argv[1]).read_text(encoding="utf-8")
    if argv[0] == "diagram":
        decl, why = parse(src)
        if decl is None:
            print(f"error: {why}", file=sys.stderr)
            return 1
        print(to_mermaid(decl), end="")
        return 0
    rep = check(src)
    print(f"{'PASS' if rep.ok else 'FAIL'} {argv[1]}: {rep.detail()}")
    return 0 if rep.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
