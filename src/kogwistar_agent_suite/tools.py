"""Safe local tools used by the initial Developer Pack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .catalog import CapabilityCatalog, CapabilityDescriptor, CapabilityKind


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    name: str
    summary: str
    required_capabilities: frozenset[str] = frozenset()
    side_effect: str = "read"

    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=f"tool:{self.tool_id}",
            name=self.name,
            kind=CapabilityKind.TOOL,
            summary=self.summary,
            required_capabilities=self.required_capabilities,
            tags=("tool", self.side_effect),
            metadata={"side_effect": self.side_effect},
        )


@dataclass(frozen=True)
class ToolCall:
    tool_id: str
    arguments: Mapping[str, Any]


ToolAcl = Callable[[ToolDescriptor], bool]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolDescriptor, Any]] = {}

    def register(self, descriptor: ToolDescriptor, implementation: Any) -> None:
        if descriptor.tool_id in self._tools:
            raise ValueError(f"duplicate tool: {descriptor.tool_id}")
        self._tools[descriptor.tool_id] = descriptor, implementation

    def descriptor_catalog(self) -> CapabilityCatalog:
        return CapabilityCatalog(item.descriptor() for item, _ in self._tools.values())

    def call(
        self,
        call: ToolCall,
        *,
        allowed_capabilities: frozenset[str],
        acl: ToolAcl | None = None,
    ) -> Any:
        descriptor, implementation = self._tools[call.tool_id]
        if descriptor.required_capabilities - allowed_capabilities:
            raise PermissionError(f"tool capability denied: {call.tool_id}")
        if acl is not None and not acl(descriptor):
            raise PermissionError(f"tool ACL denied: {call.tool_id}")
        return implementation(**dict(call.arguments))


class LocalWorkspaceTool:
    """Read-only workspace tool; path escapes are rejected."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _resolve(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if target != self.root and self.root not in target.parents:
            raise PermissionError("workspace path escapes configured root")
        return target

    def list_files(self, relative_path: str = ".", limit: int = 100) -> list[str]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        target = self._resolve(relative_path)
        if not target.is_dir():
            raise NotADirectoryError(relative_path)
        return sorted(str(path.relative_to(self.root)) for path in target.rglob("*") if path.is_file())[:limit]

    def read_text(self, relative_path: str, max_bytes: int = 65536) -> str:
        if max_bytes < 1 or max_bytes > 4 * 1024 * 1024:
            raise ValueError("max_bytes is outside safe bounds")
        data = self._resolve(relative_path).read_bytes()
        return data[:max_bytes].decode("utf-8", errors="replace")
