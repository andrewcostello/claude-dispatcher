"""Endpoint implementer agents — open-weight models behind Anthropic-compatible APIs.

The 2026-07 bakeoff pulls in three open-weight implementers: Kimi K2.7-Code
(Moonshot), GLM-5.2 (Z.ai), and DeepSeek V4-Pro-Max. All three providers ship
Anthropic-compatible endpoints, so each runs as the ordinary `claude --print`
Tasker with the environment re-pointed: ANTHROPIC_BASE_URL at the provider,
ANTHROPIC_AUTH_TOKEN carrying the provider key, and the provider's model id.
No new CLI adapters — unlike codex/grok/gemini (spawn.AGENT_BINS), an endpoint
agent reuses the whole claude spawn path, including JSON usage/cost capture
(so bakeoff cells get cost_known=True, which the cross-family CLIs never do).

Two invariants the spawn glue must respect:
  1. spawn_claude() strips ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN by default
     to bill the Claude subscription. An endpoint agent's token is the
     PROVIDER's key, not Anthropic billing — the endpoint spawn must pass
     metered=True so the token survives.
  2. ANTHROPIC_API_KEY (the real Anthropic key, if present in the parent env)
     must be REMOVED from the child env, or the claude CLI may prefer it over
     the AUTH_TOKEN and silently bill Anthropic while talking to the wrong
     host.

Default model ids below are pinned from provider docs as of 2026-07-07 and are
VERIFY-ON-FIRST-RUN: `dispatcher doctor` probes each configured endpoint once
keys exist and reports id mismatches loudly. A task-level `model:` always
overrides the default.

This module is part of the contract-first endpoint-agents feature
(features/endpoint-agents/tasks.yaml). Stubs raise NotImplementedError; each
body is filled by its dispatched task, which also un-skips the function's
contract tests in tests/test_endpoint_agents.py. The registry, dataclasses,
and function signatures here are AUTHORITATIVE — see CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class EndpointAgentSpec:
    """Static description of one Anthropic-compatible endpoint agent."""

    name: str           # agent name used in tasks.yaml `agent:` (e.g. "kimi")
    provider: str       # human label for reports/provenance (e.g. "Moonshot AI")
    base_url: str       # Anthropic-compatible API root (becomes ANTHROPIC_BASE_URL)
    key_env: str        # parent-env var holding the provider API key
    default_model: str  # provider model id when the task sets no `model:`


ENDPOINT_AGENTS: dict[str, EndpointAgentSpec] = {
    "kimi": EndpointAgentSpec(
        name="kimi", provider="Moonshot AI",
        base_url="https://api.moonshot.ai/anthropic",
        key_env="MOONSHOT_API_KEY", default_model="kimi-k2.7-code",
    ),
    "glm": EndpointAgentSpec(
        name="glm", provider="Z.ai",
        base_url="https://api.z.ai/api/anthropic",
        key_env="ZAI_API_KEY", default_model="glm-5.2",
    ),
    "deepseek": EndpointAgentSpec(
        name="deepseek", provider="DeepSeek",
        base_url="https://api.deepseek.com/anthropic",
        key_env="DEEPSEEK_API_KEY", default_model="deepseek-v4-pro-max",
    ),
}


class EndpointConfigError(RuntimeError):
    """A named endpoint agent cannot run with the current environment.

    The message must be actionable on its own: it names the agent, the
    provider, and the exact env var to set (e.g. "export MOONSHOT_API_KEY=...").
    """


@dataclass(frozen=True)
class EndpointResolution:
    """Everything the spawn glue needs to run one endpoint-agent task."""

    spec: EndpointAgentSpec
    key: str    # the provider API key (non-empty)
    model: str  # resolved model id: task `model:` if set, else spec.default_model


def resolve_endpoint_agent(
    agent: str, env: Mapping[str, str], model: str | None = None,
) -> EndpointResolution:
    """Resolve an endpoint agent name to a runnable EndpointResolution. PURE.

    Contract:
      - `agent` not in ENDPOINT_AGENTS -> EndpointConfigError naming the agent
        and listing the known endpoint agents.
      - spec.key_env absent from `env`, or present but empty/whitespace-only
        -> EndpointConfigError naming the agent, provider, and key_env.
      - otherwise return EndpointResolution(spec, key=env[key_env].strip(),
        model=model if a non-empty model was given else spec.default_model).
    """
    spec = ENDPOINT_AGENTS.get(agent)
    if spec is None:
        known = ", ".join(ENDPOINT_AGENTS)
        raise EndpointConfigError(
            f"unknown endpoint agent {agent!r}; known endpoint agents: {known}"
        )
    key = env.get(spec.key_env, "").strip()
    if not key:
        raise EndpointConfigError(
            f"endpoint agent {agent!r} ({spec.provider}) needs {spec.key_env} "
            f"set in the environment: export {spec.key_env}=..."
        )
    return EndpointResolution(spec=spec, key=key, model=model or spec.default_model)


def build_endpoint_env(
    base_env: Mapping[str, str], resolution: EndpointResolution,
) -> dict[str, str]:
    """Build the child env for one endpoint-agent claude spawn. PURE.

    Contract (returns a NEW dict; never mutates base_env):
      - starts from a copy of base_env (dispatcher task vars like TASK_KEY /
        SUMMARY_PATH / DISPATCHER_RUN_ID pass through untouched),
      - sets ANTHROPIC_BASE_URL = spec.base_url,
      - sets ANTHROPIC_AUTH_TOKEN = resolution.key,
      - sets ANTHROPIC_MODEL and ANTHROPIC_SMALL_FAST_MODEL = resolution.model
        (one provider model serves both roles; endpoint providers do not host
        Anthropic's haiku ids),
      - REMOVES ANTHROPIC_API_KEY if present (module invariant 2),
      - sets CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1" (no telemetry /
        update pings against a third-party host).
    """
    env = dict(base_env)
    env.pop("ANTHROPIC_API_KEY", None)
    env["ANTHROPIC_BASE_URL"] = resolution.spec.base_url
    env["ANTHROPIC_AUTH_TOKEN"] = resolution.key
    env["ANTHROPIC_MODEL"] = resolution.model
    env["ANTHROPIC_SMALL_FAST_MODEL"] = resolution.model
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env


def endpoint_doctor_report(env: Mapping[str, str]) -> list[tuple[str, bool, str]]:
    """Static readiness report for every registered endpoint agent. PURE.

    One (agent_name, ok, detail) tuple per ENDPOINT_AGENTS entry, in registry
    order. ok=True when the spec's key_env is present and non-blank; detail
    then reads "<provider>: <key_env> set (model <default_model>)". ok=False
    otherwise; detail then reads "<provider>: set <key_env> to enable" so the
    doctor output tells the user exactly what to export. This covers the pure
    half of doctoring; the live endpoint probe (EPA-5) is separate glue.
    """
    raise NotImplementedError("EPA-4")
