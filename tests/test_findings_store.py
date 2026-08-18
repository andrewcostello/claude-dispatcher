"""Seals for inherited panel findings (D-56).

Measured on DF-1-1: nine findings, three families independently naming ONE
defect, auto-integrated — and DF-1-2, the SEALS task for that exact constructor,
never saw them. Findings were recorded per task; prompts are built per row from
`snap.description` alone, so nothing carried them across the edge.

Two properties carry the weight: the block reaches a DEPENDENT (not just the
task itself), and nothing here can fail a task — this is context, not a gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from claude_dispatcher import findings_store as fs


def _f(desc="a real defect", sev="HIGH", fam="codex", loc="src/x.py:12"):
    return fs.Finding(family=fam, severity=sev, location=loc, description=desc)


def test_findings_are_readable_by_a_later_run(tmp_path: Path) -> None:
    """Stored run-independently on purpose: a dependency usually ran in an
    EARLIER run than the task inheriting from it, so a per-run path would make
    the common case unreadable — which is the defect, not a detail.

    Measured under: key the path by run id and this reddens.
    """
    fs.record(tmp_path, "U-1", [_f()])
    assert fs.load(tmp_path, "U-1") == [_f()]
    assert fs.path_for(tmp_path, "U-1").name == "U-1.json"


def test_the_block_reaches_a_dependent_and_names_the_source(tmp_path: Path) -> None:
    """The whole point: the SEALS task must see what the panel found on the
    scaffold it is sealing.

    Measured under: render only the current task's findings and this reddens.
    """
    fs.record(tmp_path, "U-1", [_f(desc="NUL delimiter collides")])
    block = fs.render_for_prompt(tmp_path, ["U-1"])
    assert "NUL delimiter collides" in block
    assert "Recorded on U-1" in block
    assert "HIGH" in block and "codex" in block


def test_a_clean_dependency_changes_the_prompt_not_at_all(tmp_path: Path) -> None:
    """Empty string, not a "no findings" notice. A task whose dependencies were
    clean must read exactly as it did before this existed, or every prompt in the
    project grows a paragraph that says nothing.
    """
    assert fs.render_for_prompt(tmp_path, ["NOPE"]) == ""
    assert fs.render_for_prompt(tmp_path, []) == ""


def test_recording_nothing_writes_nothing(tmp_path: Path) -> None:
    """An empty file would read as "reviewed and clean" on a task whose panel
    never ran. Those are different facts and must not share a representation.

    Measured under: write the file unconditionally and this reddens.
    """
    assert fs.record(tmp_path, "U-1", []) is None
    assert not fs.path_for(tmp_path, "U-1").exists()


def test_several_dependencies_are_all_carried(tmp_path: Path) -> None:
    fs.record(tmp_path, "U-1", [_f(desc="from one")])
    fs.record(tmp_path, "U-2", [_f(desc="from two")])
    block = fs.render_for_prompt(tmp_path, ["U-1", "U-2"])
    assert "from one" in block and "from two" in block


def test_the_block_is_bounded_so_it_cannot_crowd_out_the_diff(tmp_path: Path) -> None:
    """Findings are model-written prose. A runaway panel must not be able to
    push the actual work out of the prompt.

    Measured under: drop MAX_PER_DEP and this reddens.
    """
    fs.record(tmp_path, "U-1", [_f(desc=f"finding {i} " + "x" * 5000)
                                for i in range(40)])
    block = fs.render_for_prompt(tmp_path, ["U-1"])
    assert "and 28 more on U-1" in block
    assert len(block) < 12000, len(block)


def test_a_malformed_or_unreadable_store_never_raises(tmp_path: Path) -> None:
    """This feeds a PROMPT. The cost of missing context is a weaker prompt; the
    cost of raising is a task that cannot run at all — so it fails toward
    "dispatch without the extra context", never toward "do not dispatch".

    Measured under: drop the except clause and each case below raises.
    """
    p = fs.path_for(tmp_path, "BAD")
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text("{not json")
    assert fs.load(tmp_path, "BAD") == [] and fs.render_for_prompt(tmp_path, ["BAD"]) == ""

    p.write_text(json.dumps({"findings": "not a list"}))
    assert fs.load(tmp_path, "BAD") == []

    p.write_text(json.dumps({"findings": [{"family": None}]}))
    assert len(fs.load(tmp_path, "BAD")) == 1   # degrades per-field, does not raise

    p.write_text(json.dumps(["not", "a", "mapping"]))
    assert fs.load(tmp_path, "BAD") == []


def test_a_rerun_replaces_rather_than_appends(tmp_path: Path) -> None:
    """The file describes that task's LATEST review. Appending would carry
    findings the author has since fixed, and a stale accusation is worse than
    none — it costs a round arguing with it.
    """
    fs.record(tmp_path, "U-1", [_f(desc="round one")])
    fs.record(tmp_path, "U-1", [_f(desc="round two")])
    got = [f.description for f in fs.load(tmp_path, "U-1")]
    assert got == ["round two"]


def test_the_recorder_actually_writes_from_a_real_PanelVerdict(tmp_path) -> None:
    """EXECUTED against the real type, because asserting the call site exists is
    not a seal — and that is not hypothetical here.

    The first version read `getattr(panel, "findings", [])`. PanelVerdict has no
    such attribute (it carries `reviewers` and `blocking_findings`), so the
    recorder returned [] on every panel and wrote nothing for a whole round,
    while the row below merely asserted the call was present in the source. The
    stale backfill on disk hid it.

    Measured under: read a `findings` attribute off the panel and this reddens.
    """
    from claude_dispatcher import cross_family_reviewer as cfr, orchestrator

    finding = cfr.Finding(severity=cfr.Severity.HIGH, location="src/x.py:12",
                          description="a real defect the next author must know")
    panel = cfr.PanelVerdict(
        consensus="block",
        reviewers=[cfr.ReviewerVerdict(family="codex", verdict="CHANGES_REQUESTED",
                                       dimensions={}, findings=[finding])],
        summary="", blocking_findings=[finding], advisory=[],
    )
    cfg = SimpleNamespace(runs_dir=tmp_path)
    orchestrator._record_panel_findings(cfg, "U-1", panel, tmp_path / "log")

    got = fs.load(tmp_path, "U-1")
    assert len(got) == 1, got
    assert got[0].family == "codex"          # family lives on the REVIEWER
    assert got[0].severity == "HIGH"
    assert "a real defect" in got[0].description

    block = fs.render_for_prompt(tmp_path, ["U-1"])
    assert "a real defect the next author must know" in block


def test_the_recorder_never_raises_on_an_odd_panel(tmp_path) -> None:
    """It records CONTEXT. A failure to record must not fail a task that has
    already been reviewed.
    """
    from claude_dispatcher import orchestrator
    cfg = SimpleNamespace(runs_dir=tmp_path)
    orchestrator._record_panel_findings(cfg, "U-1", None, tmp_path / "log")
    orchestrator._record_panel_findings(
        cfg, "U-1", SimpleNamespace(reviewers="not a list"), tmp_path / "log")
    assert fs.load(tmp_path, "U-1") == []


def test_both_halves_are_wired(tmp_path: Path) -> None:
    """Recording without injecting is what D-56 measured; injecting without
    recording is the same no-op from the other end."""
    from claude_dispatcher import orchestrator
    src = Path(orchestrator.__file__).read_text()
    assert "_record_panel_findings(cfg, snap.key, panel_verdict, log_path)" in src
    assert "findings_store_mod.render_for_prompt(" in src
    assert "snap.blocked_by or []," in src
