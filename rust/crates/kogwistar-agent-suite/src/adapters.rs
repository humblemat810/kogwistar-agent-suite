use serde::Serialize;
use serde_json::Value;

use crate::authorization::{
    require_acl, require_approval, require_capabilities, AclResolver, ApprovalResolver,
};
use crate::catalog::{CapabilityDescriptor, CapabilityKind};
use crate::errors::{SuiteError, SuiteResult};
use crate::plugins::PluginManifest;

pub type JsonTransport<'a> =
    dyn Fn(&str, &str, Option<&Value>, Option<&Value>) -> SuiteResult<Value> + Send + Sync + 'a;
pub type TextFetcher<'a> = dyn Fn(&str) -> SuiteResult<String> + Send + Sync + 'a;
pub type LlmWikiParser<'a> = dyn Fn(&Value) -> SuiteResult<Value> + Send + Sync + 'a;
pub type SlackClient<'a> = dyn SlackTransport + Send + Sync + 'a;

pub trait SlackTransport {
    fn search_messages(&self, query: &str, limit: usize) -> SuiteResult<Value>;
    fn send_message(&self, channel: &str, text: &str) -> SuiteResult<Value>;
}

fn authorize(
    action: &str,
    request: &Value,
    descriptor: &CapabilityDescriptor,
    required: &[&str],
    effective: &[String],
    acl: Option<&AclResolver<'_>>,
) -> SuiteResult<()> {
    require_acl(action, request, descriptor, acl)?;
    require_capabilities(
        &required
            .iter()
            .map(|item| item.to_string())
            .collect::<Vec<_>>(),
        effective,
        action,
    )
}

fn limit(value: usize, maximum: usize) -> SuiteResult<usize> {
    if value == 0 || value > maximum {
        return Err(SuiteError::Invalid(format!(
            "limit must be between 1 and {maximum}"
        )));
    }
    Ok(value)
}

fn descriptor(
    capability_id: &str,
    name: &str,
    summary: &str,
    required: &[&str],
    provider_id: &str,
    side_effect: &str,
) -> CapabilityDescriptor {
    CapabilityDescriptor {
        capability_id: capability_id.into(),
        name: name.into(),
        kind: CapabilityKind::Tool,
        summary: summary.into(),
        required_capabilities: required.iter().map(|item| item.to_string()).collect(),
        tags: vec!["adapter".into(), side_effect.into()],
        provider_id: provider_id.into(),
        semantic_ready: false,
        metadata: [("side_effect".to_string(), side_effect.to_string())]
            .into_iter()
            .collect(),
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct AdapterManifest {
    pub manifest: PluginManifest,
}

pub struct GitHubAdapter<'a> {
    transport: Box<JsonTransport<'a>>,
    pub repository: Option<String>,
}

impl<'a> GitHubAdapter<'a> {
    pub fn new(
        transport: impl Fn(&str, &str, Option<&Value>, Option<&Value>) -> SuiteResult<Value>
            + Send
            + Sync
            + 'a,
        repository: Option<String>,
    ) -> Self {
        Self {
            transport: Box::new(transport),
            repository,
        }
    }

    pub fn manifest(&self) -> SuiteResult<PluginManifest> {
        PluginManifest::new(
            "kogwistar-agent-suite.github",
            "0.1.0",
            ["github.read", "github.write"],
        )
    }

    pub fn descriptors(&self) -> SuiteResult<Vec<CapabilityDescriptor>> {
        let manifest = self.manifest()?;
        Ok(vec![
            descriptor(
                "tool:github.search_issues",
                "Search GitHub issues",
                "Search issues and pull requests with bounded results.",
                &["github.read"],
                &manifest.plugin_id,
                "read",
            ),
            descriptor(
                "tool:github.create_issue",
                "Create GitHub issue",
                "Create an issue only after explicit host approval.",
                &["github.write"],
                &manifest.plugin_id,
                "write",
            ),
        ])
    }

    pub fn search_issues(
        &self,
        query: &str,
        effective: &[String],
        acl: Option<&AclResolver<'_>>,
        count: usize,
    ) -> SuiteResult<Value> {
        let request =
            serde_json::json!({"query": query, "repository": self.repository, "limit": count});
        authorize(
            "github.search_issues",
            &request,
            &descriptor(
                "tool:github.search_issues",
                "Search GitHub issues",
                "Search issues and pull requests with bounded results.",
                &["github.read"],
                "kogwistar-agent-suite.github",
                "read",
            ),
            &["github.read"],
            effective,
            acl,
        )?;
        let count = limit(count, 100)?;
        (self.transport)(
            "GET",
            "/search/issues",
            Some(&serde_json::json!({"q": query, "per_page": count})),
            None,
        )
    }

    pub fn create_issue(
        &self,
        title: &str,
        body: &str,
        effective: &[String],
        acl: Option<&AclResolver<'_>>,
        approve: Option<&ApprovalResolver<'_>>,
    ) -> SuiteResult<Value> {
        let request =
            serde_json::json!({"repository": self.repository, "title": title, "body": body});
        authorize(
            "github.create_issue",
            &request,
            &descriptor(
                "tool:github.create_issue",
                "Create GitHub issue",
                "Create an issue only after explicit host approval.",
                &["github.write"],
                "kogwistar-agent-suite.github",
                "write",
            ),
            &["github.write"],
            effective,
            acl,
        )?;
        let Some(repository) = &self.repository else {
            return Err(SuiteError::Invalid(
                "repository is required for issue creation".into(),
            ));
        };
        require_approval("github.create_issue", &request, approve)?;
        (self.transport)(
            "POST",
            &format!("/repos/{repository}/issues"),
            None,
            Some(&request),
        )
    }
}

pub struct BrowserAdapter<'a> {
    fetch_text: Box<TextFetcher<'a>>,
    pub max_chars: usize,
}

impl<'a> BrowserAdapter<'a> {
    pub fn new(fetch_text: impl Fn(&str) -> SuiteResult<String> + Send + Sync + 'a) -> Self {
        Self {
            fetch_text: Box::new(fetch_text),
            max_chars: 200_000,
        }
    }

    pub fn descriptors(&self) -> Vec<CapabilityDescriptor> {
        vec![descriptor(
            "tool:browser.fetch",
            "Fetch web page",
            "Fetch a bounded page through the host's browser transport.",
            &["browser.read"],
            "kogwistar-agent-suite.browser",
            "read",
        )]
    }

    pub fn fetch(
        &self,
        url: &str,
        effective: &[String],
        acl: Option<&AclResolver<'_>>,
    ) -> SuiteResult<String> {
        let request = serde_json::json!({"url": url, "side_effect": "read"});
        authorize(
            "browser.fetch",
            &request,
            &descriptor(
                "tool:browser.fetch",
                "Fetch web page",
                "Fetch a bounded page through the host's browser transport.",
                &["browser.read"],
                "kogwistar-agent-suite.browser",
                "read",
            ),
            &["browser.read"],
            effective,
            acl,
        )?;
        let text = (self.fetch_text)(url)?;
        if text.len() > self.max_chars {
            return Err(SuiteError::Invalid(format!(
                "browser response exceeds {} characters",
                self.max_chars
            )));
        }
        Ok(text)
    }
}

pub struct SlackAdapter<'a> {
    client: Box<SlackClient<'a>>,
}

impl<'a> SlackAdapter<'a> {
    pub fn new(client: impl SlackTransport + Send + Sync + 'a) -> Self {
        Self {
            client: Box::new(client),
        }
    }

    pub fn descriptors(&self) -> Vec<CapabilityDescriptor> {
        vec![
            descriptor(
                "tool:slack.search",
                "Search Slack",
                "Search messages with bounded results.",
                &["slack.read"],
                "kogwistar-agent-suite.slack",
                "read",
            ),
            descriptor(
                "tool:slack.send",
                "Send Slack message",
                "Send a message only after explicit approval.",
                &["slack.write"],
                "kogwistar-agent-suite.slack",
                "write",
            ),
        ]
    }

    pub fn search(
        &self,
        query: &str,
        effective: &[String],
        acl: Option<&AclResolver<'_>>,
        count: usize,
    ) -> SuiteResult<Value> {
        let request = serde_json::json!({"query": query, "limit": count});
        authorize(
            "slack.search",
            &request,
            &descriptor(
                "tool:slack.search",
                "Search Slack",
                "Search messages with bounded results.",
                &["slack.read"],
                "kogwistar-agent-suite.slack",
                "read",
            ),
            &["slack.read"],
            effective,
            acl,
        )?;
        let count = limit(count, 100)?;
        self.client.search_messages(query, count)
    }

    pub fn send(
        &self,
        channel: &str,
        text: &str,
        effective: &[String],
        acl: Option<&AclResolver<'_>>,
        approve: Option<&ApprovalResolver<'_>>,
    ) -> SuiteResult<Value> {
        let request = serde_json::json!({"channel": channel, "text": text});
        authorize(
            "slack.send",
            &request,
            &descriptor(
                "tool:slack.send",
                "Send Slack message",
                "Send a message only after explicit approval.",
                &["slack.write"],
                "kogwistar-agent-suite.slack",
                "write",
            ),
            &["slack.write"],
            effective,
            acl,
        )?;
        require_approval("slack.send", &request, approve)?;
        self.client.send_message(channel, text)
    }
}

pub struct AtlassianAdapter<'a> {
    transport: Box<JsonTransport<'a>>,
    pub site: String,
}

impl<'a> AtlassianAdapter<'a> {
    pub fn new(
        transport: impl Fn(&str, &str, Option<&Value>, Option<&Value>) -> SuiteResult<Value>
            + Send
            + Sync
            + 'a,
        site: impl Into<String>,
    ) -> Self {
        Self {
            transport: Box::new(transport),
            site: site.into(),
        }
    }

    pub fn descriptors(&self) -> Vec<CapabilityDescriptor> {
        vec![
            descriptor(
                "tool:atlassian.search_jira",
                "Search Jira",
                "Search Jira issues with bounded results.",
                &["atlassian.read"],
                "kogwistar-agent-suite.atlassian",
                "read",
            ),
            descriptor(
                "tool:atlassian.search_confluence",
                "Search Confluence",
                "Search Confluence pages with bounded results.",
                &["atlassian.read"],
                "kogwistar-agent-suite.atlassian",
                "read",
            ),
        ]
    }

    pub fn search_jira(
        &self,
        query: &str,
        effective: &[String],
        acl: Option<&AclResolver<'_>>,
        count: usize,
    ) -> SuiteResult<Value> {
        let request = serde_json::json!({"site": self.site, "query": query, "limit": count});
        authorize(
            "atlassian.search_jira",
            &request,
            &descriptor(
                "tool:atlassian.search_jira",
                "Search Jira",
                "Search Jira issues with bounded results.",
                &["atlassian.read"],
                "kogwistar-agent-suite.atlassian",
                "read",
            ),
            &["atlassian.read"],
            effective,
            acl,
        )?;
        let count = limit(count, 100)?;
        (self.transport)(
            "GET",
            "/rest/api/3/search",
            Some(&serde_json::json!({"jql": query, "maxResults": count})),
            None,
        )
    }

    pub fn search_confluence(
        &self,
        query: &str,
        effective: &[String],
        acl: Option<&AclResolver<'_>>,
        count: usize,
    ) -> SuiteResult<Value> {
        let request = serde_json::json!({"site": self.site, "query": query, "limit": count});
        authorize(
            "atlassian.search_confluence",
            &request,
            &descriptor(
                "tool:atlassian.search_confluence",
                "Search Confluence",
                "Search Confluence pages with bounded results.",
                &["atlassian.read"],
                "kogwistar-agent-suite.atlassian",
                "read",
            ),
            &["atlassian.read"],
            effective,
            acl,
        )?;
        let count = limit(count, 100)?;
        (self.transport)(
            "GET",
            "/wiki/rest/api/content/search",
            Some(&serde_json::json!({"cql": query, "limit": count})),
            None,
        )
    }
}

pub fn adapter_descriptors(
    adapters: &[&dyn Fn() -> SuiteResult<Vec<CapabilityDescriptor>>],
) -> SuiteResult<Vec<CapabilityDescriptor>> {
    let mut descriptors = Vec::new();
    for adapter in adapters {
        descriptors.extend(adapter()?);
    }
    Ok(descriptors)
}
