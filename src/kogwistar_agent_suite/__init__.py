"""Concrete Kogwistar agent integrations."""

from .catalog import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilitySearchResult,
    CapabilitySemanticRanker,
)
from .authorization import AclResolver, ApprovalResolver, allow_read_only_tool
from .adapters import (
    AtlassianAdapter,
    BrowserAdapter,
    GitHubAdapter,
    LlmWikiAdapter,
    SlackAdapter,
    adapter_descriptors,
    register_optional_adapter,
)
from .slack_contacts import (
    ContactObservationFactory,
    ContactPointFactory,
    SlackContactDirectorySource,
    SlackDirectoryClient,
)
from .workbench_contacts import register_slack_contact_source
from .hooks import HookBundle, run_hooks
from .mcp import McpCapability, McpCatalog
from .plugins import PluginManifest, PluginRegistry
from .profiles import DeveloperPack, developer_profile
from .skills import SkillDescriptor, developer_skills
from .tools import CommandResult, GitReadTool, LocalWorkspaceTool, ToolCall, ToolDescriptor, ToolRegistry

__all__ = [
    "CapabilityCatalog", "CapabilityDescriptor", "CapabilityKind", "CapabilitySearchResult", "CapabilitySemanticRanker",
    "AclResolver", "ApprovalResolver", "allow_read_only_tool",
    "AtlassianAdapter", "BrowserAdapter", "GitHubAdapter", "LlmWikiAdapter",
    "DeveloperPack", "HookBundle", "LocalWorkspaceTool", "McpCapability",
    "McpCatalog", "PluginManifest", "PluginRegistry", "SkillDescriptor",
    "CommandResult", "GitReadTool", "ToolCall", "ToolDescriptor", "ToolRegistry", "developer_profile",
    "developer_skills", "run_hooks", "SlackAdapter", "adapter_descriptors",
    "register_optional_adapter", "ContactObservationFactory", "ContactPointFactory",
    "SlackContactDirectorySource", "SlackDirectoryClient", "register_slack_contact_source",
]
