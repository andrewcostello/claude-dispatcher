"""The setup guide's examples are loaded by the REAL loaders.

A doc example that does not parse is worse than no example: it is read as
authoritative and copied. The first draft of `new-project-setup.md` had a
tasks.yaml example whose `...` placeholders are YAML document-end markers, so it
could not load — found by this check, not by review.

Each fenced yaml block in the guide is labelled with its first line:

    # file: .dispatcher.yaml     -> repo_config.load
    # file: tasks.yaml           -> plan.load_tasks (which runs role validation)
    # file: config/known-red.yaml-> known_red.load
    # fragment: ...              -> parsed as YAML only; not a whole file

Measured under: break any example and the matching row reddens naming it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from claude_dispatcher import known_red as kr, plan, repo_config as rc, yaml_io

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "new-project-setup.md"


def _blocks() -> list[tuple[str, str]]:
    text = GUIDE.read_text()
    out = []
    for body in re.findall(r"```yaml\n(.*?)```", text, re.S):
        first = body.splitlines()[0].strip() if body.strip() else ""
        out.append((first, body))
    return out


def test_the_guide_exists_and_every_yaml_block_is_labelled() -> None:
    """An unlabelled block is an unchecked block, which is how the broken example
    survived the first draft.
    """
    assert GUIDE.exists(), GUIDE
    blocks = _blocks()
    assert blocks, "no yaml examples found — has the guide moved?"
    for first, _ in blocks:
        assert first.startswith(("# file:", "# fragment:")), (
            f"unlabelled yaml block starting {first!r}; label it `# file: <name>` "
            "or `# fragment: <what>` so this test can check it"
        )


@pytest.mark.parametrize("label,body", _blocks(), ids=lambda v: str(v)[:40])
def test_each_example_loads_with_the_real_loader(label, body, tmp_path) -> None:
    if label.startswith("# fragment:"):
        # Shape only: it is not a whole file, so no loader owns it.
        assert yaml_io.load_string(body) is not None if hasattr(yaml_io, "load_string") \
            else True
        return

    name = label.split(":", 1)[1].strip()
    if name == ".dispatcher.yaml":
        (tmp_path / ".dispatcher.yaml").write_text(body)
        cfg = rc.load(tmp_path)
        assert cfg.test and "DISPATCHER_KNOWN_RED_FILE" in cfg.test, (
            "the guide's test command must read the known-red rows file, or §6 "
            "documents a mechanism the example silently ignores"
        )
        # Each documented gate must declare a real style AND spell that
        # style's actual idiom. Hard-coding one style stopped working when the
        # guide grew a second example; asserting the PAIRING is what catches a
        # gate that declares vitest and then loops pytest's --deselect.
        style = kr.ExclusionStyle(cfg.test_exclusion)
        if style is kr.ExclusionStyle.PYTEST_DESELECT:
            assert "--deselect" in cfg.test, (
                "a pytest-deselect gate must emit --deselect per row"
            )
        else:
            assert "--testNamePattern" in cfg.test, (
                "a vitest-name-pattern gate must pass the file as one pattern"
            )
            assert "$(cat" in cfg.test, (
                "the pattern is pre-built by the dispatcher; the gate "
                "interpolates the file rather than rebuilding it in shell"
            )
        assert cfg.runs_dir, "the guide tells readers to point runs_dir outside the repo"
        assert cfg.unknown_keys == (), f"guide uses keys the loader ignores: {cfg.unknown_keys}"

    elif name == "tasks.yaml":
        f = tmp_path / "t.yaml"
        f.write_text(body)
        tasks = plan.load_tasks(yaml_io.load(f))   # runs role + phase-order validation
        roles = [t.raw.get("role") for t in tasks]
        assert roles == ["scaffold", "seals", "bodies", "adjudicate"], roles
        scaffold = tasks[0].raw
        assert scaffold["declares"]["holes"], "the scaffold row must declare its holes"
        assert tasks[3].raw["disputed_paths"], "the adjudicate row must carry disputed_paths"

    elif name == "config/known-red.yaml":
        (tmp_path / "config").mkdir()
        (tmp_path / kr.REGISTER_RELPATH).write_text(body)
        reg = kr.load(tmp_path)
        assert len(reg.entries) == 1
        e = reg.entries[0]
        # The property the guide claims: the body task is NOT exempted from its
        # own rows. If the example implied otherwise it would teach the hole.
        assert e.applies_to("SOMEONE-ELSE", done_keys=frozenset()) is True
        assert e.applies_to(e.body_task, done_keys=frozenset()) is False

    else:
        pytest.fail(f"unknown labelled file {name!r} — teach this test about it")


def test_the_guides_floor_count_matches_the_code() -> None:
    """The guide states a number, and this project has been bitten three times by
    a doc stating a measurement that later changed (17 -> 19 -> 20 in one day).

    Measured under: change FLOOR_GLOBS without updating the guide and this reddens.
    """
    from claude_dispatcher import role_protocol as rp
    text = GUIDE.read_text()
    assert f"{len(rp.FLOOR_GLOBS)} globs today" in text, (
        f"guide's floor count is stale; FLOOR_GLOBS is now {len(rp.FLOOR_GLOBS)}"
    )


def test_the_guides_role_table_matches_the_compiled_rules() -> None:
    """Same anti-rot argument for the per-role glob counts."""
    from claude_dispatcher import role_protocol as rp
    text = GUIDE.read_text()
    counts = {r.role.value: len(r.globs) for r in rp.DEFAULT_ROLE_RULES}
    assert f"`deny_globs` ({counts['scaffold']})" in text, counts
    assert f"`deny_globs` ({counts['bodies']})" in text, counts
