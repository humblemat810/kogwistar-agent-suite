pub mod adapters;
pub mod authorization;
pub mod catalog;
pub mod cli;
pub mod errors;
pub mod hooks;
pub mod mcp;
pub mod plugins;
pub mod ports;
pub mod profiles;
pub mod selection;
pub mod skills;
pub mod tools;

pub use authorization::{
    allow_read_only_tool, require_acl, require_approval, require_capabilities, AclDecision,
    AclResolver, ApprovalResolver,
};
pub use catalog::{
    CapabilityCatalog, CapabilityDescriptor, CapabilityKind, CapabilitySearchResult, SemanticRanker,
};
pub use errors::{SuiteError, SuiteResult};
pub use hooks::{run_hooks, HookBundle, HookFn};
pub use mcp::{McpCapability, McpCatalog};
pub use plugins::{PluginManifest, PluginRegistry};
pub use ports::{CoreRuntimePort, RuntimePort, SuitePort};
pub use profiles::{DeveloperPack, DeveloperProfileBuilder};
pub use selection::{selected_implementation, Implementation, SuiteSeam, SuiteSelection};
pub use skills::{developer_skills, SkillDescriptor};
pub use tools::{
    CommandResult, GitReadTool, LocalWorkspaceTool, ToolCall, ToolDescriptor, ToolRegistry,
};
