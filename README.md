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

The first pack exposes bounded local read operations:

```text
kogwistar-agent-suite --workspace . search "test failure" --capability workspace.read --capability shell.test
kogwistar-agent-suite --workspace . profile
kogwistar-agent-suite --workspace . read README.md
```

The Python API also includes deterministic text search and read-only Git
inspection (`workspace.search_text`, `git.status`, `git.diff_stat`, and
`git.log`). Each operation has path, result-size, and timeout bounds. A caller
may explicitly compose configured external adapters into the same pack; no
adapter is discovered or connected automatically.

Useful starter skills cover code search, incident triage, execution-history
inspection, workflow design, capability discovery, citation-preserving
research, and isolated vision delegation. Skills are descriptors and policy
recipes; execution remains ordinary Kogwistar workflow composition.

## Capability Discovery

All installed capabilities share one searchable catalog. Results are filtered
before disclosure by required capabilities and an optional host ACL callback:

```python
pack = developer_profile(".")
results = pack.search(
    "workflow planning",
    allowed_capabilities=frozenset({"workspace.read"}),
)
```

Runtime additions must use the pack registration methods so progressive
discovery stays complete:

```python
pack.register_tool(descriptor, implementation)
pack.register_skill(skill_descriptor)
pack.register_mcp(mcp_descriptor)
pack.register_adapter(configured_adapter)
```

`pack.search()` exposes descriptors only. `ToolRegistry.call()` and external
adapter methods perform the second authorization check; catalog visibility is
never execution authority.

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

Detailed contracts: [`docs/capability-discovery.md`](docs/capability-discovery.md)
and [`docs/tool-and-adapter-matrix.md`](docs/tool-and-adapter-matrix.md).
