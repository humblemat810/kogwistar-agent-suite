use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::authorization::{
    require_acl, require_approval, require_capabilities, AclResolver, ApprovalResolver,
};
use crate::catalog::{CapabilityCatalog, CapabilityDescriptor, CapabilityKind};
use crate::errors::{SuiteError, SuiteResult};

pub type ToolImplementation<'a> = dyn Fn(&Value) -> SuiteResult<Value> + Send + Sync + 'a;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ToolDescriptor {
    pub tool_id: String,
    pub name: String,
    pub summary: String,
    pub required_capabilities: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub side_effect: Option<String>,
}

impl ToolDescriptor {
    pub fn descriptor(&self) -> CapabilityDescriptor {
        let side_effect = self
            .side_effect
            .clone()
            .unwrap_or_else(|| "unspecified".into());
        CapabilityDescriptor {
            capability_id: format!("tool:{}", self.tool_id),
            name: self.name.clone(),
            kind: CapabilityKind::Tool,
            summary: self.summary.clone(),
            required_capabilities: self.required_capabilities.clone(),
            tags: vec!["tool".into(), side_effect.clone()],
            provider_id: "kogwistar-agent-suite".into(),
            semantic_ready: false,
            metadata: [("side_effect".to_string(), side_effect)]
                .into_iter()
                .collect(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ToolCall {
    pub tool_id: String,
    pub arguments: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CommandResult {
    pub returncode: i32,
    pub stdout: String,
    pub stderr: String,
}

impl CommandResult {
    pub fn ok(&self) -> bool {
        self.returncode == 0
    }
}

#[derive(Default)]
pub struct ToolRegistry<'a> {
    tools: BTreeMap<String, (ToolDescriptor, Box<ToolImplementation<'a>>)>,
}

impl<'a> ToolRegistry<'a> {
    pub fn register(
        &mut self,
        descriptor: ToolDescriptor,
        implementation: impl Fn(&Value) -> SuiteResult<Value> + Send + Sync + 'a,
    ) -> SuiteResult<()> {
        let side_effect = descriptor.side_effect.as_deref().unwrap_or_default();
        if !matches!(side_effect, "read" | "write") {
            return Err(SuiteError::Invalid(
                "tool side_effect must be explicit: 'read' or 'write'".into(),
            ));
        }
        if side_effect == "write" && descriptor.required_capabilities.is_empty() {
            return Err(SuiteError::Invalid(
                "write tool requires an explicit capability".into(),
            ));
        }
        if self.tools.contains_key(&descriptor.tool_id) {
            return Err(SuiteError::Duplicate {
                kind: "tool",
                id: descriptor.tool_id.clone(),
            });
        }
        self.tools.insert(
            descriptor.tool_id.clone(),
            (descriptor, Box::new(implementation)),
        );
        Ok(())
    }

    pub fn descriptor_catalog(&self) -> SuiteResult<CapabilityCatalog> {
        CapabilityCatalog::from_items(self.tools.values().map(|(item, _)| item.descriptor()))
    }

    pub fn call(
        &self,
        call: &ToolCall,
        allowed_capabilities: &[String],
        acl: Option<&AclResolver<'_>>,
        approve: Option<&ApprovalResolver<'_>>,
    ) -> SuiteResult<Value> {
        let (descriptor, implementation) =
            self.tools
                .get(&call.tool_id)
                .ok_or_else(|| SuiteError::Unknown {
                    kind: "tool",
                    id: call.tool_id.clone(),
                })?;
        let request = serde_json::json!({
            "tool_id": call.tool_id,
            "arguments": call.arguments,
            "side_effect": descriptor.side_effect,
        });
        require_acl(&call.tool_id, &request, &descriptor.descriptor(), acl)?;
        require_capabilities(
            &descriptor.required_capabilities,
            allowed_capabilities,
            &call.tool_id,
        )?;
        if descriptor.side_effect.as_deref() == Some("write") {
            require_approval(&call.tool_id, &request, approve)?;
        }
        implementation(&call.arguments)
    }
}

#[derive(Debug, Clone)]
pub struct LocalWorkspaceTool {
    pub root: PathBuf,
}

fn normalize(path: &Path) -> PathBuf {
    #[cfg(windows)]
    {
        path.canonicalize()
            .unwrap_or_else(|_| path.to_path_buf())
            .components()
            .map(|component| {
                component
                    .as_os_str()
                    .to_string_lossy()
                    .replace("\\\\?\\", "")
            })
            .collect()
    }
    #[cfg(not(windows))]
    {
        path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
    }
}

impl LocalWorkspaceTool {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self {
            root: normalize(Path::new(&root.into())),
        }
    }

    fn resolve(&self, relative_path: &str) -> SuiteResult<PathBuf> {
        let target = normalize(&self.root.join(relative_path));
        if target != self.root && !target.starts_with(&self.root) {
            return Err(SuiteError::Invalid(
                "workspace path escapes configured root".into(),
            ));
        }
        Ok(target)
    }

    pub fn list_files(&self, relative_path: &str, limit: usize) -> SuiteResult<Vec<String>> {
        if limit == 0 || limit > 1000 {
            return Err(SuiteError::Invalid(
                "limit must be between 1 and 1000".into(),
            ));
        }
        let target = self.resolve(relative_path)?;
        if !target.is_dir() {
            return Err(SuiteError::Io(std::io::Error::new(
                std::io::ErrorKind::NotADirectory,
                relative_path,
            )));
        }
        let mut files = Vec::new();
        for entry in walkdir_sorted(&target)? {
            if entry.is_file() {
                files.push(
                    entry
                        .strip_prefix(&self.root)
                        .unwrap_or(&entry)
                        .to_string_lossy()
                        .replace('\\', "/"),
                );
            }
        }
        files.truncate(limit);
        Ok(files)
    }

    pub fn read_text(&self, relative_path: &str, max_bytes: usize) -> SuiteResult<String> {
        if max_bytes == 0 || max_bytes > 1_048_576 {
            return Err(SuiteError::Invalid(
                "max_bytes must be between 1 and 1048576".into(),
            ));
        }
        let target = self.resolve(relative_path)?;
        let metadata = std::fs::metadata(&target)?;
        if !metadata.is_file() {
            return Err(SuiteError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                relative_path,
            )));
        }
        if metadata.len() > max_bytes as u64 {
            return Err(SuiteError::Invalid(format!(
                "file exceeds {max_bytes} byte limit: {relative_path}"
            )));
        }
        Ok(String::from_utf8_lossy(&std::fs::read(&target)?).into_owned())
    }

    pub fn search_text(
        &self,
        query: &str,
        limit: usize,
        max_file_bytes: usize,
    ) -> SuiteResult<Vec<serde_json::Value>> {
        if query.trim().is_empty() {
            return Err(SuiteError::Invalid("query is required".into()));
        }
        if limit == 0 || limit > 1000 || max_file_bytes == 0 || max_file_bytes > 1_048_576 {
            return Err(SuiteError::Invalid(
                "limit must be 1..1000 and max_file_bytes 1..1048576".into(),
            ));
        }
        let query_lower = query.to_lowercase();
        let mut results = Vec::new();
        for file in walkdir_sorted(&self.root)? {
            if !file.is_file() || results.len() >= limit {
                break;
            }
            let Ok(content) = std::fs::read(&file) else {
                continue;
            };
            if content.len() > max_file_bytes {
                continue;
            }
            let text = String::from_utf8_lossy(&content);
            for (index, line) in text.lines().enumerate().take(10000) {
                if line.to_lowercase().contains(&query_lower) {
                    results.push(serde_json::json!({
                        "path": file.strip_prefix(&self.root).unwrap_or(&file).to_string_lossy().replace('\\', "/"),
                        "line": index + 1,
                        "text": line,
                    }));
                    if results.len() == limit {
                        break;
                    }
                }
            }
        }
        Ok(results)
    }
}

fn walkdir_sorted(root: &Path) -> SuiteResult<Vec<PathBuf>> {
    let mut entries = Vec::new();
    let mut queue = vec![root.to_path_buf()];
    while let Some(directory) = queue.pop() {
        let mut children = std::fs::read_dir(&directory)?
            .map(|entry| entry.map(|entry| entry.path()))
            .collect::<Result<Vec<_>, _>>()?;
        children.sort();
        for child in children {
            if child.is_dir() {
                queue.push(child);
            } else {
                entries.push(child);
            }
        }
    }
    entries.sort();
    Ok(entries)
}

#[derive(Debug, Clone)]
pub struct GitReadTool {
    pub root: PathBuf,
    pub timeout_seconds: u64,
    pub max_output_bytes: usize,
}

impl GitReadTool {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self {
            root: root.into(),
            timeout_seconds: 10,
            max_output_bytes: 256 * 1024,
        }
    }

    fn run(&self, args: &[&str]) -> SuiteResult<CommandResult> {
        let output = Command::new("git")
            .args(["-C"])
            .arg(&self.root)
            .args(args)
            .output()?;
        Ok(CommandResult {
            returncode: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        })
    }

    pub fn status(&self) -> SuiteResult<CommandResult> {
        self.run(&["status", "--short", "--branch"])
    }

    pub fn diff_stat(&self) -> SuiteResult<CommandResult> {
        self.run(&["diff", "--stat"])
    }

    pub fn log(&self, limit: usize) -> SuiteResult<CommandResult> {
        if limit == 0 || limit > 1000 {
            return Err(SuiteError::Invalid(
                "limit must be between 1 and 1000".into(),
            ));
        }
        self.run(&["log", "-n", &limit.to_string(), "--oneline"])
    }
}
