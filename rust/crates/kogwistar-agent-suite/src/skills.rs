use serde::Serialize;

use crate::catalog::{CapabilityDescriptor, CapabilityKind};

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SkillDescriptor {
    pub skill_id: String,
    pub name: String,
    pub summary: String,
    pub steps: Vec<String>,
    pub required_capabilities: Vec<String>,
    pub tags: Vec<String>,
}

impl SkillDescriptor {
    pub fn descriptor(&self) -> CapabilityDescriptor {
        CapabilityDescriptor {
            capability_id: format!("skill:{}", self.skill_id),
            name: self.name.clone(),
            kind: CapabilityKind::Skill,
            summary: self.summary.clone(),
            required_capabilities: self.required_capabilities.clone(),
            tags: [vec!["skill".into()], self.tags.clone()].concat(),
            provider_id: "kogwistar-agent-suite".into(),
            semantic_ready: false,
            metadata: [("step_count".to_string(), self.steps.len().to_string())]
                .into_iter()
                .collect(),
        }
    }
}

fn skill(
    skill_id: &str,
    name: &str,
    summary: &str,
    steps: &[&str],
    capabilities: &[&str],
    tags: &[&str],
) -> SkillDescriptor {
    SkillDescriptor {
        skill_id: skill_id.into(),
        name: name.into(),
        summary: summary.into(),
        steps: steps.iter().map(|step| step.to_string()).collect(),
        required_capabilities: capabilities
            .iter()
            .map(|capability| capability.to_string())
            .collect(),
        tags: tags.iter().map(|tag| tag.to_string()).collect(),
    }
}

pub fn developer_skills() -> Vec<SkillDescriptor> {
    vec![
        skill("diagnose-test-failure", "Diagnose test failure", "Inspect failure evidence, isolate a cause, patch, and verify with deterministic tests.", &["inspect_failure", "search_related_code", "propose_patch", "run_targeted_tests"], &["workspace.read", "shell.test"], &["developer", "testing", "repair"]),
        skill("review-pull-request", "Review pull request", "Review changed code for regressions, security, lifecycle, and missing tests.", &["read_diff", "trace_behavior", "check_tests", "write_findings"], &["workspace.read", "git.read"], &["developer", "review"]),
        skill("prepare-release", "Prepare release", "Validate version, changelog, tests, and release evidence before publishing.", &["inspect_status", "run_checks", "draft_changelog", "report_release_readiness"], &["workspace.read", "shell.test", "git.read"], &["developer", "release"]),
        skill("search-and-understand-code", "Search and understand code", "Search bounded source text, follow references, and summarize behavior before editing.", &["search_symbols", "read_context", "trace_callers", "summarize_contract"], &["workspace.read"], &["developer", "research", "safe-read"]),
        skill("research-with-citations", "Research with citations", "Collect authorized repository or adapter evidence and preserve source references.", &["discover_sources", "filter_access", "extract_evidence", "write_citations"], &["workspace.read"], &["research", "provenance"]),
        skill("inspect-past-execution", "Inspect past execution", "Find prior workflow, conversation, and agent evidence before repeating work.", &["search_history", "inspect_trace", "compare_runs", "summarize_lessons"], &["workspace.read"], &["agent", "history", "wisdom"]),
        skill("incident-triage", "Triage incident", "Bound scope, gather read-only evidence, classify impact, and propose a reversible next action.", &["classify_impact", "collect_evidence", "check_permissions", "propose_recovery"], &["workspace.read", "git.read"], &["operations", "safety", "repair"]),
        skill("build-workflow-from-request", "Build workflow from request", "Translate an objective into ordinary Kogwistar workflow nodes, edges, predicates, and checks.", &["clarify_objective", "select_capabilities", "design_graph", "validate_termination"], &["workspace.read"], &["workflow", "planning", "goal"]),
        skill("delegate-vision-inspection", "Delegate vision inspection", "Delegate isolated image or UI inspection to an approved vision-capable subagent.", &["prepare_minimal_context", "request_inspection", "check_result", "record_provenance"], &["agent.delegate"], &["agent", "delegation", "vision"]),
        skill("discover-capability", "Discover capability", "Search tools, MCP descriptors, and skills progressively before requesting installation or access.", &["search_catalog", "filter_acl", "inspect_manifest", "request_authorization"], &["workspace.read"], &["skills", "mcp", "progressive-revelation"]),
    ]
}
