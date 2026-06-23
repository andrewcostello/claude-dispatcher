"""Tests for per-task implementer-agent routing (codex/grok/gemini/claude)."""
import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from claude_dispatcher import plan, spawn


def _load(yaml_text: str):
    return plan.load_tasks(YAML().load(io.StringIO(yaml_text)))


_BASE = """tasks:
  - key: T1
    summary: s
    description: d
    type: Task
    labels: [size:S]
"""


def test_agent_absent_defaults_to_none():
    (t,) = _load(_BASE)
    assert t.agent is None  # None -> claude at spawn time


@pytest.mark.parametrize("agent", ["codex", "grok", "gemini", "claude", "GROK"])
def test_known_agent_accepted_and_lowercased(agent):
    (t,) = _load(_BASE + f"    agent: {agent}\n")
    assert t.agent == agent.lower()


def test_unknown_agent_rejected():
    with pytest.raises(plan.ValidationError, match="unknown agent"):
        _load(_BASE + "    agent: gpt5\n")


def test_spawn_agent_claude_path_delegates(monkeypatch, tmp_path):
    """agent None/claude routes through spawn_claude (so existing mocks hold)."""
    called = {}

    def fake_spawn_claude(*, claude_bin, cwd, env, prompt, extra_args, timeout_seconds):
        called["extra_args"] = extra_args
        return spawn.SpawnResult(0, Path(env["SUMMARY_PATH"]), "", "")

    monkeypatch.setattr(spawn, "spawn_claude", fake_spawn_claude)
    env = {"SUMMARY_PATH": str(tmp_path / "s.md"), "TASK_KEY": "T1"}
    spawn.spawn_agent(agent=None, cwd=tmp_path, env=env, prompt="p", model="sonnet")
    assert "--model" in called["extra_args"] and "sonnet" in called["extra_args"]


def test_agent_bins_cover_known_cross_family():
    assert set(spawn.AGENT_BINS) == {"codex", "grok", "gemini"}
    assert spawn.AGENT_BINS["gemini"] == "agy"  # authed Google CLI
