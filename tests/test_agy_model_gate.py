"""Tests for agy (Antigravity CLI) model selection + the cross-model gate.

agy ignores a launch-time `--model` and reads its engine from a global
settings.json. The dispatcher therefore (a) never passes `--model` to agy and
(b) mutates settings.json under a gate that lets same-model spawns run in
parallel while serializing different-model spawns so they can't clobber the
shared file. These tests pin all three behaviours.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from claude_dispatcher import spawn


def _read_model(p: Path) -> str:
    return json.loads(p.read_text())["model"]


# --- settings.json mutation ------------------------------------------------

def test_write_agy_model_preserves_other_keys(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"model": "Gemini 3.5 Flash (Medium)", "theme": "dark"}))
    spawn._write_agy_model("Gemini 3.1 Pro (High)", p)
    data = json.loads(p.read_text())
    assert data["model"] == "Gemini 3.1 Pro (High)"
    assert data["theme"] == "dark"  # unrelated keys survive


def test_write_agy_model_creates_missing_file_and_parents(tmp_path):
    p = tmp_path / "nested" / "settings.json"  # parent dir does not exist
    spawn._write_agy_model("Gemini 3.1 Pro (Low)", p)
    assert _read_model(p) == "Gemini 3.1 Pro (Low)"


def test_write_agy_model_tolerates_corrupt_file(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{ not valid json")
    spawn._write_agy_model("Claude Opus 4.6 (Thinking)", p)
    assert _read_model(p) == "Claude Opus 4.6 (Thinking)"


# --- argv no longer smuggles the model ------------------------------------

def test_gemini_argv_has_no_model_flag(tmp_path):
    argv = spawn._agent_argv(
        "gemini", "agy", tmp_path / "p.txt", tmp_path,
        model="Gemini 3.1 Pro (High)", prompt_text="do the thing", effort="high",
    )
    assert "--model" not in argv
    # the model string must not leak in as a positional either
    assert "Gemini 3.1 Pro (High)" not in argv
    assert argv[0] == "agy"
    assert "--print" in argv


# --- the cross-model gate --------------------------------------------------

def test_gate_same_model_runs_concurrently(tmp_path):
    gate = spawn._AgyModelGate(tmp_path / "settings.json")
    gate.acquire("Gemini 3.1 Pro (High)")
    done = threading.Event()

    def second():
        gate.acquire("Gemini 3.1 Pro (High)")  # same model -> must not block
        done.set()

    t = threading.Thread(target=second)
    t.start()
    assert done.wait(timeout=2.0), "same-model acquire should not block"
    gate.release()
    gate.release()
    t.join()


def test_gate_different_model_serializes_and_does_not_clobber(tmp_path):
    p = tmp_path / "settings.json"
    gate = spawn._AgyModelGate(p)

    gate.acquire("Gemini 3.1 Pro (High)")
    assert _read_model(p) == "Gemini 3.1 Pro (High)"

    entered = threading.Event()
    proceeded = threading.Event()

    def other():
        entered.set()
        gate.acquire("Gemini 3.5 Flash (Medium)")  # different -> must wait
        proceeded.set()

    t = threading.Thread(target=other)
    t.start()
    assert entered.wait(timeout=2.0)
    # While the Pro cohort is live, the Flash acquire blocks AND the file is
    # not rewritten out from under the running Pro process.
    assert not proceeded.wait(timeout=0.5), "different-model acquire should block"
    assert _read_model(p) == "Gemini 3.1 Pro (High)"

    gate.release()  # drain the Pro cohort -> Flash may proceed
    assert proceeded.wait(timeout=2.0), "blocked acquire should proceed after drain"
    assert _read_model(p) == "Gemini 3.5 Flash (Medium)"
    gate.release()
    t.join()


def test_gate_none_model_leaves_file_untouched(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"model": "Gemini 3.5 Flash (Medium)"}))
    gate = spawn._AgyModelGate(p)
    gate.acquire(None)  # None cohort must not rewrite settings.json
    assert _read_model(p) == "Gemini 3.5 Flash (Medium)"
    gate.release()
