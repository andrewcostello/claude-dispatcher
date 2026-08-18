"""Seals for declared state machines.

"Is every state explicit?" asked of code is a model judgement that does not
converge — measured, 4/4/7 panel findings flat across rounds. Asked of a
DECLARATION it is arithmetic, and these rows are that arithmetic.

The format was validated against a REAL machine (bay-session's confirmation and
per-shot arming, `evenplay-mono/docs/bay-session/confirmation-and-arming.md`)
rather than a toy, which is what produced its two corrections: full (state x
event) enumeration is impractical, and mermaid ids may not contain `(`/`+`/spaces.
"""

from __future__ import annotations

import textwrap

import pytest

from claude_dispatcher import state_machine as sm

_T_AB = '{"from": "A", "event": "GO", "to": "B", "effects": ["armed=TRUE"]}'
_T_BD = '{"from": "B", "event": "GO", "to": "DONE"}'


def _machine(transitions: str = None) -> str:
    """The fixture, with an injectable transitions list so a REORDER fixture is
    exact rather than a textual replace that can silently fail to apply."""
    body = transitions if transitions is not None else f"{_T_AB},\n            {_T_BD},"
    return _TEMPLATE.replace("@@TRANSITIONS@@", body)


_TEMPLATE = textwrap.dedent('''
    from enum import Enum


    class S(Enum):
        A = "a"
        B = "b"
        DONE = "done"
        NO = "no"


    class E(Enum):
        GO = "go"
        STOP = "stop"


    STATE_MACHINE = {
        "name": "m",
        "state_enum": "S",
        "event_enum": "E",
        "initial": "A",
        "terminal": ["DONE", "NO"],
        "rejection_state": "NO",
        "default_rejection": "IllegalTransition",
        "transitions": [
            @@TRANSITIONS@@
        ],
        "rejections": [
            {"from": "B", "event": "STOP", "error": "AlreadyRunning"},
        ],
    }
''')

MACHINE = _machine()


def _without(key: str) -> str:
    return MACHINE.replace(f'"{key}"', f'"_{key}_disabled"', 1)


# ------------------------------------------------------------- reading it ----

def test_a_module_with_no_declaration_is_a_named_fault() -> None:
    """The only BLOCKING finding a scaffold can earn mechanically. Measured under:
    return an empty Report for a missing declaration and this reddens.
    """
    rep = sm.check("x = 1\n")
    assert not rep.ok
    assert rep.faults[0][0] is sm.Fault.NO_DECLARATION


def test_the_declaration_is_read_by_ast_and_never_imported() -> None:
    """A gate that imports the branch it judges EXECUTES the code under judgement.

    Measured under: swap `ast.literal_eval` for `eval`/`exec` and this reddens —
    the side effect fires. The module below would delete a file on import.
    """
    hostile = textwrap.dedent('''
        import pathlib
        pathlib.Path("/tmp/sm-should-not-exist").write_text("executed")
        STATE_MACHINE = {"name": "x"}
    ''')
    import pathlib
    victim = pathlib.Path("/tmp/sm-should-not-exist")
    victim.unlink(missing_ok=True)
    sm.check(hostile)
    assert not victim.exists(), "the checker executed the module it was reading"


def test_a_non_literal_declaration_is_malformed_not_executed() -> None:
    rep = sm.check("STATE_MACHINE = compute()\n")
    assert not rep.ok and rep.faults[0][0] is sm.Fault.MALFORMED


# ------------------------------------------------- states must be enums ------

def test_states_and_events_must_be_real_enum_members() -> None:
    """The enum preference, enforced. A string state cannot be checked for
    exhaustiveness and cannot be drawn.

    Measured under: skip the `_enum_members` cross-check and this reddens.
    """
    rep = sm.check(MACHINE.replace('class S(Enum):', 'class S:'))
    assert not rep.ok
    assert any(f is sm.Fault.STATE_NOT_ENUM for f, _ in rep.faults)


def test_a_declaration_naming_a_state_the_enum_lacks_is_refused() -> None:
    rep = sm.check(MACHINE.replace('"to": "DONE"', '"to": "TYPO"'))
    assert not rep.ok
    assert any(f is sm.Fault.UNKNOWN_NAME for f, _ in rep.faults)


# --------------------------------------------------------- totality ----------

def test_totality_is_satisfiable_by_a_default_rather_than_enumeration() -> None:
    """The correction the real machine forced. bay-session is 9 states x 5 events
    with 10 meaningful edges, so full enumeration demanded 25 filler pairs — and a
    declaration that is mostly filler stops being read.

    Measured under: require every pair regardless of `default_rejection` and this
    reddens (and the bay-session fixture fails).
    """
    rep = sm.check(MACHINE)
    assert rep.ok, rep.detail()
    assert rep.defaulted_pairs > 0
    assert "covered by the default rejection" in rep.detail()


def test_neither_enumerated_nor_defaulted_is_the_failure() -> None:
    """"Undefined must not be a silent no-op" — enforced here rather than asked for.

    Measured under: drop the NON_EXHAUSTIVE branch and this reddens.
    """
    rep = sm.check(_without("default_rejection"))
    assert not rep.ok
    assert any(f is sm.Fault.NON_EXHAUSTIVE for f, _ in rep.faults)
    why = dict((f, w) for f, w in rep.faults)[sm.Fault.NON_EXHAUSTIVE]
    assert "default_rejection" in why, "the fault must say how to satisfy it"


def test_a_machine_with_no_terminal_state_is_refused() -> None:
    rep = sm.check(MACHINE.replace('"terminal": ["DONE", "NO"],', '"terminal": [],'))
    assert not rep.ok
    assert any(f is sm.Fault.NO_TERMINAL for f, _ in rep.faults)


def test_the_default_cannot_hide_how_much_it_covers() -> None:
    """A default standing in for nearly the whole machine is a different fact from
    one covering three odd corners, and the report must not flatten them.
    """
    rep = sm.check(MACHINE)
    # A and B are the only non-terminal states, 2 events = 4 pairs, 3 declared,
    # so the default stands in for exactly one: A x STOP.
    assert rep.defaulted_pairs == 1
    assert str(rep.defaulted_pairs) in rep.detail()


# ----------------------------------------------------------- the diagram ----

def test_declaration_ORDER_does_not_change_the_diagram() -> None:
    """The property the staleness gate rests on, and the first version of this row
    could not see it.

    Comparing two renders of the SAME source passes under any iteration order, so
    the mutation "render in declaration order instead of sorted" fired no row — a
    vacuous seal, found by mutation testing. The property that matters is that
    REORDERING the declaration produces identical bytes; otherwise moving two
    transitions in the source would fail the gate as though the machine changed.

    Measured under: drop the `sorted()` calls and this reddens.
    """
    forward = _machine(f"{_T_AB},\n            {_T_BD},")
    reversed_ = _machine(f"{_T_BD},\n            {_T_AB},")
    assert forward != reversed_, "the reorder fixture did not apply"
    a, why_a = sm.parse(forward)
    b, why_b = sm.parse(reversed_)
    assert a is not None and b is not None, (why_a, why_b)
    assert sm.to_mermaid(a) == sm.to_mermaid(b)
    assert sm.to_mermaid(a).count("\n") > 5


def test_the_diagram_carries_events_effects_and_typed_rejections() -> None:
    """The three things the reviewed bay-session diagram carries. A diagram without
    the field effects is not auditable, and without the typed error a reader cannot
    see what the machine refuses.
    """
    d, _ = sm.parse(MACHINE)
    out = sm.to_mermaid(d)
    assert "A --> B: GO\\narmed=TRUE" in out
    assert "B --> NO: STOP\\nAlreadyRunning" in out
    assert "IllegalTransition" in out


def test_mermaid_ids_are_safe() -> None:
    """`(`, `+` and spaces are not valid in a mermaid node id, and a real group
    label ("Turn gate (ROTATION + on_turn)") produced an unparseable diagram until
    `_mermaid_id` existed.

    Measured under: use `label.replace(" ", "_")` and this reddens.
    """
    src = MACHINE.replace('"transitions": [',
                          '"groups": {"Turn gate (ROTATION + on_turn)": ["A", "B"]},\n'
                          '    "transitions": [')
    d, why = sm.parse(src)
    assert d is not None, why
    out = sm.to_mermaid(d)
    ids = [ln.split(" as ")[1].split(" {")[0] for ln in out.splitlines() if " as " in ln]
    assert ids and all(c.isalnum() or c == "_" for i in ids for c in i), ids


def test_rejections_target_the_declared_sink_not_a_synthetic_twin() -> None:
    """Found by generating the real machine: with a declared `REJECTED` terminal and
    a synthesised `Rejected` pseudo-state, one diagram carried two nodes meaning the
    same thing.

    Measured under: always synthesise `Rejected` and this reddens.
    """
    d, _ = sm.parse(MACHINE)
    out = sm.to_mermaid(d)
    assert "--> NO: STOP" in out
    assert "Rejected" not in out


# ------------------------------------------------------- the staleness gate --

def test_a_hand_edited_diagram_does_not_reproduce() -> None:
    """The gate. A model-drawn diagram is prose, and prose describing a world that
    does not exist has blocked this project three times. A generated one cannot
    drift, because regenerating it is checked.

    Byte comparison on purpose: a diagram that "mostly" matches is one someone
    edited.
    """
    d, _ = sm.parse(MACHINE)
    good = sm.to_mermaid(d)
    assert sm.diagram_is_current(MACHINE, good)
    assert not sm.diagram_is_current(MACHINE, good.replace("armed=TRUE", "armed=FALSE"))
    assert not sm.diagram_is_current(MACHINE, good + "    A --> DONE: SNEAK\n")
    assert not sm.diagram_is_current("no declaration here", good)


def test_changing_the_machine_invalidates_the_committed_diagram() -> None:
    """The property that makes it a gate rather than a formatter: edit the machine
    and the committed diagram stops reproducing.
    """
    d, _ = sm.parse(MACHINE)
    committed = sm.to_mermaid(d)
    changed = MACHINE.replace('{"from": "B", "event": "GO", "to": "DONE"}',
                              '{"from": "B", "event": "GO", "to": "A"}')
    assert not sm.diagram_is_current(changed, committed)


# ------------------------------------------------------------------- CLI -----

def test_cli_check_and_diagram(tmp_path, capsys) -> None:
    f = tmp_path / "m.py"
    f.write_text(MACHINE)
    assert sm.main(["check", str(f)]) == 0
    assert "PASS" in capsys.readouterr().out

    f.write_text(_without("default_rejection"))
    assert sm.main(["check", str(f)]) == 1
    assert "FAIL" in capsys.readouterr().out

    f.write_text(MACHINE)
    assert sm.main(["diagram", str(f)]) == 0
    assert "stateDiagram-v2" in capsys.readouterr().out

    assert sm.main([]) == 2
    assert sm.main(["nonsense", "x"]) == 2
