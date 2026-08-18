"""The declaration spaces a per-file signature gate cannot see.

``role_protocol.compare_signatures`` compares one file at a time, so a symbol
arriving in a NEW file is an added symbol and an added symbol is not a change.
TypeScript's declaration merging turns that into a bypass: a second file widens
an interface sealed in the first and the gate reports nothing. This module is
the branch-wide half — the symbol algebra over MERGED declaration spaces. It is
unfloored so it can be built, sealed and reviewed on its own;
``role_protocol._compare_branch_signatures`` is floor glob 3 and reaches it
through one transcribed call, specified in ``docs/branch-surface-amendment.md``.

THE RULE, one level up from ``compare_signatures``' own. Build each declaration
space's merged symbol map at both revisions; a key is a branch-level change iff

  1. it exists at base,
  2. some head file contributes to it that contributed nothing to it at base,
  3. its merged fingerprint differs from base's.

Clause 1 keeps "an added symbol is not a change" — the ruled rule this unit may
not reverse. Clause 2 keeps the fold from re-reporting what the per-file loop
already reported. Clause 3 makes a MOVE — the same contribution from a
different file — silent here; the per-file loop still reports the removal from
the file it left, so a move stays REFUSED as it is today, and which way that
boundary should fall is W2-2-4's to rule.

WHICH ENROLLED LANGUAGES CAN EXPRESS IT, measured, one row each in
:data:`SURFACE_RULES`: typescript merges across files and is the only one. Go
shares a package but every cross-file contribution to it is an ADDED key
(a method keys as ``Recv.Name``; redeclaring an existing key does not compile).
Python has no cross-file declaration space at all. So the fold reads nothing on
a diff with no TypeScript in it, which is why it can sit on the gate path.

WHAT THIS DESIGN CANNOT DO — each is UNREAD, which is UNDETERMINED, never a
pass:

  * ``declare global`` targets a space no enumeration bounds.
  * a SCRIPT file's top-level declarations are global too, and no comparator
    reports module-ness today. A TypeScript file with no proof of being an
    external module (:attr:`FileSurface.module_evidence`) has its own
    declarations routed to the global space rather than to its own, so two
    scripts declaring one interface cannot pass as two unrelated files.

    MEASURED, and it is what makes this expensive rather than free: the
    fingerprinter puts the ``export`` modifier in the fingerprint VALUE, not
    the key — ``export interface Bet {…}`` keys as ``i:Bet`` with value
    ``[export]interface …``, byte-identical in key to the script spelling. So
    key-derived evidence cannot see an ordinary exported declaration, and
    every changed ``.ts`` file that is not caught by one of the three proofs
    reads UNDETERMINED. Closing it needs ``is_module`` (``ts.isExternalModule``)
    reported by the helper, or the export modifier keyed; both are floored
    (``role_protocol.py`` and the parser directory are floor globs 3 and 12).
    The fail-open alternative is the bypass this unit exists to close, so the
    default is stated here and the boundary is W2-2-4's to rule.
  * a specifier that does not resolve to exactly one attempted file, including
    the ``sub.ts`` / ``sub/index.ts`` pair, whose aliasing was a measured false
    positive.

WHAT THIS SCAFFOLD LEAVES UNDONE, on purpose: :func:`build_surface`,
:func:`compare_surfaces` and :func:`_fold`. Every judgement the seals will
score — routing, ambiguity, unread policy, revision selection, fault
precedence, the emitted result — is inside one of those three. Everything else
here is a data type, a validation, or a composition that decides nothing.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Collection, Iterable, Sequence

from .role_protocol import (
    TS_KEY_TAGS,
    TYPESCRIPT_SUPPORT,
    ComparatorUnavailable,
    Language,
    RoleDiffError,
    SignatureChange,
    SignatureCheckStatus,
    SourceUnparseable,
    _worst_signature_status,
    file_text_at,
    signature_status_for_fault,
    support_for_path,
    ts_symbol_key,
)

# `_worst_signature_status` and `signature_status_for_fault` are imported and
# never re-derived: the rank of one status against another, and the
# fault -> status map, each have exactly one home. A second copy here would be
# a gate that can disagree with itself about which reason wins.


class BranchSurfaceError(ValueError):
    """A CALLER bug: inputs from which no surface can be built.

    Never raised for a fact about a branch. An unreadable file, an unresolvable
    specifier and a space nobody can enumerate are all UNREAD, which is a
    reportable state carried in the result. :func:`fold_branch_signatures`
    converts this into ``role_protocol.RoleDiffError`` before returning,
    because that is the only exception ``check_branch`` maps to UNDETERMINED.
    """


# --------------------------------------------------------------------------- #
# Declaration spaces
# --------------------------------------------------------------------------- #


class NamespaceKind(Enum):
    """Where a key lands, and whether any read can complete it.

    FILE
        One TypeScript module. Enumerable — the space is one path, so "did the
        caller read it" is a set membership test rather than a claim.
    GLOBAL
        TypeScript's ambient global space: ``declare global``, and the
        top-level declarations of any file not known to be a module. No path
        list bounds it.
    UNRESOLVED
        A ``declare module`` specifier this gate cannot map to one file.

    There is deliberately no directory-shaped kind. A Go package is one, but Go
    does not merge (:data:`SURFACE_RULES`), so a directory space would be a
    namespace no attempted-path set could ever prove read.
    """

    FILE = "file"
    GLOBAL = "global"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Namespace:
    """One declaration space.

    ``name`` is a repo-relative posix path with its language suffix stripped
    (FILE), the specifier verbatim (UNRESOLVED), or empty (GLOBAL).
    ``language`` is part of the IDENTITY: without it ``src/f.py`` and
    ``src/f.ts`` are one space.
    """

    language: Language
    kind: NamespaceKind
    name: str = ""

    def __post_init__(self) -> None:
        if self.kind is NamespaceKind.FILE and not self.name:
            raise BranchSurfaceError("a FILE namespace needs a path")
        if self.kind is NamespaceKind.GLOBAL and self.name:
            raise BranchSurfaceError(
                f"the global space has no name; got {self.name!r}"
            )
        if self.kind is NamespaceKind.FILE and (
            self.name.startswith("/") or "\\" in self.name
        ):
            raise BranchSurfaceError(
                f"{self.name!r} is not a repo-relative posix path"
            )

    @property
    def enumerable(self) -> bool:
        """Whether a caller can name every file that may contribute here."""
        return self.kind is NamespaceKind.FILE

    @property
    def label(self) -> str:
        """Stable text for a report and for a seal's expectation."""
        if self.kind is NamespaceKind.FILE:
            return f"{self.language.value}:{self.name}"
        inner = f"{self.kind.value} {self.name}".strip()
        return f"{self.language.value}:<{inner}>"


@dataclass(frozen=True)
class SymbolKey:
    """One symbol in one declaration space, across every file that declares it."""

    namespace: Namespace
    qualname: str

    def __post_init__(self) -> None:
        if not self.qualname:
            raise BranchSurfaceError("a symbol key needs a qualname")

    @property
    def label(self) -> str:
        return f"{self.namespace.label}::{self.qualname}"


@dataclass(frozen=True)
class LanguageSurfaceRule:
    """Whether one language can express a cross-file widening, and why.

    The ``why`` is the measurement, not a preference: a language whose row says
    False costs the fold nothing, so a wrong row is a silently disabled gate.
    """

    language: Language
    merges_across_files: bool
    why: str


SURFACE_RULES: tuple[LanguageSurfaceRule, ...] = (
    LanguageSurfaceRule(
        language=Language.PYTHON,
        merges_across_files=False,
        why=(
            "a module is a file; a second module declaring the same name "
            "declares a different symbol, and the substitution that makes "
            "that a bypass is a call-site question"
        ),
    ),
    LanguageSurfaceRule(
        language=Language.GO,
        merges_across_files=False,
        why=(
            "a package is shared, but every cross-file contribution to it is "
            "an ADDED key — a method keys as Recv.Name and redeclaring an "
            "existing key does not compile"
        ),
    ),
    LanguageSurfaceRule(
        language=Language.TYPESCRIPT,
        merges_across_files=True,
        why=(
            "declaration merging: `declare module './a'`, `declare global`, a "
            "re-declared interface in a second script, and a `.d.ts` beside "
            "its source all widen a type from another file"
        ),
    ),
)


def surface_rule_for(language: Language) -> LanguageSurfaceRule:
    """The one row for ``language``.

    Raises rather than defaulting: a missing row read as "does not merge" is a
    gate that switched itself off.
    """
    for rule in SURFACE_RULES:
        if rule.language is language:
            return rule
    raise BranchSurfaceError(
        f"no surface rule for {language.value!r}; every enrolled language "
        "needs one, and absence is not 'does not merge'"
    )


#: TypeScript suffixes, LONGEST FIRST. `w.d.ts` and `w.ts` are one module to
#: every importer, so `.d.ts` must be stripped before `.ts` — strip it second
#: and the sealed symbols and the augmentation land in different namespaces.
TS_NAMESPACE_SUFFIXES: tuple[str, ...] = (".d.ts", ".tsx", ".ts")


def _strip_ts_suffix(path: str) -> str | None:
    """``path`` without its TypeScript suffix, or None if it has none."""
    for suffix in TS_NAMESPACE_SUFFIXES:
        if path.endswith(suffix):
            return path[: -len(suffix)]
    return None


def ts_namespace_of(path: str) -> Namespace:
    """The space a TypeScript MODULE's own top-level declarations land in.

    ``w.ts`` and ``w.d.ts`` share it. When both exist the compiler ignores the
    ``.d.ts``, so merging them here can over-report; it cannot under-report,
    which is the direction this gate is allowed to be wrong in.
    """
    stem = _strip_ts_suffix(path)
    if not stem:
        raise BranchSurfaceError(f"{path!r} is not a TypeScript source path")
    return Namespace(Language.TYPESCRIPT, NamespaceKind.FILE, stem)


#: Where `declare global` lands, and where a file with no proof of being an
#: external module puts its own top-level declarations.
GLOBAL_NAMESPACE = Namespace(Language.TYPESCRIPT, NamespaceKind.GLOBAL)


def unresolved_namespace(specifier: str) -> Namespace:
    """The space of a ``declare module`` target this gate could not locate.

    Keyed BY SPECIFIER: folding every unresolvable target into one bucket makes
    ``interface Bet`` in ``declare module 'a'`` and in ``declare module 'b'``
    one symbol, which invents widenings across unrelated packages.
    """
    return Namespace(Language.TYPESCRIPT, NamespaceKind.UNRESOLVED, specifier)


# --------------------------------------------------------------------------- #
# One file's surface
# --------------------------------------------------------------------------- #


def ts_key_segments(qualname: str) -> tuple[tuple[str, str], ...]:
    """Split a TypeScript symbol key into its ``(tag, text)`` segments.

    The exact inverse of ``ts_symbol_key``. Escape-aware, and that is the whole
    point — a member may be named ``a/b`` or ``i:x``, so splitting on a raw
    ``/`` reads a member name as a container boundary and routes the key into a
    space that does not exist.
    """
    parts: list[str] = []
    text: list[str] = []
    index = 0
    while index < len(qualname):
        char = qualname[index]
        if char == "\\":
            if index + 1 >= len(qualname):
                raise BranchSurfaceError(
                    f"{qualname!r} ends in a dangling escape; no key "
                    "`ts_symbol_key` builds can"
                )
            text.append(qualname[index + 1])
            index += 2
            continue
        if char == "/":
            parts.append("".join(text))
            text = []
            index += 1
            continue
        text.append(char)
        index += 1
    parts.append("".join(text))

    segments: list[tuple[str, str]] = []
    for part in parts:
        if len(part) < 3 or part[1] != ":" or part[0] not in TS_KEY_TAGS:
            raise BranchSurfaceError(
                f"segment {part!r} of {qualname!r} is not <tag>:<text> with a "
                f"tag from {sorted(TS_KEY_TAGS)}"
            )
        segments.append((part[0], part[2:]))
    return tuple(segments)


#: Leading key segments that PROVE a TypeScript file is an external module: an
#: export surface, an anonymous default export, or a relative `declare module`
#: (which the language only permits inside a module). Absence proves nothing —
#: an import-only module has no export surface either — so it is unread, not
#: "script". See `FileSurface.module_evidence`.
_TS_MODULE_EVIDENCE_KEYWORDS: frozenset[str] = frozenset({"export", "default"})


@dataclass(frozen=True)
class FileSurface:
    """One file's fingerprints at one revision, as its comparator reported them.

    ``fingerprints`` is a tuple of pairs rather than a mapping so the whole
    value stays hashable; keys are in the comparator's own key space, before
    any re-rooting.

    ``is_module`` is what a comparator REPORTED about TypeScript module-ness.
    ``None`` means it reported nothing, which is every caller today: no
    fingerprinter carries ``ts.isExternalModule``, and adding it is a floored
    comparator change. It is a tri-state rather than a bool so that "nobody
    looked" cannot be read as "it is a script" or as "it is a module" — the
    first would report every module's declarations as global, the second is
    the bypass this unit exists to close.
    """

    path: str
    language: Language
    fingerprints: tuple[tuple[str, str], ...] = ()
    is_module: bool | None = None

    def __post_init__(self) -> None:
        support = support_for_path(self.path)
        if support is None:
            raise BranchSurfaceError(
                f"{self.path!r} is in no language this gate reads"
            )
        if support.language is not self.language:
            raise BranchSurfaceError(
                f"{self.path!r} is {support.language.value}, not "
                f"{self.language.value}"
            )
        if self.is_module is not None and self.language is not Language.TYPESCRIPT:
            raise BranchSurfaceError(
                f"{self.path!r}: module-ness is a TypeScript fact; reporting "
                f"it for {self.language.value} would give a language with no "
                "cross-file declaration space a routing decision"
            )
        seen: set[str] = set()
        for qualname, fingerprint in self.fingerprints:
            if not qualname or not fingerprint:
                raise BranchSurfaceError(
                    f"{self.path}: empty qualname or fingerprint"
                )
            if qualname in seen:
                raise BranchSurfaceError(
                    f"{self.path}: duplicate key {qualname!r}; one key per "
                    "name is the comparator's own guarantee"
                )
            seen.add(qualname)

    def as_map(self) -> dict[str, str]:
        return dict(self.fingerprints)

    @property
    def module_evidence(self) -> bool:
        """Whether this file's own keys PROVE it is an external module.

        Derived from the key grammar alone, so it needs no comparator change
        and cannot be spoofed by a member name: ``k:export``/``k:default`` are
        keyword slots no identifier can spell, and a RELATIVE ``declare
        module`` specifier is only legal inside a module. A bare specifier
        (``declare module 'lodash'``) is legal in a script and is therefore not
        evidence.

        One-directional. True means module; False means unknown, never script.
        Narrow by measurement, not by choice: ``export interface Bet {…}`` keys
        as ``i:Bet``, with the modifier in the fingerprint VALUE, so an
        ordinary exported declaration is invisible here. Widening this predicate
        means keying the export modifier, which is a floored comparator change.
        """
        if self.language is not Language.TYPESCRIPT:
            return False
        for qualname, _ in self.fingerprints:
            tag, text = ts_key_segments(qualname)[0]
            if tag == "k" and text in _TS_MODULE_EVIDENCE_KEYWORDS:
                return True
            if tag == "s" and text.startswith("."):
                return True
        return False


def augmentation_specifiers(surface: FileSurface) -> tuple[str, ...]:
    """Every ``declare module`` specifier ``surface`` augments, in key order.

    Specifiers only, never the spaces that have no path: a caller feeding this
    list to git must not be handed ``<global>``. Duplicates collapse.
    """
    if surface.language is not Language.TYPESCRIPT:
        return ()
    out: list[str] = []
    for qualname, _ in surface.fingerprints:
        tag, text = ts_key_segments(qualname)[0]
        if tag == "s" and text not in out:
            out.append(text)
    return tuple(out)


def specifier_candidates(path: str, specifier: str) -> tuple[str, ...]:
    """Every file ``specifier``, written in ``path``, could name.

    Empty when the specifier is not relative: a bare or mapped specifier is
    resolved by ``tsconfig.json``, which lives in the tree under judgement, so
    reading it would let a branch decide how its own files are found.

    Enumeration only — both ``./sub`` spellings are returned and NEITHER is
    ranked. ``sub.ts`` and ``sub/index.ts`` are distinct modules when both
    exist, and aliasing them was a measured false positive; :func:`build_surface`
    refuses the ambiguity rather than picking.
    """
    if not specifier.startswith("."):
        return ()
    joined = posixpath.normpath(
        posixpath.join(posixpath.dirname(path), specifier)
    )
    if joined.startswith("..") or joined in (".", "/"):
        return ()
    stem = _strip_ts_suffix(joined) or joined
    return tuple(
        [stem + suffix for suffix in TS_NAMESPACE_SUFFIXES]
        + [f"{stem}/index{suffix}" for suffix in TS_NAMESPACE_SUFFIXES]
    )


# --------------------------------------------------------------------------- #
# A branch's merged surface
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Contribution:
    """One file's part of one merged key."""

    path: str
    fingerprint: str


def merge_fingerprints(contributions: Sequence[Contribution]) -> str:
    """The one fingerprint a merged key has, ordered by PATH.

    Two properties, both load-bearing. A single contribution merges to ITSELF,
    so a one-file space compares exactly as ``compare_signatures`` compares it.
    And the path is not in the text, so moving an identical contribution
    between files does not by itself change the merged fingerprint — which is
    what keeps clause 3 from reporting every move as a widening.
    """
    if not contributions:
        raise BranchSurfaceError("a merged key needs at least one contribution")
    ordered = sorted(contributions, key=lambda c: c.path)
    if len(ordered) == 1:
        return ordered[0].fingerprint
    return " + ".join(c.fingerprint for c in ordered)


@dataclass(frozen=True)
class SurfaceEntry:
    """One merged key and every file that declares it at one revision."""

    key: SymbolKey
    contributions: tuple[Contribution, ...]

    def __post_init__(self) -> None:
        if not self.contributions:
            raise BranchSurfaceError(f"{self.key.label} has no contribution")

    @property
    def paths(self) -> frozenset[str]:
        return frozenset(c.path for c in self.contributions)

    @property
    def merged(self) -> str:
        return merge_fingerprints(self.contributions)


class UnreadReason(Enum):
    """Why a space a contribution landed in could not be compared.

    NOT_ENUMERABLE
        The global space. No path list bounds it.
    UNRESOLVED_SPECIFIER
        Zero or several candidate files for a ``declare module`` target.
    NOT_ATTEMPTED
        An enumerable space whose file the caller never tried to read.
    MODULE_NESS_UNREPORTED
        A TypeScript file whose module-ness no comparator reported and whose
        own keys do not prove it (:attr:`FileSurface.module_evidence`). Its
        top-level declarations may be global, so they are routed there and the
        space is unread. Distinct from NOT_ENUMERABLE because the fix is
        different and nameable: report ``is_module``.
    BUDGET_EXCEEDED
        The closure needed more baseline reads than :data:`MAX_CLOSURE_READS`
        allows, so it was not completed.
    """

    NOT_ENUMERABLE = "not_enumerable"
    UNRESOLVED_SPECIFIER = "unresolved_specifier"
    NOT_ATTEMPTED = "not_attempted"
    MODULE_NESS_UNREPORTED = "module_ness_unreported"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass(frozen=True)
class UnreadNamespace:
    """A space that was not compared, and the reason.

    Never an exception: "I could not look" is an answer this gate must be able
    to report.
    """

    namespace: Namespace
    reason: UnreadReason
    detail: str = ""


@dataclass(frozen=True)
class BranchSurface:
    """One revision's merged declaration spaces.

    ``attempted`` is the completeness claim and the ONLY one: every path the
    caller TRIED to read at this revision, whether or not the tree had it. Two
    facts stay distinct that way — a path attempted and absent has nothing to
    preserve, a path never attempted leaves its space unread — and a free-form
    "namespaces I read" field could not express either.
    """

    entries: tuple[SurfaceEntry, ...] = ()
    attempted: frozenset[str] = frozenset()
    unread: tuple[UnreadNamespace, ...] = ()

    def entry(self, key: SymbolKey) -> SurfaceEntry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None

    def namespace_is_read(self, namespace: Namespace) -> bool:
        """Whether ``attempted`` bounds ``namespace``.

        A FILE space is read when SOME attempted path names it — matched
        through :func:`ts_namespace_of`, never by ``namespace.name in
        attempted``, because the name is the path with its suffix stripped and
        that test would be False for every space this module builds.
        """
        if not namespace.enumerable:
            return False
        return any(
            _strip_ts_suffix(path) == namespace.name for path in self.attempted
        )


@dataclass(frozen=True)
class SurfaceChange:
    """One sealed key widened from somewhere the per-file gate cannot see.

    ``after`` is never None: a key with no head contribution has no NEW
    contributor either, so a removal never reaches this type — it stays the
    per-file loop's finding, reported once, where the file it left is named.
    """

    key: SymbolKey
    before: str
    after: str
    introduced_by: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.introduced_by:
            raise BranchSurfaceError(
                f"{self.key.label}: a widening names the file that introduced "
                "it, or the report cannot say what to edit"
            )

    def as_signature_change(self) -> SignatureChange:
        """The floored driver's vocabulary, so no printer or caller changes.

        ``path`` is the file that introduced the contribution — the file to
        edit — and ``symbol`` carries the namespace, because a qualname alone
        is ambiguous once spaces merge.
        """
        return SignatureChange(
            path=sorted(self.introduced_by)[0],
            symbol=self.key.label,
            before=self.before,
            after=self.after,
        )


@dataclass(frozen=True)
class SurfaceComparison:
    """The branch-wide answer: what widened, and what nobody could look at."""

    changes: tuple[SurfaceChange, ...] = ()
    unread: tuple[UnreadNamespace, ...] = ()

    @property
    def clean(self) -> bool:
        """No widening AND nothing unread. An unread space is not a pass."""
        return not self.changes and not self.unread


# --------------------------------------------------------------------------- #
# The algebra — DECLARED HOLES, W2-2-3's to fill
# --------------------------------------------------------------------------- #


def build_surface(
    files: Sequence[FileSurface], *, attempted: Collection[str]
) -> BranchSurface:
    """Route every file's keys into declaration spaces. ONE REVISION.

    ROUTING, per key, by its leading segment (:func:`ts_key_segments`):

      * ``s:<specifier>`` — an ambient module declaration. Resolve
        ``specifier`` against ``attempted``: exactly one of
        :func:`specifier_candidates` present resolves to that file's
        :func:`ts_namespace_of`; zero or several give
        :func:`unresolved_namespace`, which is UNREAD — never guessed, and
        never aliased, which is what the ``sub.ts`` / ``sub/index.ts`` false
        positive cost. The key lands under the REMAINING segments, re-joined
        with ``ts_symbol_key``; the bare ``s:<specifier>`` key itself is
        DROPPED, since it is the augmenting file's own declaration and its own
        per-file comparison covers it.
      * ``k:global`` — :data:`GLOBAL_NAMESPACE`, under the remaining segments.
      * anything else — the file's OWN space, and which space that is depends
        on module-ness:

          - ``is_module is True``, or :attr:`FileSurface.module_evidence` —
            :func:`ts_namespace_of`, an enumerable FILE space;
          - otherwise :data:`GLOBAL_NAMESPACE`, recorded UNREAD with
            MODULE_NESS_UNREPORTED (or NOT_ENUMERABLE when ``is_module`` is
            False, i.e. the caller said "script"). A script's top-level
            declarations ARE global, so two scripts declaring one interface
            must not read as two unrelated files — that is the bypass with no
            per-file trace at all.

    Contributions to one key are collected across files into one
    :class:`SurfaceEntry`, sorted by path.

    UNREAD, recorded in the result and never raised: every non-enumerable
    space a contribution lands in, plus every FILE space failing
    :meth:`BranchSurface.namespace_is_read`, with NOT_ATTEMPTED.

    REFUSALS, all :class:`BranchSurfaceError`, all caller bugs:

      * a file whose language's :data:`SURFACE_RULES` row says it does not
        merge across files. Its space could never be proven read, and the fold
        must not pay to build one that decides nothing.
      * a file whose own path is not in ``attempted``: the claim and the input
        disagree, and the completeness check would then be vacuous.

    Total in ``files``: every supplied key reaches exactly one space or the one
    documented drop, so a key cannot be silently discarded.
    """
    raise NotImplementedError(
        "W2-2-3 builds this; W2-2-2's rows are red against it until then"
    )


def compare_surfaces(
    base: BranchSurface, head: BranchSurface
) -> SurfaceComparison:
    """The three clauses, over two revisions of the same spaces.

    A key is a :class:`SurfaceChange` iff ALL THREE hold:

      1. ``base.entry(key)`` is not None — an added key is not a change, which
         is the rule this unit may not reverse;
      2. the head entry's ``paths`` contains a path absent from the base
         entry's ``paths`` — a NEW contributor. Without it the fold re-reports
         every in-place edit the per-file loop already reported, and a
         contribution merely REMOVED is misread as a widening;
      3. ``head.merged != base.merged`` — without it a pure move, which is the
         same contribution from a different file, is reported as a widening.

    ``before``/``after`` are the merged fingerprints; ``introduced_by`` is the
    clause-2 path set, sorted.

    UNREAD is the union of both revisions' unread spaces, deduplicated by
    ``(namespace, reason)``. A key in a space unread at EITHER revision is not
    compared: there is nothing to say, and saying "clean" is the pass bought by
    not looking.

    Ordered by ``key.label`` and ``namespace.label`` so a report and a seal see
    one order.
    """
    raise NotImplementedError(
        "W2-2-3 builds this; W2-2-2's rows are red against it until then"
    )


# --------------------------------------------------------------------------- #
# The driver's one call
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BranchFold:
    """What the floored driver splices into its own result.

    ``status`` is CHECKED or a BLOCKING ``UNCHECKED_*``; it is folded through
    ``_worst_signature_status``, so it must be a RANKED member — never
    UNCHECKED_NO_SUPPORTED_FILE, which is the aggregate's own conclusion and
    carries no rank.
    """

    status: SignatureCheckStatus = SignatureCheckStatus.CHECKED
    changes: tuple[SignatureChange, ...] = ()
    detail: str = ""


#: A fold that found nothing and read everything it needed to. The answer for
#: every diff with no merging language in it, which is every diff in this
#: repository today.
CLEAN_FOLD = BranchFold()

#: The most baseline blobs the closure may ask for beyond the changed paths
#: themselves. Six candidates per relative specifier, so this is ~40 augmenting
#: specifiers in one diff. Exceeding it is UNREAD (BUDGET_EXCEEDED), not a
#: silent truncation: the gate's cost must be bounded, and a bound that drops
#: candidates quietly is a bypass anyone can buy with a large diff.
MAX_CLOSURE_READS: int = 256


@dataclass(frozen=True)
class ClosureRequest:
    """The baseline paths a set of head surfaces needs beyond themselves.

    Candidates to TRY, in key order, deduplicated: absent ones are simply
    absent, and :func:`build_surface` reads that as unresolved. Enumeration
    only — nothing here resolves, ranks or reports; the spaces with no path at
    all are :func:`build_surface`'s to record, so a caller may pass this whole
    tuple to git.

    ``truncated`` says :data:`MAX_CLOSURE_READS` was reached, which
    :func:`_fold` must turn into an unread space rather than a shorter read.
    """

    candidates: tuple[str, ...] = ()
    truncated: bool = False


def closure_request(surfaces: Sequence[FileSurface]) -> ClosureRequest:
    """Every candidate path the augmentations in ``surfaces`` could name."""
    candidates: list[str] = []
    seen: set[str] = set()
    for surface in surfaces:
        if not surface_rule_for(surface.language).merges_across_files:
            continue
        for specifier in augmentation_specifiers(surface):
            for candidate in specifier_candidates(surface.path, specifier):
                if candidate in seen:
                    continue
                if len(candidates) >= MAX_CLOSURE_READS:
                    return ClosureRequest(tuple(candidates), truncated=True)
                seen.add(candidate)
                candidates.append(candidate)
    return ClosureRequest(tuple(candidates))


def fold_branch_signatures(
    repo_root: str | Path,
    merge_base: str | None,
    branch_ref: str,
    changed_paths: Sequence[str],
    *,
    run: Callable[..., object] | None,
) -> BranchFold:
    """The branch-wide comparison, as the floored driver receives it.

    THE ERROR CONTRACT, which is why this wrapper exists rather than the driver
    calling :func:`_fold`: ``fingerprints`` raises ``SourceUnparseable`` and
    ``ComparatorUnavailable``, :func:`_fold` may raise
    :class:`BranchSurfaceError`, and ``check_branch`` catches none of them.
    Everything is funnelled here into ``role_protocol.RoleDiffError``, the one
    exception it maps to UNDETERMINED. **No other exception this module can
    raise reaches the floored driver** — including the holes' own
    ``NotImplementedError``, so transcribing the amendment before W2-2-3 lands
    fails CLOSED rather than aborting the gate.

    ``merge_base`` is the MERGE-BASE and never ``base_ref``'s tip: the diff was
    measured from it, and reading a baseline at another revision is the defect
    ``_compare_branch_signatures`` documents. ``None`` is only clean when the
    diff has no merging-language path in it. With one present it is a refusal:
    "there was TypeScript and no baseline to compare it against" is not a pass,
    and the driver reaching here with None and a TypeScript path would mean its
    lazy merge-base was never resolved for a file it did examine.
    """
    try:
        paths = _merging_paths(changed_paths)
        if not paths:
            return CLEAN_FOLD
        if merge_base is None:
            raise RoleDiffError(
                f"the branch-wide signature fold was given no merge-base for "
                f"{len(paths)} path(s) in a language that merges declarations "
                f"across files ({', '.join(paths[:3])}); there is no baseline "
                "to compare a widening against and no honest clean answer"
            )
        return _fold(repo_root, merge_base, branch_ref, paths, run=run)
    except RoleDiffError:
        raise
    except Exception as exc:  # incl. BranchSurfaceError and the holes
        raise RoleDiffError(
            f"the branch-wide signature fold could not complete: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


@dataclass(frozen=True)
class ReadFault:
    """One revision of one file the gate reached for and could not read."""

    path: str
    status: SignatureCheckStatus
    detail: str


def _merging_paths(changed_paths: Sequence[str]) -> tuple[str, ...]:
    """The changed paths whose language merges declarations across files.

    Everything else is dropped BEFORE any read, which is what makes the fold
    free on a diff with no TypeScript in it. Order is the diff's; duplicates
    collapse so a path is never read twice.
    """
    out: list[str] = []
    seen: set[str] = set()
    for path in changed_paths:
        if path in seen:
            continue
        seen.add(path)
        support = support_for_path(path)
        if support is None:
            continue
        if surface_rule_for(support.language).merges_across_files:
            out.append(path)
    return tuple(out)


def _surface_at(
    repo_root: str | Path,
    ref: str,
    path: str,
    *,
    run: Callable[..., object] | None,
) -> tuple[FileSurface | None, ReadFault | None]:
    """One file's surface at one revision, or the fault that stopped it.

    Both ``None`` means ABSENT from that tree, which is a fact and not a
    failure — it is the new-file half of the bypass this unit closes.
    ``ComparatorError`` is turned into a fault here, per file, because neither
    of its subclasses is caught anywhere on the floored gate path.

    ``is_module`` is left unreported: no fingerprinter carries it today, so
    routing falls to :attr:`FileSurface.module_evidence` and, failing that, to
    the unread global space.
    """
    text = file_text_at(repo_root, ref, path, run=run)
    if text is None:
        return None, None
    support = support_for_path(path)
    if support is None:  # pragma: no cover - _merging_paths filtered these
        raise BranchSurfaceError(f"{path!r} is in no language this gate reads")
    try:
        fingerprints = support.fingerprinter.fingerprints(path, text)
    except SourceUnparseable as exc:
        return None, ReadFault(
            path,
            SignatureCheckStatus.UNCHECKED_UNPARSEABLE,
            f"{path} at {ref} does not parse: {exc.message}",
        )
    except ComparatorUnavailable as exc:
        return None, ReadFault(
            path,
            signature_status_for_fault(exc.fault),
            f"{path} at {ref} could not be read: {exc.message}",
        )
    return (
        FileSurface(path, support.language, tuple(sorted(fingerprints.items()))),
        None,
    )


def _fold(
    repo_root: str | Path,
    merge_base: str,
    branch_ref: str,
    paths: Sequence[str],
    *,
    run: Callable[..., object] | None,
) -> BranchFold:
    """The procedure, inside :func:`fold_branch_signatures`' error contract.

    ``paths`` is already :func:`_merging_paths`-filtered and non-empty.

    THE READS, and the bound is the whole reason the order is specified:

      1. each path in ``paths`` at ``merge_base`` and at ``branch_ref``, via
         :func:`_surface_at` — 2 per path. A path absent at ``merge_base`` has
         no base surface and DOES have a head one; that asymmetry IS the
         bypass, so the head surface is recorded whatever the base read said.
      2. :func:`closure_request` over the HEAD surfaces, each candidate not
         already in ``paths`` read at ``merge_base`` ONLY — at most
         :data:`MAX_CLOSURE_READS` more. A path the diff does not name has the
         same content at both revisions (that is what a three-dot diff means),
         so one read serves both surfaces, and reading it at ``branch_ref``
         would be the wrong-revision defect step 1 avoids.

      Total: ``2 * len(paths) + MAX_CLOSURE_READS`` blob reads, and zero on any
      diff that never reaches here. A truncated :class:`ClosureRequest` is an
      unread space (BUDGET_EXCEEDED), never a shorter read.

    ``attempted`` is what was TRIED at each revision — the paths, plus the
    closure candidates for the base — and not the surfaces that came back, so
    "absent from the tree" and "never opened" stay different facts.

    FAULTS SHORT-CIRCUIT, before the surfaces are built: both fault statuses
    rank worse than CHECKED so the branch is refused either way, and building
    on a file that did not parse manufactures unresolved spaces out of the
    fault and reports the wrong reason. Ranked with ``_worst_signature_status``.

    THE RESULT:

      * everything read → CHECKED, widenings as
        :meth:`SurfaceChange.as_signature_change`;
      * a read fault → its status, ranked, with every fault's detail;
      * any unread space out of :func:`compare_surfaces` → raise
        ``RoleDiffError`` naming each one and its reason. There is no status
        for "I could not bound the space", and inventing one is an edit to a
        floored enum; UNDETERMINED is what the gate already says when it could
        not decide.

    ``detail`` names every widening in one clause each, for the line
    ``check_branch`` prints.
    """
    raise NotImplementedError(
        "W2-2-3 builds this; see docs/branch-surface-amendment.md precondition 1"
    )


# --------------------------------------------------------------------------- #
# Behaviour table
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExpectedChange:
    """One widening a row must produce, in full — not just its key.

    Merged fingerprints and the introducing paths are the part a wrong
    implementation gets wrong while still naming the right key, so a seal that
    asserts labels alone passes an algebra that merged the wrong contributions.
    """

    key: str
    before: str
    after: str
    introduced_by: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedUnread:
    """One space a row must report unread, and why it could not be read."""

    namespace: str
    reason: UnreadReason


@dataclass(frozen=True)
class BehaviourRow:
    """One measured input pair and the answer it must produce.

    Inputs, not prose: a seal is

        base = build_surface(row.base, attempted=set(row.base_attempted))
        head = build_surface(row.head, attempted=set(row.head_attempted))
        got = compare_surfaces(base, head)

    asserting ``got.changes`` field-for-field against ``row.changes`` and
    ``got.unread`` against ``row.unread``, with ``row.refused`` rows asserting
    :class:`BranchSurfaceError` out of either ``build_surface`` instead.
    ``is_control`` marks the rows that must stay green under any fix: a change
    that reddens one has broken the gate it was extending.
    """

    name: str
    base: tuple[FileSurface, ...]
    base_attempted: tuple[str, ...]
    head: tuple[FileSurface, ...]
    head_attempted: tuple[str, ...]
    changes: tuple[ExpectedChange, ...] = ()
    unread: tuple[ExpectedUnread, ...] = ()
    refused: bool = False
    is_control: bool = False


def _ts_module(path: str, keys: dict[str, str]) -> FileSurface:
    """A TypeScript file the caller KNOWS is a module."""
    return FileSurface(
        path, Language.TYPESCRIPT, tuple(sorted(keys.items())), is_module=True
    )


def _ts_unknown(path: str, keys: dict[str, str]) -> FileSurface:
    """A TypeScript file no comparator reported module-ness for — today's
    caller, and the input the script bypass arrives on."""
    return FileSurface(path, Language.TYPESCRIPT, tuple(sorted(keys.items())))


def _augment(specifier: str, *segments: tuple[str, str]) -> str:
    """A key inside ``declare module <specifier>``, escaped by the real builder
    so no row hand-spells the ``\\/`` a specifier needs."""
    return ts_symbol_key((("s", specifier),) + segments)


_A = "web/src/a.ts"
_B = "web/src/b.ts"
_NS_A = "typescript:web/src/a"
_BET = ts_symbol_key((("i", "Bet"),))
_BET_X = ts_symbol_key((("i", "Bet"), ("i", "x")))
_EXPORTED = ts_symbol_key((("k", "export"), ("i", "run")))

SURFACE_BEHAVIOUR_ROWS: tuple[BehaviourRow, ...] = (
    BehaviourRow(
        name="in-place widening stays the per-file loop's, reported once",
        base=(_ts_module(_A, {_BET: "A"}),),
        base_attempted=(_A,),
        head=(_ts_module(_A, {_BET: "A2"}),),
        head_attempted=(_A,),
        is_control=True,
    ),
    BehaviourRow(
        name="a new file augmenting a sealed interface is one widening",
        base=(_ts_module(_A, {_BET: "A"}),),
        base_attempted=(_A,),
        head=(
            _ts_module(_A, {_BET: "A"}),
            _ts_module(
                _B,
                {
                    _augment("./a", ("i", "Bet")): "B",
                    _augment("./a", ("i", "Bet"), ("i", "x")): "F",
                },
            ),
        ),
        head_attempted=(_A, _B),
        changes=(
            ExpectedChange(
                key=f"{_NS_A}::{_BET}",
                before="A",
                after="A + B",
                introduced_by=(_B,),
            ),
        ),
    ),
    BehaviourRow(
        name="an augmentation added to a file that already existed",
        base=(_ts_module(_A, {_BET: "A"}), _ts_module(_B, {_EXPORTED: "E"})),
        base_attempted=(_A, _B),
        head=(
            _ts_module(_A, {_BET: "A"}),
            _ts_module(_B, {_EXPORTED: "E", _augment("./a", ("i", "Bet")): "B"}),
        ),
        head_attempted=(_A, _B),
        changes=(
            ExpectedChange(
                key=f"{_NS_A}::{_BET}",
                before="A",
                after="A + B",
                introduced_by=(_B,),
            ),
        ),
    ),
    BehaviourRow(
        name="an unchanged augmentation is not a widening a second time",
        base=(
            _ts_module(_A, {_BET: "A"}),
            _ts_module(_B, {_augment("./a", ("i", "Bet")): "B"}),
        ),
        base_attempted=(_A, _B),
        head=(
            _ts_module(_A, {_BET: "A"}),
            _ts_module(_B, {_augment("./a", ("i", "Bet")): "B"}),
        ),
        head_attempted=(_A, _B),
        is_control=True,
    ),
    BehaviourRow(
        name="an added key is not a change (clause 1, held in isolation)",
        base=(_ts_module(_A, {_BET: "A"}),),
        base_attempted=(_A,),
        head=(_ts_module(_A, {_BET: "A", _BET_X: "F"}),),
        head_attempted=(_A,),
        is_control=True,
    ),
    BehaviourRow(
        name="declare global leaves a space nothing can enumerate",
        base=(_ts_module(_A, {_BET: "A"}),),
        base_attempted=(_A,),
        head=(
            _ts_module(_A, {_BET: "A"}),
            _ts_module(_B, {ts_symbol_key((("k", "global"), ("i", "S"))): "G"}),
        ),
        head_attempted=(_A, _B),
        unread=(
            ExpectedUnread("typescript:<global>", UnreadReason.NOT_ENUMERABLE),
        ),
    ),
    BehaviourRow(
        name="a bare specifier is unread, and keyed by the specifier",
        base=(_ts_module(_A, {_BET: "A"}),),
        base_attempted=(_A,),
        head=(
            _ts_module(_A, {_BET: "A"}),
            _ts_module(_B, {_augment("lodash", ("i", "X")): "L"}),
        ),
        head_attempted=(_A, _B),
        unread=(
            ExpectedUnread(
                "typescript:<unresolved lodash>",
                UnreadReason.UNRESOLVED_SPECIFIER,
            ),
        ),
    ),
    BehaviourRow(
        name="./sub with sub.ts and sub/index.ts both present is unread",
        base=(
            _ts_module("web/src/sub.ts", {_BET: "A"}),
            _ts_module("web/src/sub/index.ts", {_BET: "I"}),
        ),
        base_attempted=("web/src/sub.ts", "web/src/sub/index.ts"),
        head=(
            _ts_module("web/src/sub.ts", {_BET: "A"}),
            _ts_module("web/src/sub/index.ts", {_BET: "I"}),
            _ts_module(_B, {_augment("./sub", ("i", "Bet")): "B"}),
        ),
        head_attempted=("web/src/sub.ts", "web/src/sub/index.ts", _B),
        unread=(
            ExpectedUnread(
                "typescript:<unresolved ./sub>",
                UnreadReason.UNRESOLVED_SPECIFIER,
            ),
        ),
    ),
    BehaviourRow(
        name="a second SCRIPT declaring the same interface is not two files",
        base=(_ts_unknown(_A, {_BET: "A"}),),
        base_attempted=(_A,),
        head=(_ts_unknown(_A, {_BET: "A"}), _ts_unknown(_B, {_BET_X: "F"})),
        head_attempted=(_A, _B),
        unread=(
            ExpectedUnread(
                "typescript:<global>", UnreadReason.MODULE_NESS_UNREPORTED
            ),
        ),
    ),
    BehaviourRow(
        name="a file the caller KNOWS is a script declares into the global space",
        base=(
            FileSurface(_A, Language.TYPESCRIPT, ((_BET, "A"),), is_module=False),
        ),
        base_attempted=(_A,),
        head=(
            FileSurface(_A, Language.TYPESCRIPT, ((_BET, "A"),), is_module=False),
            FileSurface(_B, Language.TYPESCRIPT, ((_BET, "B"),), is_module=False),
        ),
        head_attempted=(_A, _B),
        unread=(
            ExpectedUnread("typescript:<global>", UnreadReason.NOT_ENUMERABLE),
        ),
    ),
    BehaviourRow(
        name="an ordinary exported interface is NOT proof, and costs UNDETERMINED",
        base=(_ts_unknown(_A, {_BET: "[export]interface"}),),
        base_attempted=(_A,),
        head=(_ts_unknown(_A, {_BET: "[export]interface2"}),),
        head_attempted=(_A,),
        unread=(
            ExpectedUnread(
                "typescript:<global>", UnreadReason.MODULE_NESS_UNREPORTED
            ),
        ),
    ),
    BehaviourRow(
        name="an export surface is proof of module-ness with nothing reported",
        base=(_ts_unknown(_A, {_BET: "A", _EXPORTED: "E"}),),
        base_attempted=(_A,),
        head=(_ts_unknown(_A, {_BET: "A2", _EXPORTED: "E"}),),
        head_attempted=(_A,),
        is_control=True,
    ),
    BehaviourRow(
        name="a base file nobody attempted leaves its space unread",
        base=(_ts_module(_A, {_BET: "A"}),),
        base_attempted=(_A,),
        head=(_ts_module(_B, {_augment("./a", ("i", "Bet")): "B"}),),
        head_attempted=(_B,),
        unread=(
            ExpectedUnread(
                "typescript:<unresolved ./a>", UnreadReason.UNRESOLVED_SPECIFIER
            ),
        ),
    ),
    BehaviourRow(
        name="python does not merge: a second module is refused, not compared",
        base=(FileSurface("src/pkg/wallet.py", Language.PYTHON, (("Wallet", "A"),)),),
        base_attempted=("src/pkg/wallet.py",),
        head=(
            FileSurface("src/pkg/wallet.py", Language.PYTHON, (("Wallet", "A"),)),
            FileSurface(
                "src/pkg/wallet_v2.py", Language.PYTHON, (("Wallet", "B"),)
            ),
        ),
        head_attempted=("src/pkg/wallet.py", "src/pkg/wallet_v2.py"),
        refused=True,
    ),
    BehaviourRow(
        name="go does not merge: a new file's method is an added key",
        base=(FileSurface("pkg/wallet.go", Language.GO, (("Wallet", "A"),)),),
        base_attempted=("pkg/wallet.go",),
        head=(
            FileSurface("pkg/wallet.go", Language.GO, (("Wallet", "A"),)),
            FileSurface("pkg/debit.go", Language.GO, (("Wallet.Debit", "D"),)),
        ),
        head_attempted=("pkg/wallet.go", "pkg/debit.go"),
        refused=True,
    ),
)


def _validate_rules(
    rules: Sequence[LanguageSurfaceRule] = SURFACE_RULES,
    extensions: Iterable[str] = TYPESCRIPT_SUPPORT.extensions,
) -> None:
    """Refuse a table that could give one language two answers, or none.

    Runs at import over a literal, so it either always passes or always fails,
    and the failure is on the first test collection rather than on the first
    TypeScript branch. The suffix half is the one that decays: enrolling
    ``.mts`` would make every ``.mts`` module's namespace its full path minus
    ``.ts``, and no augmentation could meet it.

    The suffix check drives :func:`_strip_ts_suffix` itself and demands the
    exact stem back. An ``endswith`` test would pass ``.mts``, ``.cts`` and
    ``.tsx`` on the ``.ts`` row alone — the decay this function exists to stop.
    """
    seen: set[Language] = set()
    for rule in rules:
        if rule.language in seen:
            raise BranchSurfaceError(
                f"two surface rules for {rule.language.value!r}"
            )
        seen.add(rule.language)
    missing = [lang.value for lang in Language if lang not in seen]
    if missing:
        raise BranchSurfaceError(
            f"no surface rule for {', '.join(missing)}; absence is not "
            "'does not merge'"
        )
    for extension in extensions:
        if _strip_ts_suffix("m" + extension) != "m":
            raise BranchSurfaceError(
                f"enrolled TypeScript extension {extension!r} is not stripped "
                "whole by TS_NAMESPACE_SUFFIXES, so its module namespace would "
                "keep part of the extension and no specifier could meet it"
            )


_validate_rules()
