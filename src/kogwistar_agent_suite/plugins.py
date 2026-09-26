"""Plugin manifests and cleanup lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    version: str
    capabilities: tuple[str, ...] = ()
    optional: bool = True
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plugin_id or not self.version:
            raise ValueError("plugin_id and version are required")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("plugin capabilities must be unique")


Cleanup = Callable[[], None]


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, tuple[PluginManifest, Cleanup | None]] = {}

    def register(self, manifest: PluginManifest, cleanup: Cleanup | None = None) -> None:
        if manifest.plugin_id in self._plugins:
            raise ValueError(f"duplicate plugin: {manifest.plugin_id}")
        self._plugins[manifest.plugin_id] = manifest, cleanup

    def get(self, plugin_id: str) -> PluginManifest:
        return self._plugins[plugin_id][0]

    def unload(self, plugin_id: str) -> None:
        _, cleanup = self._plugins.pop(plugin_id)
        if cleanup is not None:
            cleanup()

    def close(self) -> None:
        for plugin_id in tuple(self._plugins):
            self.unload(plugin_id)

    def __len__(self) -> int:
        return len(self._plugins)
