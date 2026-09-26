# Kogwistar Agent Suite

Concrete tools, plugins, hooks, MCP descriptors, skills, and starter
profiles built on top of the Kogwistar agent substrate.

Workflow execution, ACL authority, budgets, provenance, and persistence remain
owned by `kogwistar`. This package is local-first and uses deterministic tests.

## Development

```text
pip install -e ../graphrag_v2_working_tree
pip install -e .
python -m pytest -q
```

The first pack exposes only bounded read operations:

```text
kogwistar-agent-suite --workspace . search "test failure" --capability workspace.read --capability shell.test
kogwistar-agent-suite --workspace . profile
kogwistar-agent-suite --workspace . read README.md
```

External MCP invocation, shell mutation, GitHub writes, and model providers
remain separate plugins. They must pass host ACL, approval, budget, and
provenance checks before being added.

Optional adapter extras are independent:

```text
pip install -e ".[github]"
pip install -e ".[browser]"
pip install -e ".[slack]"
pip install -e ".[atlassian]"
```

The adapters accept injected clients, so deterministic tests and deployments
may use an internal gateway or local fake without installing a vendor SDK.
No adapter is auto-discovered or compulsory. LLM-Wiki integration reuses the
core provider-neutral ingestion contract and remains optional.
