"""Seals for the TypeScript reader.

Two properties carry the weight, and the second is a security property:

  * the TS reader agrees with the Python and Go readers on one logical machine —
    the rules live once, in `state_machine.check_parsed`, so three readers cannot
    become three policies;
  * the parser is loaded by ABSOLUTE PATH. `require('typescript')` walks up for
    `node_modules`, and on a judged checkout the only TypeScript that walk finds
    is INSIDE THE REPOSITORY UNDER JUDGEMENT — a branch could then choose the
    program that reads its own state machine.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import state_machine as sm, ts_state_machine as tsm

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None
    or not (tsm.rp.ts_parser_home() / "typescript.js").exists(),
    reason="no node, or the vendored parser is not provisioned",
)

DECL_OBJECT = '''
export const STATE_MACHINE = {
  name: "m",
  state_enum: "BetState",
  event_enum: "BetEvent",
  initial: "Accepted",
  terminal: ["Settled"],
  default_rejection: "IllegalTransition",
  transitions: [
    { from: "Accepted", event: "go", to: "Settled", effects: ["armed=TRUE"] },
  ],
} as const;
'''

PRELUDE = textwrap.dedent('''
    export enum BetState {
      Accepted = "accepted",
      Settled = "settled",
    }

    export type BetEvent = "go" | "stop";
    ''')


def _ts(tmp_path: Path, decl: str = DECL_OBJECT, prelude: str = PRELUDE) -> Path:
    p = tmp_path / "bay.ts"
    p.write_text(prelude + decl)
    return p


def test_an_object_literal_declaration_is_read(tmp_path: Path) -> None:
    """The idiomatic TS spelling. Imposing the Go string form would make the
    checker refuse normal code rather than check it.
    """
    rep = tsm.check(_ts(tmp_path))
    assert rep.ok, rep.detail()
    assert rep.declaration.name == "m"


def test_a_json_string_declaration_is_also_read(tmp_path: Path) -> None:
    """The Go spelling, so one machine can move between languages verbatim."""
    decl = ('export const STATE_MACHINE = `{"name": "m", "state_enum": "BetState",'
            ' "event_enum": "BetEvent", "initial": "Accepted",'
            ' "terminal": ["Settled"], "default_rejection": "X",'
            ' "transitions": [{"from": "Accepted", "event": "go",'
            ' "to": "Settled"}]}`;\n')
    rep = tsm.check(_ts(tmp_path, decl))
    assert rep.ok, rep.detail()


def test_enum_member_NAMES_and_union_VALUES_are_both_found(tmp_path: Path) -> None:
    """TypeScript has three enum-ish shapes. `enum` contributes member NAMES,
    a string-literal union contributes its VALUES, and a declaration references
    whichever its own code uses.

    Measured under: drop the TypeAliasDeclaration arm and the union events read as
    unknown names, so this reddens.
    """
    _decl, enums, why = tsm.read(_ts(tmp_path))
    assert why == "", why
    assert enums["BetState"] == ("Accepted", "Settled")
    assert enums["BetEvent"] == ("go", "stop")


def test_a_const_enum_is_found(tmp_path: Path) -> None:
    prelude = PRELUDE.replace("export enum BetState", "export const enum BetState")
    _decl, enums, _why = tsm.read(_ts(tmp_path, prelude=prelude))
    assert enums["BetState"] == ("Accepted", "Settled")


def test_a_non_literal_declaration_is_refused_not_evaluated(tmp_path: Path) -> None:
    """Evaluating a declaration means running the branch's code. Refusing is the
    only safe answer, and it must be MALFORMED rather than absent.
    """
    rep = tsm.check(_ts(tmp_path, "export const STATE_MACHINE = buildIt();\n"))
    assert not rep.ok
    assert rep.faults[0][0] is sm.Fault.MALFORMED, rep.faults
    # Assert the REASON, not just the class. Mutation testing found this row
    # passing for the wrong reason: a mutant that "evaluated" the call to an empty
    # object also lands on MALFORMED (via missing keys), so the fault class alone
    # cannot tell "refused as non-literal" from "accepted as empty".
    assert "not a literal" in rep.detail(), rep.detail()


def test_a_missing_declaration_is_named_absent(tmp_path: Path) -> None:
    rep = tsm.check(_ts(tmp_path, "export const other = 1;\n"))
    assert not rep.ok and rep.faults[0][0] is sm.Fault.NO_DECLARATION


def test_totality_is_enforced_through_the_ts_path(tmp_path: Path) -> None:
    rep = tsm.check(_ts(tmp_path, DECL_OBJECT.replace(
        '  default_rejection: "IllegalTransition",\n', "")))
    assert not rep.ok
    assert any(f is sm.Fault.NON_EXHAUSTIVE for f, _ in rep.faults)


def test_the_parser_is_the_vendored_one_by_absolute_path() -> None:
    """The security property, and the only one of its three mechanisms that is
    checkable from outside the helper.

    The absolute-path require and the NODE_* scrub are both unfalsifiable here: on
    a machine with an ambient TypeScript a mutant reaching for it would resolve,
    run, and go green with the defect present. So the helper reports which file
    Node actually loaded, read from the loader's own record.

    Measured under: change `require(PARSER)` to `require('typescript')` and this
    reddens — verified on this machine, where no ambient copy resolves from the
    parser's cwd, so the helper fails loudly.

    WHAT THIS ROW CANNOT SEAL, stated rather than implied: that `probe` reads the
    loader's own record instead of recomputing the specifier. A mutant returning
    PARSER directly reports the same path, so no assertion here separates them —
    confirmed by mutation testing (no row fired). It is the same limitation
    `ts_signature_fingerprint`'s own docstring records for the same mechanism:
    separating a lie from the truth needs a machine where an ambient TypeScript
    resolves, and this is not one. Kept as a checkable-from-outside signal, not
    claimed as a proof.
    """
    loaded = tsm.probe()
    assert loaded is not None
    assert Path(loaded) == (tsm.rp.ts_parser_home() / "typescript.js").resolve() \
        or Path(loaded) == tsm.rp.ts_parser_home() / "typescript.js", loaded
    assert "node_modules" not in loaded, (
        "the parser came from a node_modules — on a judged checkout that is the "
        "branch's own copy deciding what its state machine says"
    )


def test_the_node_environment_contract_is_reused_not_restated() -> None:
    """Every NODE_* and NPM_CONFIG_* stripped, PATH and HOME inherited. Two copies
    of a security contract is the defect main.cjs exists to avoid, so this asserts
    the shared builder is what runs.
    """
    env = tsm.rp._node_toolchain_environment()
    assert not [k for k in env if k.startswith(("NODE_", "NPM_CONFIG_"))]
    assert "PATH" in env and "HOME" in env


def test_the_rules_are_not_reimplemented_in_javascript() -> None:
    """main.cjs reads and reports; `check_parsed` decides.

    Measured under: add a totality check to main.cjs and this reddens naming it.
    """
    src = (tsm.helper_dir() / "main.cjs").read_text().lower()
    for word in ("exhaustive", "default_rejection", "terminal"):
        assert word not in src, f"main.cjs mentions {word!r} — a rule in a reader"


def test_all_three_readers_agree_on_one_logical_machine(tmp_path: Path) -> None:
    """The cross-language property, over the whole set. If any reader can disagree
    there are as many policies as readers.
    """
    from claude_dispatcher import go_state_machine as gsm

    if shutil.which("go") is None:
        pytest.skip("no Go toolchain")

    ts_rep = tsm.check(_ts(tmp_path))

    go_file = tmp_path / "bay.go"
    go_file.write_text(textwrap.dedent('''
        package bay

        type BetState string

        const (
        \tAccepted BetState = "accepted"
        \tSettled  BetState = "settled"
        )

        type BetEvent int

        const (
        \tgo_ BetEvent = iota
        )
        ''') + 'const StateMachine = `{"name": "m", "state_enum": "BetState",'
             ' "event_enum": "BetEvent", "initial": "Accepted",'
             ' "terminal": ["Settled"], "default_rejection": "X",'
             ' "transitions": [{"from": "Accepted", "event": "go_",'
             ' "to": "Settled", "effects": ["armed=TRUE"]}]}`\n')
    go_rep = gsm.check(go_file)

    py_file = tmp_path / "bay.py"
    py_file.write_text(textwrap.dedent('''
        from enum import Enum


        class BetState(Enum):
            Accepted = "accepted"
            Settled = "settled"


        class BetEvent(Enum):
            go = "go"
            stop = "stop"


        STATE_MACHINE = {
            "name": "m",
            "state_enum": "BetState",
            "event_enum": "BetEvent",
            "initial": "Accepted",
            "terminal": ["Settled"],
            "default_rejection": "IllegalTransition",
            "transitions": [
                {"from": "Accepted", "event": "go", "to": "Settled",
                 "effects": ["armed=TRUE"]},
            ],
        }
        '''))
    py_rep = sm.check(py_file.read_text())

    assert py_rep.ok and go_rep.ok and ts_rep.ok, (
        py_rep.detail(), go_rep.detail(), ts_rep.detail())
    # Python and TS use the same member names, so their diagrams must be identical.
    assert sm.to_mermaid(py_rep.declaration) == sm.to_mermaid(ts_rep.declaration)


def test_a_broken_helper_is_a_named_fault_not_a_clean_read(tmp_path: Path,
                                                          monkeypatch) -> None:
    """A TypeScript repo we cannot read must not look like one that declared
    nothing: the first needs a machine fixed, the second a scaffold.
    """
    monkeypatch.setattr(tsm, "_entrypoint",
                        lambda: (_ for _ in ()).throw(
                            tsm.TsHelperUnavailable("gone")))
    with pytest.raises(tsm.TsHelperUnavailable):
        tsm.read(_ts(tmp_path))
    assert tsm.main(["check", str(_ts(tmp_path))]) == 3
