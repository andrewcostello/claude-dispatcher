"""Tests for run_feature_review (step 3) — uses a fake diff + fake panel."""
from types import SimpleNamespace as NS

from claude_dispatcher import orchestrator as orch
from claude_dispatcher import cross_family_reviewer as cfr
from claude_dispatcher.orchestrator import RunConfig, run_feature_review


def _cfg(tmp_path, **kw):
    base = dict(
        tasks_path=tmp_path / "t.yaml", runs_dir=tmp_path / "runs", run_id="R",
        mode="unattended", max_parallel=1, max_iterations=1, reviewer_count=None,
        skip_design=False, skip_security_linter=False, financial_paths="",
        claude_bin="claude", worktree_base=None, label_filter=[], only_keys=None,
        base_branch="main", feature_branch="feat/x",
    )
    base.update(kw)
    return RunConfig(**base)  # journal defaults None -> events no-op


def test_run_feature_review_none_when_no_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(cfr, "collect_diff", lambda **k: "")
    assert run_feature_review(_cfg(tmp_path), tmp_path, {"tasks": []},
                              tmp_path / "run.log") is None


def test_run_feature_review_runs_panel_against_prd(tmp_path, monkeypatch):
    monkeypatch.setattr(cfr, "collect_diff", lambda **k: "diff --git a b\n+x\n")
    monkeypatch.setattr(orch, "_panel_reviewer_factory", lambda cfg: [])
    monkeypatch.setattr(orch, "_panel_advisory_reviewer_factory", lambda *a, **k: [])
    captured = {}
    fake_verdict = NS(consensus="block", blocking_findings=[object()], reviewers=[])

    def fake_run_panel(**kw):
        captured.update(kw)
        return fake_verdict

    monkeypatch.setattr(cfr, "run_panel", fake_run_panel)
    prd = tmp_path / "features" / "x" / "PRD.md"
    prd.parent.mkdir(parents=True)
    prd.write_text("ACCEPTANCE: the widget foos", encoding="utf-8")

    v = run_feature_review(
        _cfg(tmp_path), tmp_path,
        {"prd": "features/x/PRD.md", "epic": "X", "tasks": []},
        tmp_path / "run.log",
    )
    assert v is fake_verdict
    assert captured["ticket_key"] == "FEATURE-REVIEW"
    # The PRD content is threaded into the review prompt (the oracle).
    assert "ACCEPTANCE: the widget foos" in captured["summary_md"]
    # And the cumulative diff is what's reviewed.
    assert "diff --git" in captured["diff"]
