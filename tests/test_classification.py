"""Path-derived classification and the panel override it feeds.

The property under test throughout: path evidence may only ever ADD review.
A classification never cancels a panel that labels or run-mode already required,
and a classification failure never changes the existing decision.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from claude_dispatcher import classification
from claude_dispatcher import cross_family_reviewer as cfr


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #


_GOOD = {
    "risk": "low",
    "financial_paths_touched": False,
    "client_only": False,
    "server_surface": True,
    "migration": False,
    "human_pr_gate": False,
    "panel": {"reduced": False, "seats": 5},
}


WALLET_PAYLOAD = {
    "risk": "critical",
    "components": ["bet-settlement", "wallet"],
    "financial_paths_touched": True,
    "client_only": False,
    "server_surface": True,
    "migration": True,
    "human_pr_gate": True,
    "recheck_min_severity": "medium",
    "panel": {"required": True, "seats": 5, "reduced": False, "reasons": ["financial path touched"]},
    "gate_signals": [{"signal": "env-gate", "file": "a.ts", "sample": "process.env.X"}],
    "unmatched_files": ["apps/new-thing/main.go"],
    "risk_reasons": ["apps/finance-domain/wallet/service/debit.go → critical via wallet-service"],
}


def test_parse_classification_maps_every_field():
    c = classification.parse_classification(WALLET_PAYLOAD)
    assert c.risk == "critical"
    assert c.components == ("bet-settlement", "wallet")
    assert c.financial_paths_touched is True
    assert c.migration is True
    assert c.human_pr_gate is True
    assert c.recheck_min_severity == "medium"
    assert c.panel_seats == 5
    assert c.panel_reduced is False
    assert c.gate_signals == ("env-gate",)
    assert c.unmatched_files == ("apps/new-thing/main.go",)


def test_parse_classification_rejects_a_payload_with_no_risk():
    """This test previously asserted the opposite, and the assertion WAS the bug.

    `parse_classification({})` used to return risk="low" — a confident weakest
    tier manufactured out of an empty object. Because the fail-closed guard in
    classify_diff_result only fires when this function RAISES, valid-but-
    meaningless JSON sailed straight past it into a "low risk, safe to
    auto-merge" verdict. Found by the claude seat on GO-1 round 2.
    """
    with pytest.raises(ValueError, match="no 'risk' key"):
        classification.parse_classification({})


def test_parse_classification_rejects_an_unrecognised_tier():
    """_rank used to return 0 — the WEAKEST tier — for anything unrecognised:
    "", None, a typo, a future tier this build predates. Every unknown became a
    confident "low"."""
    for bad in ({"risk": ""}, {"risk": None}, {"risk": "lowish"}, {"risk": "sev1"}):
        with pytest.raises(ValueError, match="unrecognised risk tier"):
            classification.parse_classification(bad)


def test_parse_classification_accepts_a_minimal_but_real_payload():
    """Strict about POLICY fields, still tolerant about descriptive ones.

    "Minimal" no longer means risk-only: cmd/classify emits every policy-bearing
    field unconditionally, so a payload without them is not classify output.
    Descriptive extras (components, reasons, changed_files) stay optional.
    """
    c = classification.parse_classification(dict(_GOOD))
    assert c.risk == "low"
    assert c.components == ()          # optional, absent is fine
    assert c.risk_reasons == ()        # optional
    assert c.requires_full_panel is True


def test_a_meaningless_payload_fails_closed_end_to_end(monkeypatch, tmp_path):
    """The property that matters: garbage in must not become a passing verdict.

    Strictness in the parser is only useful if it reaches the caller as
    CLASSIFY_FAILED — the status whose whole job is to stop a gate relaxing.
    """
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout="{}"))

    result = classification.classify_diff_result(
        diff="diff --git a/x b/x\n", binary=str(fake_bin)
    )
    assert result.status == classification.CLASSIFY_FAILED
    assert result.classification is None
    assert "risk" in (result.detail or "")


def test_requires_full_panel_follows_the_reduced_flag():
    full = classification.parse_classification(WALLET_PAYLOAD)
    assert full.requires_full_panel is True

    reduced = classification.parse_classification({
        "risk": "low",
        "financial_paths_touched": False,
        "client_only": True,
        "server_surface": False,
        "migration": False,
        "human_pr_gate": False,
        "panel": {"required": True, "seats": 1, "reduced": True},
    })
    assert reduced.requires_full_panel is False


def test_review_context_names_the_things_a_reviewer_needs():
    ctx = classification.parse_classification(WALLET_PAYLOAD).review_context()
    assert "critical" in ctx
    assert "wallet" in ctx
    assert "financial path" in ctx.lower()
    assert "migration" in ctx.lower()
    assert "env-gate" in ctx
    assert "match no risk rule" in ctx  # the unclassified-paths warning


def test_summary_line_is_compact_and_informative():
    line = classification.parse_classification(WALLET_PAYLOAD).summary_line()
    assert "risk=critical" in line
    assert "financial" in line
    assert "gate-signals=env-gate" in line


# --------------------------------------------------------------------------- #
# invocation + degradation
# --------------------------------------------------------------------------- #


def _fake_run(stdout="", returncode=0, exc=None):
    def _run(argv, **kwargs):
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="boom")

    return _run


def test_classify_diff_parses_binary_output(monkeypatch, tmp_path):
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=json.dumps(WALLET_PAYLOAD)))

    c = classification.classify_diff(diff="diff --git a/x b/x\n", binary=str(fake_bin))
    assert c is not None
    assert c.risk == "critical"


def test_classify_diff_returns_none_on_empty_diff():
    assert classification.classify_diff(diff="") is None
    assert classification.classify_diff(diff="   \n") is None


def test_classify_diff_returns_none_when_binary_missing(monkeypatch):
    monkeypatch.setattr(classification, "classify_binary", lambda: None)
    assert classification.classify_diff(diff="diff --git a/x b/x\n") is None


@pytest.mark.parametrize(
    "runner",
    [
        _fake_run(returncode=3),                       # INVALID_INPUT
        _fake_run(stdout="not json at all"),           # unparsable
        _fake_run(exc=OSError("no such binary")),      # exec failure
        _fake_run(exc=subprocess.TimeoutExpired("classify", 60)),
    ],
)
def test_classify_diff_degrades_to_none(monkeypatch, tmp_path, runner):
    """A classification failure must never break a run — it only stops adding
    its safety net."""
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", runner)
    assert classification.classify_diff(diff="diff --git a/x b/x\n", binary=str(fake_bin)) is None


# --------------------------------------------------------------------------- #
# classify_diff_result: WHY there is no classification (GO-1)
#
# classify_diff() collapses "no binary" and "the binary failed" into one None,
# which is only safe for callers that can never relax a gate on None. Callers
# that could self-approve need the difference.
# --------------------------------------------------------------------------- #


def test_result_reports_absent_when_the_binary_is_missing(monkeypatch):
    monkeypatch.setattr(classification, "classify_binary", lambda: None)
    r = classification.classify_diff_result(diff="diff --git a/x b/x\n")
    assert r.status == classification.CLASSIFY_ABSENT
    assert r.absent and not r.failed and not r.ok


def test_result_reports_empty_rather_than_failed_on_an_empty_diff():
    r = classification.classify_diff_result(diff="   \n")
    assert r.status == classification.CLASSIFY_EMPTY
    assert not r.failed


@pytest.mark.parametrize(
    "runner, needle",
    [
        (_fake_run(returncode=3), "exited 3"),
        (_fake_run(stdout="not json at all"), "unparsable JSON"),
        (_fake_run(exc=OSError("no such binary")), "invocation failed"),
        (_fake_run(exc=subprocess.TimeoutExpired("classify", 60)), "invocation failed"),
    ],
)
def test_result_reports_failed_when_a_present_binary_does_not_answer(
    monkeypatch, tmp_path, runner, needle
):
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", runner)

    r = classification.classify_diff_result(
        diff="diff --git a/x b/x\n", binary=str(fake_bin)
    )

    assert r.status == classification.CLASSIFY_FAILED
    assert r.failed and not r.ok and r.classification is None
    assert needle in (r.detail or "")


def test_result_reports_failed_on_json_that_is_not_a_classification(
    monkeypatch, tmp_path
):
    """Exit 0, valid JSON, wrong shape — a rule-table or contract regression."""
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout='{"panel": {"seats": "?"}}'))

    r = classification.classify_diff_result(
        diff="diff --git a/x b/x\n", binary=str(fake_bin)
    )

    assert r.status == classification.CLASSIFY_FAILED
    assert "unusable classify output" in (r.detail or "")


def test_result_is_ok_on_a_good_answer(monkeypatch, tmp_path):
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=json.dumps(WALLET_PAYLOAD)))

    r = classification.classify_diff_result(
        diff="diff --git a/x b/x\n", binary=str(fake_bin)
    )

    assert r.status == classification.CLASSIFY_OK
    assert r.ok and not r.failed
    assert r.classification.risk == "critical"


def test_classify_binary_honours_env_override(monkeypatch, tmp_path):
    real = tmp_path / "classify"
    real.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CLASSIFY_BIN", str(real))
    assert classification.classify_binary() == str(real)

    monkeypatch.setenv("CLASSIFY_BIN", str(tmp_path / "nope"))
    assert classification.classify_binary() is None


# --------------------------------------------------------------------------- #
# the panel gate
# --------------------------------------------------------------------------- #


FULL = classification.parse_classification(WALLET_PAYLOAD)
# A complete producer payload for the reduced-panel case. It used to omit every
# policy-bearing field except risk and panel, and parsed fine — which is exactly
# the permissiveness the round-3 findings closed. It now has to be a real
# payload, and its collection-time failure was the first proof the validation
# bites.
REDUCED = classification.parse_classification({
    "risk": "low",
    "financial_paths_touched": False,
    "client_only": True,
    "server_surface": False,
    "migration": False,
    "human_pr_gate": False,
    "panel": {"required": True, "seats": 1, "reduced": True},
})


def test_panel_required_unchanged_without_a_classification():
    """The existing metadata behaviour is untouched when no classification is
    supplied — this change is additive."""
    assert cfr.panel_required(["risk:critical"]) is True
    assert cfr.panel_required(["size:S"]) is False
    assert cfr.panel_required(["risk:critical"], task_type="docs") is False


def test_path_evidence_forces_the_panel_over_an_unlabelled_ticket():
    """The PR 1294 shape: no risk label, but the diff touches money."""
    assert cfr.panel_required([], classification=FULL) is True
    assert cfr.panel_required(None, classification=FULL) is True


def test_path_evidence_overrides_the_docs_type_skip():
    """A 'docs' ticket whose diff touches a wallet file is a mislabelled ticket,
    not a docs ticket."""
    assert cfr.panel_required(["size:XS"], task_type="docs") is False
    assert cfr.panel_required(["size:XS"], task_type="docs", classification=FULL) is True


def test_a_reduced_classification_never_cancels_a_labelled_panel():
    """One-directional: path evidence adds review, it never removes it."""
    assert cfr.panel_required(["risk:critical"], classification=REDUCED) is True


def test_a_reduced_classification_leaves_a_skip_a_skip():
    assert cfr.panel_required(["size:S"], classification=REDUCED) is False


def test_none_classification_is_the_old_behaviour_exactly():
    for labels in ([], ["risk:critical"], ["size:S"], None):
        assert cfr.panel_required(labels, classification=None) == cfr.panel_required(labels)


# --------------------------------------------------------------------------- #
# the prompt
# --------------------------------------------------------------------------- #


def test_review_prompt_carries_the_risk_context():
    prompt = cfr.build_review_prompt(
        family="claude",
        ticket_key="SMG-1",
        ticket_summary="s",
        summary_md="m",
        diff="diff --git a/x b/x",
        branch="feat/x",
        base_branch="main",
        risk_context=FULL.review_context(),
    )
    assert "critical" in prompt
    assert "wallet" in prompt
    assert "hard per-dimension floors" in prompt


def test_review_prompt_says_so_when_classification_is_unavailable():
    """An absent tier must read as absent, not as 'low'."""
    prompt = cfr.build_review_prompt(
        family="claude",
        ticket_key="SMG-1",
        ticket_summary="s",
        summary_md="m",
        diff="diff --git a/x b/x",
        branch="feat/x",
        base_branch="main",
    )
    assert "classification unavailable" in prompt


# --------------------------------------------------------------------------- #
# Wire-contract validation (GO-1 round 3, codex seat)
# --------------------------------------------------------------------------- #
#
# Strictness that stops at `risk` is not strictness. The parser still coerced
# every policy-bearing field, and bool("false") is True — so a producer emitting
# a JSON string where a bool belongs silently INVERTED a gate.

def test_a_healthy_producer_payload_still_parses():
    c = classification.parse_classification(dict(_GOOD))
    assert c.risk == "low"
    assert c.requires_full_panel is True


def test_the_codex_reproduction_is_rejected():
    """Verbatim from the finding: the signal string filters to (), while
    bool("false") makes panel_reduced True and suppresses the panel."""
    bad = dict(_GOOD, gate_signals="env-gate", panel={"reduced": "false"})
    with pytest.raises(ValueError, match="panel.reduced"):
        classification.parse_classification(bad)


@pytest.mark.parametrize("key", [
    "financial_paths_touched", "client_only", "server_surface",
    "migration", "human_pr_gate",
])
def test_a_missing_policy_bool_is_rejected(key):
    bad = dict(_GOOD)
    del bad[key]
    with pytest.raises(ValueError, match=key):
        classification.parse_classification(bad)


@pytest.mark.parametrize("bogus", ["false", "true", 0, 1, None, [], {}])
def test_a_non_boolean_policy_field_is_rejected(bogus):
    """bool("false") is True; bool(0) is False. Coercion inverts gates."""
    bad = dict(_GOOD, financial_paths_touched=bogus)
    with pytest.raises(ValueError, match="financial_paths_touched"):
        classification.parse_classification(bad)


@pytest.mark.parametrize("panel", [
    "reduced", {"seats": 5}, {"reduced": "false"}, {"reduced": None},
    {"reduced": False, "seats": 0}, {"reduced": False, "seats": "5"},
])
def test_a_malformed_panel_block_is_rejected(panel):
    with pytest.raises(ValueError, match="panel"):
        classification.parse_classification(dict(_GOOD, panel=panel))


def test_absent_gate_signals_means_none_but_a_bare_string_is_rejected():
    """gate_signals is omitempty on the producer, so absent genuinely means
    "no signals" — but a present bare string would filter to an empty tuple,
    silently discarding every signal it named."""
    assert classification.parse_classification(dict(_GOOD)).gate_signals == ()

    with pytest.raises(ValueError, match="gate_signals"):
        classification.parse_classification(dict(_GOOD, gate_signals="env-gate"))
    with pytest.raises(ValueError, match="gate_signals"):
        classification.parse_classification(dict(_GOOD, gate_signals=[{"nope": 1}]))


def test_every_malformed_policy_field_reaches_the_caller_as_failed(monkeypatch, tmp_path):
    """Validation is only useful if it arrives as CLASSIFY_FAILED — the status
    whose whole job is to stop a gate relaxing."""
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    payload = json.dumps(dict(_GOOD, panel={"reduced": "false"}))
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=payload))

    result = classification.classify_diff_result(
        diff="diff --git a/x b/x\n", binary=str(fake_bin)
    )
    assert result.status == classification.CLASSIFY_FAILED
    assert result.classification is None
