"""Descriptor-first capability catalog with lexical/BM25 fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
import re
from collections.abc import Mapping
from typing import Callable, Iterable


class CapabilityKind(StrEnum):
    TOOL = "tool"
    MCP = "mcp"
    SKILL = "skill"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    name: str
    kind: CapabilityKind
    summary: str
    required_capabilities: frozenset[str] = frozenset()
    tags: tuple[str, ...] = ()
    provider_id: str = "kogwistar-agent-suite"
    metadata: dict[str, str] = field(default_factory=dict)

    def searchable_text(self) -> str:
        metadata = tuple(f"{key} {value}" for key, value in self.metadata.items())
        return " ".join((self.capability_id, self.name, self.summary, *self.tags, *metadata)).lower()


@dataclass(frozen=True)
class CapabilitySearchResult:
    descriptor: CapabilityDescriptor
    score: float
    match: str


AclCheck = Callable[[CapabilityDescriptor], bool]
CapabilitySemanticRanker = Callable[[str, tuple[CapabilityDescriptor, ...]], Mapping[str, float]]


class CapabilityCatalog:
    """Catalog only; authorization and invocation remain separate concerns."""

    def __init__(
        self,
        descriptors: Iterable[CapabilityDescriptor] = (),
        *,
        semantic_ranker: CapabilitySemanticRanker | None = None,
    ) -> None:
        self._items: dict[str, CapabilityDescriptor] = {}
        self.semantic_ranker = semantic_ranker
        for descriptor in descriptors:
            self.add(descriptor)

    def add(self, descriptor: CapabilityDescriptor) -> None:
        if descriptor.capability_id in self._items:
            raise ValueError(f"duplicate capability: {descriptor.capability_id}")
        self._items[descriptor.capability_id] = descriptor

    def search(
        self,
        query: str,
        *,
        allowed_capabilities: frozenset[str] = frozenset(),
        acl: AclCheck | None = None,
        mode: str = "lexical",
        limit: int = 20,
    ) -> tuple[CapabilityDescriptor, ...]:
        return tuple(
            result.descriptor
            for result in self.search_ranked(
                query,
                allowed_capabilities=allowed_capabilities,
                acl=acl,
                mode=mode,
                limit=limit,
            )
        )

    def search_ranked(
        self,
        query: str,
        *,
        allowed_capabilities: frozenset[str] = frozenset(),
        acl: AclCheck | None = None,
        mode: str = "lexical",
        limit: int = 20,
    ) -> tuple[CapabilitySearchResult, ...]:
        """Search visible descriptors; BM25 never bypasses ACL filtering."""

        if limit < 1:
            return ()
        if mode not in {"lexical", "bm25", "semantic"}:
            raise ValueError("mode must be lexical, bm25, or semantic")
        query = str(query).strip().lower()
        visible = []
        for item in self._items.values():
            if item.required_capabilities - allowed_capabilities:
                continue
            if acl is not None and not acl(item):
                continue
            visible.append(item)
        if not query:
            return tuple(
                CapabilitySearchResult(item, 1.0, "lexical")
                for item in sorted(visible, key=lambda value: value.capability_id)[:limit]
            )

        if mode == "semantic" and self.semantic_ranker is not None:
            candidates = tuple(visible)
            try:
                scores = self.semantic_ranker(query, candidates)
                if not isinstance(scores, Mapping):
                    raise TypeError("semantic_ranker must return a mapping")
                semantic = tuple(
                    CapabilitySearchResult(item, float(scores.get(item.capability_id, 0.0)), "semantic")
                    for item in candidates
                    if math.isfinite(float(scores.get(item.capability_id, 0.0)))
                    and float(scores.get(item.capability_id, 0.0)) > 0.0
                )
                if semantic:
                    return tuple(
                        sorted(semantic, key=lambda result: (-result.score, result.descriptor.capability_id))[:limit]
                    )
            except Exception:
                # Optional ranker failure must not make discovery unavailable.
                pass
        # No mandatory vector dependency: semantic fallback remains deterministic BM25.
        effective_mode = "bm25" if mode == "semantic" else mode
        query_tokens = set(_tokens(query))
        token_sets = {item.capability_id: set(_tokens(item.searchable_text())) for item in visible}
        document_frequency: dict[str, int] = {}
        for tokens in token_sets.values():
            for token in tokens:
                document_frequency[token] = document_frequency.get(token, 0) + 1
        average_length = sum(len(tokens) for tokens in token_sets.values()) / max(len(visible), 1)
        ranked: list[CapabilitySearchResult] = []
        for item in visible:
            searchable = item.searchable_text()
            names = (item.capability_id.lower(), item.name.lower(), *(tag.lower() for tag in item.tags))
            if query in names:
                ranked.append(CapabilitySearchResult(item, 1.0, "exact"))
                continue
            if any(value.startswith(query) for value in names):
                ranked.append(CapabilitySearchResult(item, 0.8, "prefix"))
                continue
            tokens = token_sets[item.capability_id]
            overlap = tokens & query_tokens
            if overlap:
                if effective_mode == "bm25":
                    score = 0.0
                    document_length = max(len(tokens), 1)
                    for term in query_tokens:
                        if term not in tokens:
                            continue
                        count = document_frequency.get(term, 0)
                        idf = math.log(1.0 + (len(visible) - count + 0.5) / (count + 0.5))
                        normalization = 1.2 * (1.0 - 0.75 + 0.75 * document_length / max(average_length, 1.0))
                        score += idf * (2.2 / (1.0 + normalization))
                    ranked.append(CapabilitySearchResult(item, score, "bm25"))
                else:
                    ranked.append(CapabilitySearchResult(item, 0.5 + len(overlap) / max(len(query_tokens), 1) / 10, "lexical"))
                continue
            if query in searchable:
                ranked.append(CapabilitySearchResult(item, 0.3, "partial"))
        return tuple(sorted(ranked, key=lambda result: (-result.score, result.descriptor.capability_id))[:limit])

    def get(self, capability_id: str) -> CapabilityDescriptor:
        return self._items[capability_id]

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        """Return current descriptors in stable capability-ID order."""

        return tuple(self._items[key] for key in sorted(self._items))

    def __len__(self) -> int:
        return len(self._items)


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_RE.findall(value))
