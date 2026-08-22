"""Seals for DF-5-1's money-net contract [DF-5-2].

The task: seal the RELATIONSHIP between ``cli.DEFAULT_FINANCIAL_PATHS`` (the
shipped fallback) and the tracked money table — not a transcription of either.
A count or a literal goes green the moment someone pastes a new literal; the
relationship stays red until the defect is actually gone.

Three seal groups:

1. **Drift** — the shipped fallback must carry exactly the financial paths
   the authoritative tracked table carries. RED today: the table at the
   authoritative commit holds 74 unique financial paths and 49 are absent
   from the fallback, including all six the task names.
2. **Retirement** — the condemned surfaces (the fallback constant and its
   parity-test file) must be gone, and the derivation body must land in the
   same commit that retires them (the DF-3-1 one-commit rule). RED today,
   green when DF-5-3 lands, red again on revert.
3. **Contract** — the implemented halves of DF-5-1 (the record's
   unconstructible illegal shapes, both folds, the table fold) behave as
   ruled. Green today; these bind the seals to real names so DF-5-3 is a
   transcription, not a design.

Shape rulings, each fixing a measured vacuity (panel review of the previous
attempt):

* **No defect-conditioned xfail.** A marker conditioned on "the fallback
  exists" re-arms when DF-5-3 is reverted, so the revert turns the suite
  green — the exact vacuity the task forbids. The red rows here are plain
  assertions: red while the defect ships, green when it retires, red again
  on revert, with no edit to this file in between.
* **The authoritative read is fail-closed and never skips.** The table is
  read from one explicitly selected repository (``EVENPLAY_MONO_ROOT`` env
  override, else the documented default checkout) at one pinned commit —
  full 40-hex SHA, so the content is immutable wherever the object exists.
  There is no branch search and no fallback candidate list. Every failure
  mode — missing checkout, missing object, path absent at the commit,
  any other git error — is a test FAILURE carrying git's stderr, each with
  a distinct message. A machine that cannot see the authority reports red,
  never a silent pass.
* **Retirement expectations are this file's own.** The required retired
  surfaces are hardcoded here (:data:`REQUIRED_RETIREMENTS`) and asserted
  directly; production's ``CONDEMNED_SURFACES`` tuple is separately sealed
  to still *name* them, so clearing or weakening that tuple cannot quietly
  pass the retirement seals.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import cli, money_net
from claude_dispatcher.money_net import (
    ABSENT_ENV_VALUE,
    TABLE_RELPATH,
    MoneyNet,
    MoneyNetSource,
    MoneyNetState,
    derive_money_net,
    financial_globs_from_table,
)

# --------------------------------------------------------------------------- #
# The authority: one repository, one pinned commit. No search, no fallback.
# --------------------------------------------------------------------------- #

#: Env var naming the evenplay-mono checkout to read the table from.
REPO_ENV = "EVENPLAY_MONO_ROOT"

#: The documented default checkout when the env var is unset.
DEFAULT_REPO = Path.home() / "Project" / "evenplay-mono"

#: PR #1387's branch tip — the commit DF-5-1's contract measured the drift
#: against. A full SHA pins immutable content: any checkout that has this
#: object yields byte-identical table JSON.
AUTHORITATIVE_COMMIT = "164d3a828764e4261615d756b15bd52461b787a5"

#: The surfaces DF-5-3 must retire, stated here independently of
#: production's CONDEMNED_SURFACES so weakening that tuple cannot weaken
#: these seals.
REQUIRED_RETIREMENTS = (
    "claude_dispatcher.cli.DEFAULT_FINANCIAL_PATHS",
    "tests/test_default_financial_paths.py",
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


def _authoritative_table_json() -> str:
    """Read the tracked table at the pinned commit, fail-closed.

    Every branch below is ``pytest.fail`` — this helper never skips and
    never swallows a git error. The messages are distinct so a red row says
    which of the four failure modes it is.
    """
    override = os.environ.get(REPO_ENV, "").strip()
    repo = Path(override) if override else DEFAULT_REPO

    probe = _git(repo, "rev-parse", "--git-dir")
    if probe.returncode != 0:
        pytest.fail(
            f"authoritative checkout unavailable: {repo} is not a git "
            f"repository (set ${REPO_ENV} to an evenplay-mono checkout that "
            f"has commit {AUTHORITATIVE_COMMIT}). git stderr: "
            f"{probe.stderr.strip()}"
        )
    has_commit = _git(repo, "cat-file", "-e", f"{AUTHORITATIVE_COMMIT}^{{commit}}")
    if has_commit.returncode != 0:
        pytest.fail(
            f"authoritative commit {AUTHORITATIVE_COMMIT} is not present in "
            f"{repo} — fetch PR #1387's branch (fix/agent-config-money-paths) "
            f"or point ${REPO_ENV} at a checkout that has it. git stderr: "
            f"{has_commit.stderr.strip()}"
        )
    has_path = _git(
        repo, "cat-file", "-e", f"{AUTHORITATIVE_COMMIT}:{TABLE_RELPATH}"
    )
    if has_path.returncode != 0:
        pytest.fail(
            f"{TABLE_RELPATH} is absent at the authoritative commit "
            f"{AUTHORITATIVE_COMMIT} — this contradicts DF-5-1's measured "
            "contract and needs a human look, not a skip. git stderr: "
            f"{has_path.stderr.strip()}"
        )
    blob = _git(
        repo, "cat-file", "blob", f"{AUTHORITATIVE_COMMIT}:{TABLE_RELPATH}"
    )
    if blob.returncode != 0:
        pytest.fail(
            "git object read failed for "
            f"{AUTHORITATIVE_COMMIT}:{TABLE_RELPATH} in {repo} — an "
            "operational git failure, not an absence. git stderr: "
            f"{blob.stderr.strip()}"
        )
    return blob.stdout


# --------------------------------------------------------------------------- #
# Group 1 — drift: the relationship between the fallback and the table.
# RED today (49 of the table's 74 financial paths are absent from the
# fallback). Self-retires structurally: once DF-5-3 removes the constant
# there is no fallback to drift, and group 2 seals that removal directly.
# Reverting DF-5-3 restores the constant and this row goes red again.
# --------------------------------------------------------------------------- #


def test_shipped_fallback_has_not_drifted_from_the_tracked_table() -> None:
    fallback_csv = getattr(cli, "DEFAULT_FINANCIAL_PATHS", None)
    if fallback_csv is None:
        # Retired end-state: no hand list exists to drift. The retirement
        # itself is sealed independently by group 2, so this early return
        # cannot hide a missing net.
        return
    fallback = fallback_csv.split(",")
    table = financial_globs_from_table(_authoritative_table_json())
    missing = [g for g in table if g not in fallback]
    extra = [e for e in fallback if e not in table]
    assert not missing and not extra, (
        "cli.DEFAULT_FINANCIAL_PATHS has drifted from the tracked table "
        f"({TABLE_RELPATH} @ {AUTHORITATIVE_COMMIT[:12]}): "
        f"{len(missing)} table path(s) missing from the fallback "
        f"(under-gating) {missing!r}; {len(extra)} fallback entr(ies) the "
        f"table does not carry (noise) {extra!r}. Do not re-sync the "
        "literal — syncing buys a day. DF-5-3 retires the fallback and "
        "derives the net from the table (money_net.derive_money_net)."
    )


# --------------------------------------------------------------------------- #
# Group 2 — retirement: the condemned surfaces are gone, and body + wiring +
# retirement land as one commit. The two absence rows are RED today.
# --------------------------------------------------------------------------- #


def test_condemned_fallback_constant_is_retired() -> None:
    assert not hasattr(cli, "DEFAULT_FINANCIAL_PATHS"), (
        f"{REQUIRED_RETIREMENTS[0]} still ships. It is a condemned second "
        "hand-list of the money table (DF-5-1); DF-5-3 must retire it in "
        "the same commit that wires derive_money_net in."
    )


def test_condemned_parity_test_file_is_retired() -> None:
    parity = Path(__file__).parent / "test_default_financial_paths.py"
    assert not parity.exists(), (
        f"{REQUIRED_RETIREMENTS[1]} still exists. Its truth source is an "
        "untracked mirror frozen pre-#1387 (DF-5-1, measurement 1) — it is "
        "the hand-list bug with a file read in front of it, and it retires "
        "with the fallback constant."
    )


def test_condemned_surfaces_tuple_still_names_the_retired_surfaces() -> None:
    # Guards the production tuple against weakening: the retirement seals
    # above assert this file's own expectations, and this row pins the
    # production record to (at least) the same surfaces.
    for surface in REQUIRED_RETIREMENTS:
        assert surface in money_net.CONDEMNED_SURFACES, (
            f"money_net.CONDEMNED_SURFACES no longer names {surface!r} — "
            "the condemnation record must not be weakened while the seals "
            "in this file still require that retirement."
        )


def _derivation_is_stubbed(scratch: Path) -> bool:
    """True iff derive_money_net is still DF-5-1's NotImplementedError stub.

    ``scratch`` is not a git repository, so a landed body cannot reach a
    DERIVED result here — per the ruled mechanics it folds the failure to
    ABSENT (or raises something operational). Only the stub raises
    NotImplementedError.
    """
    try:
        derive_money_net(scratch, "HEAD")
    except NotImplementedError:
        return True
    except Exception:
        return False
    return False


def test_derivation_body_and_fallback_retirement_land_together(
    tmp_path: Path,
) -> None:
    # The DF-3-1 one-commit rule, as a relationship: a wired stub breaks
    # every run; an unwired body is a silent no-op. Green today (stub +
    # fallback both present), green after DF-5-3 (both gone), red on any
    # split — including a revert that restores only one of them.
    stubbed = _derivation_is_stubbed(tmp_path)
    fallback_present = hasattr(cli, "DEFAULT_FINANCIAL_PATHS")
    assert stubbed == fallback_present, (
        "derive_money_net's body and DEFAULT_FINANCIAL_PATHS' retirement "
        "must land in one commit: "
        f"derivation stubbed={stubbed}, fallback present={fallback_present}. "
        "A landed body with the fallback still shipping is a silent no-op; "
        "a retired fallback with the stub still in place breaks every run."
    )


# --------------------------------------------------------------------------- #
# Group 3 — contract: DF-5-1's implemented halves. Green today.
# --------------------------------------------------------------------------- #


def test_source_enum_has_no_member_for_the_measured_defect_shapes() -> None:
    # The structural exclusion: a shipped constant, an untracked working-tree
    # file, and another checkout's mirror have no enum member, so a net from
    # those sources is unconstructible. Exact equality is the seal — adding
    # any member is a contract change and must come here first.
    assert {m.value for m in MoneyNetSource} == {
        "tracked-table",
        "operator-override",
    }, (
        "MoneyNetSource grew or lost a member. The contract admits exactly "
        "two provenances: the tracked table at the run's base ref, and an "
        "explicit operator override. A shipped constant, an untracked file, "
        "and a mirror checkout are the three measured defect shapes and "
        "must stay unrepresentable."
    )


def _tracked_net(globs: tuple[str, ...]) -> MoneyNet:
    return MoneyNet(
        state=MoneyNetState.DERIVED,
        financial_globs=globs,
        source=MoneyNetSource.TRACKED_TABLE,
        base_ref="origin/main",
        table_blob_sha="a" * 40,
    )


def test_derived_fold_round_trips_the_comma_grammar() -> None:
    globs = (
        "apps/finance-domain/wallet/**",
        "cmd/bay-session/main.go",  # exact-file row: legal (measurement 3)
        "store/liability*",
    )
    net = _tracked_net(globs)
    assert net.env_value() == ",".join(globs)
    assert tuple(net.env_value().split(",")) == globs
    assert TABLE_RELPATH in net.plan_value()
    assert "origin/main" in net.plan_value()


def test_absent_fold_is_the_universal_glob() -> None:
    net = MoneyNet(state=MoneyNetState.ABSENT, detail="no table at ref X")
    assert net.env_value() == ABSENT_ENV_VALUE == "**", (
        "the ABSENT fold must be the universal glob: an empty string is the "
        "dead-net bug (GO-0) and a sentinel word matches nothing — both "
        "silently under-gate an unaware matcher"
    )
    assert "no table at ref X" in net.plan_value()
    assert "fail-closed" in net.plan_value()


def test_empty_derived_net_is_unconstructible() -> None:
    with pytest.raises(ValueError, match="ABSENT"):
        MoneyNet(
            state=MoneyNetState.DERIVED,
            financial_globs=(),
            source=MoneyNetSource.TRACKED_TABLE,
            base_ref="origin/main",
            table_blob_sha="a" * 40,
        )


def test_derived_net_without_a_source_is_unconstructible() -> None:
    with pytest.raises(ValueError, match="source"):
        MoneyNet(
            state=MoneyNetState.DERIVED,
            financial_globs=("apps/finance-domain/wallet/**",),
        )


def test_tracked_table_net_requires_ref_and_blob_witness() -> None:
    with pytest.raises(ValueError, match="base ref"):
        MoneyNet(
            state=MoneyNetState.DERIVED,
            financial_globs=("apps/finance-domain/wallet/**",),
            source=MoneyNetSource.TRACKED_TABLE,
            table_blob_sha="a" * 40,
        )
    with pytest.raises(ValueError, match="blob SHA"):
        MoneyNet(
            state=MoneyNetState.DERIVED,
            financial_globs=("apps/finance-domain/wallet/**",),
            source=MoneyNetSource.TRACKED_TABLE,
            base_ref="origin/main",
            table_blob_sha="not-a-sha",
        )


def test_operator_override_carries_no_table_provenance() -> None:
    with pytest.raises(ValueError, match="operator override"):
        MoneyNet(
            state=MoneyNetState.DERIVED,
            financial_globs=("apps/finance-domain/wallet/**",),
            source=MoneyNetSource.OPERATOR_OVERRIDE,
            base_ref="origin/main",
        )


def test_absent_net_requires_detail_and_carries_nothing() -> None:
    with pytest.raises(ValueError, match="say why"):
        MoneyNet(state=MoneyNetState.ABSENT)
    with pytest.raises(ValueError, match="no globs"):
        MoneyNet(
            state=MoneyNetState.ABSENT,
            detail="x",
            financial_globs=("apps/finance-domain/wallet/**",),
        )
    with pytest.raises(ValueError, match="no source provenance"):
        MoneyNet(
            state=MoneyNetState.ABSENT,
            detail="x",
            source=MoneyNetSource.TRACKED_TABLE,
        )


def test_a_glob_with_a_comma_is_unconstructible() -> None:
    # A comma inside one glob would corrupt the comma-joined env fold into
    # two different globs for every consumer.
    with pytest.raises(ValueError, match="comma"):
        _tracked_net(("store/{a,b}*",))


def test_table_fold_filters_dedupes_and_accepts_exact_file_rows() -> None:
    table = json.dumps(
        {
            "rules": [
                {"financial": True, "paths": ["apps/finance-domain/wallet/**"]},
                {"financial": False, "paths": ["docs/**"]},
                {
                    "financial": True,
                    # Exact file, no wildcard — 14 of the authoritative
                    # table's 74 rows have this shape (measurement 3).
                    "paths": ["cmd/bay-session/main.go",
                              "apps/finance-domain/wallet/**"],
                },
            ]
        }
    )
    assert financial_globs_from_table(table) == (
        "apps/finance-domain/wallet/**",
        "cmd/bay-session/main.go",
    )


def test_table_fold_refuses_malformed_tables() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        financial_globs_from_table("{nope")
    with pytest.raises(ValueError, match="'rules' list"):
        financial_globs_from_table(json.dumps({"paths": []}))
    with pytest.raises(ValueError, match="'paths' list"):
        financial_globs_from_table(
            json.dumps({"rules": [{"financial": True, "paths": "wallet/**"}]})
        )


def test_zero_financial_rules_folds_to_empty_for_the_caller() -> None:
    # () is not a legal DERIVED net (see the unconstructibility seal above):
    # the caller must fold this to ABSENT with a named reason, never to an
    # empty net.
    table = json.dumps({"rules": [{"financial": False, "paths": ["docs/**"]}]})
    assert financial_globs_from_table(table) == ()
