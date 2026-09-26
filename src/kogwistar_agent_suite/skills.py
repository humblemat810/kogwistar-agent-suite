"""Installable skill descriptors for the Developer Pack."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import CapabilityDescriptor, CapabilityKind


@dataclass(frozen=True)
class SkillDescriptor:
    skill_id: str
    name: str
    summary: str
    steps: tuple[str, ...]
    required_capabilities: frozenset[str] = frozenset()
    tags: tuple[str, ...] = ()

    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=f"skill:{self.skill_id}",
            name=self.name,
            kind=CapabilityKind.SKILL,
            summary=self.summary,
            required_capabilities=self.required_capabilities,
            tags=("skill", *self.tags),
            metadata={"step_count": str(len(self.steps))},
        )


def developer_skills() -> tuple[SkillDescriptor, ...]:
    return (
        SkillDescriptor(
            "diagnose-test-failure",
            "Diagnose test failure",
            "Inspect failure evidence, isolate a cause, patch, and verify with deterministic tests.",
            ("inspect_failure", "search_related_code", "propose_patch", "run_targeted_tests"),
            frozenset({"workspace.read", "shell.test"}),
            ("developer", "testing", "repair"),
        ),
        SkillDescriptor(
            "review-pull-request",
            "Review pull request",
            "Review changed code for regressions, security, lifecycle, and missing tests.",
            ("read_diff", "trace_behavior", "check_tests", "write_findings"),
            frozenset({"workspace.read", "git.read"}),
            ("developer", "review"),
        ),
        SkillDescriptor(
            "prepare-release",
            "Prepare release",
            "Validate version, changelog, tests, and release evidence before publishing.",
            ("inspect_status", "run_checks", "draft_changelog", "report_release_readiness"),
            frozenset({"workspace.read", "shell.test", "git.read"}),
            ("developer", "release"),
        ),
        SkillDescriptor(
            "search-and-understand-code",
            "Search and understand code",
            "Search bounded source text, follow references, and summarize behavior before editing.",
            ("search_symbols", "read_context", "trace_callers", "summarize_contract"),
            frozenset({"workspace.read"}),
            ("developer", "research", "safe-read"),
        ),
        SkillDescriptor(
            "research-with-citations",
            "Research with citations",
            "Collect authorized repository or adapter evidence and preserve source references.",
            ("discover_sources", "filter_access", "extract_evidence", "write_citations"),
            frozenset({"workspace.read"}),
            ("research", "provenance"),
        ),
        SkillDescriptor(
            "inspect-past-execution",
            "Inspect past execution",
            "Find prior workflow, conversation, and agent evidence before repeating work.",
            ("search_history", "inspect_trace", "compare_runs", "summarize_lessons"),
            frozenset({"workspace.read"}),
            ("agent", "history", "wisdom"),
        ),
        SkillDescriptor(
            "incident-triage",
            "Triage incident",
            "Bound scope, gather read-only evidence, classify impact, and propose a reversible next action.",
            ("classify_impact", "collect_evidence", "check_permissions", "propose_recovery"),
            frozenset({"workspace.read", "git.read"}),
            ("operations", "safety", "repair"),
        ),
        SkillDescriptor(
            "build-workflow-from-request",
            "Build workflow from request",
            "Translate an objective into ordinary Kogwistar workflow nodes, edges, predicates, and checks.",
            ("clarify_objective", "select_capabilities", "design_graph", "validate_termination"),
            frozenset({"workspace.read"}),
            ("workflow", "planning", "goal"),
        ),
        SkillDescriptor(
            "delegate-vision-inspection",
            "Delegate vision inspection",
            "Delegate isolated image or UI inspection to an approved vision-capable subagent.",
            ("prepare_minimal_context", "request_inspection", "check_result", "record_provenance"),
            frozenset({"agent.delegate"}),
            ("agent", "delegation", "vision"),
        ),
        SkillDescriptor(
            "discover-capability",
            "Discover capability",
            "Search tools, MCP descriptors, and skills progressively before requesting installation or access.",
            ("search_catalog", "filter_acl", "inspect_manifest", "request_authorization"),
            frozenset({"workspace.read"}),
            ("skills", "mcp", "progressive-revelation"),
        ),
    )
