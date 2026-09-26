"""Descriptor-first capability catalog with lexical fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
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
        return " ".join((self.capability_id, self.name, self.summary, *self.tags)).lower()


AclCheck = Callable[[CapabilityDescriptor], bool]


class CapabilityCatalog:
    """Catalog only; authorization and invocation remain separate concerns."""

    def __init__(self, descriptors: Iterable[CapabilityDescriptor] = ()) -> None:
        self._items: dict[str, CapabilityDescriptor] = {}
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
        limit: int = 20,
    ) -> tuple[CapabilityDescriptor, ...]:
        if limit < 1:
            return ()
        terms = tuple(part for part in query.lower().split() if part)
        candidates: list[tuple[int, CapabilityDescriptor]] = []
        for item in self._items.values():
            if item.required_capabilities - allowed_capabilities:
                continue
            if acl is not None and not acl(item):
                continue
            haystack = item.searchable_text()
            score = sum(haystack.count(term) for term in terms) if terms else 1
            if score:
                candidates.append((score, item))
        candidates.sort(key=lambda pair: (-pair[0], pair[1].capability_id))
        return tuple(item for _, item in candidates[:limit])

    def get(self, capability_id: str) -> CapabilityDescriptor:
        return self._items[capability_id]

    def __len__(self) -> int:
        return len(self._items)
