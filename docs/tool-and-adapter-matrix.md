# Tool And Adapter Matrix

This matrix is the current suite surface. It is intentionally small and
local-first; entries are optional composition points, not mandatory runtime
features.

| Surface | Search ID pattern | Invocation owner | Side effect |
| --- | --- | --- | --- |
| local tool | `tool:workspace.*`, `tool:git.*` | `ToolRegistry` | read |
| custom tool | `tool:<tool_id>` | host-provided callable | descriptor-defined |
| skill | `skill:<skill_id>` | ordinary Kogwistar workflow | policy recipe |
| MCP | `mcp:<server>:<tool>` | authorized MCP adapter | provider-defined |
| GitHub | `tool:github.*` | injected transport | write approval for issue creation |
| Browser | `tool:browser.fetch_text` | injected fetcher | read |
| Slack | `tool:slack.*` | injected client | write approval for send |
| Atlassian | `tool:atlassian.*` | injected transport | read |
| LLM-Wiki | `tool:llm_wiki.ingest_skill` | core ingestion adapter | authorized ingestion |

Use `pack.search()` for one disclosure surface. Use the specific invocation
API only after host ACL, capability, approval, budget, and provenance policy
has been applied.

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
