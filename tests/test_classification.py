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


def test_parse_classification_tolerates_a_sparse_payload():
    c = classification.parse_classification({})
    assert c.risk == "low"
    assert c.components == ()
    assert c.requires_full_panel is True  # absent panel block defaults to full


def test_requires_full_panel_follows_the_reduced_flag():
    full = classification.parse_classification(WALLET_PAYLOAD)
    assert full.requires_full_panel is True

    reduced = classification.parse_classification(
        {"risk": "low", "panel": {"required": True, "seats": 1, "reduced": True}}
    )
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


# GO-1: the strict entry point tells "absent" from "present but failed".


def test_classify_diff_strict_returns_none_only_when_the_binary_is_absent(monkeypatch):
    monkeypatch.setattr(classification, "classify_binary", lambda: None)
    assert classification.classify_diff_strict(diff="diff --git a/x b/x\n") is None
    assert classification.classify_diff_strict(diff="") is None


@pytest.mark.parametrize(
    "runner, needle",
    [
        (_fake_run(returncode=3), "classify exited 3: boom"),
        (_fake_run(returncode=1, stdout=json.dumps(WALLET_PAYLOAD)), "classify exited 1"),
        (_fake_run(stdout="not json at all"), "unusable output (JSONDecodeError"),
        (_fake_run(stdout=json.dumps({"panel": {"seats": "many"}})), "unusable output (ValueError"),
        (_fake_run(exc=OSError("no such binary")), "invocation failed (OSError"),
        (_fake_run(exc=subprocess.TimeoutExpired("classify", 60)), "invocation failed (TimeoutExpired"),
        (_fake_run(exc=RuntimeError("anything")), "invocation failed (RuntimeError"),
    ],
)
def test_classify_diff_strict_raises_when_a_present_binary_fails(
    monkeypatch, tmp_path, runner, needle
):
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", runner)
    with pytest.raises(classification.ClassificationError, match=needle.replace("(", "\\(")):
        classification.classify_diff_strict(diff="diff --git a/x b/x\n", binary=str(fake_bin))
    # The lenient wrapper still collapses the same failure to None.
    assert classification.classify_diff(diff="diff --git a/x b/x\n", binary=str(fake_bin)) is None


def test_classify_diff_strict_parses_binary_output(monkeypatch, tmp_path):
    fake_bin = tmp_path / "classify"
    fake_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=json.dumps(WALLET_PAYLOAD)))
    c = classification.classify_diff_strict(diff="diff --git a/x b/x\n", binary=str(fake_bin))
    assert c is not None and c.risk == "critical"


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
REDUCED = classification.parse_classification(
    {"risk": "low", "panel": {"required": True, "seats": 1, "reduced": True}}
)


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


@pytest.fixture(autouse=True)
def _journal_less_test_process():
    from claude_dispatcher import prompt_provenance as pp
    pp.declare_unanchored("tests/test_classification.py", "test process: no run journal")
