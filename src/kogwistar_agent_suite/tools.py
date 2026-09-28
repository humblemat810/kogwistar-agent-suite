"""Bounded, read-only local tools used by the Developer Pack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Mapping

from .catalog import CapabilityCatalog, CapabilityDescriptor, CapabilityKind
from .authorization import (
    AclResolver,
    ApprovalResolver,
    require_acl,
    require_approval,
    require_capabilities,
)


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    name: str
    summary: str
    required_capabilities: frozenset[str] = frozenset()
    side_effect: str | None = None

    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=f"tool:{self.tool_id}",
            name=self.name,
            kind=CapabilityKind.TOOL,
            summary=self.summary,
            required_capabilities=self.required_capabilities,
            tags=("tool", self.side_effect or "unspecified"),
            metadata={"side_effect": self.side_effect or "unspecified"},
        )


@dataclass(frozen=True)
class ToolCall:
    tool_id: str
    arguments: Mapping[str, Any]


ToolAcl = AclResolver


@dataclass(frozen=True)
class CommandResult:
    """Bounded result from a read-only local command."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolDescriptor, Any]] = {}

    def register(self, descriptor: ToolDescriptor, implementation: Any) -> None:
        if descriptor.tool_id in self._tools:
            raise ValueError(f"duplicate tool: {descriptor.tool_id}")
        if descriptor.side_effect is None:
            raise ValueError("tool side_effect must be explicit: 'read' or 'write'")
        if descriptor.side_effect not in {"read", "write"}:
            raise ValueError("tool side_effect must be 'read' or 'write'")
        if descriptor.side_effect == "write" and not descriptor.required_capabilities:
            raise ValueError("write tool requires an explicit capability")
        self._tools[descriptor.tool_id] = descriptor, implementation

    def descriptor_catalog(self) -> CapabilityCatalog:
        return CapabilityCatalog(item.descriptor() for item, _ in self._tools.values())

    def call(
        self,
        call: ToolCall,
        *,
        allowed_capabilities: frozenset[str],
        acl: ToolAcl | None = None,
        approve: ApprovalResolver | None = None,
    ) -> Any:
        descriptor, implementation = self._tools[call.tool_id]
        request = {
            "tool_id": call.tool_id,
            "arguments": dict(call.arguments),
            "side_effect": descriptor.side_effect,
        }
        require_acl(action=call.tool_id, request=request, acl=acl)
        require_capabilities(
            descriptor.required_capabilities,
            allowed_capabilities,
            action=call.tool_id,
        )
        if descriptor.side_effect == "write":
            require_approval(action=call.tool_id, request=request, approve=approve)
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

    def search_text(
        self,
        query: str,
        relative_path: str = ".",
        glob: str = "*",
        max_matches: int = 100,
        max_file_bytes: int = 1024 * 1024,
    ) -> list[dict[str, object]]:
        """Search bounded UTF-8 text without invoking a shell or network."""

        if not query:
            raise ValueError("query is required")
        if max_matches < 1 or max_matches > 1000:
            raise ValueError("max_matches must be between 1 and 1000")
        if max_file_bytes < 1 or max_file_bytes > 4 * 1024 * 1024:
            raise ValueError("max_file_bytes is outside safe bounds")
        target = self._resolve(relative_path)
        if not target.is_dir():
            raise NotADirectoryError(relative_path)

        matches: list[dict[str, object]] = []
        for path in sorted(target.rglob(glob)):
            resolved = path.resolve()
            if not path.is_file() or resolved != self.root and self.root not in resolved.parents:
                continue
            data = path.read_bytes()
            if b"\x00" in data[:4096]:
                continue
            text = data[:max_file_bytes].decode("utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if query.casefold() in line.casefold():
                    matches.append(
                        {
                            "path": str(resolved.relative_to(self.root)),
                            "line": line_number,
                            "text": line,
                        }
                    )
                    if len(matches) >= max_matches:
                        return matches
        return matches


class GitReadTool:
    """Read-only Git inspection with bounded execution."""

    def __init__(self, root: str | Path, *, timeout_seconds: float = 10.0, max_output_bytes: int = 256 * 1024) -> None:
        self.root = Path(root).resolve()
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("timeout_seconds must be between 0 and 60")
        if max_output_bytes < 1 or max_output_bytes > 4 * 1024 * 1024:
            raise ValueError("max_output_bytes is outside safe bounds")
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def _run(self, *args: str) -> CommandResult:
        if any("\x00" in arg for arg in args):
            raise ValueError("Git arguments cannot contain NUL")
        try:
            completed = subprocess.run(
                ["git", "--no-optional-locks", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(124, str(exc.stdout or "")[: self.max_output_bytes], "git command timed out")
        except OSError as exc:
            return CommandResult(127, "", str(exc))
        return CommandResult(
            completed.returncode,
            completed.stdout[: self.max_output_bytes],
            completed.stderr[: self.max_output_bytes],
        )

    def status(self) -> CommandResult:
        return self._run("status", "--short", "--branch")

    def diff_stat(self) -> CommandResult:
        return self._run("diff", "--stat")

    def log(self, limit: int = 20) -> CommandResult:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        return self._run("log", f"-{limit}", "--oneline", "--decorate")
