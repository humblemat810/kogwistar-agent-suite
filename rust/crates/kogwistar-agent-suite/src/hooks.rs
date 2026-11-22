use serde_json::{Map, Value};

use crate::errors::{SuiteError, SuiteResult};
use crate::selection::selected_implementation;

pub type HookFn<'a> = dyn Fn(&Value) -> SuiteResult<Option<Map<String, Value>>> + Send + Sync + 'a;

pub struct HookBundle<'a> {
    pub name: String,
    pub hooks: Vec<Box<HookFn<'a>>>,
    pub fail_closed: bool,
    pub timeout_ms: u64,
    pub required_capabilities: Vec<String>,
}

impl<'a> HookBundle<'a> {
    pub fn new(name: impl Into<String>) -> SuiteResult<Self> {
        Self::with_details(name, Vec::new(), true, 1000, Vec::new())
    }

    pub fn with_details(
        name: impl Into<String>,
        hooks: Vec<Box<HookFn<'a>>>,
        fail_closed: bool,
        timeout_ms: u64,
        required_capabilities: Vec<String>,
    ) -> SuiteResult<Self> {
        let name = name.into();
        if name.trim().is_empty() {
            return Err(SuiteError::Invalid("hook bundle name is required".into()));
        }
        if timeout_ms == 0 {
            return Err(SuiteError::Invalid("hook timeout must be positive".into()));
        }
        Ok(Self {
            name,
            hooks,
            fail_closed,
            timeout_ms,
            required_capabilities,
        })
    }
}

pub fn run_hooks<'a>(
    bundles: &[HookBundle<'a>],
    payload: &Value,
    effective_capabilities: &[String],
) -> SuiteResult<Value> {
    let selected = selected_implementation(crate::selection::SuiteSeam::Hooks)?;
    if matches!(selected, crate::selection::Implementation::Rust) {
        let mut current = payload.clone();
        for bundle in bundles {
            for (index, hook) in bundle.hooks.iter().enumerate() {
                if !bundle
                    .required_capabilities
                    .iter()
                    .all(|capability| effective_capabilities.contains(capability))
                {
                    if bundle.fail_closed {
                        return Err(SuiteError::CapabilitiesDenied {
                            action: format!("{}:{index}", bundle.name),
                            missing: bundle.required_capabilities.join(", "),
                        });
                    }
                    continue;
                }
                match hook(&current) {
                    Ok(Some(annotations)) => {
                        if let Value::Object(current) = &mut current {
                            for (key, value) in annotations {
                                current.insert(key, value);
                            }
                        }
                    }
                    Ok(None) => {}
                    Err(error) if bundle.fail_closed => return Err(error),
                    Err(_) => {}
                }
            }
        }
        return Ok(current);
    }
    Ok(payload.clone())
}
