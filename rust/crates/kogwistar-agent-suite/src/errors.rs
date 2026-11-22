use thiserror::Error;

#[derive(Debug, Error)]
pub enum SuiteError {
    #[error("explicit ACL resolver required: {action}")]
    MissingAcl { action: String },
    #[error("ACL denied: {action}")]
    AclDenied { action: String },
    #[error("explicit approval required: {action}")]
    MissingApproval { action: String },
    #[error("capabilities denied for {action}: {missing}")]
    CapabilitiesDenied { action: String, missing: String },
    #[error("duplicate {kind}: {id}")]
    Duplicate { kind: &'static str, id: String },
    #[error("unknown {kind}: {id}")]
    Unknown { kind: &'static str, id: String },
    #[error("{0}")]
    Invalid(String),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type SuiteResult<T> = Result<T, SuiteError>;
