"""Tests for SpawnUsage + parse_usage_from_json.

The dispatcher invokes `claude --print --output-format=json` and the JSON
output contains per-task cost + token + duration metadata. These tests
cover the parser's resilience to:
  - Real-world JSON shapes (cost_usd, usage.*, modelUsage.*).
  - Missing fields (older CLI builds may omit some).
  - Garbage / non-JSON stdout (text mode, or claude error output).
  - Stream-json mode (line-delimited; we don't parse it — must not crash).
"""

from __future__ import annotations

import json

from claude_dispatcher.spawn import (
    SpawnUsage,
    parse_usage_from_json,
)


# A redacted real-world response from `claude --print --output-format=json`.
REAL_OUTPUT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "duration_ms": 3967,
    "duration_api_ms": 3866,
    "ttft_ms": 3840,
    "num_turns": 1,
    "result": "Hello",
    "session_id": "701294c5-7d43-40d4-b194-588d80f0c4d3",
    "total_cost_usd": 0.11339949999999999,
    "usage": {
        "input_tokens": 6,
        "cache_creation_input_tokens": 16624,
        "cache_read_input_tokens": 18589,
        "output_tokens": 7,
    },
    "modelUsage": {
        "claude-opus-4-7[1m]": {
            "inputTokens": 6,
            "outputTokens": 7,
            "cacheReadInputTokens": 18589,
            "cacheCreationInputTokens": 16624,
            "costUSD": 0.11339949999999999,
        }
    },
}


def test_parse_real_world_output():
    """Verify the parser extracts every field we care about from a real
    Claude CLI JSON response."""
    u = parse_usage_from_json(json.dumps(REAL_OUTPUT))
    assert u.cost_usd == 0.11339949999999999
    assert u.input_tokens == 6
    assert u.output_tokens == 7
    assert u.cache_read_input_tokens == 18589
    assert u.cache_creation_input_tokens == 16624
    assert u.duration_ms == 3967
    assert u.duration_api_ms == 3866
    assert u.ttft_ms == 3840
    assert u.num_turns == 1
    assert u.model == "claude-opus-4-7[1m]"
    assert u.session_id == "701294c5-7d43-40d4-b194-588d80f0c4d3"


def test_empty_stdout_returns_empty_usage():
    """No stdout = no usage. Don't crash."""
    u = parse_usage_from_json("")
    assert u == SpawnUsage()
    u = parse_usage_from_json("   \n\n  ")
    assert u == SpawnUsage()


def test_non_json_stdout_returns_empty_usage():
    """If the spawn ran without --output-format=json (or claude returned
    a non-JSON error message), the parser bails cleanly."""
    u = parse_usage_from_json("Hello, this is plain text output")
    assert u == SpawnUsage()
    # Half-JSON.
    u = parse_usage_from_json('{"type":"result",')
    assert u == SpawnUsage()
    # Whitespace-only.
    u = parse_usage_from_json("\n")
    assert u == SpawnUsage()


def test_missing_fields_partial_populate():
    """An older CLI build might omit some fields. Parser fills what it can,
    leaves the rest as None."""
    doc = {"total_cost_usd": 0.05, "duration_ms": 1234}
    u = parse_usage_from_json(json.dumps(doc))
    assert u.cost_usd == 0.05
    assert u.duration_ms == 1234
    assert u.input_tokens is None
    assert u.output_tokens is None
    assert u.model is None


def test_non_dict_root_returns_empty():
    """If the JSON root is a list or string (shouldn't happen for the CLI
    but be defensive), return empty usage rather than crash."""
    u = parse_usage_from_json('["a", "list"]')
    assert u == SpawnUsage()
    u = parse_usage_from_json('"just a string"')
    assert u == SpawnUsage()


def test_type_coercion_is_resilient():
    """Field values that arrive as strings (some CLIs return cost as a
    decimal string) get coerced; truly bad values become None without
    crashing the parser."""
    doc = {
        "total_cost_usd": "0.42",         # string-typed float → coerced
        "duration_ms": "5000",            # string-typed int → coerced
        "num_turns": "not-a-number",      # garbage → None
        "usage": {
            "input_tokens": "100",        # string-typed int → coerced
            "output_tokens": None,        # explicit None → stays None
        },
    }
    u = parse_usage_from_json(json.dumps(doc))
    assert u.cost_usd == 0.42
    assert u.duration_ms == 5000
    assert u.num_turns is None
    assert u.input_tokens == 100
    assert u.output_tokens is None


def test_stream_json_format_does_not_crash():
    """stream-json mode emits line-delimited events; we don't parse it but
    we must not crash the worker if it's accidentally enabled."""
    stream_output = (
        '{"type":"system","subtype":"init"}\n'
        '{"type":"assistant","message":{"role":"assistant"}}\n'
        '{"type":"result","total_cost_usd":0.05}\n'
    )
    u = parse_usage_from_json(stream_output)
    # Multi-document JSON — the first line is parsed (init event), no usage
    # data in it, so we get empty SpawnUsage. The point is no crash.
    assert isinstance(u, SpawnUsage)


def test_modelusage_first_key_wins_for_model_name():
    """modelUsage is a dict keyed by model id; we surface the first key
    as the model name (single-model runs have exactly one)."""
    doc = {
        "total_cost_usd": 0.01,
        "modelUsage": {"claude-sonnet-4-5": {"costUSD": 0.01}},
    }
    u = parse_usage_from_json(json.dumps(doc))
    assert u.model == "claude-sonnet-4-5"


def test_model_name_absent_when_modelusage_empty():
    doc = {"total_cost_usd": 0.01, "modelUsage": {}}
    u = parse_usage_from_json(json.dumps(doc))
    assert u.model is None
