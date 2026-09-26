"""Starter profiles composed from suite descriptors."""

from __future__ import annotations

from dataclasses import dataclass

from kogwistar.agent import AgentProfile, build_goal_workflow, build_plan_workflow

from .catalog import CapabilityCatalog
from .hooks import HookBundle
from .plugins import PluginManifest, PluginRegistry
from .skills import SkillDescriptor, developer_skills
from .tools import LocalWorkspaceTool, ToolDescriptor, ToolRegistry


@dataclass
class DeveloperPack:
    tools: ToolRegistry
    catalog: CapabilityCatalog
    plugins: PluginRegistry
    skills: tuple[SkillDescriptor, ...]
    hooks: tuple[HookBundle, ...]

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


def developer_profile(workspace_root: str) -> DeveloperPack:
    workspace = LocalWorkspaceTool(workspace_root)
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
    plugins = PluginRegistry()
    plugins.register(
        PluginManifest(
            "kogwistar-agent-suite.developer",
            "0.1.0",
            ("workspace.read", "shell.test", "git.read"),
        )
    )
    skills = developer_skills()
    catalog = tools.descriptor_catalog()
    for skill in skills:
        catalog.add(skill.descriptor())
    return DeveloperPack(tools, catalog, plugins, skills, ())
