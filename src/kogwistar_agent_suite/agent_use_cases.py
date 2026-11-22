from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kogwistar.agent import (
    AgentReadTools,
    CatalogEntry,
    CatalogStore,
    ReadScope,
    WhisperConfig,
    WhisperResult,
    build_whisper_context,
)
from kogwistar.agent.workflows import build_plan_workflow
from kogwistar.engine_core.engine import GraphKnowledgeEngine
from kogwistar.engine_core.in_memory_backend import build_in_memory_backend
from kogwistar.engine_core.models import Edge, Grounding, Node, Span
from typing import TYPE_CHECKING, Any

from kogwistar.runtime import MappingStepResolver, WorkflowRuntime
from kogwistar.runtime.models import RunSuccess

from .tools import LocalWorkspaceTool

if TYPE_CHECKING:
    from kogwistar_agent import WhisperResult
    from kogwistar_agent import TrustedToolRegistry
    from kogwistar_agent.orchestration import ModelProvider


@dataclass(frozen=True, slots=True)
class PatchTool:
    root: Path

    def _resolve(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if target != self.root and self.root not in target.parents:
            raise PermissionError("workspace path escapes configured root")
        return target

    def apply_patch(
        self,
        *,
        path: str,
        old_text: str,
        new_text: str,
    ) -> dict[str, str]:
        target = self._resolve(path)
        content = target.read_text(encoding="utf-8")
        if old_text not in content:
            raise ValueError("old text not found")
        target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return {"path": path, "old_text": old_text, "new_text": new_text}


@dataclass(frozen=True, slots=True)
class WhisperedCodingResult:
    run_id: str
    status: str
    errors: tuple[str, ...]
    final_answer: str
    proposed_patch: dict[str, object] | None
    executions: tuple[object, ...]
    whisper_hints: tuple[Any, ...]


class WhisperedCodingProvider:
    def __init__(
        self,
        provider: "ModelProvider",
        *,
        read_tools: AgentReadTools,
        scope: ReadScope,
        config: WhisperConfig,
        effective_capabilities: tuple[str, ...],
    ) -> None:
        self.provider = provider
        self.read_tools = read_tools
        self.scope = scope
        self.config = config
        self.effective_capabilities = effective_capabilities
        self.results: list[WhisperResult] = []

    def complete(self, request: Any) -> Any:
        from kogwistar_agent.orchestration import ModelMessage, ModelRequest

        query = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        whisper = build_whisper_context(
            query=query,
            config=self.config,
            read_tools=self.read_tools,
            scope=self.scope,
            effective_capabilities=self.effective_capabilities,
        )
        self.results.append(whisper)
        messages = list(request.messages)
        if whisper.status != "empty":
            payload = json.dumps(whisper.model_dump(), ensure_ascii=False, separators=(",", ":"))
            messages.append(ModelMessage("system", "Whisper context: " + payload))
        return self.provider.complete(
            ModelRequest(
                messages=tuple(messages),
                tools=request.tools,
                policy_revision=request.policy_revision,
                max_response_bytes=request.max_response_bytes,
            )
        )


class _ConstantEmbeddingFunction:
    def __call__(self, documents_or_texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in documents_or_texts]


class _GraphKnowledgeSource:
    def __init__(self, engine: GraphKnowledgeEngine) -> None:
        self.engine = engine

    def search(
        self,
        *,
        query: str,
        namespace: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        del namespace, tenant_id, project_id
        hits = self.engine.search_nodes_as_of_scored(
            query=query,
            as_of_ts=datetime.now(UTC),
            n_results=limit,
        )
        return [_readable_node(hit.node) for hit in hits]

    def get(self, *, entity_id: str) -> list[dict[str, object]]:
        return [
            _readable_node(node)
            for node in self.engine.read.get_nodes(ids=[entity_id], limit=1)
        ]

    def expand(
        self,
        *,
        entity_id: str,
        depth: int = 1,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        edges = self.engine.read.get_edges(
            ids=None,
            where={
                "source_ids": {"$contains": entity_id},
                "relation": "related_to",
            },
            limit=limit,
        )
        targets = [edge.target_ids[0] for edge in edges if edge.target_ids]
        return [
            _readable_node(node)
            for node in self.engine.read.get_nodes(ids=targets, limit=limit)
        ]


def _grounding(source_id: str) -> Grounding:
    return Grounding(spans=[Span.from_dummy_for_workflow(source_id)])


def _readable_node(node: Node) -> dict[str, object]:
    data = dict(node.model_dump())
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        data.update(
            {
                key: value
                for key in (
                    "entity_id",
                    "title",
                    "summary",
                    "tenant_id",
                    "project_id",
                    "security_scope",
                    "kogwistar_whisper",
                )
                if (value := metadata.get(key)) is not None
            }
        )
    return data


def _knowledge_node(
    entity_id: str,
    *,
    title: str,
    summary: str,
    tenant_id: str,
    project_id: str,
    security_scope: str,
) -> Node:
    return Node(
        id=entity_id,
        label=title,
        type="entity",
        doc_id=entity_id,
        summary=summary,
        properties={},
        metadata={
            "entity_id": entity_id,
            "title": title,
            "summary": summary,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "security_scope": security_scope,
            "kogwistar_whisper": True,
        },
        mentions=[_grounding(entity_id)],
        level_from_root=0,
        domain_id=None,
        canonical_entity_id=None,
        embedding=[1.0, 0.0, 0.0],
    )


def _knowledge_edge(source_id: str, target_id: str) -> Edge:
    edge_id = f"edge:{source_id}:{target_id}"
    return Edge(
        id=edge_id,
        label="related_to",
        type="relationship",
        doc_id=edge_id,
        summary="related",
        properties={},
        mentions=[_grounding(edge_id)],
        source_ids=[source_id],
        target_ids=[target_id],
        relation="related_to",
        source_edge_ids=[],
        target_edge_ids=[],
        metadata={},
        level_from_root=0,
        domain_id=None,
        canonical_entity_id=None,
        embedding=[1.0, 0.0, 0.0],
    )


def _catalog_entry(
    logical_id: str,
    *,
    name: str,
    summary: str,
    required_capabilities: list[str],
    scope: str,
    tenant_id: str,
    project_id: str,
) -> CatalogEntry:
    return CatalogEntry(
        logical_id=logical_id,
        provider_id="kogwistar-agent-suite",
        provider_local_id=logical_id,
        kind="tool",
        name=name,
        summary=summary,
        source_fingerprint=hashlib.sha256(logical_id.encode("utf-8")).hexdigest(),
        required_capabilities=required_capabilities,
        scope=scope,
        tenant_id=tenant_id,
        project_id=project_id,
    )


def _read_tools(
    *,
    engine: GraphKnowledgeEngine,
    principal_id: str,
    scope: str,
    tenant_id: str,
    project_id: str,
) -> AgentReadTools:
    catalog = CatalogStore(
        acl_enabled=True,
        acl_checker=lambda entry, principal: principal == principal_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    for logical_id, name, summary, capabilities in (
        (
            "tool:workspace.search_text",
            "Search workspace text",
            "Bounded read-only text search in the configured workspace.",
            ["workspace.read"],
        ),
        (
            "tool:patch.propose",
            "Propose patch",
            "Return an explicit file patch proposal.",
            ["workspace.read"],
        ),
        (
            "tool:patch.apply",
            "Apply patch",
            "Apply one bounded file replacement inside the workspace.",
            ["workspace.write"],
        ),
    ):
        catalog.upsert(
            _catalog_entry(
                logical_id,
                name=name,
                summary=summary,
                required_capabilities=capabilities,
                scope=scope,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        )
    return AgentReadTools(
        catalog=catalog,
        knowledge_source=_GraphKnowledgeSource(engine),
        visibility_checker=lambda item, checked: (
            item.get("tenant_id") == checked.tenant_id
            and item.get("project_id") == checked.project_id
            and item.get("security_scope") == checked.security_scope
        ),
    )


def _trusted_tools(root: Path) -> TrustedToolRegistry:
    from kogwistar_agent import (
        Capability,
        ToolDescriptor,
        TrustedToolRegistry,
    )

    workspace = LocalWorkspaceTool(root)
    patch_tool = PatchTool(root)
    resource = f"repo:{root.as_posix()}"
    read_capability = Capability("workspace.read", resource, "read")
    write_capability = Capability("workspace.write", resource, "execute")
    registry = TrustedToolRegistry()

    def _search(arguments: dict[str, object]) -> object:
        return workspace.search_text(
            str(arguments.get("query", "")),
            relative_path=str(arguments.get("relative_path", ".")),
            max_matches=int(arguments.get("max_matches", 20)),
        )

    def _propose(arguments: dict[str, object]) -> object:
        return {
            "path": arguments.get("path", ""),
            "old_text": arguments.get("old_text", ""),
            "new_text": arguments.get("new_text", ""),
        }

    def _apply(arguments: dict[str, object]) -> object:
        return patch_tool.apply_patch(
            path=str(arguments.get("path", "")),
            old_text=str(arguments.get("old_text", "")),
            new_text=str(arguments.get("new_text", "")),
        )

    for tool_id, implementation, capability, source in (
        ("workspace.search_text", _search, read_capability, b"workspace-search-v1"),
        ("patch.propose", _propose, read_capability, b"patch-propose-v1"),
        ("patch.apply", _apply, write_capability, b"patch-apply-v1"),
    ):
        registry.register_builtin(
            ToolDescriptor(
                tool_id,
                "1.0.0",
                "core",
                hashlib.sha256(source).hexdigest(),
                frozenset({capability}),
            ),
            implementation,
            approved_digest=hashlib.sha256(source).hexdigest(),
            source_bytes=source,
        )
    return registry


def run_whispered_coding_use_case(
    workspace_root: str | Path,
    *,
    task: str,
    provider: "ModelProvider",
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    security_scope: str = "project-a",
    whisper: WhisperConfig | None = None,
) -> WhisperedCodingResult:
    from kogwistar_agent import (
        AgentRuntime,
        Capability,
        InMemoryAuditSink,
        PolicyBroker,
        Principal,
    )
    from kogwistar_agent.orchestration import AgentOrchestrator, ModelMessage

    root = Path(workspace_root).resolve()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_path = Path(temp_dir)
        embedding = _ConstantEmbeddingFunction()
        knowledge_engine = GraphKnowledgeEngine(
            persist_directory=str(temp_path / "knowledge"),
            kg_graph_type="knowledge",
            embedding_function=embedding,
            backend_factory=build_in_memory_backend,
        )
        workflow_engine = GraphKnowledgeEngine(
            persist_directory=str(temp_path / "workflow"),
            kg_graph_type="workflow",
            embedding_function=embedding,
            backend_factory=build_in_memory_backend,
        )
        conversation_engine = GraphKnowledgeEngine(
            persist_directory=str(temp_path / "conversation"),
            kg_graph_type="conversation",
            embedding_function=embedding,
            backend_factory=build_in_memory_backend,
        )
        for node in (
            _knowledge_node(
                "doc:safe-add",
                title="Prefer safe_add",
                summary="Use safe_add for bounded integer addition.",
                tenant_id=tenant_id,
                project_id=project_id,
                security_scope=security_scope,
            ),
            _knowledge_node(
                "code:safe-add",
                title="safe_add signature",
                summary="safe_add(left: int, right: int) -> int",
                tenant_id=tenant_id,
                project_id=project_id,
                security_scope=security_scope,
            ),
        ):
            knowledge_engine.write.add_node(node)
        knowledge_engine.write.add_edge(
            _knowledge_edge("doc:safe-add", "code:safe-add")
        )

        principal_id = "agent:coder"
        read_scope = ReadScope(
            principal_id=principal_id,
            security_scope=security_scope,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        read_tools = _read_tools(
            engine=knowledge_engine,
            principal_id=principal_id,
            scope=security_scope,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        principal = Principal(principal_id, "agent")
        resource = f"repo:{root.as_posix()}"
        policy = PolicyBroker()
        policy.grant(
            principal,
            [
                Capability("workspace.read", resource, "read"),
                Capability("workspace.write", resource, "execute"),
            ],
        )
        runtime = AgentRuntime(
            principal=principal,
            policy=policy,
            tools=_trusted_tools(root),
            audit=InMemoryAuditSink(),
        )
        whisper_config = whisper or WhisperConfig(enabled=True)
        whispered_provider = WhisperedCodingProvider(
            provider,
            read_tools=read_tools,
            scope=read_scope,
            config=whisper_config,
            effective_capabilities=("workspace.read", "workspace.write"),
        )
        orchestrator = AgentOrchestrator(runtime=runtime, provider=whispered_provider, max_steps=3)

        resolver = MappingStepResolver()

        @resolver.register("agent.observe")
        def _observe(context) -> RunSuccess:
            page = read_tools.knowledge_search(
                task,
                scope=read_scope,
                limit=3,
            )
            return RunSuccess(
                state_update=[("u", {"agent_evidence": page.to_dict()})]
            )

        @resolver.register("agent.plan")
        def _plan(context) -> RunSuccess:
            result = orchestrator.run(
                [ModelMessage("user", task)],
                tools=(),
            )
            proposal = next(
                (
                    execution.value
                    for execution in reversed(result.executions)
                    if execution.value is not None
                ),
                None,
            )
            return RunSuccess(
                state_update=[
                    (
                        "u",
                        {
                            "agent_answer": result.final_text,
                            "proposed_patch": proposal,
                            "approval": "approved",
                        },
                    )
                ]
            )

        @resolver.register("agent.approve")
        def _approve(context) -> RunSuccess:
            return RunSuccess(state_update=[])

        @resolver.register("agent.execute")
        def _execute(context) -> RunSuccess:
            arguments = context.state_view.get("proposed_patch")
            if not isinstance(arguments, dict):
                return RunSuccess(state_update=[])
            execution = runtime.call(
                "patch.apply",
                arguments=arguments,
                capability_name="workspace.write",
                resource=resource,
                operation="execute",
            )
            return RunSuccess(
                state_update=[("u", {"applied_patch": execution.value})]
            )

        @resolver.register("agent.done")
        def _done(context) -> RunSuccess:
            return RunSuccess(state_update=[])

        @resolver.register("agent.rejected")
        def _rejected(context) -> RunSuccess:
            return RunSuccess(state_update=[])

        design = build_plan_workflow(workflow_id="agent.whisper.coding.v1")
        for node in design.nodes:
            workflow_engine.write.add_node(node)
        for edge in design.edges:
            workflow_engine.write.add_edge(edge)
        runtime_run = WorkflowRuntime(
            workflow_engine=workflow_engine,
            conversation_engine=conversation_engine,
            step_resolver=resolver,
            predicate_registry={
                "approved": lambda _info, state, _result: state.get("approval") == "approved",
                "rejected": lambda _info, state, _result: state.get("approval") != "approved",
            },
        ).run(
            workflow_id=design.workflow_id,
            conversation_id="whisper-coding-use-case",
            turn_node_id="whisper-coding-turn",
            initial_state={"_deps": {}, "agent_prompt": task},
        )
        try:
            return WhisperedCodingResult(
                run_id=runtime_run.run_id,
                status=runtime_run.status,
                errors=tuple(runtime_run.errors),
                final_answer=str(runtime_run.final_state.get("agent_answer", "")),
                proposed_patch=runtime_run.final_state.get("proposed_patch"),
                executions=(),
                whisper_hints=tuple(whispered_provider.results),
            )
        finally:
            knowledge_engine.close()
            workflow_engine.close()
            conversation_engine.close()


__all__ = [
    "WhisperedCodingProvider",
    "WhisperedCodingResult",
    "run_whispered_coding_use_case",
]
