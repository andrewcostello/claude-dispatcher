"""Contract test for the top-level `prd:` field (skipped; PRD-1 body-fill un-skips)."""
import io

import pytest
from ruamel.yaml import YAML

from claude_dispatcher import plan


def _doc(yaml_text):
    return YAML().load(io.StringIO(yaml_text))


_TASKS = """tasks:
  - key: T1
    summary: s
    description: d
    type: Task
    labels: [size:S]
"""


def test_feature_prd_returns_path_when_present():
    doc = _doc("prd: features/x/PRD.md\n" + _TASKS)
    assert plan.feature_prd(doc) == "features/x/PRD.md"


def test_feature_prd_none_when_absent():
    assert plan.feature_prd(_doc(_TASKS)) is None


def test_feature_prd_none_when_blank():
    assert plan.feature_prd(_doc("prd: '  '\n" + _TASKS)) is None


def test_feature_prd_rejects_non_string():
    # A non-string prd (list/mapping/number) is a config error, not silently
    # stringified — consistent with plan.py's strict field handling.
    with pytest.raises(plan.ValidationError):
        plan.feature_prd(_doc("prd: [a, b]\n" + _TASKS))
