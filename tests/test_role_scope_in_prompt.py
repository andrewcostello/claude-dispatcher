"""The author must be told the rule they are judged by.

Measured 2026-08-18 on W2-3-2: the role gate blocked a SEALS task for a
COMMENT-ONLY edit to `src/claude_dispatcher/mutation_ledger.py` — AST-identical
before and after — and the write rule appeared NOWHERE the author could see it.
Not in the implementer prompt (`build_prompt` took no role at all) and not in
the task's 918-character brief. The rules were compiled in, enforced after the
fact, and never stated.

Second instance of the shape: `FLOOR_GLOBS` records a seal author who had to
write `src/` for a typed constant the scaffold never landed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from claude_dispatcher import (
    orchestrator as orch,
    role_protocol as rp,
    spawn as spawn_mod,
)


def _rule(role: rp.Role) -> rp.RoleRule:
    return next(r for r in rp.DEFAULT_ROLE_RULES if r.role is role)


def test_an_allow_only_role_is_told_what_it_MAY_write() -> None:
    """Measured under: return "" for ALLOW_ONLY and this reddens."""
    text = rp.describe_scope(_rule(rp.Role.SEALS))
    assert "SEALS" in text
    assert "may write ONLY" in text.lower() or "write ONLY" in text
    assert "docs/**" in text


def test_a_deny_role_is_told_what_it_MAY_NOT_write() -> None:
    text = rp.describe_scope(_rule(rp.Role.SCAFFOLD))
    assert "SCAFFOLD" in text
    assert "EXCEPT" in text
    assert "tests" in text


def test_the_scope_says_a_COMMENT_is_not_exempt() -> None:
    """The exact defect measured: the author edited only a comment and believed
    that harmless. The gate compares PATHS, not behaviour, so the text has to
    say so — otherwise the next author reasons the same way.

    Measured under: drop the comment/docstring clause and this reddens.
    """
    for role in (rp.Role.SEALS, rp.Role.SCAFFOLD):
        text = rp.describe_scope(_rule(role)).lower()
        assert "comment" in text and "docstring" in text, role
    # The words alone are a weak assertion — an earlier version of this row
    # passed a mutation that deleted the REASON and kept the nouns. The clause
    # that changes an author's reasoning is the one saying the gate compares
    # paths rather than behaviour, so pin that.
    seals = rp.describe_scope(_rule(rp.Role.SEALS)).lower()
    assert "not exempt" in seals
    assert "paths, not behaviour" in seals


def test_the_scope_names_the_channel_for_disagreeing() -> None:
    """The wrong half of the lesson is "touch nothing". A role that believes a
    file outside its scope is wrong is the most valuable signal this protocol
    collects, and it must be told where that goes.

    Measured under: remove the Deviation guidance and this reddens.
    """
    text = rp.describe_scope(_rule(rp.Role.SEALS))
    assert "Deviation" in text
    assert "blast_radius" in text


def test_no_rule_renders_nothing() -> None:
    """A role-less task's prompt is unchanged — this must add a section, never
    replace or disturb the existing brief.
    """
    assert rp.describe_scope(None) == ""


def test_a_long_glob_list_is_summarised_not_dumped() -> None:
    """A wall of patterns is not guidance. The gate names the exact glob it
    matched when a violation happens; the prompt gives the shape.
    """
    many = rp.RoleRule(role=rp.Role.BODIES, kind=rp.RuleKind.DENY_GLOBS,
                       globs=tuple(f"**/p{i}/**" for i in range(20)),
                       rationale="a synthetic rule with more globs than fit")
    text = rp.describe_scope(many)
    assert "and 12 more" in text
    assert text.count("`**/p") == rp.SCOPE_GLOBS_SHOWN


# --------------------------------------------------------------------------
# It has to reach the prompt
# --------------------------------------------------------------------------

def test_the_scope_is_appended_to_the_implementer_prompt(tmp_path: Path) -> None:
    """Measured under: drop `role_scope` from `build_prompt` and this reddens."""
    kw = dict(task_key="T-1", task_summary="s", task_type="Task", task_labels=[],
              task_description="d", branch="b", summary_path=tmp_path / "s.md",
              run_id="r", max_iterations=4, financial_paths="**",
              skip_design=False, skip_security_linter=False, reviewer_count=3)
    without = spawn_mod.build_prompt(**kw)
    with_scope = spawn_mod.build_prompt(**kw, role_scope="\n\nSCOPE-MARKER\n")
    assert "SCOPE-MARKER" in with_scope
    assert "SCOPE-MARKER" not in without
    assert with_scope.startswith(without), (
        "the scope must be ADDED to the brief, not replace part of it")


def test_a_seals_task_prompt_carries_its_real_rule(tmp_path: Path) -> None:
    """End to end through the orchestrator's resolver, using the same
    `effective_rule` the gate judges by — so the prompt and the verdict cannot
    drift into two different rules.

    Measured under: resolve the scope from a hard-coded table instead of
    `effective_rule` and this stays green while the gate diverges; measured
    under dropping the `_role_scope_for` call, it reddens.
    """
    spec = rp.TaskRoleSpec(task_key="W-2", role=rp.Role.SEALS)
    snap = SimpleNamespace(key="W-2", role_specs=[spec])
    text = orch._role_scope_for(snap, tmp_path / "log")
    assert text is not None
    assert "SEALS" in text and "Deviation" in text


def test_a_role_less_task_gets_no_section(tmp_path: Path) -> None:
    assert orch._role_scope_for(
        SimpleNamespace(key="T", role_specs=[]), tmp_path / "log") is None
    assert orch._role_scope_for(
        SimpleNamespace(key="T", role_specs=None), tmp_path / "log") is None


def test_a_broken_policy_does_not_stop_the_spawn(tmp_path: Path, monkeypatch) -> None:
    """A prompt is not the place to discover a malformed policy. A task that
    cannot be told its scope is still better dispatched — the GATE still
    refuses it — than not dispatched at all.

    Measured under: let the exception propagate and this reddens.
    """
    def _boom(*a, **k):
        raise RuntimeError("policy is malformed")

    monkeypatch.setattr(rp, "effective_rule", _boom)
    spec = rp.TaskRoleSpec(task_key="W-2", role=rp.Role.SEALS)
    snap = SimpleNamespace(key="W-2", role_specs=[spec])
    assert orch._role_scope_for(snap, tmp_path / "log") is None


def test_the_prompt_builder_is_actually_given_the_scope() -> None:
    """AST, not a substring: the resolver is worthless if the call site drops
    it. This is the vacuity class the 2026-08-18 panel blocked three tasks for.

    Measured under: remove `role_scope=` from the `build_prompt` call and this
    reddens.
    """
    import ast

    tree = ast.parse(Path(orch.__file__).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "build_prompt"]
    assert calls, "build_prompt is never called"
    implementer = [c for c in calls
                   if any(k.arg == "role_scope" for k in c.keywords)]
    assert implementer, "no build_prompt call passes role_scope"
