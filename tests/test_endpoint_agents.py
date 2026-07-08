"""Contract tests for the endpoint-agents body-fills (features/endpoint-agents).

Each test is skipped in the skeleton; the dispatched body-fill task that
implements its function removes the skip (so the pytest gate stays green for
sibling tasks until each is filled). EPA-1/2/4 are pure — no
subprocess/network/fs. EPA-3 exercises the spawn seam with spawn_claude
monkeypatched; it must not spawn anything real.
"""
from pathlib import Path

import pytest

from claude_dispatcher import endpoint_agents as ea
from claude_dispatcher import spawn as spawn_mod


_ENV = {
    "MOONSHOT_API_KEY": "mk-test",
    "ZAI_API_KEY": "zk-test",
    "DEEPSEEK_API_KEY": "dk-test",
    "ANTHROPIC_API_KEY": "real-anthropic-key",
    "TASK_KEY": "EPA-T",
    "SUMMARY_PATH": "/tmp/epa/summary.md",
}


# --- registry (skeleton — live now, no skip) --------------------------------
def test_registry_names_are_known_agents():
    from claude_dispatcher import plan as plan_mod
    assert set(ea.ENDPOINT_AGENTS) == {"kimi", "glm", "deepseek"}
    assert set(ea.ENDPOINT_AGENTS) <= plan_mod.KNOWN_AGENTS
    # endpoint agents must never shadow a cross-family CLI adapter
    assert not set(ea.ENDPOINT_AGENTS) & set(spawn_mod.AGENT_BINS)


# --- resolve_endpoint_agent (EPA-1) -----------------------------------------
def test_resolve_known_agent_with_key():
    r = ea.resolve_endpoint_agent("kimi", _ENV)
    assert r.spec.name == "kimi"
    assert r.key == "mk-test"
    assert r.model == ea.ENDPOINT_AGENTS["kimi"].default_model


def test_resolve_task_model_overrides_default():
    r = ea.resolve_endpoint_agent("glm", _ENV, model="glm-5.2-air")
    assert r.model == "glm-5.2-air"


def test_resolve_missing_key_is_actionable_error():
    env = {k: v for k, v in _ENV.items() if k != "DEEPSEEK_API_KEY"}
    with pytest.raises(ea.EndpointConfigError) as exc:
        ea.resolve_endpoint_agent("deepseek", env)
    assert "DEEPSEEK_API_KEY" in str(exc.value)
    assert "deepseek" in str(exc.value)


def test_resolve_blank_key_treated_as_missing():
    env = dict(_ENV, MOONSHOT_API_KEY="   ")
    with pytest.raises(ea.EndpointConfigError):
        ea.resolve_endpoint_agent("kimi", env)


def test_resolve_unknown_agent_names_known_ones():
    with pytest.raises(ea.EndpointConfigError) as exc:
        ea.resolve_endpoint_agent("qwen", _ENV)
    assert "qwen" in str(exc.value)
    assert "kimi" in str(exc.value)  # error lists the known endpoint agents


# --- build_endpoint_env (EPA-2) ---------------------------------------------
def _resolution(agent="kimi", model=None):
    spec = ea.ENDPOINT_AGENTS[agent]
    return ea.EndpointResolution(
        spec=spec, key=f"{agent}-key", model=model or spec.default_model,
    )


@pytest.mark.skip(reason="EPA-2 body-fill")
def test_build_env_points_at_provider():
    env = ea.build_endpoint_env(_ENV, _resolution("kimi"))
    assert env["ANTHROPIC_BASE_URL"] == "https://api.moonshot.ai/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "kimi-key"
    assert env["ANTHROPIC_MODEL"] == ea.ENDPOINT_AGENTS["kimi"].default_model
    assert env["ANTHROPIC_SMALL_FAST_MODEL"] == env["ANTHROPIC_MODEL"]
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"


@pytest.mark.skip(reason="EPA-2 body-fill")
def test_build_env_strips_real_anthropic_key():
    env = ea.build_endpoint_env(_ENV, _resolution("glm"))
    assert "ANTHROPIC_API_KEY" not in env


@pytest.mark.skip(reason="EPA-2 body-fill")
def test_build_env_passes_dispatcher_vars_and_does_not_mutate():
    base = dict(_ENV)
    env = ea.build_endpoint_env(base, _resolution("deepseek"))
    assert env["TASK_KEY"] == "EPA-T"
    assert env["SUMMARY_PATH"] == "/tmp/epa/summary.md"
    assert base == _ENV  # input untouched


# --- spawn_endpoint_agent (EPA-3) -------------------------------------------
@pytest.mark.skip(reason="EPA-3 body-fill")
def test_spawn_routes_through_metered_spawn_claude(monkeypatch, tmp_path):
    seen = {}

    def fake_spawn_claude(*, claude_bin, cwd, env, prompt, extra_args=None,
                          timeout_seconds=0, metered=False):
        seen.update(env=env, extra_args=extra_args or [], metered=metered)
        return spawn_mod.SpawnResult(
            exit_code=0, summary_path=Path(env["SUMMARY_PATH"]),
            stdout="", stderr="", usage=spawn_mod.SpawnUsage(model="wrong"),
        )

    monkeypatch.setattr(spawn_mod, "spawn_claude", fake_spawn_claude)
    env = dict(_ENV, SUMMARY_PATH=str(tmp_path / "s.md"))
    res = spawn_mod.spawn_endpoint_agent(
        agent="kimi", cwd=tmp_path, env=env, prompt="p",
    )
    assert seen["metered"] is True
    assert seen["env"]["ANTHROPIC_BASE_URL"] == "https://api.moonshot.ai/anthropic"
    kimi_model = ea.ENDPOINT_AGENTS["kimi"].default_model
    assert seen["extra_args"][-2:] == ["--model", kimi_model]
    assert res.usage.model == kimi_model  # provenance overrides passthrough


@pytest.mark.skip(reason="EPA-3 body-fill")
def test_spawn_agent_dispatches_endpoint_names(monkeypatch, tmp_path):
    called = {}

    def fake_endpoint(*, agent, **kw):
        called["agent"] = agent
        return spawn_mod.SpawnResult(
            exit_code=0, summary_path=tmp_path / "s.md", stdout="", stderr="",
            usage=spawn_mod.SpawnUsage(model="m"),
        )

    monkeypatch.setattr(spawn_mod, "spawn_endpoint_agent", fake_endpoint)
    spawn_mod.spawn_agent(
        agent="glm", cwd=tmp_path,
        env=dict(_ENV, SUMMARY_PATH=str(tmp_path / "s.md")), prompt="p",
    )
    assert called["agent"] == "glm"


@pytest.mark.skip(reason="EPA-3 body-fill")
def test_spawn_missing_key_fails_loudly_no_fallback(monkeypatch, tmp_path):
    def boom(**kw):  # any real spawn attempt is a contract violation
        raise AssertionError("spawn_claude must not be called on config error")

    monkeypatch.setattr(spawn_mod, "spawn_claude", boom)
    env = {k: v for k, v in _ENV.items() if k != "ZAI_API_KEY"}
    env["SUMMARY_PATH"] = str(tmp_path / "s.md")
    with pytest.raises(ea.EndpointConfigError):
        spawn_mod.spawn_endpoint_agent(
            agent="glm", cwd=tmp_path, env=env, prompt="p",
        )


# --- endpoint_doctor_report (EPA-4) -----------------------------------------
@pytest.mark.skip(reason="EPA-4 body-fill")
def test_doctor_report_all_keys_present():
    report = ea.endpoint_doctor_report(_ENV)
    assert [name for name, _, _ in report] == list(ea.ENDPOINT_AGENTS)
    assert all(ok for _, ok, _ in report)


@pytest.mark.skip(reason="EPA-4 body-fill")
def test_doctor_report_missing_key_says_what_to_set():
    env = {k: v for k, v in _ENV.items() if k != "ZAI_API_KEY"}
    report = {name: (ok, detail) for name, ok, detail in ea.endpoint_doctor_report(env)}
    ok, detail = report["glm"]
    assert ok is False
    assert "ZAI_API_KEY" in detail
