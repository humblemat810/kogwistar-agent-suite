# Whispered Coding Agent Use Case

This suite includes an end-to-end coding use case that composes the secure
`kogwistar-agent` boundary with Kogwistar's whisper sidecar.

The use case:

1. Builds a small graph-backed knowledge base.
2. Creates scoped `AgentReadTools`.
3. Runs `build_plan_workflow` through `MappingStepResolver` and `WorkflowRuntime`.
4. Uses `build_whisper_context` to add bounded hints before each model call.
5. Lets `AgentRuntime` authorize and execute workspace search and patch tools.

Install the optional agent dependency:

```text
pip install -e ".[agent]"
```

Run the deterministic tests:

```text
pytest tests/test_agent_whisper_use_case.py -q
```

The use case demonstrates:

- bounded graph retrieval;
- scoped capability checks;
- explicit patch approval;
- successful patch application;
- a disabled-whisper path where no hint is injected;
- an unauthorized write path that fails closed.

The implementation lives in
`kogwistar_agent_suite.agent_use_cases`; the tests live in
`tests/test_agent_whisper_use_case.py`.
