use kogwistar_agent_suite::*;
use serde_json::json;

fn descriptor(
    id: &str,
    summary: &str,
    capabilities: &[&str],
    semantic_ready: bool,
) -> CapabilityDescriptor {
    CapabilityDescriptor {
        capability_id: id.into(),
        name: id.into(),
        kind: CapabilityKind::Tool,
        summary: summary.into(),
        required_capabilities: capabilities.iter().map(|item| item.to_string()).collect(),
        tags: vec![],
        provider_id: "test".into(),
        semantic_ready,
        metadata: Default::default(),
    }
}

#[test]
fn catalog_filters_acl_before_ranking() {
    let mut catalog = CapabilityCatalog::new();
    catalog
        .add(descriptor(
            "tool:allowed",
            "allowed",
            &["workspace.read"],
            false,
        ))
        .unwrap();
    catalog
        .add(descriptor("tool:hidden", "hidden", &["admin"], false))
        .unwrap();
    let visible = catalog
        .search("tool", &["workspace.read".to_string()], None, "lexical", 10)
        .unwrap();
    assert_eq!(visible.len(), 1);
    assert_eq!(visible[0].capability_id, "tool:allowed");
}

#[test]
fn selection_is_explicit_and_per_seam() {
    let selection = SuiteSelection {
        mode: Implementation::Rust,
        seams: [(SuiteSeam::Tools, Implementation::Python)]
            .into_iter()
            .collect(),
    };
    assert_eq!(selection.selected(SuiteSeam::Catalog), Implementation::Rust);
    assert_eq!(selection.selected(SuiteSeam::Tools), Implementation::Python);
}

#[test]
fn workspace_rejects_escape() {
    let workspace = LocalWorkspaceTool::new(".");
    assert!(workspace.read_text("../Cargo.toml", 1024).is_err());
}

#[test]
fn tool_call_requires_acl_before_implementation() {
    let mut registry: ToolRegistry = ToolRegistry::default();
    registry
        .register(
            ToolDescriptor {
                tool_id: "workspace.read_text".into(),
                name: "Read workspace text".into(),
                summary: "Read text".into(),
                required_capabilities: vec!["workspace.read".into()],
                side_effect: Some("read".into()),
            },
            |_arguments| Ok(json!({"ok": true})),
        )
        .unwrap();
    let call = ToolCall {
        tool_id: "workspace.read_text".into(),
        arguments: json!({}),
    };
    let error = registry
        .call(&call, &["workspace.read".to_string()], None, None)
        .unwrap_err();
    assert!(error.to_string().contains("explicit ACL resolver required"));
}

#[test]
fn tool_call_with_acl_invokes_implementation() {
    let mut registry: ToolRegistry = ToolRegistry::default();
    registry
        .register(
            ToolDescriptor {
                tool_id: "workspace.read_text".into(),
                name: "Read workspace text".into(),
                summary: "Read text".into(),
                required_capabilities: vec!["workspace.read".into()],
                side_effect: Some("read".into()),
            },
            |_arguments| Ok(json!({"ok": true})),
        )
        .unwrap();
    let call = ToolCall {
        tool_id: "workspace.read_text".into(),
        arguments: json!({}),
    };
    let result = registry
        .call(
            &call,
            &["workspace.read".to_string()],
            Some(&|_descriptor| true),
            None,
        )
        .unwrap();
    assert_eq!(result, json!({"ok": true}));
}

#[test]
fn github_adapter_requires_acl_before_transport() {
    let called = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let observed = called.clone();
    let adapter = kogwistar_agent_suite::adapters::GitHubAdapter::new(
        move |_method, _path, _params, _json| {
            observed.store(true, std::sync::atomic::Ordering::SeqCst);
            Ok(json!({"items": []}))
        },
        Some("owner/repo".into()),
    );
    let error = adapter
        .search_issues("rust", &["github.read".to_string()], None, 10)
        .unwrap_err();
    assert!(error.to_string().contains("explicit ACL resolver required"));
    assert!(!called.load(std::sync::atomic::Ordering::SeqCst));
}

#[test]
fn core_runtime_port_reports_rust_implementation() {
    let port = kogwistar_agent_suite::CoreRuntimePort;
    assert_eq!(port.implementation(), Implementation::Rust);
}

#[test]
fn core_runtime_port_validates_core_contract() {
    let error = kogwistar_agent_suite::CoreRuntimePort
        .run(&json!({}))
        .unwrap_err();
    assert!(error.to_string().contains("missing field"));
}
