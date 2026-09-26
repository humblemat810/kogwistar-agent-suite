"""Starter profiles composed from suite descriptors."""

from __future__ import annotations

from dataclasses import dataclass

from kogwistar.agent import AgentProfile, build_goal_workflow, build_plan_workflow

from .catalog import CapabilityCatalog, CapabilitySemanticRanker
from .adapters import OptionalAdapter, register_optional_adapter
from .hooks import HookBundle
from .mcp import McpCapability
from .plugins import PluginManifest, PluginRegistry
from .skills import SkillDescriptor, developer_skills
from .tools import GitReadTool, LocalWorkspaceTool, ToolDescriptor, ToolRegistry


@dataclass
class DeveloperPack:
    tools: ToolRegistry
    catalog: CapabilityCatalog
    plugins: PluginRegistry
    skills: tuple[SkillDescriptor, ...]
    hooks: tuple[HookBundle, ...]

    def _ensure_capability_available(self, capability_id: str) -> None:
        try:
            self.catalog.get(capability_id)
        except KeyError:
            return
        raise ValueError(f"duplicate capability: {capability_id}")

    def search(
        self,
        query: str,
        *,
        allowed_capabilities: frozenset[str] = frozenset(),
        acl=None,
        mode: str = "lexical",
        limit: int = 20,
    ):
        """Search every installed tool, MCP descriptor, skill, and adapter."""

        return self.catalog.search(
            query,
            allowed_capabilities=allowed_capabilities,
            acl=acl,
            mode=mode,
            limit=limit,
        )

    def search_ranked(self, query: str, **kwargs):
        """Return scores/match modes for progressive-disclosure decisions."""

        return self.catalog.search_ranked(query, **kwargs)

    def register_tool(self, descriptor: ToolDescriptor, implementation) -> None:
        """Register a tool and publish its descriptor to progressive search."""

        self._ensure_capability_available(f"tool:{descriptor.tool_id}")
        self.tools.register(descriptor, implementation)
        self.catalog.add(descriptor.descriptor())

    def register_skill(self, skill: SkillDescriptor) -> None:
        """Register a skill descriptor without granting execution authority."""

        self._ensure_capability_available(f"skill:{skill.skill_id}")
        self.skills = (*self.skills, skill)
        self.catalog.add(skill.descriptor())

    def register_mcp(self, capability: McpCapability) -> None:
        """Publish an MCP descriptor; invocation remains a separate adapter."""

        self._ensure_capability_available(capability.capability_id)
        self.catalog.add(capability.descriptor())

    def register_adapter(self, adapter: OptionalAdapter) -> None:
        """Attach one explicitly configured optional adapter to this pack."""

        descriptors = adapter.descriptors()
        descriptor_ids: set[str] = set()
        for descriptor in descriptors:
            if descriptor.capability_id in descriptor_ids:
                raise ValueError(f"duplicate capability: {descriptor.capability_id}")
            descriptor_ids.add(descriptor.capability_id)
            self._ensure_capability_available(descriptor.capability_id)
        register_optional_adapter(self.plugins, adapter)
        for descriptor in descriptors:
            self.catalog.add(descriptor)

    def close(self) -> None:
        self.plugins.close()

    def agent_profile(self) -> AgentProfile:
        """Return the core profile; it remains subject to host ACL checks."""

        return AgentProfile(
            agent_id="kogwistar.developer",
            workflow_id="agent.plan.v1",
            workflow_mode="plan",
            model_profile="default",
            requested_tool_capabilities=[
                "git.read",
                "shell.test",
                "workspace.read",
            ],
            skill_providers=["kogwistar-agent-suite.developer"],
            plugin_ids=["kogwistar-agent-suite.developer"],
            hook_ids=[hook.name for hook in self.hooks],
            acl_required=True,
        )

    def workflow_design(self, mode: str = "plan"):
        """Build an ordinary core workflow design for this profile."""

        if mode == "plan":
            return build_plan_workflow(workflow_id="agent.plan.v1")
        if mode == "goal":
            return build_goal_workflow(workflow_id="agent.goal.v1")
        raise ValueError("mode must be 'plan' or 'goal'")


def developer_profile(
    workspace_root: str,
    adapters: tuple[OptionalAdapter, ...] = (),
    *,
    semantic_ranker: CapabilitySemanticRanker | None = None,
) -> DeveloperPack:
    workspace = LocalWorkspaceTool(workspace_root)
    git = GitReadTool(workspace_root)
    tools = ToolRegistry()
    tools.register(
        ToolDescriptor(
            "workspace.list_files",
            "List workspace files",
            "List bounded files below the configured workspace root.",
            frozenset({"workspace.read"}),
        ),
        workspace.list_files,
    )
    tools.register(
        ToolDescriptor(
            "workspace.read_text",
            "Read workspace text",
            "Read bounded UTF-8 text below the configured workspace root.",
            frozenset({"workspace.read"}),
        ),
        workspace.read_text,
    )
    tools.register(
        ToolDescriptor(
            "workspace.search_text",
            "Search workspace text",
            "Search bounded UTF-8 text below the configured workspace root.",
            frozenset({"workspace.read"}),
        ),
        workspace.search_text,
    )
    for tool_id, name, summary, implementation in (
        ("git.status", "Read Git status", "Read branch and working-tree status without mutation.", git.status),
        ("git.diff_stat", "Read Git diff stat", "Read a bounded working-tree diff summary.", git.diff_stat),
        ("git.log", "Read Git log", "Read a bounded recent commit log.", git.log),
    ):
        tools.register(ToolDescriptor(tool_id, name, summary, frozenset({"git.read"})), implementation)
    plugins = PluginRegistry()
    plugins.register(
        PluginManifest(
            "kogwistar-agent-suite.developer",
            "0.1.0",
            ("workspace.read", "shell.test", "git.read"),
        )
    )
    skills = developer_skills()
    catalog = CapabilityCatalog(tools.descriptor_catalog().descriptors(), semantic_ranker=semantic_ranker)
    for skill in skills:
        catalog.add(skill.descriptor())
    pack = DeveloperPack(tools, catalog, plugins, skills, ())
    for adapter in adapters:
        pack.register_adapter(adapter)
    return pack
