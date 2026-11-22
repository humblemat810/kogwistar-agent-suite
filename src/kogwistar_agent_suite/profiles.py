"""Starter profiles composed from suite descriptors."""

from __future__ import annotations

from dataclasses import dataclass

from kogwistar.agent import (
    AgentHarness,
    AgentProfile,
    AsyncAgentHarness,
    build_goal_workflow,
    build_plan_workflow,
)

from .catalog import CapabilityCatalog, CapabilitySemanticRanker
from .adapters import OptionalAdapter, register_optional_adapter
from .hooks import HookBundle
from .mcp import McpCapability
from .plugins import PluginManifest, PluginRegistry
from .skills import SkillDescriptor, developer_skills
from .tools import GitReadTool, LocalWorkspaceTool, ToolDescriptor, ToolRegistry
from .implementation_selection import Implementation, SuiteSeam, SuiteSelection, selection_from_env
from .errors import SuiteImplementationUnavailable


@dataclass
class DeveloperPack:
    tools: ToolRegistry
    catalog: CapabilityCatalog
    plugins: PluginRegistry
    skills: tuple[SkillDescriptor, ...]
    hooks: tuple[HookBundle, ...]
    implementation: Implementation = "python"

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

        selected = self.implementation
        if selected != "python":
            from ._rust_bridge import RustAgentSuiteExtension
            from dataclasses import asdict

            extension = RustAgentSuiteExtension()
            descriptors = [
                asdict(result.descriptor)
                for result in self.catalog.search_ranked(
                    query,
                    allowed_capabilities=allowed_capabilities,
                    acl=acl,
                    mode="lexical",
                    limit=self.catalog.len() if hasattr(self.catalog, "len") else 1000,
                )
            ]
            results = extension.search(
                descriptors,
                query=query,
                allowed_capabilities=allowed_capabilities,
                mode=mode,
                limit=limit,
            )
            from .catalog import CapabilitySearchResult

            return tuple(
                CapabilitySearchResult(
                    descriptor=self.catalog.get(result["descriptor"]["capability_id"]),
                    score=result["score"],
                    match=result["match"],
                )
                for result in results
            )

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

    def make_harness(self, workflow_runtime, *, caller_capabilities, **kwargs):
        """Bind this composition to core's synchronous harness and ACL seam."""

        return AgentHarness(
            profile=self.agent_profile(),
            workflow_runtime=workflow_runtime,
            known_workflows={"agent.plan.v1", "agent.goal.v1"},
            known_model_profiles={"default"},
            caller_capabilities=tuple(caller_capabilities),
            **kwargs,
        )

    def make_async_harness(self, workflow_runtime, *, caller_capabilities, **kwargs):
        """Bind this composition to core's async-compatible harness."""

        return AsyncAgentHarness(
            profile=self.agent_profile(),
            workflow_runtime=workflow_runtime,
            known_workflows={"agent.plan.v1", "agent.goal.v1"},
            known_model_profiles={"default"},
            caller_capabilities=tuple(caller_capabilities),
            **kwargs,
        )


def developer_profile(
    workspace_root: str,
    adapters: tuple[OptionalAdapter, ...] = (),
    *,
    semantic_ranker: CapabilitySemanticRanker | None = None,
    implementation: Implementation | None = None,
    seams: dict[SuiteSeam, Implementation] | None = None,
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
            side_effect="read",
        ),
        workspace.list_files,
    )
    tools.register(
        ToolDescriptor(
            "workspace.read_text",
            "Read workspace text",
            "Read bounded UTF-8 text below the configured workspace root.",
            frozenset({"workspace.read"}),
            side_effect="read",
        ),
        workspace.read_text,
    )
    tools.register(
        ToolDescriptor(
            "workspace.search_text",
            "Search workspace text",
            "Search bounded UTF-8 text below the configured workspace root.",
            frozenset({"workspace.read"}),
            side_effect="read",
        ),
        workspace.search_text,
    )
    for tool_id, name, summary, tool_implementation in (
        ("git.status", "Read Git status", "Read branch and working-tree status without mutation.", git.status),
        ("git.diff_stat", "Read Git diff stat", "Read a bounded working-tree diff summary.", git.diff_stat),
        ("git.log", "Read Git log", "Read a bounded recent commit log.", git.log),
    ):
        tools.register(ToolDescriptor(tool_id, name, summary, frozenset({"git.read"}), side_effect="read"), tool_implementation)
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
    selected = SuiteSelection(
        mode=implementation if implementation is not None else selection_from_env().mode,
        seams=seams,
    )
    if selected.mode not in {"python", "rust", "shadow"}:
        raise ValueError("implementation must be python, rust, or shadow")
    if selected.mode != "python":
        try:
            from ._rust_bridge import RustAgentSuiteExtension

            RustAgentSuiteExtension()
        except SuiteImplementationUnavailable as error:
            raise error
    pack = DeveloperPack(
        tools=tools,
        catalog=catalog,
        plugins=plugins,
        skills=skills,
        hooks=(),
        implementation=selected.mode,
    )
    for adapter in adapters:
        pack.register_adapter(adapter)
    return pack
