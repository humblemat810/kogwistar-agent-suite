"""MCP descriptors for progressive disclosure."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import AclCheck, CapabilityCatalog, CapabilityDescriptor, CapabilityKind


@dataclass(frozen=True)
class McpCapability:
    server_id: str
    tool_name: str
    summary: str
    required_capabilities: frozenset[str] = frozenset()

    @property
    def capability_id(self) -> str:
        return f"mcp:{self.server_id}:{self.tool_name}"

    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=self.capability_id,
            name=self.tool_name,
            kind=CapabilityKind.MCP,
            summary=self.summary,
            required_capabilities=self.required_capabilities,
            tags=("mcp", self.server_id),
            provider_id=self.server_id,
        )


class McpCatalog:
    """Catalog only; execution requires a separate authorized adapter."""

    def __init__(self, capabilities: tuple[McpCapability, ...] = ()) -> None:
        self._capabilities = {item.capability_id: item for item in capabilities}

    def add(self, capability: McpCapability) -> None:
        if capability.capability_id in self._capabilities:
            raise ValueError(f"duplicate MCP capability: {capability.capability_id}")
        self._capabilities[capability.capability_id] = capability

    def search(
        self,
        query: str,
        *,
        allowed_capabilities: frozenset[str] = frozenset(),
        acl: AclCheck | None = None,
        mode: str = "lexical",
        limit: int = 20,
    ) -> tuple[CapabilityDescriptor, ...]:
        catalog = CapabilityCatalog(item.descriptor() for item in self._capabilities.values())
        return catalog.search(query, allowed_capabilities=allowed_capabilities, acl=acl, mode=mode, limit=limit)
