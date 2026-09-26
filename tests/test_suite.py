import asyncio
from pathlib import Path

import pytest
from kogwistar.agent import parse_skill_text

from kogwistar_agent_suite import (
    AtlassianAdapter,
    BrowserAdapter,
    GitHubAdapter,
    HookBundle,
    LlmWikiAdapter,
    McpCapability,
    McpCatalog,
    PluginManifest,
    PluginRegistry,
    SlackAdapter,
    SkillDescriptor,
    ToolCall,
    ToolDescriptor,
    developer_profile,
    GitReadTool,
    run_hooks,
)
from kogwistar_agent_suite.adapters import adapter_descriptors, register_optional_adapter
from kogwistar_agent_suite.cli import main


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.closed = False

    def request(self, method: str, path: str, *, params=None, json=None):
        self.calls.append((method, path, {"params": params, "json": json}))
        if path == "/search/issues":
            return {"items": [{"number": 1}, {"number": 2}]}
        return {"ok": True, "path": path}

    def close(self) -> None:
        self.closed = True


class FakeSlack:
    def __init__(self) -> None:
        self.closed = False

    def search_messages(self, *, query: str, limit: int):
        return {"query": query, "limit": limit}

    def send_message(self, *, channel: str, text: str):
        return {"channel": channel, "text": text}

    def close(self) -> None:
        self.closed = True


def test_developer_pack_searches_skills_and_tools(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    results = pack.catalog.search(
        "test failure",
        allowed_capabilities=frozenset({"workspace.read", "shell.test"}),
    )
    assert results[0].capability_id == "skill:diagnose-test-failure"


def test_capability_search_supports_bm25_partial_and_acl(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    ranked = pack.search_ranked(
        "workflow planning",
        allowed_capabilities=frozenset({"workspace.read"}),
        mode="bm25",
    )
    assert ranked[0].descriptor.capability_id == "skill:build-workflow-from-request"
    assert ranked[0].match == "bm25"
    assert pack.search_ranked(
        "vision",
        allowed_capabilities=frozenset({"workspace.read"}),
        mode="semantic",
    ) == ()
    partial = pack.search_ranked(
        "capabil",
        allowed_capabilities=frozenset({"workspace.read"}),
    )
    assert partial and partial[0].match in {"partial", "prefix", "exact"}


def test_optional_semantic_ranker_runs_after_acl_and_falls_back(tmp_path: Path) -> None:
    seen: list[str] = []

    def rank(query: str, candidates) -> dict[str, float]:
        seen.append(query)
        return {item.capability_id: 10.0 for item in candidates if item.capability_id.startswith("skill:")}

    pack = developer_profile(str(tmp_path), semantic_ranker=rank)
    pack.catalog.set_semantic_ready("skill:build-workflow-from-request")
    result = pack.search_ranked(
        "anything",
        allowed_capabilities=frozenset({"workspace.read"}),
        mode="semantic",
    )
    assert result[0].match == "semantic"
    assert result[0].descriptor.capability_id.startswith("skill:")
    assert seen == ["anything"]

    def broken(_query: str, _candidates) -> dict[str, float]:
        raise RuntimeError("ranker unavailable")

    fallback = developer_profile(str(tmp_path), semantic_ranker=broken).search_ranked(
        "workflow planning",
        allowed_capabilities=frozenset({"workspace.read"}),
        mode="semantic",
    )
    assert fallback[0].match == "bm25"


def test_semantic_ranker_excludes_pending_projection(tmp_path: Path) -> None:
    seen: list[tuple[str, ...]] = []

    def rank(_query: str, candidates) -> dict[str, float]:
        seen.append(tuple(item.capability_id for item in candidates))
        return {item.capability_id: 1.0 for item in candidates}

    pack = developer_profile(str(tmp_path), semantic_ranker=rank)
    result = pack.search_ranked(
        "workspace",
        allowed_capabilities=frozenset({"workspace.read"}),
        mode="semantic",
    )
    assert result[0].match == "bm25"
    assert seen == [()]


def test_workspace_search_is_bounded_and_deterministic(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("needle second\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("needle first\n", encoding="utf-8")
    pack = developer_profile(str(tmp_path))
    result = pack.tools.call(
        ToolCall("workspace.search_text", {"query": "needle"}),
        allowed_capabilities=frozenset({"workspace.read"}),
    )
    assert [item["path"] for item in result] == ["a.txt", "b.txt"]
    with pytest.raises(PermissionError):
        pack.tools.call(
            ToolCall("workspace.search_text", {"query": "needle", "relative_path": ".."}),
            allowed_capabilities=frozenset({"workspace.read"}),
        )
    with pytest.raises(ValueError):
        pack.tools.call(
            ToolCall("workspace.search_text", {"query": "needle", "max_matches": 0}),
            allowed_capabilities=frozenset({"workspace.read"}),
        )


def test_git_read_tools_are_read_only_and_bounded() -> None:
    tool = GitReadTool(Path(__file__).parents[1])
    assert tool.status().returncode == 0
    assert tool.diff_stat().returncode == 0
    assert tool.log(1).returncode == 0
    with pytest.raises(ValueError):
        tool.log(101)


def test_optional_adapter_composes_into_pack_and_closes(tmp_path: Path) -> None:
    transport = FakeTransport()
    pack = developer_profile(
        str(tmp_path),
        adapters=(GitHubAdapter(transport, repository="example/project"),),
    )
    assert pack.catalog.get("tool:github.search_issues").provider_id == "kogwistar-agent-suite.github"
    assert len(pack.plugins) == 2
    pack.close()
    assert transport.closed is True


def test_skill_ingestion_returns_validated_core_graph(tmp_path: Path) -> None:
    adapter = LlmWikiAdapter(
        lambda source: parse_skill_text(
            str(source["text"]), provider_id="llm-wiki", provider_local_id="deploy"
        ).model_copy(update={"project_id": source.get("project_id")}),
        authorize=lambda source: source.get("project_id") == "project-1",
    )
    artifact = adapter.ingest(
        {"text": "# Deploy\n\nCapability: git.read\n\n1. inspect\n", "project_id": "project-1"},
        effective_capabilities=frozenset({"llm_wiki.ingest"}),
    )
    assert artifact.provider_id == "llm-wiki"
    assert artifact.nodes
    assert artifact.edges
    assert all(node.source_ref for node in artifact.nodes)
    assert artifact.artifact_fingerprint()


def test_runtime_capability_registration_updates_search_catalog(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    pack.register_tool(
        ToolDescriptor("custom.inspect", "Inspect custom", "Inspect a local custom resource."),
        lambda: "ok",
    )
    pack.register_mcp(McpCapability("custom", "lookup", "Look up an authorized custom resource."))
    pack.register_skill(
        SkillDescriptor(
            "custom-research",
            "Custom research",
            "Research a custom source.",
            ("lookup",),
        )
    )
    ids = {item.capability_id for item in pack.search("custom", limit=20)}
    assert ids >= {"tool:custom.inspect", "mcp:custom:lookup", "skill:custom-research"}
    with pytest.raises(ValueError):
        pack.register_tool(ToolDescriptor("custom.inspect", "Duplicate", "Duplicate"), lambda: None)


def test_useful_agent_skills_are_discoverable(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    ids = {
        item.capability_id
        for item in pack.catalog.search(
            "workflow planning",
            allowed_capabilities=frozenset({"workspace.read"}),
            limit=20,
        )
    }
    assert "skill:build-workflow-from-request" in ids
    assert "skill:discover-capability" not in ids


def test_developer_pack_composes_core_agent_profile(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    profile = pack.agent_profile()
    assert profile.workflow_mode == "plan"
    assert profile.acl_required is True
    assert profile.effective_capabilities(
        caller_capabilities=["workspace.read", "shell.test"],
    ) == ("shell.test", "workspace.read")
    assert pack.workflow_design().workflow_id == "agent.plan.v1"
    assert pack.workflow_design("goal").workflow_id == "agent.goal.v1"


def test_developer_pack_binds_core_harness_without_new_runtime(tmp_path: Path) -> None:
    class FakeRuntime:
        def run(self, **kwargs):
            return kwargs

    pack = developer_profile(str(tmp_path))
    harness = pack.make_harness(
        FakeRuntime(),
        caller_capabilities=("workspace.read", "shell.test", "git.read"),
    )
    result = harness.run(initial_state={"request": "inspect"}, conversation_id="c1")
    assert result["workflow_id"] == "agent.plan.v1"
    assert result["_authority_context"]["principal_id"] == "kogwistar.developer"


def test_developer_pack_binds_async_core_harness(tmp_path: Path) -> None:
    class FakeAsyncRuntime:
        async def run(self, **kwargs):
            return kwargs

    pack = developer_profile(str(tmp_path))
    harness = pack.make_async_harness(
        FakeAsyncRuntime(),
        caller_capabilities=("workspace.read", "shell.test", "git.read"),
    )
    result = asyncio.run(
        harness.run(initial_state={"request": "inspect"}, conversation_id="c1")
    )
    assert result["workflow_id"] == "agent.plan.v1"
    assert result["_authority_context"]["effective_capabilities"] == (
        "git.read",
        "shell.test",
        "workspace.read",
    )


def test_acl_filters_tool_calls(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    with pytest.raises(PermissionError):
        pack.tools.call(ToolCall("workspace.list_files", {}), allowed_capabilities=frozenset())
    assert pack.tools.call(
        ToolCall("workspace.list_files", {}),
        allowed_capabilities=frozenset({"workspace.read"}),
    ) == []
    with pytest.raises(PermissionError):
        pack.tools.call(
            ToolCall("workspace.list_files", {}),
            allowed_capabilities=frozenset({"workspace.read"}),
            acl=lambda _descriptor: False,
        )


def test_workspace_tool_rejects_escape(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    with pytest.raises(PermissionError):
        pack.tools.call(
            ToolCall("workspace.read_text", {"relative_path": "../secret"}),
            allowed_capabilities=frozenset({"workspace.read"}),
        )


def test_mcp_is_descriptor_only_until_authorized() -> None:
    catalog = McpCatalog((McpCapability("github", "issue_search", "Search issues", frozenset({"github.read"})),))
    assert catalog.search("issue", allowed_capabilities=frozenset()) == ()
    assert catalog.search("issue", allowed_capabilities=frozenset({"github.read"}))[0].capability_id == "mcp:github:issue_search"


def test_plugin_cleanup_is_deterministic() -> None:
    closed: list[str] = []
    registry = PluginRegistry()
    registry.register(PluginManifest("example", "1"), lambda: closed.append("closed"))
    registry.close()
    assert closed == ["closed"]


def test_hooks_transform_context_in_order() -> None:
    result = run_hooks(
        (
            HookBundle("mode", (lambda payload: {"mode": "plan"},)),
            HookBundle("budget", (lambda payload: {"steps_left": 3},)),
        ),
        {"request": "review"},
    )
    assert result == {"request": "review", "mode": "plan", "steps_left": 3}


def test_hooks_require_effective_capability() -> None:
    bundle = HookBundle(
        "budget",
        (lambda _payload: {"steps_left": 3},),
        required_capabilities=frozenset({"agent.budget"}),
    )
    assert run_hooks((bundle,), {}) == {}
    assert run_hooks((bundle,), {}, effective_capabilities=("agent.budget",)) == {"steps_left": 3}


def test_fail_closed_hook_does_not_hide_errors() -> None:
    def broken(_payload: object) -> None:
        raise RuntimeError("hook failure")

    with pytest.raises(RuntimeError, match="hook failure"):
        run_hooks((HookBundle("security", (broken,)),), {})


def test_optional_adapters_are_acl_and_approval_gated() -> None:
    transport = FakeTransport()
    github = GitHubAdapter(transport, repository="example/project")
    assert github.search_issues("bug", effective_capabilities=frozenset({"github.read"})) == ({"number": 1}, {"number": 2})
    with pytest.raises(PermissionError):
        github.search_issues("bug", effective_capabilities=frozenset())
    with pytest.raises(PermissionError):
        github.create_issue("title", "body", effective_capabilities=frozenset({"github.write"}), approve=None)
    assert github.create_issue(
        "title",
        "body",
        effective_capabilities=frozenset({"github.write"}),
        approve=lambda action, request: action == "github.create_issue" and request["repository"] == "example/project",
    )["ok"] is True

    browser = BrowserAdapter(lambda _url: "abcdef", max_chars=3)
    assert browser.fetch("https://example.test", effective_capabilities=frozenset({"browser.read"})) == "abc"
    slack_client = FakeSlack()
    slack = SlackAdapter(slack_client)
    assert slack.search("incident", effective_capabilities=frozenset({"slack.read"}))["limit"] == 20
    with pytest.raises(PermissionError):
        slack.send("#ops", "hello", effective_capabilities=frozenset({"slack.write"}), approve=None)

    atlassian = AtlassianAdapter(transport, site="example.atlassian.net")
    assert atlassian.search_jira("project = KOG", effective_capabilities=frozenset({"atlassian.read"}))["ok"] is True
    llm_wiki = LlmWikiAdapter(lambda source: source, authorize=lambda _source: True)
    assert llm_wiki.descriptors()[0].capability_id == "tool:llm_wiki.ingest_skill"

    registry = PluginRegistry()
    register_optional_adapter(registry, github)
    register_optional_adapter(registry, slack)
    assert len(adapter_descriptors((github, browser, slack, atlassian, llm_wiki))) == 8
    registry.close()
    assert transport.closed is True
    assert slack_client.closed is True


def test_cli_profile_is_deterministic(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profile"]) == 0
    output = capsys.readouterr().out
    assert '"agent_id":"kogwistar.developer"' in output
    assert '"acl_required":true' in output
