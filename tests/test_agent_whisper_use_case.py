from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("kogwistar_agent")

from kogwistar.agent import WhisperConfig
from kogwistar_agent.orchestration import ActionProposal, ModelRequest, ModelResponse

from kogwistar_agent_suite.agent_use_cases import run_whispered_coding_use_case


class SequenceCodingProvider:
    def __init__(self, resource: str) -> None:
        self.resource = resource
        self.contexts: list[ModelRequest] = []
        self.calls = 0

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.contexts.append(request)
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                "search-1",
                "searching",
                (
                    ActionProposal(
                        kind="trusted",
                        tool_id="workspace.search_text",
                        capability_name="workspace.read",
                        resource=self.resource,
                        operation="read",
                        arguments={"query": "safe_add"},
                    ),
                ),
            )
        if self.calls == 2:
            return ModelResponse(
                "patch-1",
                "patching",
                (
                    ActionProposal(
                        kind="trusted",
                        tool_id="patch.propose",
                        capability_name="workspace.read",
                        resource=self.resource,
                        operation="read",
                        arguments={
                            "path": "src/calculator.py",
                            "old_text": "def add(left: int, right: int) -> int:\n    return left + right\n",
                            "new_text": "def safe_add(left: int, right: int) -> int:\n    return left + right\n",
                        },
                    ),
                ),
            )
        return ModelResponse("done-1", "done")


def _workspace(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    source.mkdir()
    (source / "calculator.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right\n",
        encoding="utf-8",
    )
    return tmp_path


def test_whispered_coding_use_case_applies_patch_with_graph_hints(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    provider = SequenceCodingProvider(f"repo:{workspace.as_posix()}")
    result = run_whispered_coding_use_case(
        workspace,
        task="replace add with safe_add",
        provider=provider,
    )

    assert result.status == "succeeded", result
    assert result.final_answer == "done"
    assert "safe_add" in (workspace / "src" / "calculator.py").read_text(encoding="utf-8")
    assert result.whisper_hints
    assert result.whisper_hints[0].status == "ok", result.whisper_hints
    assert provider.contexts
    assert any(
        "Whisper context" in message.content
        for request in provider.contexts
        for message in request.messages
    )


def test_whispered_coding_use_case_can_disable_whisper(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    provider = SequenceCodingProvider(f"repo:{workspace.as_posix()}")
    result = run_whispered_coding_use_case(
        workspace,
        task="replace add with safe_add",
        provider=provider,
        whisper=WhisperConfig(enabled=False),
    )

    assert result.status == "succeeded"
    assert all(
        "Whisper context" not in message.content
        for request in provider.contexts
        for message in request.messages
    )
