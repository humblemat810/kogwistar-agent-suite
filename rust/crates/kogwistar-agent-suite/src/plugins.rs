use serde::Serialize;

use crate::errors::{SuiteError, SuiteResult};

pub type CleanupFn<'a> = dyn Fn() -> SuiteResult<()> + Send + Sync + 'a;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PluginManifest {
    pub plugin_id: String,
    pub version: String,
    pub capabilities: Vec<String>,
    pub optional: bool,
    pub metadata: std::collections::BTreeMap<String, String>,
}

impl PluginManifest {
    pub fn new(
        plugin_id: impl Into<String>,
        version: impl Into<String>,
        capabilities: impl IntoIterator<Item = impl Into<String>>,
    ) -> SuiteResult<Self> {
        let plugin_id = plugin_id.into();
        let version = version.into();
        if plugin_id.trim().is_empty() || version.trim().is_empty() {
            return Err(SuiteError::Invalid(
                "plugin id and version are required".into(),
            ));
        }
        Ok(Self {
            plugin_id,
            version,
            capabilities: capabilities.into_iter().map(Into::into).collect(),
            optional: true,
            metadata: Default::default(),
        })
    }
}

#[derive(Default)]
pub struct PluginRegistry<'a> {
    plugins: std::collections::BTreeMap<String, (PluginManifest, Option<Box<CleanupFn<'a>>>)>,
}

impl<'a> PluginRegistry<'a> {
    pub fn register(
        &mut self,
        manifest: PluginManifest,
        cleanup: Option<impl Fn() -> SuiteResult<()> + Send + Sync + 'a>,
    ) -> SuiteResult<()> {
        if self
            .plugins
            .insert(
                manifest.plugin_id.clone(),
                (
                    manifest.clone(),
                    cleanup.map(|cleanup| Box::new(cleanup) as Box<CleanupFn<'a>>),
                ),
            )
            .is_some()
        {
            return Err(SuiteError::Duplicate {
                kind: "plugin",
                id: manifest.plugin_id,
            });
        }
        Ok(())
    }

    pub fn get(&self, plugin_id: &str) -> SuiteResult<&PluginManifest> {
        self.plugins
            .get(plugin_id)
            .map(|(manifest, _)| manifest)
            .ok_or_else(|| SuiteError::Unknown {
                kind: "plugin",
                id: plugin_id.into(),
            })
    }

    pub fn unload(&mut self, plugin_id: &str) -> SuiteResult<()> {
        let (_, cleanup) = self
            .plugins
            .remove(plugin_id)
            .ok_or_else(|| SuiteError::Unknown {
                kind: "plugin",
                id: plugin_id.into(),
            })?;
        if let Some(cleanup) = cleanup {
            cleanup()?;
        }
        Ok(())
    }

    pub fn close(&mut self) -> SuiteResult<()> {
        let ids: Vec<String> = self.plugins.keys().cloned().collect();
        for id in ids {
            self.unload(&id)?;
        }
        Ok(())
    }

    pub fn len(&self) -> usize {
        self.plugins.len()
    }

    pub fn is_empty(&self) -> bool {
        self.plugins.is_empty()
    }
}
