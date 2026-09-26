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
    )
