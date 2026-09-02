"""Seals for spawn-failure classification (D-64).

Built from a live event rather than a hypothetical. 2026-08-18, W2-1-1:

    "terminal_reason":"api_error", "api_error_status":529,
    "result":"API Error: 529 Overloaded. This is a server-side issue,
              usually temporary — try again in a moment."

recorded on the row as `session_exit_code_1`, which reads as the agent failing.
The cascade had already been escalated by an earlier transient failure, so there
was no rung left and the task went straight to Blocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_dispatcher import spawn_failure as sf

LIVE = json.dumps({
    "type": "result", "subtype": "success", "terminal_reason": "api_error",
    "api_error_status": 529,
    "result": ("API Error: 529 Overloaded. This is a server-side issue, usually "
               "temporary — try again in a moment."),
    "duration_ms": 422866,
})


def test_the_live_529_is_infrastructure_and_retryable_now() -> None:
    """The event this exists for.

    Measured under: return QUALITY for an api_error and this reddens — which is
    exactly the state that spent a cascade rung on a server overload.
    """
    c = sf.classify(1, LIVE)
    assert c.is_infrastructure
    assert c.retry is sf.Retry.NOW
    assert c.api_error_status == 529


def test_the_providers_own_message_reaches_the_reason() -> None:
    """`session_exit_code_1` tells a human nothing. "Overloaded ... try again in a
    moment" tells them what to do, and the provider already said it.

    Measured under: drop `provider_message` from the reason and this reddens.
    """
    c = sf.classify(1, LIVE)
    assert "Overloaded" in c.reason
    assert "try again in a moment" in c.reason
    assert "529" in c.reason


@pytest.mark.parametrize("status,expected", [
    (429, sf.Retry.LATER),   # quota: resets hours later, an immediate retry fails
    (503, sf.Retry.NOW),
    (500, sf.Retry.NOW),
    (529, sf.Retry.NOW),
    (401, sf.Retry.NEVER),   # credentials: no retry helps, a human must act
    (403, sf.Retry.NEVER),
])
def test_statuses_are_not_one_class(status: int, expected: sf.Retry) -> None:
    """Collapsing them is how "just re-run it" became the only advice. A 529 is
    retryable in seconds, a 429 is not retryable until a reset, a 401 never is.

    Measured under: map every api_error to one Retry and the 429 and 401 rows
    redden.
    """
    c = sf.classify(1, LIVE.replace('"api_error_status": 529', f'"api_error_status": {status}'))
    assert c.is_infrastructure
    assert c.retry is expected


def test_an_api_error_with_no_status_is_still_infrastructure() -> None:
    """The provider said `api_error`. Treating it as a quality failure would spend
    a rung on it; NOW is the safe reading, because the alternative is stranding a
    task on a transient condition for the price of one spawn.
    """
    c = sf.classify(1, json.dumps({"type": "result", "terminal_reason": "api_error"}))
    assert c.is_infrastructure and c.retry is sf.Retry.NOW


def test_an_unrecognised_failure_keeps_TODAYS_behaviour() -> None:
    """The conservative direction, and the one that matters for not breaking
    anything: if nothing identifies a failure as infrastructure it stays QUALITY
    and still cascades. Silently stopping the cascade would be a worse regression
    than the defect being fixed.

    Measured under: default to INFRASTRUCTURE and this reddens.
    """
    for text in ("", "segfault", "Traceback (most recent call last):", "{not json"):
        c = sf.classify(1, text)
        assert c.kind is sf.FailureKind.QUALITY, text
        assert c.retry is sf.Retry.CASCADE
        assert c.reason == "session_exit_code_1"


def test_the_LAST_result_envelope_wins() -> None:
    """The CLI emits progress objects before the result. A prefix-greedy parse
    finds the wrong one and reports a stale status.

    Measured under: scan forwards instead of backwards and this reddens.
    """
    noise = json.dumps({"type": "progress", "api_error_status": 429}) + "\n" + LIVE
    assert sf.classify(1, noise).api_error_status == 529


#: The REAL 600-character tail the dispatcher logged for W2-1-1 on 2026-08-18,
#: verbatim. It begins mid-token because the log truncates, so it contains no
#: opening brace and no parseable document.
LIVE_TRUNCATED_TAIL = 'heCreationInputTokens":56759,"webSearchRequests":0,"costUSD":0.9785080000000002,"contextWindow":1000000,"maxOutputTokens":64000,"canonicalModel":"claude-opus-5","provider":"firstParty"}},"permission_denials":[],"terminal_reason":"api_error","fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required","subtype":"success","api_error_status":529,"result":"API Error: 529 Overloaded. This is a server-side issue, usually temporary — try again in a moment. If it persists, check https://status.claude.com.","type":"result","duration_ms":422866,"uuid":"31904343-7e4c-4e23-b474-419a9a43357a"}'


def test_the_REAL_truncated_tail_is_still_classified() -> None:
    """Classified against the live artifact, not a reconstruction of it — and the
    reconstruction is what hid this.

    Both parse tiers return nothing here: the tail starts mid-token, with no
    opening brace, so there is no document to parse. The first implementation
    therefore reported this exact failure as a plain session_exit_code_1 — the
    defect it was written to fix — and only testing the real bytes showed it.

    Measured under: remove the `_scavenge` tier and this reddens.
    """
    c = sf.classify(1, LIVE_TRUNCATED_TAIL)
    assert c.is_infrastructure
    assert c.api_error_status == 529
    assert c.retry is sf.Retry.NOW


def test_the_providers_words_survive_intact_from_a_fragment() -> None:
    """A garbled quote is a quote an operator stops trusting.

    Measured under: decode with `unicode_escape` and this reddens — it
    re-interprets already-decoded UTF-8 byte-by-byte and renders the em dash as
    "temporary â try again".
    """
    reason = sf.classify(1, LIVE_TRUNCATED_TAIL).reason
    assert "usually temporary — try again in a moment" in reason
    assert "â" not in reason


def test_a_truncated_envelope_does_not_raise() -> None:
    """This runs on the output of a process that just died, so half-written JSON
    is the normal case, not the exotic one.
    """
    half = LIVE[:len(LIVE) // 2]
    c = sf.classify(1, half)
    # It does not raise; whether it identifies anything depends on how much of
    # the envelope survived, and either answer is acceptable here. What is NOT
    # acceptable is an exception, because the caller has already lost the spawn.
    assert c.kind in (sf.FailureKind.QUALITY, sf.FailureKind.INFRASTRUCTURE)


def test_stderr_is_read_when_stdout_is_empty() -> None:
    c = sf.classify(1, "", LIVE)
    assert c.is_infrastructure and c.api_error_status == 529


def test_the_orchestrator_breaks_rather_than_cascading(tmp_path: Path) -> None:
    """The wiring, and the whole point: a failure a stronger rung cannot fix must
    NOT advance the cascade.

    INFRASTRUCTURE, because the next rung resets the worktree and is spent
    against the same server condition. CONFIG, because the next rung runs a
    DIFFERENT model and its output is then recorded under the failed agent's
    name — measured 2026-09-01, when `grok-build` was rejected as an unknown
    model id and claude-opus-5[1m]'s work was scored as grok's.

    Measured under: change the `break` to `continue` and this reddens.
    """
    from claude_dispatcher import orchestrator
    src = Path(orchestrator.__file__).read_text()
    at = src.index("failure = spawn_failure_mod.classify(")
    block = src[at:at + 1400]
    assert "if failure.blocks_cascade:" in block
    assert "break" in block.split("if failure.blocks_cascade:")[1].split("fail_reason")[0]
    assert "final_blocked_reason = failure.reason" in block


def test_a_bad_model_pin_is_config_and_never_cascades() -> None:
    """A cross-family CLI reports a bad pin in plain text, not an Anthropic
    envelope, so it used to fall through to QUALITY/CASCADE and be hidden behind
    whatever model the next rung ran."""
    c = sf.classify(
        1, "Error: Couldn't set model 'grok-build': Invalid params: "
           '"unknown model id". Run \'grok models\' to see available models.')
    assert c.kind is sf.FailureKind.CONFIG
    assert c.retry is sf.Retry.NEVER
    assert c.blocks_cascade is True
    assert "grok-build" in c.reason


def test_an_ordinary_failure_still_cascades() -> None:
    """The guard must not become "nothing ever escalates": only the named
    misconfiguration signatures stop the cascade."""
    c = sf.classify(1, "the tests did not pass")
    assert c.kind is sf.FailureKind.QUALITY
    assert c.retry is sf.Retry.CASCADE
    assert c.blocks_cascade is False


def test_the_quality_path_still_sets_a_cascade_reason() -> None:
    """The other half of the wiring: a genuine quality failure must still cascade,
    so the fix cannot become "nothing ever escalates".
    """
    from claude_dispatcher import orchestrator
    src = Path(orchestrator.__file__).read_text()
    at = src.index("failure = spawn_failure_mod.classify(")
    block = src[at:at + 1400]
    assert "fail_reason = failure.reason" in block
    assert "continue" in block


# --------------------------------------------------- the bounded retry -------

def test_the_retry_is_bounded_at_one() -> None:
    """ONE retry, then park. An unbounded retry against a flapping provider burns
    the cost ceiling with nothing to show, and a second failure is evidence the
    condition is not passing rather than a blip.

    Measured under: raise INFRA_RETRY_LIMIT and this reddens.
    """
    from claude_dispatcher import orchestrator
    assert orchestrator.INFRA_RETRY_LIMIT == 1


def test_only_retryable_NOW_is_retried() -> None:
    """A 429 quota resets hours later, so an immediate retry is guaranteed to
    fail and costs a spawn to learn nothing; a 401 never becomes retryable. Both
    must park at once.

    Measured under: retry on any infrastructure failure and this reddens.
    """
    from pathlib import Path
    from claude_dispatcher import orchestrator
    src = Path(orchestrator.__file__).read_text()
    at = src.index("infra_retries = 0")
    block = src[at:at + 2600]
    assert "transient.retry is not spawn_failure_mod.Retry.NOW" in block
    assert "infra_retries >= INFRA_RETRY_LIMIT" in block


def test_the_retry_does_not_cascade(tmp_path: Path) -> None:
    """The property that makes it a retry rather than an escalation: same rung,
    same agent, same effort, no fallback event and NO WORKTREE RESET — the next
    rung begins by resetting the worktree, which would destroy the diff a human
    is being blocked to read, and it would be spent against the same server.

    Measured under: move the retry into the cascade loop and this reddens.
    """
    from pathlib import Path as P
    from claude_dispatcher import orchestrator
    src = P(orchestrator.__file__).read_text()
    at = src.index("infra_retries = 0")
    block = src[at:src.index("if result is None:", at)]
    assert "agent_fallback" not in block, "a retry must not emit a cascade event"
    assert "_reset_worktree" not in block, "a retry must not reset the worktree"
    assert "attempt_agent" in block and "attempt_effort" in block


def test_every_attempt_including_a_retry_is_billed() -> None:
    """A retried spawn costs real money and must count toward the ceiling, or a
    flapping provider could spend past it invisibly.

    Measured under: move `_account_spawn` outside the retry loop and this reddens.
    """
    from pathlib import Path as P
    from claude_dispatcher import orchestrator
    src = P(orchestrator.__file__).read_text()
    at = src.index("infra_retries = 0")
    block = src[at:src.index("if result is None:", at)]
    assert "_account_spawn(cfg, snap.key, result, kind=\"implementer\")" in block
