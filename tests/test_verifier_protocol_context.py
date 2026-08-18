"""Seals for the build-protocol block handed to the verifier (B4).

Check #1 of `verifier.md` reports a `NotImplementedError` body as a gap. For a
SCAFFOLD that body IS the deliverable, so the check is inverted unless the
verifier knows the role — measured 2026-08-17, its prompt had no role placeholder
at all.

A two-arm probe that day proved the verifier discriminates: a planted stub gave
INCOMPLETE with four precise gaps, a real implementation gave VERIFIED. So this
is not about making it fire — it is about making check #1 answerable from a FACT
(`declares.holes`) rather than from whatever the brief happened to say in prose.
"""

from __future__ import annotations

from pathlib import Path

from claude_dispatcher import verifier as v


def test_a_scaffolds_stubs_are_named_as_the_deliverable() -> None:
    """Measured under: drop the scaffold branch and this reddens — the verifier
    would apply check #1 unchanged and a correct scaffold reads as incomplete.
    """
    block = v.protocol_context("scaffold")
    assert "role is **scaffold**" in block
    assert "NOT a gap" in block
    # And the inverse is still reportable.
    assert "destroyed the point of sealing first" in block


def test_a_bodies_task_is_told_an_unfilled_hole_IS_the_gap() -> None:
    block = v.protocol_context("bodies", ("src/m.py::decide",))
    assert "still unimplemented is a gap" in block


def test_seals_are_told_red_rows_are_the_deliverable() -> None:
    """A SEALS task commits tests that must FAIL. Judged by check #1 unchanged, a
    correct seals task looks like an unfinished implementation.
    """
    block = v.protocol_context("seals")
    assert "committed deliberately RED" in block
    assert "may not write the implementation" in block


def test_declared_holes_are_listed_and_bound_the_exemption() -> None:
    """The exemption must be CLOSED: a stub anywhere else is still a gap, and a
    declared hole the diff never created is one too — otherwise the block reads
    as "stubs are fine here" and check #1 is neutered.

    Measured under: drop the closing sentence and this reddens.
    """
    block = v.protocol_context("scaffold", ("a.py::x", "b.py::C.y"))
    assert "a.py::x" in block and "b.py::C.y" in block
    assert "ANYWHERE ELSE is still a gap" in block
    assert "never created" in block


def test_no_declarations_says_so_rather_than_implying_stubs_are_fine() -> None:
    block = v.protocol_context("scaffold")
    assert "declared no holes" in block


def test_a_role_less_task_gets_an_empty_block() -> None:
    """Pre-protocol rows must behave exactly as before; the CALLER renders the
    fallback so one place owns that wording.
    """
    assert v.protocol_context(None) == ""
    assert v.protocol_context("") == ""


def test_the_prompt_template_carries_the_placeholder() -> None:
    """A rendered block nothing interpolates is a silent no-op.

    Measured under: remove `{protocol}` from verifier.md and this reddens.
    """
    md = (Path(v.__file__).parent / "verifier_prompts" / "verifier.md").read_text()
    assert "{protocol}" in md
    # And check #1 must defer to it, or the two contradict each other.
    assert "marks the stub as expected" in md


def test_build_verifier_prompt_interpolates_it_with_a_fallback() -> None:
    task = {"key": "T-1", "summary": "s", "type": "Task", "labels": [],
            "description": "d"}
    rendered = v.build_verifier_prompt(
        task, "diff", "summary", protocol=v.protocol_context("scaffold"),
    )
    assert "role is **scaffold**" in rendered

    bare = v.build_verifier_prompt(task, "diff", "summary")
    assert "no role protocol on this task" in bare


def test_run_verifier_and_the_orchestrator_agree_on_the_kwarg() -> None:
    """Measured under: rename either side and this reddens — a mismatch would be
    a silent no-op, the shape that left the panel role-blind for four rounds.
    """
    import inspect
    assert "protocol" in inspect.signature(v.run_verifier).parameters
    src = Path(
        __import__("claude_dispatcher.orchestrator", fromlist=["x"]).__file__
    ).read_text()
    assert "protocol=protocol_block," in src
    assert "verifier_mod.protocol_context(" in src
