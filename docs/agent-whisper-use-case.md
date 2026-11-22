# Whispered Coding Agent Use Case

The suite includes a deterministic example of the Kogwistar whisper pattern.
While the main coding agent is planning, a sidecar retrieves scoped graph
knowledge and injects a bounded prompt-safe hint before the next model call.

The example composes existing Kogwistar primitives:

- `GraphKnowledgeEngine` stores the mocked coding facts.
- `AgentReadTools` and `ReadScope` perform tenant/project/scope-filtered reads.
- `WhisperConfig` and `build_whisper_context` build the bounded sidecar payload.
- `MappingStepResolver`, `WorkflowRuntime`, and `build_plan_workflow` execute
  the agent graph.
- `kogwistar-agent` owns the fail-closed tool boundary through `AgentRuntime`.

The public entrypoint is
`kogwistar_agent_suite.run_whispered_coding_use_case`. Install the optional
agent dependency with:

```text
pip install -e .[agent]
```

The use case searches workspace text, proposes a patch, approves it, and applies
it through a trusted tool. Tests cover both the whispered and disabled-whisper
paths, so the model-visible hint is present only when explicitly enabled.
