# Tool And Adapter Matrix

This matrix is the current suite surface. It is intentionally small and
local-first; entries are optional composition points, not mandatory runtime
features.

| Surface | Search ID pattern | Invocation owner | Side effect |
| --- | --- | --- | --- |
| local tool | `tool:workspace.*`, `tool:git.*` | `ToolRegistry` | read |
| custom tool | `tool:<tool_id>` | host-provided callable | descriptor-defined |
| skill | `skill:<skill_id>` | descriptor/catalog only; host maps it to an ordinary workflow | discovery recipe |
| MCP | `mcp:<server>:<tool>` | descriptor/catalog only; host supplies authorized MCP client | provider-defined |
| GitHub | `tool:github.*` | injected transport | write approval for issue creation |
| Browser | `tool:browser.fetch_text` | injected fetcher | read |
| Slack | `tool:slack.*` | injected client | write approval for send |
| Slack notifications | `source:slack.*` | host `NotificationSourceCollection` | read; host owns digest/outbox |
| Atlassian | `tool:atlassian.*` | injected transport | read |
| LLM-Wiki | `tool:llm_wiki.ingest_skill` | core ingestion adapter | authorized ingestion |

`DeveloperPack` registries and catalog are process-local composition state;
they do not persist descriptors to a Kogwistar backend. `pack.search()` is a
discovery API, not an invocation API. Registering a skill only publishes its
descriptor and steps; it does not execute those steps, materialize a workflow,
or persist the skill. Registering MCP only publishes a descriptor; it does not
connect to or invoke an MCP server. A host must resolve discovery results to an
ordinary Kogwistar workflow or an explicitly configured client.

Direct `ToolRegistry.call()` and external adapter methods require a supplied
ACL resolver and effective capabilities before action. Write tools/adapters
also require the explicit approval callback implemented for that action.
Missing ACL resolver is denial, not an implicit role. `ToolRegistry` rejects
custom write descriptors without a capability. The suite itself does not
provide a universal invocation pipeline, persistent ACL decisions, budget
accounting, or provenance recording; the host/runtime must compose those
policies around the adapter action.

`SlackNotificationSource` is an optional message-source adapter. It reads only
explicitly bound channels through injected `conversations_history`, rechecks
ACL around every provider call, applies a bounded time window and event count,
and emits host `NotificationEvent` values through a supplied factory. It does
not send messages, group digests, persist cursors, or write the graph. The host
can compose it with the email plugin through `NotificationSourceCollection`.

For ranking diagnostics use `pack.search_ranked()` or CLI `--ranked`. BM25 is
the useful no-embedding fallback. Hosts may inject a vector/semantic ranker;
the package keeps it optional and falls back safely when unavailable.

## Optional dependency policy

Base import must work without vendor SDKs. Optional extras are convenience
metadata for deployments; adapters still accept injected clients. The suite
never auto-connects to GitHub, browser, Slack, Atlassian, or LLM-Wiki.

## Verification

Run deterministic tests with a repository-local temporary directory when the
host temp directory is restricted:

```text
python -m pytest -q --basetemp .pytest-tmp-suite
python -m ruff check src tests
python -m build --wheel --no-isolation
```
