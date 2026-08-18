"""Anchor the reviewer's instruction tree to the run, or name the load.

The panel renders ``reviewer_prompts/`` from the RUNNING package, and the run's
genesis already records ``hash_tree`` of that directory as
``reviewer_prompts_hash`` — a fact nothing compares to anything. This module is
that comparison. Every outcome is a named state; there is no "load quietly".

P1 of unit W2-1: contract and stubs. Bodies and wiring are W2-1-3's, the floored
half W2-1-4's (:data:`FLOOR_GLOBS_OWED`, :data:`FLOORED_OBLIGATIONS`).

The five constraints a later editor would otherwise break:

1. READ THEN VERIFY. :func:`check_prompt_tree` takes a :class:`TreeSnapshot` —
   bytes the caller has already read — and digests THOSE BYTES; the caller
   renders from the same object. A path-taking overload reopens the window this
   ordering closes.
2. ONE DIGEST IMPLEMENTATION. ``journal.hash_tree`` delegates to
   :func:`digest_of_snapshot`. A second spelling makes every run read DRIFTED.
3. "NO ANCHOR" IS THREE STATES AND THE DEFAULT REFUSES. An unusable anchor and
   no anchor both refuse; only a process that DECLARED itself journal-less
   (:func:`declare_unanchored`) loads unanchored, and says so. An anchor and a
   declaration never coexist, or dropping the anchor uncovers the declaration.
4. THE ANCHOR IS PER-RUN and a process may hold several. Ambiguity is decided by
   DISAGREEMENT, not by count: where the live anchors attest one digest the
   answer does not depend on which run this load belongs to, and no run identity
   reaches this seam.
5. PUBLISHING IS TOTAL AND NEVER SILENT. :func:`publish_pin_from_genesis` does
   not raise, and its call sites must not wrap it in ``except Exception: pass``;
   a failure it records is constraint 3's refusal.

What this does NOT close: an ADJUDICATE row may still declare ``_shared.md`` in
``disputed_paths:`` and rewrite it. That remedy is floored and handed over. Why
this remedy and not the two unfloored alternatives — including reading the prompt
from the BASE revision, which this unit could have built and did not — is
:data:`REMEDY_DISPOSITIONS`. What is NOT in the class, and on what measurement,
is :data:`OUT_OF_CLASS`.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

#: The instruction trees the review gate EXECUTES, repo-relative. Only the first
#: is anchored — the genesis records a digest for it alone, and giving the second
#: one is floored (:data:`FLOORED_OBLIGATIONS`) — but both are named so neither
#: leaves the class by a reader grepping only for reviewer prompts.
INSTRUCTION_TREES: tuple[str, ...] = (
    "src/claude_dispatcher/reviewer_prompts",
    "src/claude_dispatcher/verifier_prompts",
)

#: Named and deliberately NOT in :data:`INSTRUCTION_TREES`. The class is "bytes a
#: RUNNING dispatcher process opens and hands to the model that judges a diff";
#: a reader who greps for the next most obvious prompt file must find the ruling
#: rather than silence, which is why an exclusion is recorded as data.
OUT_OF_CLASS: tuple[tuple[str, str], ...] = (
    (
        "docs/templates/planner-prompt.md",
        "OUT. Measured 2026-08-17: `grep -rn planner-prompt src/ tools/ tests/ "
        "scripts/` returns nothing — the file is linked from four markdown docs "
        "and is pasted by a HUMAN into a planning agent. No dispatcher code "
        "opens it, so there is no load event for check_prompt_tree to gate and "
        "no run to anchor it to: it is read BEFORE a run exists, and what it "
        "produces is a worklist the panel then judges normally. Out because "
        "this mechanism has no purchase on it, NOT because editing it is "
        "harmless — SEALS may already write it under role_protocol's "
        "`**/docs/**` allowance, and that is a separate question from this one.",
    ),
)

#: Genesis payload keys, read in one place so the two journal entry points cannot
#: disagree. ``run_nonce`` and not ``run_id`` is the identity: it is required of
#: every genesis, where ``run_id`` may be None.
GENESIS_DIGEST_KEY = "reviewer_prompts_hash"
GENESIS_NONCE_KEY = "run_nonce"

#: What :func:`digest_of_snapshot` returns for a tree that is EMPTY **or ABSENT**
#: — ``hash_tree`` walks a missing directory without raising (measured). So an
#: absent tree is DRIFTED against a real anchor. This gate does not police
#: existence; it answers only "did the prompt move".
EMPTY_TREE_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#: The floored half, spelled so W2-1-4 transcribes rather than re-derives it. NOT
#: installed — ``role_protocol.FLOOR_GLOBS`` is glob 3 of its own tuple. Rejected
#: spellings and their probe counts are in this commit's message; two properties
#: a transcription would lose:
#:
#:   * the SUBTREE entries buy DIFF-TIME enforcement only. Measured with both
#:     appended, ``_floor_glob_named_by`` returns None for every spelling of the
#:     declaration — it refuses a pure-wildcard tail by design — so ``validate``
#:     still ACCEPTS a P4 row naming the prompt until a rule over
#:     ``disputed_paths:`` lands beside them;
#:   * the third entry is THIS MODULE, which decides whether the prompt loads
#:     once W2-1-3 wires it. It buys the plan-time reach the subtrees do not.
FLOOR_GLOBS_OWED: tuple[str, ...] = (
    "**/src/claude_dispatcher/reviewer_prompts/**",
    "**/src/claude_dispatcher/verifier_prompts/**",
    "**/src/claude_dispatcher/prompt_provenance.py",
)

#: Obligations this unit cannot discharge because they land in a floored file.
#: Data, not prose, so W2-1-4 transcribes a list and a grep finds them.
FLOORED_OBLIGATIONS: tuple[str, ...] = (
    "role_protocol.py: install FLOOR_GLOBS_OWED, plus a rule over "
    "disputed_paths: — the subtree globs alone do not reach plan time.",
    "orchestrator.py: install a journal-backed reporter via set_load_reporter, "
    "so a load decision lands on the run's own chain and not only on stderr. "
    "Until then the default reporter is all there is.",
    "orchestrator.py or journal.py: give verifier_prompts/ a genesis digest. A "
    "new REQUIRED GENESIS_PROVENANCE_KEYS entry rejects every older journal, so "
    "it is an optional key written where the genesis is built.",
)

#: The four remedies this unit was handed, and which one it is. Data rather than
#: prose because "why not the other one" is asked long after the commit message
#: has scrolled away, and an undispositioned alternative reads as an oversight.
#: Each entry is (remedy, disposition).
REMEDY_DISPOSITIONS: tuple[tuple[str, str], ...] = (
    (
        "prompt trees join role_protocol.FLOOR_GLOBS",
        "OWED, floored. Spelled at FLOOR_GLOBS_OWED for W2-1-4. It is the only "
        "remedy that denies the WRITE, and so the only one that survives a tree "
        "drifted BEFORE a run starts — see the chosen remedy's limit below.",
    ),
    (
        "ADJUDICATE gains a deny row for the two prompt trees",
        "OWED, floored. FLOORED_OBLIGATIONS entry 1, together with the rule "
        "over `disputed_paths:` without which the globs do not reach plan time.",
    ),
    (
        "resolve the prompt from the BASE revision, as scripts/check_body_"
        "branch.sh reads the gate's own code out of <base>'s object store",
        "REJECTED, and NOT because it is floored — it is not; it is a "
        "cross_family_reviewer.py edit this unit could have made. Three "
        "measured reasons, in the order that decides it: (1) WRONG EXPOSURE. "
        "That script's base-read is entered on exactly one condition — the "
        "gate's code lies inside the tree under judgement. `_PROMPTS_DIR = "
        "Path(__file__).parent / 'reviewer_prompts'` means the panel's prompt "
        "comes from the RUNNING package, so that condition holds only in the "
        "dogfooding window. The honest exposure is the other one: the edit "
        "lands, is MERGED, and every later run is judged by it — after which "
        "<base> carries the edit and a base-read returns exactly the rewritten "
        "prompt. (2) NO NAMED STATE. Base-resolution substitutes bytes; it does "
        "not compare, and check_body_branch.sh says why it must not — 'a "
        "comparison is a decision, and differs is the ordinary state of an "
        "honest branch'. It therefore cannot produce the disagreement state "
        "this contract is required to name, because by construction it has "
        "none. (3) NO BASE AT THIS SEAM. That script takes <base> as an "
        "argument; `_load_prompt` is reached from run_panel by the three "
        "journal-less callers in UNANCHORED_ENTRY_POINTS, none of which knows a "
        "protected base, and an installed package has no object store to read. "
        "It is a new mechanism, not a cheaper one.",
    ),
    (
        "compare the loaded tree against the digest the genesis already records "
        "as reviewer_prompts_hash — THIS CONTRACT",
        "CHOSEN. It is unfloored, and the reason it is honest rather than "
        "merely reachable is that it is the only one of the four that answers "
        "the question actually asked: is the tree the panel is about to execute "
        "the tree this run was started with, and if not, say so in a named "
        "state. journal.py:578 already writes the digest and nothing reads it, "
        "so this is a comparison of a recorded fact, not a new mechanism. Its "
        "LIMIT, stated because it is what the floored half is still for: the "
        "anchor attests UNCHANGED-SINCE-GENESIS, not CORRECT. A tree rewritten "
        "before the genesis is hashed is attested by its own drift and refuses "
        "nothing. Only the write denial closes that, and it is owed, not "
        "replaced by remedy 3 — which closes it no better.",
    ),
)

#: Call sites that reach ``cross_family_reviewer._load_prompt`` without ever
#: opening a journal. Each owes a :func:`declare_unanchored` call once W2-1-3
#: wires the gate, or it refuses — which callers are journal-less is the fact
#: that decides whether constraint 3's default breaks a tool.
UNANCHORED_ENTRY_POINTS: tuple[str, ...] = (
    "src/claude_dispatcher/bakeoff.py:384 cfr.run_panel",
    "tools/cross_family_panel.py:110 cfr.run_panel",
    "tools/retroactive_sweep.py:114 cfr.run_panel",
)


class PromptProvenanceError(RuntimeError):
    """Base for this module's refusals."""


class PromptRefusal(PromptProvenanceError):
    """A prompt load that must not happen, carrying the decision that refused it."""

    def __init__(self, decision: "PromptLoad", message: str) -> None:
        # The decision must survive the raise, or a caller re-derives it from
        # message text.
        super().__init__(message)
        self.decision = decision


# --- what a genesis attests --------------------------------------------------


class PinSource(Enum):
    """Which genesis read produced a recorded anchor.

    Both members are genesis-derived and there is none for "a caller hashed the
    tree and anchored that" — but the guarantee is AUDITABLE, not unforgeable:
    :func:`record_anchor` and :func:`digest_of_snapshot` are both public (two
    journal call sites and every seal need the first), so a caller in-process can
    compose a self-anchor. What is enforced is that it must lie about its source
    in writing, since ``source`` and ``detail`` are quoted in every refusal and
    every load record. Closing it is the WRITE denial in
    :data:`FLOOR_GLOBS_OWED`.
    """

    #: ``Journal.create`` computed the digest as it wrote the genesis: tree and
    #: anchor are the same bytes at that instant.
    RUN_START = "run-start"

    #: ``Journal.resume`` read it back off a chain that already passed
    #: ``verify()``. Republication of one digest, never a re-anchor.
    RESUMED_GENESIS = "resumed-genesis"


@dataclass(frozen=True)
class PromptPin:
    """One run's anchor: the digest its genesis attests, and where it came from."""

    #: The SHA-256 recorded under :data:`GENESIS_DIGEST_KEY`, lower-cased.
    digest: str
    #: The genesis ``run_nonce`` — the run's identity.
    run_nonce: str
    #: How the digest reached this process. Never inferred.
    source: PinSource
    #: Which run and journal, in operator words: what a refusal quotes, since one
    #: that cannot say what it compared against gets worked around.
    detail: str

    def __post_init__(self) -> None:
        # A malformed digest compares unequal to every tree, so a fail-closed
        # gate built on one refuses everything — which is how a gate gets
        # switched off. Shape only; the decision is W2-1-2's to seal.
        object.__setattr__(self, "digest", _require_hex64(self.digest, "prompt pin digest"))
        _require_text(self.run_nonce, "prompt pin run_nonce")
        _require_text(self.detail, "prompt pin detail")
        if not isinstance(self.source, PinSource):
            raise ValueError(f"prompt pin source must be a PinSource, got {self.source!r}")


@dataclass(frozen=True)
class AnchorFailure:
    """A genesis that reached the publisher and could not be anchored.

    Narrow by construction: ``build_genesis_payload`` cannot produce one (always
    a fresh ``hash_tree`` and ``token_hex`` nonce), but the genesis check is
    ``[k for k in GENESIS_PROVENANCE_KEYS if k not in event.payload]`` — key
    PRESENCE, never shape. Measured 2026-08-18 by rewriting a created chain's
    genesis to ``"reviewer_prompts_hash": None`` and re-covering its hash:
    ``verify`` returns ``ok=True``, so ``Journal.resume`` hands that payload to
    the publisher. The state is reachable by the input every resumed run takes.
    Do not delete it because the happy path cannot reach it: a total publisher
    needs somewhere to put the answer, and the alternative is a silent skip.
    """

    #: The genesis ``run_nonce``, or ``"unknown:<journal path>"`` when the nonce
    #: is itself the unusable field — keyed by path so repeated failures on one
    #: journal collapse and two journals do not.
    run_nonce: str
    #: Why the anchor is unusable, in operator words.
    reason: str
    #: Which run and journal; same role as :attr:`PromptPin.detail`.
    detail: str

    def __post_init__(self) -> None:
        _require_text(self.run_nonce, "anchor failure run_nonce")
        _require_text(self.reason, "anchor failure reason")
        _require_text(self.detail, "anchor failure detail")


#: What the process holds. Two shapes, both meaning "a genesis happened here";
#: their absence is a third state and is not a value.
Anchor = PromptPin | AnchorFailure


@dataclass(frozen=True)
class UnanchoredDeclaration:
    """An entry point stating on the record that it runs without a journal.

    Consulted ONLY when the process holds no anchor at all, so it can never
    override or weaken a live one.
    """

    #: The entry point, as it appears in :data:`UNANCHORED_ENTRY_POINTS`.
    who: str
    #: Why this caller has no journal. Quoted in the load record.
    reason: str

    def __post_init__(self) -> None:
        _require_text(self.who, "unanchored declaration who")
        _require_text(self.reason, "unanchored declaration reason")


# --- the tree, as bytes ------------------------------------------------------


@dataclass(frozen=True)
class TreeSnapshot:
    """Every file of an instruction tree, read once, in canonical order.

    The digest subject and the render source are one object, which is what makes
    constraint 1 hold: there is no interval between the bytes hashed and the
    bytes rendered for a swap to land in. ``members`` is the WHOLE tree, because
    the anchor is a whole-tree digest; :meth:`render` picks.
    """

    #: Where the members were read from. Reported, never re-read.
    tree_dir: str
    #: Human name of the tree ("reviewer prompts"): a refusal must say which of
    #: the two trees in this class moved.
    what: str
    #: ``(tree-relative posix name, bytes)`` in :func:`canonical_order`.
    members: tuple[tuple[str, bytes], ...]

    def __post_init__(self) -> None:
        # The order check is load-bearing, not tidiness: the same files digested
        # in another order yield a digest matching no anchor.
        _require_text(self.tree_dir, "tree snapshot tree_dir")
        _require_text(self.what, "tree snapshot what")
        if not isinstance(self.members, tuple):
            raise ValueError(
                f"tree snapshot {self.what!r} members must be a tuple, got "
                f"{type(self.members).__name__}; a frozen dataclass over a list "
                "advertises an immutability it does not have"
            )
        names: list[str] = []
        for entry in self.members:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise ValueError(
                    f"tree snapshot {self.what!r} member must be (name, bytes), "
                    f"got {entry!r}"
                )
            name, data = entry
            _require_text(name, "tree snapshot member name")
            if not isinstance(data, bytes):
                raise ValueError(
                    f"tree snapshot {self.what!r} member {name!r} must be bytes, "
                    f"got {type(data).__name__}"
                )
            names.append(name)
        if len(set(names)) != len(names):
            raise ValueError(f"tree snapshot {self.what!r} repeats a member name")
        if names != canonical_order(names):
            raise ValueError(
                f"tree snapshot {self.what!r} members are not in canonical order; "
                "the digest is order-sensitive and would match no anchor"
            )

    def render(self, *names: str, separator: str = "\n\n") -> str:
        """Concatenate the named members, in the order given.

        Total over this module's errors: a missing, empty or undecodable member
        raises :class:`PromptProvenanceError` rather than a bare ``KeyError`` or
        ``UnicodeDecodeError`` out of the load path. EMPTY is refused because a
        reviewer handed an empty preamble is told nothing and answers anyway — a
        route the drift check never sees.
        """
        index = dict(self.members)
        out: list[str] = []
        for name in names:
            if name not in index:
                raise PromptProvenanceError(
                    f"{self.what} has no member {name!r} in {self.tree_dir}"
                )
            data = index[name]
            if not data.strip():
                raise PromptProvenanceError(
                    f"{self.what} member {name!r} is empty; a reviewer rendered "
                    "an empty prompt answers with no instructions"
                )
            try:
                out.append(data.decode("utf-8"))
            except UnicodeDecodeError as e:
                raise PromptProvenanceError(
                    f"{self.what} member {name!r} is not UTF-8: {e}"
                ) from e
        return separator.join(out)


def canonical_order(names: Sequence[str]) -> list[str]:
    """Tree-relative names in the order the digest consumes them.

    Sorted by PATH COMPONENTS, which is what ``hash_tree``'s ``sorted()`` over
    ``Path`` objects does and is NOT sorting the joined strings: measured,
    ``a/b`` sorts before ``a-b/c`` by components and after it by string, because
    ``-`` < ``/``. Getting this wrong changes the digest of any tree with
    subdirectories, and nothing else would say so.
    """
    return sorted(names, key=lambda n: n.split("/"))


#: Width of the length prefix :func:`digest_of_snapshot` writes before every
#: field. 8 bytes big-endian covers any file this process can read into memory.
_LENGTH_PREFIX_BYTES = 8


def digest_of_snapshot(members: Sequence[tuple[str, bytes]]) -> str:
    """The canonical instruction-tree digest, over bytes already in hand.

    THE definition — ``journal.hash_tree`` delegates here, so the anchor a
    genesis records and the digest a load computes cannot drift apart.
    ``members`` must already be in :func:`canonical_order`: re-sorting here would
    silently repair a snapshot that lied about its order.

    Every field is LENGTH-PREFIXED, never delimited. A delimiter must be a byte
    that cannot occur inside a field, and no such byte exists here: file contents
    are arbitrary bytes, so a NUL separator collides — measured,
    ``[("a", b"b\\x00c\\x00")]`` and ``[("a", b"b"), ("c", b"")]`` hash equal
    under it. On a tree of prompt files that is a preimage an editor controls: it
    lets a rewritten tree present the anchored digest. A fixed-width prefix makes
    the encoding injective, so distinct member lists have distinct digests.
    """
    digest = hashlib.sha256()
    for rel, data in members:
        name = rel.encode("utf-8")
        digest.update(len(name).to_bytes(_LENGTH_PREFIX_BYTES, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(_LENGTH_PREFIX_BYTES, "big"))
        digest.update(data)
    return digest.hexdigest()


def read_tree_members(root: str | os.PathLike[str]) -> tuple[tuple[str, bytes], ...]:
    """Every regular file under ``root``, in canonical order; absent root → ``()``.

    One filesystem pass, so the digest and the render cannot come from two reads.
    """
    root_path = Path(root)
    return tuple(
        (p.relative_to(root_path).as_posix(), p.read_bytes())
        for p in sorted(q for q in root_path.rglob("*") if q.is_file())
    )


def snapshot_tree(tree_dir: str | os.PathLike[str], what: str) -> TreeSnapshot:
    """Read a whole instruction tree into a :class:`TreeSnapshot`."""
    return TreeSnapshot(
        tree_dir=str(tree_dir), what=what, members=read_tree_members(tree_dir)
    )


# --- the states --------------------------------------------------------------


class PromptIntegrity(Enum):
    """What is known about the tree about to be loaded. TOTAL over the facts that
    decide it; no member for "matched approximately"."""

    #: Every live anchor is a pin attesting one digest, and the tree matches.
    ANCHORED = "anchored"

    #: One attested digest, and the tree is not it: the tree moved between the
    #: genesis (or the resume) and this load.
    DRIFTED = "drifted"

    #: No anchor, and no entry point said why. Constraint 3's default.
    UNANCHORED = "unanchored"

    #: No anchor, and an entry point declared itself journal-less. The one member
    #: that loads without a comparison — an abstention, not a silence.
    UNANCHORED_DECLARED = "unanchored-declared"

    #: A genesis in this process published an :class:`AnchorFailure`.
    ANCHOR_FAILED = "anchor-failed"

    #: Live pins DISAGREE, and this seam carries no run identity to choose.
    ANCHOR_AMBIGUOUS = "anchor-ambiguous"


class PromptLoad(Enum):
    """What a caller does about a :class:`PromptIntegrity`. Named in every world
    — there is no member spelled "load"."""

    #: Load: the tree is the one the run recorded.
    LOAD_ANCHORED = "load-anchored"

    #: Load, and SAY SO: a declared journal-less caller.
    LOAD_UNANCHORED_DECLARED = "load-unanchored-declared"

    #: Do not load: the tree moved.
    REFUSE_DRIFTED = "refuse-drifted"

    #: Do not load: nothing anchors this tree and nobody said why.
    REFUSE_UNANCHORED = "refuse-unanchored"

    #: Do not load: this run's anchor could not be published.
    REFUSE_ANCHOR_FAILED = "refuse-anchor-failed"

    #: Do not load: live anchors disagree about what this tree should be.
    REFUSE_ANCHOR_AMBIGUOUS = "refuse-anchor-ambiguous"

    @property
    def refuses(self) -> bool:
        """Whether this decision forbids the load. Spelled from the member's own
        name so W2-1-3 cannot re-derive the refusing set as a literal that goes
        stale the day a member is added."""
        return self.name.startswith("REFUSE_")


#: Integrity → decision. TOTAL; a new member lands in :func:`load_decision`'s
#: raise rather than in a default, because the permissive answer here is "load"
#: and "load" is the silence this module exists to remove.
_LOAD_BY_INTEGRITY: dict[PromptIntegrity, PromptLoad] = {
    PromptIntegrity.ANCHORED: PromptLoad.LOAD_ANCHORED,
    PromptIntegrity.DRIFTED: PromptLoad.REFUSE_DRIFTED,
    PromptIntegrity.UNANCHORED: PromptLoad.REFUSE_UNANCHORED,
    PromptIntegrity.UNANCHORED_DECLARED: PromptLoad.LOAD_UNANCHORED_DECLARED,
    PromptIntegrity.ANCHOR_FAILED: PromptLoad.REFUSE_ANCHOR_FAILED,
    PromptIntegrity.ANCHOR_AMBIGUOUS: PromptLoad.REFUSE_ANCHOR_AMBIGUOUS,
}


def load_decision(integrity: PromptIntegrity) -> PromptLoad:
    """The decision for an integrity state. Total; raises on an unmapped member.

    Implemented for the reason ``loop_gate.decision_for`` gives about its own
    table: "every member is mapped, and an unmapped one raises" is not checkable
    against a function that raises for everything.
    """
    try:
        return _LOAD_BY_INTEGRITY[integrity]
    except KeyError:
        raise PromptProvenanceError(
            f"no load decision is defined for {integrity!r}; a new "
            "PromptIntegrity member must be given one here rather than fall "
            "through to whichever branch is last"
        ) from None


def integrity_of(
    anchors: Sequence[Anchor],
    observed_digest: str,
    *,
    declaration: UnanchoredDeclaration | None,
) -> PromptIntegrity:
    """Classify a tree's digest against what this process holds.

    STUB — W2-1-3's body. The ruled mechanics, in this precedence, so it
    transcribes rather than designs and W2-1-2 seals each row separately:

    * any :class:`AnchorFailure` → :attr:`~PromptIntegrity.ANCHOR_FAILED`. It
      wins over pins and over a declaration: a genesis here could not be
      anchored, and this seam cannot tell whether this load is that run's. It is
      therefore sticky for the process, and the recovery is
      :func:`release_anchor` on that key, not a later good publish;
    * else the DISTINCT digests of the live pins decide. Two or more →
      :attr:`~PromptIntegrity.ANCHOR_AMBIGUOUS`. Exactly one →
      :attr:`~PromptIntegrity.ANCHORED` if ``observed_digest`` equals it, else
      :attr:`~PromptIntegrity.DRIFTED`. Agreement suffices because the answer
      does not depend on which run this load belongs to; disagreement does not,
      because it does, and threading a run identity here is ``orchestrator.py``,
      floor glob 17;
    * no anchors → :attr:`~PromptIntegrity.UNANCHORED_DECLARED` when
      ``declaration`` is not None, else :attr:`~PromptIntegrity.UNANCHORED`.

    A BLANK ``observed_digest`` — what a caller passes when it has bytes but no
    digest — is DRIFTED against a pin, never a match: "I could not digest the
    tree" must not answer "the tree is fine".

    Pure by construction: no process state, no filesystem, so a seal drives every
    row without a journal.
    """
    raise NotImplementedError(
        "W2-1-3 lands the classification; this scaffold fixes the contract (W2-1-1)"
    )


# --- the process's anchors ---------------------------------------------------
#
# Process state rather than a parameter because the parameter shape is
# unavailable to any role: every call site that would thread a run identity into
# the load seam is in `orchestrator.py`, floor glob 17. The pins live in the
# process that published them, so a load in a CHILD process sees none and
# refuses — the wiring must keep `_load_prompt` in the process that opened the
# journal, or declare.

_anchor_lock = threading.Lock()
_anchors: list[Anchor] = []
_declaration: UnanchoredDeclaration | None = None


def record_anchor(anchor: Anchor) -> None:
    """Publish one anchor. Additive; an exactly identical one is not repeated.

    Deliberately holds no merge rule. A second pin for a nonce ADDS rather than
    overwrites, so a republication that disagrees becomes two distinct digests
    and :func:`integrity_of` refuses; an overwrite would let the later write
    define the anchor, which is the laundering this unit exists to stop.
    ``create`` then ``resume`` of one run adds two pins carrying one digest,
    which is agreement, not ambiguity.

    Publishing REVOKES any declaration: a process that reached a genesis is not
    journal-less, whatever it said earlier. Without this the two facts coexist
    and :func:`release_anchor` re-exposes the stale declaration — an ANCHORED
    process becoming UNANCHORED_DECLARED, which LOADS. See
    :func:`declare_unanchored` for the other half of the invariant.
    """
    global _declaration
    if not isinstance(anchor, (PromptPin, AnchorFailure)):
        raise TypeError(f"record_anchor takes an Anchor, got {type(anchor).__name__}")
    with _anchor_lock:
        if anchor not in _anchors:
            _anchors.append(anchor)
        _declaration = None


def live_anchors() -> tuple[Anchor, ...]:
    """Every anchor published in this process, in publication order."""
    with _anchor_lock:
        return tuple(_anchors)


def release_anchor(run_nonce: str) -> int:
    """Drop every anchor under ``run_nonce``; returns how many.

    The PRODUCTION eviction seam: a run releases its own anchor and cannot blank
    another's. It cannot open the gate — releasing the last anchor leaves
    UNANCHORED, which refuses, and never UNANCHORED_DECLARED, because
    :func:`record_anchor` and :func:`declare_unanchored` keep an anchor and a
    declaration from ever coexisting for this function to uncover. It is the
    documented recovery from a sticky ANCHOR_FAILED.
    """
    _require_text(run_nonce, "release_anchor run_nonce")
    with _anchor_lock:
        before = len(_anchors)
        _anchors[:] = [a for a in _anchors if a.run_nonce != run_nonce]
        return before - len(_anchors)


def clear_anchors() -> None:
    """Reset every process fact this module holds. TEST FIXTURE ONLY.

    Owned by the autouse fixture W2-1-2 lands in ``tests/conftest.py``; a single
    known caller is what keeps those seals from being order-dependent. Production
    code uses :func:`release_anchor`. Not a fail-open switch under constraint 3 —
    clearing leaves UNANCHORED, which refuses — but it drops the declaration too,
    so a journal-less tool that calls it stops loading.
    """
    global _declaration
    with _anchor_lock:
        _anchors.clear()
        _declaration = None


def declare_unanchored(who: str, reason: str) -> UnanchoredDeclaration:
    """Record that this process runs without a journal, and may load anyway.

    The module's one permissive seam, so it is narrow and named: consulted only
    when no anchor exists, carried into the load record, and owed by exactly the
    call sites in :data:`UNANCHORED_ENTRY_POINTS`. A second call replaces the
    first — a process is journal-less or it is not.

    RAISES while any anchor is live, rather than being stored and outranked. A
    stored one survives :func:`release_anchor` and turns the resulting no-anchor
    state permissive; refusing here is the invariant's other half, and it is a
    raise because a caller holding a genesis asking to be excused from it is a
    wiring bug, not a state to record.
    """
    global _declaration
    declaration = UnanchoredDeclaration(who=who, reason=reason)
    with _anchor_lock:
        if _anchors:
            raise PromptProvenanceError(
                f"{who} declared itself journal-less while this process holds "
                f"{len(_anchors)} anchor(s); a declaration outlives the anchors "
                "it is stored beside and would make releasing them permissive"
            )
        _declaration = declaration
    return declaration


def live_declaration() -> UnanchoredDeclaration | None:
    """The declaration in force, or None."""
    with _anchor_lock:
        return _declaration


def publish_pin_from_genesis(
    payload: Mapping[str, Any], *, source: PinSource, detail: str
) -> PromptPin | None:
    """Read the anchor out of a genesis payload and publish it. Total; never raises.

    STUB — W2-1-3's body, landing with its two call sites in one commit. The
    ruled mechanics:

    * read :data:`GENESIS_DIGEST_KEY` and :data:`GENESIS_NONCE_KEY`, build a
      :class:`PromptPin` with ``source`` and ``detail``, publish it with
      :func:`record_anchor`, return it;
    * a missing, blank or malformed value of EITHER key publishes an
      :class:`AnchorFailure` instead, warns to stderr quoting the RAW value, and
      returns None. Raw, not coerced: an absent key and a non-string both render
      as ``''`` otherwise. Where the NONCE is the unusable field, key the failure
      ``f"unknown:{journal_path}"``;
    * it does not raise, and callers must not wrap it in
      ``except Exception: pass``. A journal is never a precondition for a run, so
      a bad anchor must not take down a dispatch; constraint 5 is that it must
      not be invisible either.

    THE TWO CALL SITES IT IS OWED, both in ``journal.py`` (unfloored), neither
    wired here because a stub on the live path breaks every run that opens a
    journal:

    * ``Journal.create``, AFTER the genesis append and its ``fsync``, with
      ``source=PinSource.RUN_START`` — so a genesis that failed to write leaves
      no anchor claiming it succeeded;
    * ``Journal.resume``, from the genesis event the chain already verified, with
      ``source=PinSource.RESUMED_GENESIS``. Anchoring only in ``create`` leaves
      every RESUMED run unanchored, and a resume is exactly the span in which the
      installed tree moves without anyone doing anything wrong (an operator
      reinstall). In ``Journal.resume`` rather than ``resume.execute`` so
      ``merge_prs``'s own call gets it too.

    A tree that moved across that interruption is REFUSE_DRIFTED for that run's
    life. That is the ruling: the remedy is a NEW run, recording the new tree on
    a new chain an operator can see. Re-anchoring a resumed run against the tree
    in front of it is the laundering constraint 4 forbids.

    NOT owed a call site: ``orchestrator._open_journal``'s ``except`` branch. It
    returns None and publishes nothing, so the run holds no anchor and every load
    REFUSES as UNANCHORED. Were absence a load, that branch would be the live way
    to switch this gate off and would need a floored edit to close.
    """
    raise NotImplementedError(
        "W2-1-3 lands the parser and its two journal call sites; this scaffold "
        "fixes the contract (W2-1-1)"
    )


# --- reporting the decision --------------------------------------------------


@dataclass(frozen=True)
class PromptLoadRecord:
    """One load decision, in a form something other than a human can keep.

    Stderr is not where a run is reconstructed from: a wave dispatching dozens of
    tasks with three reviewers each produces a warning per seat that nobody
    reads, and the journal would say nothing about which prompt judged what.
    """

    decision: PromptLoad
    what: str
    tree_dir: str
    observed_digest: str
    #: The digest the anchors agreed on, or None when there was none to agree.
    anchor_digest: str | None = None
    #: The winning anchor's ``detail``, or the declaration's ``reason``.
    anchor_detail: str | None = None
    members: tuple[str, ...] = ()


#: Called with EVERY decision, including the anchored one — a reporter that only
#: hears about problems cannot answer "which prompt judged this task".
LoadReporter = Callable[[PromptLoadRecord], None]


def default_load_reporter(record: PromptLoadRecord) -> None:
    """Warn to stderr for anything but a clean anchored load, which stays silent
    or the one line that matters is skimmed. Refusals are not printed here: they
    raise, and the exception carries them."""
    if record.decision is PromptLoad.LOAD_ANCHORED:
        return
    sys.stderr.write(
        f"warning: {record.what} loaded {record.decision.value} "
        f"({record.tree_dir}): {record.anchor_detail or 'no anchor in this process'}\n"
    )


_reporter: LoadReporter = default_load_reporter


def set_load_reporter(reporter: LoadReporter) -> LoadReporter:
    """Install the sink for load records; returns the previous one.

    The seam ``orchestrator.py`` uses to put these on the run's chain — owed, and
    floored, so it is in :data:`FLOORED_OBLIGATIONS`. Until it lands the default
    is all there is, and this says so rather than implying the journal sees them.
    """
    global _reporter
    previous = _reporter
    _reporter = reporter
    return previous


def report_load(record: PromptLoadRecord) -> None:
    """Hand a record to the installed reporter. A reporter that raises is a bug in
    the reporter, not grounds to skip the gate: the exception propagates rather
    than being swallowed into a silent load."""
    _reporter(record)


def check_prompt_tree(loaded: TreeSnapshot) -> PromptLoad:
    """Gate one prompt-tree load against this process's anchors.

    STUB — W2-1-3's body, wired into ``cross_family_reviewer._load_prompt`` in
    the SAME commit. The ruled mechanics:

    * digest ``loaded.members`` with :func:`digest_of_snapshot` — the bytes the
      caller already holds, never a second walk of ``loaded.tree_dir``. That is
      constraint 1, and the reason this takes a snapshot and not a path;
    * ``decision = load_decision(integrity_of(live_anchors(), digest,
      declaration=live_declaration()))``;
    * build a :class:`PromptLoadRecord` and :func:`report_load` it for EVERY
      decision, before returning or raising;
    * :attr:`~PromptLoad.refuses` → raise :class:`PromptRefusal` carrying the
      decision and naming ``loaded.what``, ``loaded.tree_dir``, the member names
      and — for a drift — BOTH digests with the anchor's ``detail`` and
      ``source``. This refusal can block a whole wave, and one an operator cannot
      diagnose gets worked around;
    * otherwise return the decision. The caller renders from ``loaded`` — the
      object that was hashed — and must not re-read the directory.

    An ABSENT tree does not raise here: it digests to :data:`EMPTY_TREE_DIGEST`
    and compares normally. Existence is the loader's question.
    """
    raise NotImplementedError(
        "W2-1-3 lands the drift check and its wiring into "
        "cross_family_reviewer._load_prompt; this scaffold fixes the contract "
        "(W2-1-1). The floored half — FLOOR_GLOBS_OWED and FLOORED_OBLIGATIONS "
        "— is W2-1-4's handover and is NOT closed here"
    )


def _require_text(value: object, what: str) -> str:
    """Refuse a blank or non-string field. Shared so the validated types cannot
    disagree about what "present" means."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be non-blank text, got {value!r}")
    return value


def _require_hex64(value: object, what: str) -> str:
    """Refuse anything that is not a bare SHA-256, and return it lower-cased.

    Case-folded rather than case-checked: ``hexdigest()`` is lower case today,
    but a producer that ever changed would fail every pin construction and turn
    every journalled run into a refusal — a spelling difference must not read as
    tampering.
    """
    _require_text(value, what)
    text = str(value).strip().lower()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise ValueError(
            f"{what} must be a 64-hex SHA-256, got {value!r}; a malformed "
            "anchor compares unequal to every tree and would refuse every load"
        )
    return text
