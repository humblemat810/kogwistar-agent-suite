"""Fail-closed authorization guards for optional suite integrations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol


class AclResolver(Protocol):
    """Host-supplied resource/action authorization decision."""

    def __call__(self, action: str, request: Mapping[str, Any]) -> bool: ...


class ApprovalResolver(Protocol):
    """Host-supplied confirmation for mutating operations."""

    def __call__(self, action: str, request: Mapping[str, Any]) -> bool: ...


def require_acl(
    *, action: str, request: Mapping[str, Any], acl: AclResolver | None
) -> None:
    """Require an explicit host ACL decision before any direct action."""

    if acl is None:
        raise PermissionError(f"explicit ACL resolver required: {action}")
    if not acl(action, request):
        raise PermissionError(f"ACL denied: {action}")


def require_approval(
    *, action: str, request: Mapping[str, Any], approve: ApprovalResolver | None
) -> None:
    if approve is None or not approve(action, request):
        raise PermissionError(f"explicit approval required: {action}")


def require_capabilities(
    required: frozenset[str], effective: frozenset[str], *, action: str
) -> None:
    missing = required - effective
    if missing:
        raise PermissionError(
            f"capabilities denied for {action}: {', '.join(sorted(missing))}"
        )


def allow_read_only_tool(_action: str, request: Mapping[str, Any]) -> bool:
    """Explicit local policy useful for CLI read-only commands."""

    return request.get("side_effect") == "read"


AclCallback = Callable[[str, Mapping[str, Any]], bool]
