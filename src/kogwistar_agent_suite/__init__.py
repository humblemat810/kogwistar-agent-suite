"""Concrete Kogwistar agent integrations."""

from .catalog import CapabilityCatalog, CapabilityDescriptor, CapabilityKind
from .hooks import HookBundle, run_hooks
from .mcp import McpCapability, McpCatalog
from .plugins import PluginManifest, PluginRegistry
from .profiles import DeveloperPack, developer_profile
from .skills import SkillDescriptor, developer_skills
from .tools import LocalWorkspaceTool, ToolCall, ToolDescriptor, ToolRegistry

__all__ = [
    "CapabilityCatalog", "CapabilityDescriptor", "CapabilityKind",
    "DeveloperPack", "HookBundle", "LocalWorkspaceTool", "McpCapability",
    "McpCatalog", "PluginManifest", "PluginRegistry", "SkillDescriptor",
    "ToolCall", "ToolDescriptor", "ToolRegistry", "developer_profile",
    "developer_skills", "run_hooks",
]
