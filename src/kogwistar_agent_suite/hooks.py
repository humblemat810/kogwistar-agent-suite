"""Bounded, deterministic suite hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping


Hook = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


@dataclass(frozen=True)
class HookBundle:
    name: str
    hooks: tuple[Hook, ...] = ()
    fail_closed: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("hook bundle name is required")


def run_hooks(bundles: Iterable[HookBundle], payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run context hooks in order; hooks cannot select branches or bypass ACL."""

    current = dict(payload)
    for bundle in bundles:
        for hook in bundle.hooks:
            try:
                update = hook(current)
            except Exception:
                if bundle.fail_closed:
                    raise
                continue
            if update is not None:
                current.update(update)
    return current
