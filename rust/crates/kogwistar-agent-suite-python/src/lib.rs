use kogwistar_agent_suite::RuntimePort;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use serde_json::Value;

fn value_error(error: kogwistar_agent_suite::SuiteError) -> PyErr {
    PyErr::new::<PyValueError, _>(error.to_string())
}

#[pyfunction]
#[pyo3(signature = (payload_json))]
fn capability_search_json(_py: Python<'_>, payload_json: &str) -> PyResult<String> {
    let payload: Value = serde_json::from_str(payload_json)
        .map_err(|error| PyErr::new::<PyValueError, _>(format!("invalid JSON: {error}")))?;
    let query = payload
        .get("query")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let allowed: Vec<String> = payload
        .get("allowed_capabilities")
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default();
    let mode = payload
        .get("mode")
        .and_then(Value::as_str)
        .unwrap_or("lexical");
    let limit = payload.get("limit").and_then(Value::as_u64).unwrap_or(20) as usize;
    let descriptors: Vec<kogwistar_agent_suite::CapabilityDescriptor> = payload
        .get("descriptors")
        .cloned()
        .map(serde_json::from_value)
        .transpose()
        .map_err(|error| value_error(error.into()))?
        .unwrap_or_default();
    let result: kogwistar_agent_suite::SuiteResult<Vec<_>> = {
        let mut catalog = kogwistar_agent_suite::CapabilityCatalog::new();
        for item in descriptors {
            if let Err(error) = catalog.add(item) {
                return Err(value_error(error));
            }
        }
        catalog.search(query, &allowed, None, mode, limit)
    };
    let result = result.map_err(value_error)?;
    serde_json::to_string(&result).map_err(|error| PyErr::new::<PyValueError, _>(error.to_string()))
}

fn workspace_tool_from_payload(
    payload: &Value,
) -> Result<kogwistar_agent_suite::LocalWorkspaceTool, PyErr> {
    let root = payload
        .get("workspace_root")
        .and_then(Value::as_str)
        .ok_or_else(|| PyErr::new::<PyValueError, _>("workspace_root is required"))?;
    Ok(kogwistar_agent_suite::LocalWorkspaceTool::new(root))
}

#[pyfunction]
fn workspace_list_files_json(_py: Python<'_>, payload_json: &str) -> PyResult<String> {
    let payload: Value = serde_json::from_str(payload_json)
        .map_err(|error| PyErr::new::<PyValueError, _>(format!("invalid JSON: {error}")))?;
    let tool = workspace_tool_from_payload(&payload)?;
    let path = payload
        .get("relative_path")
        .and_then(Value::as_str)
        .unwrap_or(".");
    let limit = payload.get("limit").and_then(Value::as_u64).unwrap_or(100) as usize;
    let result = tool.list_files(path, limit).map_err(value_error)?;
    serde_json::to_string(&result).map_err(|error| PyErr::new::<PyValueError, _>(error.to_string()))
}

#[pyfunction]
fn workspace_read_text_json(_py: Python<'_>, payload_json: &str) -> PyResult<String> {
    let payload: Value = serde_json::from_str(payload_json)
        .map_err(|error| PyErr::new::<PyValueError, _>(format!("invalid JSON: {error}")))?;
    let tool = workspace_tool_from_payload(&payload)?;
    let path = payload
        .get("relative_path")
        .and_then(Value::as_str)
        .unwrap_or(".");
    let max_bytes = payload
        .get("max_bytes")
        .and_then(Value::as_u64)
        .unwrap_or(65536) as usize;
    let result = tool.read_text(path, max_bytes).map_err(value_error)?;
    serde_json::to_string(&result).map_err(|error| PyErr::new::<PyValueError, _>(error.to_string()))
}

#[pyfunction]
fn workspace_search_text_json(_py: Python<'_>, payload_json: &str) -> PyResult<String> {
    let payload: Value = serde_json::from_str(payload_json)
        .map_err(|error| PyErr::new::<PyValueError, _>(format!("invalid JSON: {error}")))?;
    let tool = workspace_tool_from_payload(&payload)?;
    let query = payload
        .get("query")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let limit = payload.get("limit").and_then(Value::as_u64).unwrap_or(100) as usize;
    let max_file_bytes = payload
        .get("max_file_bytes")
        .and_then(Value::as_u64)
        .unwrap_or(65536) as usize;
    let result = tool
        .search_text(query, limit, max_file_bytes)
        .map_err(value_error)?;
    serde_json::to_string(&result).map_err(|error| PyErr::new::<PyValueError, _>(error.to_string()))
}

#[pyfunction]
fn git_status_json(_py: Python<'_>, payload_json: &str) -> PyResult<String> {
    let payload: Value = serde_json::from_str(payload_json)
        .map_err(|error| PyErr::new::<PyValueError, _>(format!("invalid JSON: {error}")))?;
    let root = payload
        .get("workspace_root")
        .and_then(Value::as_str)
        .unwrap_or(".");
    let result = kogwistar_agent_suite::GitReadTool::new(root)
        .status()
        .map_err(value_error)?;
    serde_json::to_string(&result).map_err(|error| PyErr::new::<PyValueError, _>(error.to_string()))
}

#[pyfunction]
fn core_runtime_run_json(_py: Python<'_>, payload_json: &str) -> PyResult<String> {
    let payload: Value = serde_json::from_str(payload_json)
        .map_err(|error| PyErr::new::<PyValueError, _>(format!("invalid JSON: {error}")))?;
    let result = kogwistar_agent_suite::CoreRuntimePort.run(&payload);
    let result = result.map_err(value_error)?;
    serde_json::to_string(&result).map_err(|error| PyErr::new::<PyValueError, _>(error.to_string()))
}

#[pyfunction]
fn core_runtime_resume_json(_py: Python<'_>, payload_json: &str) -> PyResult<String> {
    let payload: Value = serde_json::from_str(payload_json)
        .map_err(|error| PyErr::new::<PyValueError, _>(format!("invalid JSON: {error}")))?;
    let result = kogwistar_agent_suite::CoreRuntimePort.resume_from_latest_checkpoint(&payload);
    let result = result.map_err(value_error)?;
    serde_json::to_string(&result).map_err(|error| PyErr::new::<PyValueError, _>(error.to_string()))
}

#[pyfunction]
fn implementation_version() -> String {
    env!("CARGO_PKG_VERSION").into()
}

#[pymodule]
fn _rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(capability_search_json, module)?)?;
    module.add_function(wrap_pyfunction!(workspace_list_files_json, module)?)?;
    module.add_function(wrap_pyfunction!(workspace_read_text_json, module)?)?;
    module.add_function(wrap_pyfunction!(workspace_search_text_json, module)?)?;
    module.add_function(wrap_pyfunction!(git_status_json, module)?)?;
    module.add_function(wrap_pyfunction!(core_runtime_run_json, module)?)?;
    module.add_function(wrap_pyfunction!(core_runtime_resume_json, module)?)?;
    module.add_function(wrap_pyfunction!(implementation_version, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
