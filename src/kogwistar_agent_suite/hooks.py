"""Bounded, deterministic suite hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from kogwistar.agent import HookRegistry, HookSpec


Hook = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


@dataclass(frozen=True)
class HookBundle:
    name: str
    hooks: tuple[Hook, ...] = ()
    fail_closed: bool = True
    timeout_ms: int = 1_000
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("hook bundle name is required")
        if self.timeout_ms < 1:
            raise ValueError("hook timeout must be positive")


def run_hooks(
    bundles: Iterable[HookBundle],
    payload: Mapping[str, Any],
    *,
    effective_capabilities: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Run bounded core hooks in order; hooks cannot bypass ACL."""

    current = dict(payload)
    for bundle in bundles:
        registry = HookRegistry(max_concurrent_callbacks=max(1, len(bundle.hooks)))
        try:
            for index, hook in enumerate(bundle.hooks):
                registry.register(
                    HookSpec(
                        hook_id=f"{bundle.name}:{index}",
                        callback=hook,
                        order=index,
                        timeout_ms=bundle.timeout_ms,
                        failure_mode="fail_closed" if bundle.fail_closed else "fail_open",
                        effect="annotate",
                        required_capabilities=tuple(sorted(bundle.required_capabilities)),
                    )
                )
            for result in registry.run(current, effective_capabilities=effective_capabilities):
                if result.status == "applied":
                    current.update(result.annotations)
        finally:
            for spec in registry.list():
                registry.unregister(spec.hook_id)
    return current
