from pathlib import Path

import pytest

from kogwistar_agent_suite import (
    HookBundle,
    McpCapability,
    McpCatalog,
    PluginManifest,
    PluginRegistry,
    ToolCall,
    developer_profile,
    run_hooks,
)
from kogwistar_agent_suite.cli import main


def test_developer_pack_searches_skills_and_tools(tmp_path: Path) -> None:
    pack = developer_profile(str(tmp_path))
    results = pack.catalog.search(
        "test failure",
        allowed_capabilities=frozenset({"workspace.read", "shell.test"}),
    )
    assert results[0].capability_id == "skill:diagnose-test-failure"


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


def test_fail_closed_hook_does_not_hide_errors() -> None:
    def broken(_payload: object) -> None:
        raise RuntimeError("hook failure")

    with pytest.raises(RuntimeError, match="hook failure"):
        run_hooks((HookBundle("security", (broken,)),), {})


def test_cli_profile_is_deterministic(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profile"]) == 0
    output = capsys.readouterr().out
    assert '"agent_id":"kogwistar.developer"' in output
    assert '"acl_required":true' in output
