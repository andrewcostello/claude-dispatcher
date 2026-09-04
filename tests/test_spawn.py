

# --- which model actually did the work -------------------------------------
#
# `modelUsage` is a MAP. Taking its first key records whichever model the CLI
# logged first, which is routinely a tiny auxiliary call. Measured 2026-09-03:
# 20 of 26 wallet tasks were journaled as haiku while costing $0.110 per 1k
# output tokens -- ~20x Haiku's list price, so a premium model did the work.
# That wrong label is written back onto the task row, which then corrupted the
# routing record and produced a false family-collision warning.


def _usage_doc(model_usage: dict) -> str:
    import json
    return json.dumps({
        "total_cost_usd": 1.0, "num_turns": 3,
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "modelUsage": model_usage,
    })
from claude_dispatcher import spawn


def test_the_costliest_model_is_the_one_recorded() -> None:
    """Cost, not token count, and not map order. From a real probe: the
    auxiliary haiku call had MORE output tokens (8) than the model that
    answered (4) and cost 5x less, so tokens pick the wrong one."""
    doc = _usage_doc({
        "claude-haiku-4-5-20251001": {"inputTokens": 899, "outputTokens": 8,
                                      "costUSD": 0.000939},
        "claude-fable-5-1": {"inputTokens": 2, "outputTokens": 4,
                             "costUSD": 0.00514275},
    })
    assert spawn.parse_usage_from_json(doc).model == "claude-fable-5-1"


def test_map_order_does_not_decide() -> None:
    """The same two models with the cheap one listed FIRST must still resolve
    to the expensive one — first-key order is exactly the old bug."""
    doc = _usage_doc({
        "claude-haiku-4-5-20251001": {"outputTokens": 99, "costUSD": 0.001},
        "claude-opus-5": {"outputTokens": 1, "costUSD": 5.0},
    })
    assert spawn.parse_usage_from_json(doc).model == "claude-opus-5"


def test_a_single_model_run_is_unchanged() -> None:
    doc = _usage_doc({"claude-opus-5": {"outputTokens": 20, "costUSD": 1.0}})
    assert spawn.parse_usage_from_json(doc).model == "claude-opus-5"


def test_no_cost_falls_back_to_output_tokens() -> None:
    """Some CLI versions omit costUSD. Then the busiest model is the best
    available answer — still better than map order."""
    doc = _usage_doc({
        "claude-haiku-4-5-20251001": {"outputTokens": 5},
        "claude-fable-5-1": {"outputTokens": 5000},
    })
    assert spawn.parse_usage_from_json(doc).model == "claude-fable-5-1"


def test_an_empty_model_usage_map_records_nothing() -> None:
    assert spawn.parse_usage_from_json(_usage_doc({})).model is None


def test_codex_can_write_the_summary_outside_its_workspace() -> None:
    """codex runs `--sandbox workspace-write`, and SUMMARY_PATH is under the
    RUNS DIR, outside the worktree. So codex could never write the summary the
    dispatcher requires, and the dispatcher salvaged a transcript tail instead.

    Measured 2026-09-04, WAL-APPEND-3. The agent had found the scaffold
    unimplementable (every parameter it must read is the blank identifier `_`)
    and said so: "I'm now making the required final summary write with a
    concrete Blocked outcome and the exact deviations" -- then "the sandbox
    rejected both attempts to write the required external summary.md path
    because it is outside the writable worktree".

    So a correct, well-reasoned DEVIATION was destroyed by a sandbox
    permission, and survived only because the transcript happened to be
    captured. The protocol depends on that record.

    Verified against a real runs-dir path (NOT /tmp, which codex allows by
    default -- my first probe used /tmp and wrongly cleared the sandbox).
    """
    from pathlib import Path as _P
    argv = spawn._agent_argv(
        "codex", "codex", _P("/tmp/p.txt"), _P("/tmp/wt"),
        "gpt-5.6-sol", "prompt", "xhigh",
        summary_dir="/home/andrew/Project/dispatcher-runs/R/KEY",
    )
    joined = " ".join(argv)
    assert "sandbox_workspace_write.writable_roots" in joined, joined
    assert "/home/andrew/Project/dispatcher-runs/R/KEY" in joined, joined
    # Unchanged when no summary dir is supplied.
    assert "writable_roots" not in " ".join(spawn._agent_argv(
        "codex", "codex", _P("/tmp/p.txt"), _P("/tmp/wt"),
        "gpt-5.6-sol", "prompt", "xhigh"))
