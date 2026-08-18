"""Seals for a re-round seeing its OWN blocking findings.

D-56 gave a task the findings recorded against the tasks it names in
`blockedBy`. A task never names itself, so a task sent back for a second round
inherited its predecessor's findings and NOT the ones that blocked it — the one
thing it most needs. Measured on the 2026-08-18 wave-2 re-queue: all three seals
tasks re-dispatched carrying only their scaffold's findings.
"""

from __future__ import annotations

import json
from pathlib import Path

from claude_dispatcher import findings_store as fs


def _write(runs_dir: Path, key: str, rows: list[dict]) -> None:
    d = runs_dir / "findings"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps({"task_key": key, "findings": rows}))


def _row(sev: str, desc: str, family: str = "codex", location: str = "a.py:1") -> dict:
    return {"family": family, "severity": sev, "location": location,
            "description": desc}


def test_a_reround_is_told_why_it_was_blocked(tmp_path: Path) -> None:
    """Measured under: drop `render_own_for_prompt`'s call and this reddens."""
    _write(tmp_path, "T-1", [_row("HIGH", "the seal greps for a string")])
    out = fs.render_own_for_prompt(tmp_path, "T-1")
    assert "BLOCKED" in out
    assert "the seal greps for a string" in out
    assert "a.py:1" in out and "HIGH" in out


def test_the_framing_is_not_the_inherited_framing(tmp_path: Path) -> None:
    """The two blocks say opposite things and must not be interchanged: a
    dependency's findings are explicitly "NOT accusations against you", these
    are. Swapping the renderers would tell an author to treat the reason it was
    blocked as someone else's problem.
    """
    _write(tmp_path, "T-1", [_row("HIGH", "x")])
    own = fs.render_own_for_prompt(tmp_path, "T-1")
    inherited = fs.render_for_prompt(tmp_path, ["T-1"])
    assert "NOT accusations against you" in inherited
    assert "NOT accusations against you" not in own
    assert "YOUR OWN work" in own


def test_blocking_findings_survive_truncation(tmp_path: Path) -> None:
    """A task can collect more findings than the bound: wave-2's W2-2-2 recorded
    14. If the block's cause is the row that gets dropped, the re-round is told
    everything except the reason.

    Measured under: remove the severity sort and this reddens — the HIGH sits
    last in the stored order.
    """
    rows = [_row("LOW", f"noise {i}") for i in range(fs.MAX_PER_DEP + 3)]
    rows.append(_row("HIGH", "THE REASON", family="claude"))
    _write(tmp_path, "T-1", rows)
    out = fs.render_own_for_prompt(tmp_path, "T-1")
    assert "THE REASON" in out
    assert "and 4 more" in out


def test_a_first_round_reads_exactly_as_before(tmp_path: Path) -> None:
    """No findings means no block, not a "nothing recorded" notice."""
    assert fs.render_own_for_prompt(tmp_path, "T-1") == ""


def test_the_call_site_feeds_the_description_and_not_a_dead_local() -> None:
    """The renderer is worthless unless its result reaches the prompt.

    Deliberately NOT the substring search `test_findings_store.py:176` uses for
    the D-56 call — a comment, an import or an unused local satisfies that, and
    it is the same vacuity the wave-2 panel raised against W2-1-2. This walks
    the AST: the call must be ASSIGNED, and the name it binds must appear in a
    statement that assigns to `desc`.

    Measured under: delete the call, or assign it and never fold it into `desc`,
    and this reddens.
    """
    import ast
    from claude_dispatcher import orchestrator

    tree = ast.parse(Path(orchestrator.__file__).read_text(encoding="utf-8"))

    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        fn = node.value.func
        if isinstance(fn, ast.Attribute) and fn.attr == "render_own_for_prompt":
            bound.update(t.id for t in node.targets if isinstance(t, ast.Name))
    assert bound, "render_own_for_prompt is never called and assigned"

    feeds_desc = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "desc" for t in node.targets):
            continue
        used = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        if used & bound:
            feeds_desc = True
    assert feeds_desc, (
        f"{bound} is bound but never folded into `desc` — the findings are "
        "computed and thrown away"
    )
