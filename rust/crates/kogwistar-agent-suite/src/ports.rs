use serde_json::Value;

use kogwistar_runtime::{
    execute_native_step, reduce_recorded_transition, RecordedRuntimeState,
    RecordedRuntimeTransition, RuntimeNativeStepRequest,
};

use crate::catalog::CapabilityDescriptor;
use crate::errors::SuiteResult;
use crate::selection::Implementation;

pub trait SuitePort: Send + Sync {
    fn implementation(&self) -> Implementation;
    fn descriptors(&self) -> SuiteResult<Vec<CapabilityDescriptor>>;
    fn invoke(&self, operation: &str, arguments: &Value) -> SuiteResult<Value>;
    fn close(&self) -> SuiteResult<()> {
        Ok(())
    }
}

pub trait RuntimePort: Send + Sync {
    fn implementation(&self) -> Implementation;
    fn run(&self, request: &Value) -> SuiteResult<Value>;
    fn resume_from_latest_checkpoint(&self, request: &Value) -> SuiteResult<Value>;
}

pub struct CoreRuntimePort;

impl RuntimePort for CoreRuntimePort {
    fn implementation(&self) -> Implementation {
        Implementation::Rust
    }

    fn run(&self, request: &Value) -> SuiteResult<Value> {
        let step: RuntimeNativeStepRequest = serde_json::from_value(request.clone())?;
        let effect = execute_native_step(&step)
            .map_err(|error| crate::errors::SuiteError::Invalid(error.to_string()))?;
        Ok(serde_json::to_value(effect)?)
    }

    fn resume_from_latest_checkpoint(&self, request: &Value) -> SuiteResult<Value> {
        let current: Option<RecordedRuntimeState> = match request.get("current") {
            Some(value) if !value.is_null() => Some(serde_json::from_value(value.clone())?),
            _ => None,
        };
        let transition: RecordedRuntimeTransition =
            serde_json::from_value(request.get("transition").cloned().ok_or_else(|| {
                crate::errors::SuiteError::Invalid("transition is required".into())
            })?)?;
        let reduced = reduce_recorded_transition(current.as_ref(), &transition)
            .map_err(|error| crate::errors::SuiteError::Invalid(error.to_string()))?;
        Ok(serde_json::to_value(reduced)?)
    }
}
