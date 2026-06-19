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


def test_apply_dispositions_classifies_records_all_no_silent_drops(tmp_path):
    from claude_dispatcher.disposition import DispositionLedger
    F = lambda loc, sev: NS(location=loc, severity=sev, description="d")
    verdict = NS(reviewers=[
        NS(family="claude", findings=[F("a:1", "CRITICAL"), F("b:2", "CRITICAL"),
                                      F("c:3", "MEDIUM")]),
        NS(family="codex", findings=[F("a:1", "CRITICAL")]),  # corroborates a:1
    ], blocking_findings=[])
    led = DispositionLedger()
    accepted, held = orch.apply_dispositions(
        _cfg(tmp_path), verdict, mode="unattended", ledger=led, log_path=tmp_path / "l")
    assert {f["location"] for f in accepted} == {"a:1"}   # corroborated CRITICAL
    assert {f["location"] for f in held} == {"b:2"}        # lone CRITICAL -> hold
    assert led.tally() == {"accept": 1, "hold": 1, "defer": 1}  # MEDIUM c:3 -> defer
    assert len(led.records) == 3                            # nothing silently dropped


def _tasks_yaml(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("project: X\nepic: e\ntasks:\n"
                 "  - key: T1\n    summary: s\n    description: d\n"
                 "    type: Task\n    labels: [size:S]\n    status: Merged\n",
                 encoding="utf-8")
    return p


def test_append_fix_tasks_writes_valid_runnable_rows(tmp_path):
    from claude_dispatcher import plan, yaml_io
    p = _tasks_yaml(tmp_path)
    n = orch._append_fix_tasks(_cfg(tmp_path, tasks_path=p), [
        {"location": "a.py:1", "severity": "HIGH", "description": "bug here",
         "corroboration": 2}], review_round=0)
    assert n == 1
    fix = [t for t in plan.load_tasks(yaml_io.load(p)) if t.key == "FIX-1"]
    assert fix and fix[0].agent == "claude" and fix[0].size_label == "S"
    assert fix[0].status == plan.TODO  # runnable


def _patch_review(monkeypatch, verdict):
    monkeypatch.setattr(orch, "run_feature_review", lambda *a, **k: verdict)


def test_feature_review_round_appends_fix_on_accept(tmp_path, monkeypatch):
    from claude_dispatcher.disposition import DispositionLedger
    from claude_dispatcher import plan, yaml_io
    p = _tasks_yaml(tmp_path)
    F = lambda loc, sev: NS(location=loc, severity=sev, description="d")
    _patch_review(monkeypatch, NS(reviewers=[
        NS(family="claude", findings=[F("a:1", "CRITICAL")]),
        NS(family="codex", findings=[F("a:1", "CRITICAL")]),  # corroborated -> accept
    ], blocking_findings=[]))
    cont = orch._feature_review_round(_cfg(tmp_path, tasks_path=p), tmp_path,
                                      tmp_path / "l", DispositionLedger(), 0)
    assert cont is True
    assert any(t.key == "FIX-1" for t in plan.load_tasks(yaml_io.load(p)))


def test_feature_review_round_stops_when_clean(tmp_path, monkeypatch):
    from claude_dispatcher.disposition import DispositionLedger
    _patch_review(monkeypatch, NS(reviewers=[], blocking_findings=[]))
    assert orch._feature_review_round(_cfg(tmp_path, tasks_path=_tasks_yaml(tmp_path)),
                                      tmp_path, tmp_path / "l", DispositionLedger(), 0) is False


def test_feature_review_round_stops_on_no_diff(tmp_path, monkeypatch):
    from claude_dispatcher.disposition import DispositionLedger
    _patch_review(monkeypatch, None)
    assert orch._feature_review_round(_cfg(tmp_path, tasks_path=_tasks_yaml(tmp_path)),
                                      tmp_path, tmp_path / "l", DispositionLedger(), 0) is False


def test_feature_review_round_holds_on_lone_critical(tmp_path, monkeypatch):
    from claude_dispatcher.disposition import DispositionLedger
    from claude_dispatcher import plan, yaml_io
    p = _tasks_yaml(tmp_path)
    _patch_review(monkeypatch, NS(reviewers=[
        NS(family="claude", findings=[NS(location="z:9", severity="CRITICAL",
                                          description="d")])], blocking_findings=[]))
    cont = orch._feature_review_round(_cfg(tmp_path, tasks_path=p), tmp_path,
                                      tmp_path / "l", DispositionLedger(), 0)
    assert cont is False  # lone CRITICAL -> held, no fix appended
    assert not any(t.key.startswith("FIX-") for t in plan.load_tasks(yaml_io.load(p)))
