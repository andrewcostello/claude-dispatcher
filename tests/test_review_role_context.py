"""Seals for the role block handed to the review panel (D-62).

The panel reviews a DIFF and carried nothing about who wrote it, so "this needs
tests" was emitted identically whether the author may write tests or is
forbidden from doing so. Four recorded occurrences pushed a role into a breach it
was then blocked for — the fourth being W2-3-1, a SCAFFOLD told its module had no
tests when SCAFFOLD denies `tests/**`.
"""

from __future__ import annotations

import pytest

from pathlib import Path

from claude_dispatcher import cross_family_reviewer as cfr, role_protocol as rp


def _spec(role: rp.Role, key: str = "T-1") -> rp.TaskRoleSpec:
    kw = {"task_key": key, "role": role}
    if role is rp.Role.ADJUDICATE:
        kw["disputed_paths"] = ("tests/test_x.py",)
    return rp.TaskRoleSpec(**kw)


def test_a_scaffolds_block_names_the_test_paths_it_may_not_write() -> None:
    """The exact fact the panel lacked when it demanded tests from W2-3-1.

    Measured under: return "" unconditionally from `review_role_context` and this
    reddens.
    """
    block = rp.review_role_context([_spec(rp.Role.SCAFFOLD)])
    assert "scaffold" in block
    assert "MAY NOT write" in block
    assert "**/tests/**" in block
    assert "Do NOT report missing tests" in block


def test_an_allow_only_role_is_described_as_allow_only() -> None:
    """SEALS and ADJUDICATE are ALLOW_ONLY; describing them as a deny list would
    tell the panel the opposite of the truth.

    Measured under: collapse the RuleKind branches to one and this reddens.
    """
    seals = rp.review_role_context([_spec(rp.Role.SEALS)])
    assert "may write ONLY" in seals
    adj = rp.review_role_context([_spec(rp.Role.ADJUDICATE)])
    assert "may write ONLY" in adj
    assert "tests/test_x.py" in adj


def test_the_rendered_prompt_carries_the_floor_but_the_role_block_does_not(
) -> None:
    """A finding asking for a floored edit is unactionable by EVERY role, so the
    panel needs the floor as well as the per-role table (the two tables D-55 found
    conflated in a brief). It is appended by the reviewer module, not by
    `review_role_context`.

    Why the split: `test_floor_closure` holds that every module-level function in
    `role_protocol` naming FLOOR_GLOBS is a floor DECISION reachable from the
    gate's roots. A prose renderer naming it makes that premise false, so the
    floor is rendered at prompt time instead. Measured under: move the paragraph
    back into `review_role_context` and `test_floor_closure` reddens naming it.

    Rendered, never written out: the list changed 17 -> 19 when the known-red
    register landed, and a stale copy would tell the panel a path is writable
    when no role may touch it.
    """
    block = rp.review_role_context([_spec(rp.Role.BODIES)])
    assert "writable by NOBODY" not in block

    kw = dict(ticket_key="T", ticket_summary="s", summary_md="m", diff="d",
              branch="b", base_branch="base")
    rendered = cfr.build_review_prompt(family="claude", role_context=block, **kw)
    assert "writable by NOBODY" in rendered
    assert "role_protocol.py" in rendered
    for glob in rp.FLOOR_GLOBS:
        assert glob in rendered, f"floor glob missing from the prompt: {glob}"


def test_the_block_warns_about_the_over_build_rather_than_the_stubs() -> None:
    """The panel penalised W2-3-1 for HAVING stubs. Leaving them is the scaffold's
    deliverable; filling them is the defect.

    Measured under: drop the closing paragraph and this reddens.
    """
    block = rp.review_role_context([_spec(rp.Role.SCAFFOLD)])
    assert "unimplemented stubs" in block
    assert "destroyed the point of sealing first" in block


def test_a_role_less_task_gets_an_empty_block_not_an_invented_one() -> None:
    """LEGACY rows are pre-protocol and must behave exactly as before. Empty here,
    so the CALLER renders the fallback — one place decides that wording.

    Measured under: return a block for LEGACY and this reddens.
    """
    assert rp.review_role_context([]) == ""
    assert rp.review_role_context([_spec(rp.Role.LEGACY)]) == ""


def test_the_prompt_template_actually_carries_the_placeholder() -> None:
    """A rendered block nothing interpolates is a silent no-op — the D-72 shape
    (the right thing written where nothing reads it).

    Measured under: remove `{role_context}` from `_shared.md` and this reddens.
    """
    shared = (Path(cfr.__file__).parent / "reviewer_prompts" / "_shared.md").read_text()
    assert "{role_context}" in shared


def test_build_review_prompt_interpolates_it_and_falls_back_when_empty() -> None:
    """Every seat's prompt is the shared block, so one interpolation covers all.

    Measured under: drop `role_context=` from the `.format()` call and this
    reddens with a KeyError, which is the correct loud failure.
    """
    kw = dict(
        ticket_key="T-1", ticket_summary="s", summary_md="m", diff="d",
        branch="b", base_branch="base",
    )
    block = rp.review_role_context([_spec(rp.Role.SCAFFOLD)])
    rendered = cfr.build_review_prompt(family="claude", role_context=block, **kw)
    assert "MAY NOT write" in rendered

    bare = cfr.build_review_prompt(family="claude", **kw)
    assert "no role protocol on this task" in bare


def test_run_panel_accepts_the_kwarg_so_the_orchestrator_can_pass_it() -> None:
    """Measured under: remove the parameter from `run_panel` and this reddens —
    the orchestrator computes the block and would fail to hand it over.
    """
    import inspect
    assert "role_context" in inspect.signature(cfr.run_panel).parameters


def test_the_orchestrator_forwards_it_at_every_run_panel_call_site() -> None:
    """Two staged seats plus the single-stage path — a call site that forgot it
    would silently review role-blind again, which is the defect returning.

    Measured under: delete any one forward and this reddens.
    """
    src = Path(
        __import__("claude_dispatcher.orchestrator", fromlist=["x"]).__file__
    ).read_text()
    assert src.count("role_context=role_context,") == 3
    assert src.count("risk_context=risk_context,") == 3


@pytest.fixture(autouse=True)
def _journal_less_test_process():
    from claude_dispatcher import prompt_provenance as pp
    pp.declare_unanchored("tests/test_review_role_context.py", "test process: no run journal")
