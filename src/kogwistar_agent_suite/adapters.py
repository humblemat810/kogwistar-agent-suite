"""Optional external adapters with no mandatory vendor SDK imports.

Adapters receive an injected client/transport. Credentials, network policy,
retries, and host authorization remain outside this package.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from kogwistar.agent import LlmWikiIngestionAdapter

from .catalog import CapabilityDescriptor, CapabilityKind
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


Approval = Callable[[str, Mapping[str, Any]], bool]
TextFetcher = Callable[[str], str]


def _require_capabilities(required: frozenset[str], effective: frozenset[str]) -> None:
    missing = required - effective
    if missing:
        raise PermissionError("adapter capabilities denied: " + ", ".join(sorted(missing)))


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

    def search_issues(self, query: str, *, effective_capabilities: frozenset[str], limit: int = 20) -> tuple[Mapping[str, Any], ...]:
        _require_capabilities(frozenset({"github.read"}), effective_capabilities)
        count = _limit(limit)
        payload = self._transport.request("GET", "/search/issues", params={"q": query, "per_page": count})
        items = payload.get("items", ())
        if not isinstance(items, (list, tuple)):
            raise ValueError("GitHub search response items must be a sequence")
        return tuple(item for item in items[:count] if isinstance(item, Mapping))

    def create_issue(self, title: str, body: str, *, effective_capabilities: frozenset[str], approve: Approval | None) -> Mapping[str, Any]:
        _require_capabilities(frozenset({"github.write"}), effective_capabilities)
        if not self.repository:
            raise ValueError("repository is required for issue creation")
        request = {"repository": self.repository, "title": title, "body": body}
        if approve is None or not approve("github.create_issue", request):
            raise PermissionError("GitHub write requires explicit approval")
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

    def fetch(self, url: str, *, effective_capabilities: frozenset[str]) -> str:
        _require_capabilities(frozenset({"browser.read"}), effective_capabilities)
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

    def search(self, query: str, *, effective_capabilities: frozenset[str], limit: int = 20) -> Any:
        _require_capabilities(frozenset({"slack.read"}), effective_capabilities)
        return self._client.search_messages(query=query, limit=_limit(limit))

    def send(self, channel: str, text: str, *, effective_capabilities: frozenset[str], approve: Approval | None) -> Any:
        _require_capabilities(frozenset({"slack.write"}), effective_capabilities)
        request = {"channel": channel, "text": text}
        if approve is None or not approve("slack.send", request):
            raise PermissionError("Slack write requires explicit approval")
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

    def ingest(self, source: Mapping[str, Any], *, effective_capabilities: frozenset[str]) -> Any:
        _require_capabilities(frozenset({"llm_wiki.ingest"}), effective_capabilities)
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

    def search_jira(self, query: str, *, effective_capabilities: frozenset[str], limit: int = 20) -> Mapping[str, Any]:
        _require_capabilities(frozenset({"atlassian.read"}), effective_capabilities)
        return self._transport.request("GET", "/rest/api/3/search", params={"jql": query, "maxResults": _limit(limit)})

    def search_confluence(self, query: str, *, effective_capabilities: frozenset[str], limit: int = 20) -> Mapping[str, Any]:
        _require_capabilities(frozenset({"atlassian.read"}), effective_capabilities)
        return self._transport.request("GET", "/wiki/rest/api/content/search", params={"cql": query, "limit": _limit(limit)})

    def close(self) -> None:
        close = getattr(self._transport, "close", None)
        if callable(close):
            close()


def register_optional_adapter(registry: PluginRegistry, adapter: OptionalAdapter) -> None:
    """Register an already-configured adapter; no adapter is auto-loaded."""

    registry.register(adapter.manifest, adapter.close)


def adapter_descriptors(adapters: tuple[OptionalAdapter, ...]) -> tuple[CapabilityDescriptor, ...]:
    return tuple(descriptor for adapter in adapters for descriptor in adapter.descriptors())
