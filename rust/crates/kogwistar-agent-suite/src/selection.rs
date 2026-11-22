use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::errors::{SuiteError, SuiteResult};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Implementation {
    Python,
    Rust,
    Shadow,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SuiteSeam {
    Catalog,
    Tools,
    Runtime,
    Adapters,
    Hooks,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SuiteSelection {
    pub mode: Implementation,
    pub seams: BTreeMap<SuiteSeam, Implementation>,
}

impl Default for SuiteSelection {
    fn default() -> Self {
        Self::python()
    }
}

fn parse(value: &str) -> SuiteResult<Implementation> {
    match value.trim().to_ascii_lowercase().as_str() {
        "python" => Ok(Implementation::Python),
        "rust" => Ok(Implementation::Rust),
        "shadow" => Ok(Implementation::Shadow),
        _ => Err(SuiteError::Invalid(format!(
            "implementation must be python, rust, or shadow: {value}"
        ))),
    }
}

fn env(name: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
}

impl SuiteSelection {
    pub fn python() -> Self {
        Self {
            mode: Implementation::Python,
            seams: BTreeMap::new(),
        }
    }

    pub fn from_env() -> SuiteResult<Self> {
        Self::from_values(
            env("KOGWISTAR_AGENT_IMPL_MODE"),
            &[
                (SuiteSeam::Catalog, "KOGWISTAR_AGENT_IMPL_CATALOG"),
                (SuiteSeam::Tools, "KOGWISTAR_AGENT_IMPL_TOOLS"),
                (SuiteSeam::Runtime, "KOGWISTAR_AGENT_IMPL_RUNTIME"),
                (SuiteSeam::Adapters, "KOGWISTAR_AGENT_IMPL_ADAPTERS"),
                (SuiteSeam::Hooks, "KOGWISTAR_AGENT_IMPL_HOOKS"),
            ],
        )
    }

    pub fn from_values(mode: Option<String>, seam_envs: &[(SuiteSeam, &str)]) -> SuiteResult<Self> {
        let mode = match mode.as_deref() {
            Some(value) => parse(value)?,
            None => Implementation::Python,
        };
        let seams = seam_envs
            .iter()
            .filter_map(|(seam, name)| {
                env(name).map(|value| parse(&value).map(|value| (*seam, value)))
            })
            .collect::<Result<BTreeMap<_, _>, _>>()?;
        Ok(Self { mode, seams })
    }

    pub fn selected(&self, seam: SuiteSeam) -> Implementation {
        *self.seams.get(&seam).unwrap_or(&self.mode)
    }
}

pub fn selected_implementation(seam: SuiteSeam) -> SuiteResult<Implementation> {
    Ok(SuiteSelection::from_env()?.selected(seam))
}
