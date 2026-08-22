"""Seals for the Go reader.

bay-session is a Go repository, so Go is the real target and Python was only the
proof of the format. Two properties carry the weight here:

  * the Go reader and the Python reader give the SAME verdict for the same logical
    machine — the rules live once, in `state_machine.check_parsed`, so a
    per-language reader cannot drift into a laxer answer;
  * a broken toolchain is a NAMED fault, never "no declaration". Reading a Go repo
    with a broken helper must not look like a Go repo that declared nothing,
    because those route to different decisions.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import go_state_machine as gsm, state_machine as sm

pytestmark = pytest.mark.skipif(
    shutil.which("go") is None, reason="no Go toolchain on this machine"
)

DECL = '''{
  "name": "m",
  "state_enum": "BetState",
  "event_enum": "BetEvent",
  "initial": "BetStateAccepted",
  "terminal": ["BetStateSettled"],
  "default_rejection": "IllegalTransition",
  "transitions": [
    {"from": "BetStateAccepted", "event": "BetEventGo", "to": "BetStateSettled",
     "effects": ["armed=TRUE"]}
  ]
}'''


def _go(tmp_path: Path, decl: str = DECL, *, body: str = "") -> Path:
    src = textwrap.dedent('''
        package baysession

        type BetState string

        const (
        \tBetStateAccepted BetState = "accepted"
        \tBetStateSettled  BetState = "settled"
        )

        type BetEvent int

        const (
        \tBetEventGo BetEvent = iota
        \tBetEventStop
        )
        ''') + body + f"\nconst StateMachine = `{decl}`\n"
    p = tmp_path / "bay.go"
    p.write_text(src)
    return p


def test_a_declared_go_machine_passes(tmp_path: Path) -> None:
    rep = gsm.check(_go(tmp_path))
    assert rep.ok, rep.detail()
    assert rep.declaration is not None and rep.declaration.name == "m"


def test_the_iota_spelling_finds_every_member(tmp_path: Path) -> None:
    """Go states the type on the FIRST spec of an iota block and the rest inherit
    it. A reader that does not carry the type forward finds one member of a
    nine-member enum and then reports the other eight as unknown names.

    Measured under: drop `lastType` carry-forward in collectEnums and this reddens.
    """
    decl, enums, why = gsm.read(_go(tmp_path))
    assert why == "", why
    assert enums["BetEvent"] == ("BetEventGo", "BetEventStop"), enums
    assert len(enums["BetState"]) == 2


def test_the_blank_identifier_is_not_a_member(tmp_path: Path) -> None:
    """`_ BetEvent = iota` is the skipped-zero idiom, not a state.

    Measured under: stop skipping `_` and this reddens — the enum gains a phantom
    member and exhaustiveness then demands pairs for it.
    """
    body = "const (\n\t_ BetEvent = iota\n\tBetEventLater\n)\n"
    _decl, enums, _why = gsm.read(_go(tmp_path, body=body))
    assert "_" not in enums.get("BetEvent", ())


def test_a_string_state_is_refused_because_it_is_not_an_enum(tmp_path: Path) -> None:
    """The enum requirement, enforced through the Go reader too."""
    rep = gsm.check(_go(tmp_path, DECL.replace('"BetState"', '"NotAType"')))
    assert not rep.ok
    assert any(f is sm.Fault.STATE_NOT_ENUM for f, _ in rep.faults)


def test_a_missing_declaration_is_named_as_absent(tmp_path: Path) -> None:
    p = tmp_path / "plain.go"
    p.write_text("package x\n\ntype T string\n")
    rep = gsm.check(p)
    assert not rep.ok and rep.faults[0][0] is sm.Fault.NO_DECLARATION


def test_a_present_but_broken_declaration_is_MALFORMED_not_absent(
    tmp_path: Path,
) -> None:
    """Different faults, deliberately: "nothing declared" and "declared badly"
    route to different decisions, and collapsing them would let a typo read as an
    opt-out.

    Measured under: report every unreadable declaration as absent and this reddens.
    """
    rep = gsm.check(_go(tmp_path, '{"name": "m", "not_valid_json'))
    assert not rep.ok
    assert rep.faults[0][0] is sm.Fault.MALFORMED, rep.faults


def test_totality_is_enforced_through_the_go_path_too(tmp_path: Path) -> None:
    rep = gsm.check(_go(tmp_path, DECL.replace(
        '  "default_rejection": "IllegalTransition",\n', "")))
    assert not rep.ok
    assert any(f is sm.Fault.NON_EXHAUSTIVE for f, _ in rep.faults)


def test_the_go_and_python_readers_agree_on_the_same_machine(tmp_path: Path) -> None:
    """The cross-language property. The rules live in `check_parsed`; only the
    reader is per-language. If Go and Python can disagree, there are two policies.

    Measured under: reimplement any rule inside the Go helper and this reddens.
    """
    go_rep = gsm.check(_go(tmp_path))

    py = tmp_path / "m.py"
    py.write_text(textwrap.dedent('''
        from enum import Enum


        class BetState(Enum):
            BetStateAccepted = "accepted"
            BetStateSettled = "settled"


        class BetEvent(Enum):
            BetEventGo = "go"
            BetEventStop = "stop"


        STATE_MACHINE = ''') + DECL.replace("null", "None") + "\n")
    py_rep = sm.check(py.read_text())

    assert py_rep.ok == go_rep.ok, (py_rep.detail(), go_rep.detail())
    assert py_rep.defaulted_pairs == go_rep.defaulted_pairs
    assert sm.to_mermaid(py_rep.declaration) == sm.to_mermaid(go_rep.declaration)


def test_the_diagram_generates_from_a_go_declaration(tmp_path: Path) -> None:
    decl, _enums, _why = gsm.read(_go(tmp_path))
    out = sm.to_mermaid(decl)
    assert "BetStateAccepted --> BetStateSettled: BetEventGo\\narmed=TRUE" in out


def test_a_broken_toolchain_is_a_named_fault_not_a_clean_read(
    tmp_path: Path, monkeypatch,
) -> None:
    """bay-session is a Go repo. "We could not read it" must never be reported as
    "it declared nothing" — the first needs a machine fixed, the second needs a
    scaffold fixed.

    Measured under: return an empty result instead of raising and this reddens.
    """
    monkeypatch.setattr(gsm, "_PREPARED", (None, gsm.GoHelperUnavailable("no go")))
    with pytest.raises(gsm.GoHelperUnavailable):
        gsm.read(_go(tmp_path))
    assert gsm.main(["check", str(_go(tmp_path))]) == 3


def test_the_helper_is_a_module_of_its_own(tmp_path: Path) -> None:
    """It must not inherit the judged repository's go.mod, or the helper's
    behaviour depends on the tree it is judging — the same argument that governs
    the other two Go helpers, and it is why this ships its own module.
    """
    mod = (gsm.helper_dir() / "go.mod").read_text()
    assert "module claude-dispatcher/go-state-machine" in mod
    assert "require" not in mod, "the helper must stay stdlib-only"


def test_the_rules_are_not_reimplemented_in_go() -> None:
    """The Go source must not carry the vocabulary of the decisions. It reads and
    reports; `check_parsed` decides.

    Measured under: add a totality or exhaustiveness check to main.go and this
    reddens naming it.
    """
    go_src = (gsm.helper_dir() / "main.go").read_text().lower()
    for word in ("exhaustive", "default_rejection", "terminal", "non_exhaustive"):
        assert word not in go_src.replace("# ", ""), (
            f"main.go mentions {word!r} — a rule leaking into the reader"
        )
