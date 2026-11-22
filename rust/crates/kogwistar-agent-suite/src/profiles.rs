use serde_json::Value;
use std::collections::BTreeMap;
use std::path::PathBuf;

use crate::catalog::{CapabilityCatalog, CapabilitySearchResult};
use crate::errors::SuiteResult;
use crate::hooks::HookBundle;
use crate::plugins::{PluginManifest, PluginRegistry};
use crate::selection::{Implementation, SuiteSeam, SuiteSelection};
use crate::skills::{developer_skills, SkillDescriptor};
use crate::tools::{LocalWorkspaceTool, ToolDescriptor, ToolRegistry};

pub struct DeveloperPack<'a> {
    pub tools: ToolRegistry<'a>,
    pub catalog: CapabilityCatalog,
    pub plugins: PluginRegistry<'a>,
    pub skills: Vec<SkillDescriptor>,
    pub hooks: Vec<HookBundle<'a>>,
}

impl<'a> DeveloperPack<'a> {
    pub fn search(
        &self,
        query: &str,
        allowed_capabilities: &[String],
        acl: Option<&crate::authorization::AclResolver<'_>>,
        mode: &str,
        limit: usize,
    ) -> SuiteResult<Vec<CapabilitySearchResult>> {
        self.catalog
            .search_ranked(query, allowed_capabilities, acl, mode, limit)
    }
}

#[derive(Debug, Default)]
pub struct DeveloperProfileBuilder {
    workspace_root: Option<PathBuf>,
    selection: SuiteSelection,
}

impl DeveloperProfileBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn workspace_root(mut self, root: impl Into<PathBuf>) -> Self {
        self.workspace_root = Some(root.into());
        self
    }

    pub fn selection(mut self, selection: SuiteSelection) -> Self {
        self.selection = selection;
        self
    }

    pub fn seam(mut self, seam: SuiteSeam, implementation: Implementation) -> Self {
        self.selection.seams.insert(seam, implementation);
        self
    }

    pub fn build<'a>(self) -> SuiteResult<DeveloperPack<'a>> {
        let root = self.workspace_root.unwrap_or_else(|| PathBuf::from("."));
        let list_files = LocalWorkspaceTool::new(&root);
        let read_text = LocalWorkspaceTool::new(&root);
        let search_text = LocalWorkspaceTool::new(&root);
        let mut tools = ToolRegistry::default();
        tools.register(
            ToolDescriptor {
                tool_id: "workspace.list_files".into(),
                name: "List workspace files".into(),
                summary: "List bounded files below the configured workspace root.".into(),
                required_capabilities: vec!["workspace.read".into()],
                side_effect: Some("read".into()),
            },
            move |arguments: &Value| {
                let path = arguments
                    .get("relative_path")
                    .and_then(Value::as_str)
                    .unwrap_or(".");
                let limit = arguments
                    .get("limit")
                    .and_then(Value::as_u64)
                    .unwrap_or(100) as usize;
                Ok(serde_json::to_value(list_files.list_files(path, limit)?)?)
            },
        )?;
        tools.register(
            ToolDescriptor {
                tool_id: "workspace.read_text".into(),
                name: "Read workspace text".into(),
                summary: "Read bounded UTF-8 text below the configured workspace root.".into(),
                required_capabilities: vec!["workspace.read".into()],
                side_effect: Some("read".into()),
            },
            move |arguments: &Value| {
                let path = arguments
                    .get("relative_path")
                    .and_then(Value::as_str)
                    .unwrap_or(".");
                let max_bytes = arguments
                    .get("max_bytes")
                    .and_then(Value::as_u64)
                    .unwrap_or(65536) as usize;
                Ok(serde_json::to_value(read_text.read_text(path, max_bytes)?)?)
            },
        )?;
        tools.register(
            ToolDescriptor {
                tool_id: "workspace.search_text".into(),
                name: "Search workspace text".into(),
                summary: "Search bounded UTF-8 text below the configured workspace root.".into(),
                required_capabilities: vec!["workspace.read".into()],
                side_effect: Some("read".into()),
            },
            move |arguments: &Value| {
                let query = arguments
                    .get("query")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                let limit = arguments
                    .get("limit")
                    .and_then(Value::as_u64)
                    .unwrap_or(100) as usize;
                let max_file_bytes = arguments
                    .get("max_file_bytes")
                    .and_then(Value::as_u64)
                    .unwrap_or(65536) as usize;
                Ok(serde_json::to_value(search_text.search_text(
                    query,
                    limit,
                    max_file_bytes,
                )?)?)
            },
        )?;
        for (tool_id, name, summary) in [
            (
                "git.status",
                "Read Git status",
                "Read branch and working-tree status without mutation.",
            ),
            (
                "git.diff_stat",
                "Read Git diff stat",
                "Read a bounded working-tree diff summary.",
            ),
        ] {
            tools.register(
                ToolDescriptor {
                    tool_id: tool_id.into(),
                    name: name.into(),
                    summary: summary.into(),
                    required_capabilities: vec!["git.read".into()],
                    side_effect: Some("read".into()),
                },
                move |_arguments: &Value| Ok(serde_json::json!({"ok": true})),
            )?;
        }
        let mut catalog = CapabilityCatalog::new();
        for descriptor in tools.descriptor_catalog()?.descriptors() {
            catalog.add(descriptor)?;
        }
        for skill in developer_skills() {
            catalog.add(skill.descriptor())?;
        }
        let mut plugins = PluginRegistry::default();
        plugins.register(
            PluginManifest {
                plugin_id: "kogwistar-agent-suite.developer".into(),
                version: "0.2.0".into(),
                capabilities: vec![
                    "workspace.read".into(),
                    "git.read".into(),
                    "shell.test".into(),
                ],
                optional: true,
                metadata: BTreeMap::new(),
            },
            None::<fn() -> SuiteResult<()>>,
        )?;
        Ok(DeveloperPack {
            tools,
            catalog,
            plugins,
            skills: developer_skills(),
            hooks: Vec::new(),
        })
    }
}
