use crate::catalog::{CapabilityCatalog, CapabilityDescriptor, CapabilityKind};
use crate::errors::SuiteResult;
use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct McpCapability {
    pub server_id: String,
    pub tool_name: String,
    pub summary: String,
    pub required_capabilities: Vec<String>,
}

impl McpCapability {
    pub fn capability_id(&self) -> String {
        format!("mcp:{}:{}", self.server_id, self.tool_name)
    }

    pub fn descriptor(&self) -> CapabilityDescriptor {
        CapabilityDescriptor {
            capability_id: self.capability_id(),
            name: self.tool_name.clone(),
            kind: CapabilityKind::Mcp,
            summary: self.summary.clone(),
            required_capabilities: self.required_capabilities.clone(),
            tags: vec!["mcp".into(), self.server_id.clone()],
            provider_id: self.server_id.clone(),
            semantic_ready: false,
            metadata: Default::default(),
        }
    }
}

#[derive(Default)]
pub struct McpCatalog {
    capabilities: Vec<McpCapability>,
}

impl McpCatalog {
    pub fn new(capabilities: impl IntoIterator<Item = McpCapability>) -> SuiteResult<Self> {
        let mut catalog = Self::default();
        for capability in capabilities {
            catalog.add(capability)?;
        }
        Ok(catalog)
    }

    pub fn add(&mut self, capability: McpCapability) -> SuiteResult<()> {
        if self
            .capabilities
            .iter()
            .any(|item| item.capability_id() == capability.capability_id())
        {
            return Err(crate::errors::SuiteError::Duplicate {
                kind: "MCP capability",
                id: capability.capability_id(),
            });
        }
        self.capabilities.push(capability);
        Ok(())
    }

    pub fn search(
        &self,
        query: &str,
        allowed_capabilities: &[String],
        acl: Option<&crate::authorization::AclResolver<'_>>,
        mode: &str,
        limit: usize,
    ) -> SuiteResult<Vec<CapabilityDescriptor>> {
        CapabilityCatalog::from_items(self.capabilities.iter().map(McpCapability::descriptor))?
            .search(query, allowed_capabilities, acl, mode, limit)
    }
}
