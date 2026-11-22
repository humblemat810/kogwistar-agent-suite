use serde_json::Value;

use crate::errors::{SuiteError, SuiteResult};

use crate::catalog::CapabilityDescriptor;

pub type AclResolver<'a> = dyn Fn(&CapabilityDescriptor) -> bool + Send + Sync + 'a;
pub type ApprovalResolver<'a> = dyn Fn(&str, &Value) -> bool + Send + Sync + 'a;

pub fn allow_read_only_tool(_action: &str, request: &Value) -> bool {
    request.get("side_effect").and_then(Value::as_str) == Some("read")
}

pub fn require_acl<'a>(
    action: &str,
    _request: &Value,
    descriptor: &CapabilityDescriptor,
    acl: Option<&AclResolver<'a>>,
) -> SuiteResult<()> {
    let Some(acl) = acl else {
        return Err(SuiteError::MissingAcl {
            action: action.into(),
        });
    };
    if acl(descriptor) {
        Ok(())
    } else {
        Err(SuiteError::AclDenied {
            action: action.into(),
        })
    }
}

pub fn require_approval<'a>(
    action: &str,
    request: &Value,
    approve: Option<&ApprovalResolver<'a>>,
) -> SuiteResult<()> {
    if approve.is_some_and(|approve| approve(action, request)) {
        Ok(())
    } else {
        Err(SuiteError::MissingApproval {
            action: action.into(),
        })
    }
}

pub fn require_capabilities(
    required: &[String],
    effective: &[String],
    action: &str,
) -> SuiteResult<()> {
    let missing: Vec<String> = required
        .iter()
        .filter(|capability| !effective.contains(capability))
        .cloned()
        .collect();
    if missing.is_empty() {
        Ok(())
    } else {
        let mut missing = missing;
        missing.sort();
        Err(SuiteError::CapabilitiesDenied {
            action: action.into(),
            missing: missing.join(", "),
        })
    }
}

pub type AclDecision = bool;
