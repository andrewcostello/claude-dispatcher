"""Shared fixtures for the boundary (PR0) seals.

T6 (design §12 harness rules): every parametrised seal in tests/boundary
must carry at least one deny row. The convention enforced here is the id
prefix ``deny-`` on pytest.param ids; ``test_pr0.test_t6_every_parametrized
_module_has_a_deny_case`` walks this directory's ASTs and fails any
parametrised module without one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = REPO_ROOT / "schema"
VECTORS_DIR = REPO_ROOT / "tests/boundary/vectors/t19"

# The dispatcher package is normally importable via PYTHONPATH=src (see
# .dispatcher.yaml's test command); keep worktree runs working regardless.
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


@pytest.fixture(scope="session")
def schemas() -> dict:
    out = {}
    for name in ("lifecycle_fsm", "panel_aggregate", "boundary_errors",
                 "classifier_protocol", "ast_allowlists"):
        with open(SCHEMA_DIR / f"{name}.yaml", encoding="utf-8") as fh:
            out[name] = yaml.safe_load(fh)
    return out


@pytest.fixture(scope="session")
def generated():
    from claude_dispatcher.boundary import generated as g
    return g


def load_vectors() -> dict[str, dict]:
    out = {}
    for path in sorted(VECTORS_DIR.glob("*.json")):
        out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return out
