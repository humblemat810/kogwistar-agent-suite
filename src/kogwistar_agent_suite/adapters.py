"""Optional external adapters with no mandatory vendor SDK imports.

Adapters receive an injected client/transport. Credentials, network policy,
retries, and host authorization remain outside this package.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from kogwistar.agent import LlmWikiIngestionAdapter

from .catalog import CapabilityDescriptor, CapabilityKind
from .authorization import AclResolver, ApprovalResolver, require_acl, require_approval, require_capabilities
from .plugins import PluginManifest, PluginRegistry


class JsonTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]: ...


Approval = ApprovalResolver
TextFetcher = Callable[[str], str]


def _authorize(
    *,
    action: str,
    request: Mapping[str, Any],
    required: frozenset[str],
    effective: frozenset[str],
    acl: AclResolver | None,
) -> None:
    require_acl(action=action, request=request, acl=acl)
    require_capabilities(required, effective, action=action)


def _limit(value: int, *, maximum: int = 100) -> int:
    if value < 1 or value > maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return value


def _descriptor(
    capability_id: str,
    name: str,
    summary: str,
    required: frozenset[str],
    provider_id: str,
    *,
    side_effect: str = "read",
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        name=name,
        kind=CapabilityKind.TOOL,
        summary=summary,
        required_capabilities=required,
        tags=("adapter", side_effect),
        provider_id=provider_id,
        metadata={"side_effect": side_effect},
    )


class OptionalAdapter(Protocol):
    manifest: PluginManifest

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]: ...

    def close(self) -> None: ...


class GitHubAdapter:
    manifest = PluginManifest("kogwistar-agent-suite.github", "0.1.0", ("github.read", "github.write"))

    def __init__(self, transport: JsonTransport, *, repository: str | None = None) -> None:
        self._transport = transport
        self.repository = repository

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return (
            _descriptor("tool:github.search_issues", "Search GitHub issues", "Search issues and pull requests with bounded results.", frozenset({"github.read"}), self.manifest.plugin_id),
            _descriptor("tool:github.create_issue", "Create GitHub issue", "Create an issue only after explicit host approval.", frozenset({"github.write"}), self.manifest.plugin_id, side_effect="write"),
        )

    def search_issues(self, query: str, *, effective_capabilities: frozenset[str], acl: AclResolver | None = None, limit: int = 20) -> tuple[Mapping[str, Any], ...]:
        request = {"query": query, "repository": self.repository, "limit": limit}
        _authorize(action="github.search_issues", request=request, required=frozenset({"github.read"}), effective=effective_capabilities, acl=acl)
        count = _limit(limit)
        payload = self._transport.request("GET", "/search/issues", params={"q": query, "per_page": count})
        items = payload.get("items", ())
        if not isinstance(items, (list, tuple)):
            raise ValueError("GitHub search response items must be a sequence")
        return tuple(item for item in items[:count] if isinstance(item, Mapping))

    def create_issue(self, title: str, body: str, *, effective_capabilities: frozenset[str], acl: AclResolver | None = None, approve: Approval | None = None) -> Mapping[str, Any]:
        request = {"repository": self.repository, "title": title, "body": body}
        _authorize(action="github.create_issue", request=request, required=frozenset({"github.write"}), effective=effective_capabilities, acl=acl)
        if not self.repository:
            raise ValueError("repository is required for issue creation")
        require_approval(action="github.create_issue", request=request, approve=approve)
        return self._transport.request("POST", f"/repos/{self.repository}/issues", json={"title": title, "body": body})

    def close(self) -> None:
        close = getattr(self._transport, "close", None)
        if callable(close):
            close()


class BrowserAdapter:
    manifest = PluginManifest("kogwistar-agent-suite.browser", "0.1.0", ("browser.read",))

    def __init__(self, fetch_text: TextFetcher, *, max_chars: int = 200_000) -> None:
        self._fetch_text = fetch_text
        self.max_chars = max(1, max_chars)

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return (_descriptor("tool:browser.fetch_text", "Fetch browser text", "Fetch bounded page text through an injected browser client.", frozenset({"browser.read"}), self.manifest.plugin_id),)

    def fetch(self, url: str, *, effective_capabilities: frozenset[str], acl: AclResolver | None = None) -> str:
        _authorize(action="browser.fetch_text", request={"url": url, "max_chars": self.max_chars}, required=frozenset({"browser.read"}), effective=effective_capabilities, acl=acl)
        return self._fetch_text(url)[: self.max_chars]

    def close(self) -> None:
        close = getattr(self._fetch_text, "close", None)
        if callable(close):
            close()


class SlackAdapter:
    manifest = PluginManifest("kogwistar-agent-suite.slack", "0.1.0", ("slack.read", "slack.write"))

    def __init__(self, client: Any) -> None:
        self._client = client

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return (
            _descriptor("tool:slack.search", "Search Slack", "Search messages with bounded results.", frozenset({"slack.read"}), self.manifest.plugin_id),
            _descriptor("tool:slack.send", "Send Slack message", "Send a message only after explicit approval.", frozenset({"slack.write"}), self.manifest.plugin_id, side_effect="write"),
        )

    def search(self, query: str, *, effective_capabilities: frozenset[str], acl: AclResolver | None = None, limit: int = 20) -> Any:
        _authorize(action="slack.search", request={"query": query, "limit": limit}, required=frozenset({"slack.read"}), effective=effective_capabilities, acl=acl)
        count = _limit(limit)
        return self._client.search_messages(query=query, limit=count)

    def send(self, channel: str, text: str, *, effective_capabilities: frozenset[str], acl: AclResolver | None = None, approve: Approval | None = None) -> Any:
        request = {"channel": channel, "text": text}
        _authorize(action="slack.send", request=request, required=frozenset({"slack.write"}), effective=effective_capabilities, acl=acl)
        require_approval(action="slack.send", request=request, approve=approve)
        return self._client.send_message(channel=channel, text=text)

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()


class LlmWikiAdapter:
    manifest = PluginManifest("kogwistar-agent-suite.llm-wiki", "0.1.0", ("llm_wiki.ingest",))

    def __init__(self, parse: Callable[..., Any], *, authorize: Callable[[Mapping[str, Any]], bool]) -> None:
        self._adapter = LlmWikiIngestionAdapter(parse, authorize=authorize)

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return (_descriptor("tool:llm_wiki.ingest_skill", "Ingest LLM-Wiki skill", "Parse an authorized skill source into a validated graph artifact.", frozenset({"llm_wiki.ingest"}), self.manifest.plugin_id),)

    def ingest(self, source: Mapping[str, Any], *, effective_capabilities: frozenset[str], acl: AclResolver | None = None) -> Any:
        _authorize(action="llm_wiki.ingest_skill", request=source, required=frozenset({"llm_wiki.ingest"}), effective=effective_capabilities, acl=acl)
        return self._adapter.parse(source)

    def close(self) -> None:
        self._adapter.close()


class AtlassianAdapter:
    manifest = PluginManifest("kogwistar-agent-suite.atlassian", "0.1.0", ("atlassian.read",))

    def __init__(self, transport: JsonTransport, *, site: str) -> None:
        self._transport = transport
        self.site = site

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return (
            _descriptor("tool:atlassian.search_jira", "Search Jira", "Search Jira issues with bounded results.", frozenset({"atlassian.read"}), self.manifest.plugin_id),
            _descriptor("tool:atlassian.search_confluence", "Search Confluence", "Search Confluence pages with bounded results.", frozenset({"atlassian.read"}), self.manifest.plugin_id),
        )

    def search_jira(self, query: str, *, effective_capabilities: frozenset[str], acl: AclResolver | None = None, limit: int = 20) -> Mapping[str, Any]:
        _authorize(action="atlassian.search_jira", request={"site": self.site, "query": query, "limit": limit}, required=frozenset({"atlassian.read"}), effective=effective_capabilities, acl=acl)
        count = _limit(limit)
        return self._transport.request("GET", "/rest/api/3/search", params={"jql": query, "maxResults": count})

    def search_confluence(self, query: str, *, effective_capabilities: frozenset[str], acl: AclResolver | None = None, limit: int = 20) -> Mapping[str, Any]:
        _authorize(action="atlassian.search_confluence", request={"site": self.site, "query": query, "limit": limit}, required=frozenset({"atlassian.read"}), effective=effective_capabilities, acl=acl)
        count = _limit(limit)
        return self._transport.request("GET", "/wiki/rest/api/content/search", params={"cql": query, "limit": count})

    def close(self) -> None:
        close = getattr(self._transport, "close", None)
        if callable(close):
            close()


def register_optional_adapter(registry: PluginRegistry, adapter: OptionalAdapter) -> None:
    """Register an already-configured adapter; no adapter is auto-loaded."""

    registry.register(adapter.manifest, adapter.close)


def adapter_descriptors(adapters: tuple[OptionalAdapter, ...]) -> tuple[CapabilityDescriptor, ...]:
    return tuple(descriptor for adapter in adapters for descriptor in adapter.descriptors())
