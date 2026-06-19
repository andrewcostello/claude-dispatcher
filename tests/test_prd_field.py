"""Contract test for the top-level `prd:` field (plan.feature_prd)."""
import io

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
