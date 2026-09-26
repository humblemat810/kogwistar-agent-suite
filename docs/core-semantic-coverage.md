# Core Semantic Coverage

This suite is an optional composition layer. Core Kogwistar remains authority
for execution, ACL, workflow state, checkpoints, steering, delegation,
compression, memory, knowledge, wisdom, and durable skill projections.

## Reused semantics

- `DeveloperPack.make_harness()` binds `AgentHarness` or `AsyncAgentHarness`;
  it does not create a second runtime.
- `DeveloperPack.workflow_design()` returns a graph artifact only. The host
  must register/validate that artifact and supply resolver handlers to the
  existing `WorkflowRuntime`; the suite does not auto-install workflow
  authority.
- Profile authority is intersected with caller capabilities by core ACL rules.
- Plan and goal are ordinary core workflow designs, selected by workflow ID.
- Optional adapters expose descriptors only until an explicitly authorized call.
- LLM-Wiki ingestion returns core `SkillGraphArtifact`; persistence belongs to
  core projection stores, not this suite.
- Catalog search is progressive disclosure: ACL filtering precedes ranking.
- Semantic ranking sees only `semantic_ready` derived projections. Pending or
  failed embeddings fall back to deterministic BM25/lexical search.

## Intentionally not duplicated

This package does not implement a runtime, scheduler, event store, memory
database, wisdom lifecycle, steering queue, compression engine, subagent
protocol, or durable catalog authority. Hosts must use the corresponding core
APIs for those semantics.

Hooks are explicit composition helpers. `DeveloperPack.hooks` does not cause
callbacks to run implicitly; a host or ordinary workflow step must call
`run_hooks()` at its chosen lifecycle point. This keeps hook policy visible
and below the core runtime's ACL and budget guards.

The local catalog is an in-memory discovery composition. Durable graph-native
groups, scopes, aliases, versions, approval state, provenance, and rebuildable
skill/MCP projections remain core responsibilities.

## Acceptance boundary

Suite tests prove composition, ACL filtering, progressive discovery, adapter
approval, and deterministic local behavior. Core integration tests must still
prove backend parity, persistence/recovery, async execution, and durable
projection behavior.
