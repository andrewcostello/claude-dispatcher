"""Seals for the grok-first ⇄ main integration fixes.

Covers the review findings fixed in the integration pass:
  * spawn_agent is the single choke point that drops claude-shaped model
    pins for non-claude agents (primary spawn AND every retry/iterate path
    inherit it).
  * the unified brief instructs agents to COMMIT their work (the
    committed-tree gate keys evidence to the agent's own commit; the
    dispatcher auto-commit is only the cross-family fallback).
  * _panel_should_run honors explicit panel: pins over the small-leaf skip.
"""

from __future__ import annotations

from pathlib import Path

from claude_dispatcher import orchestrator
from claude_dispatcher import plan as plan_mod
from claude_dispatcher import spawn as spawn_mod


# --- spawn_agent model-pin choke point ---------------------------------------


def _capture_grok_argv(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(argv, **kwargs):
        seen.append(list(argv))

        class P:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return P()

    monkeypatch.setattr(spawn_mod.subprocess, "run", fake_run)

    def grok_argv() -> list[str]:
        for argv in seen:
            if "--always-approve" in argv:
                return argv
        raise AssertionError(f"no grok invocation captured: {seen}")

    return grok_argv


def test_spawn_agent_drops_claude_model_pin_for_grok(tmp_path, monkeypatch):
    """A claude-shaped model pin must never reach a non-claude CLI argv —
    guarded inside spawn_agent so retries/iterates can't bypass it."""
    grok_argv = _capture_grok_argv(monkeypatch)
    env = {"SUMMARY_PATH": str(tmp_path / "summary.md"), "TASK_KEY": "T-1"}
    spawn_mod.spawn_agent(
        agent="grok", cwd=tmp_path, env=env,
        prompt="p", model="claude-fable-5",
    )
    assert "--model" not in grok_argv(), grok_argv()


def test_spawn_agent_keeps_native_model_for_grok(tmp_path, monkeypatch):
    grok_argv = _capture_grok_argv(monkeypatch)
    env = {"SUMMARY_PATH": str(tmp_path / "summary.md"), "TASK_KEY": "T-1"}
    spawn_mod.spawn_agent(
        agent="grok", cwd=tmp_path, env=env,
        prompt="p", model="grok-4-fast",
    )
    argv = grok_argv()
    assert "--model" in argv and argv[argv.index("--model") + 1] == "grok-4-fast"


# --- the brief instructs agents to commit (evidence boundary) -----------------


def test_brief_instructs_commit_and_forbids_push_and_pr():
    """The commit contract must agree with the committed-tree gate: agents
    commit their own work (the gate keys evidence to that commit); only
    push/PR are the dispatcher's. A brief that forbids committing forces a
    commit-retry spawn on every obedient claude task (2026-07-13 smokes)."""
    prompt = spawn_mod.build_prompt(
        task_key="T-1", task_summary="s", task_type="Task",
        task_labels=["size:xs"], task_description="d", branch="feat/x",
        summary_path=Path("/tmp/s.md"), run_id="r", max_iterations=1,
        financial_paths="", skip_design=False, skip_security_linter=False,
        reviewer_count=None, agent="claude",
    )
    assert "Commit your work" in prompt
    assert "Do NOT run `git commit`" not in prompt
    assert "Do NOT push" in prompt and "do NOT open a PR" in prompt


# --- panel pins beat the small-leaf skip --------------------------------------


def _snap(labels, panel=None):
    return orchestrator.TaskSnapshot(
        key="P-1", summary="s", description="d", type="Task",
        labels=labels, panel=panel, batch_keys=["P-1"],
    )


def _cfg(tmp_path):
    return orchestrator.RunConfig(
        tasks_path=tmp_path / "tasks.yaml",
        runs_dir=tmp_path / "runs",
        run_id="r", mode="unattended",
        max_parallel=1, max_iterations=1, reviewer_count=None,
        skip_design=False, skip_security_linter=False,
        financial_paths="", claude_bin="claude",
        worktree_base=None,
        label_filter=plan_mod.parse_label_filter(None),
        only_keys=None,
        cross_family_panel="always",
    )


def test_small_leaf_without_pin_skips_panel(tmp_path):
    cfg = _cfg(tmp_path)
    assert orchestrator._panel_should_run(cfg, _snap(["size:xs"])) is False


def test_small_leaf_explicit_full_pin_runs_panel(tmp_path):
    """An explicit panel: pin always wins — silently discarding one is a
    fail-open on a quality gate."""
    cfg = _cfg(tmp_path)
    assert orchestrator._panel_should_run(
        cfg, _snap(["size:xs"], panel="full")) is True


def test_small_leaf_explicit_single_pin_runs_panel(tmp_path):
    cfg = _cfg(tmp_path)
    assert orchestrator._panel_should_run(
        cfg, _snap(["size:xs"], panel="single")) is True
