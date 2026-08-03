"""Shared fixtures for the boundary (PR0) seals.

T6 (design §12 harness rules): every parametrised seal in tests/boundary
must carry at least one deny row. The check runs over the COLLECTED pytest
items' real param ids (see ``test_pr0.test_t6_every_parametrized_seal_has_a
_deny_row``) — collection-time introspection, not a substring scan, so
dynamically-built param lists are covered too. The convention is an id
starting with ``deny``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = REPO_ROOT / "schema"

# The dispatcher package is normally importable via PYTHONPATH=src (see
# scripts/test.sh); keep worktree runs working regardless.
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
