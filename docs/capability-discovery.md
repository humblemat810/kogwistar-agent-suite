# Capability Discovery

The suite uses descriptor-first progressive disclosure. A descriptor says
what exists, which capabilities it requires, and whether it is read-only or
side-effecting. It does not grant access and it does not execute a provider.

## Search flow

```text
installed provider
    -> CapabilityDescriptor
    -> DeveloperPack.catalog
    -> pack.search(query, allowed_capabilities, acl)
    -> host ACL / approval
    -> tool or adapter invocation
```

Search is deterministic lexical fallback. It ranks term frequency, then uses
capability ID as a stable tie-breaker. Semantic search may be added by a host,
but it must preserve the same ACL filtering and deterministic fallback.

The agent should reveal only descriptors whose
`required_capabilities` are present. The host may apply a stricter `acl` check.
The returned descriptor is a proposal for discovery, not proof that invocation
is allowed.

## Runtime registration

Use `DeveloperPack` registration methods, not direct mutation:

| Method | Adds to searchable catalog | Grants execution |
| --- | --- | --- |
| `register_tool` | yes | registers callable in `ToolRegistry` |
| `register_skill` | yes | no; skill remains a workflow recipe |
| `register_mcp` | yes | no; MCP invocation needs an adapter |
| `register_adapter` | yes | registers configured adapter cleanup |

Registration rejects duplicate capability IDs. Adapters must be configured and
passed explicitly. No package import discovers credentials, opens a network
connection, or installs a skill.

## Core local tools

`developer_profile()` installs these bounded read tools:

| ID | Capability | Behavior |
| --- | --- | --- |
| `workspace.list_files` | `workspace.read` | sorted bounded file listing |
| `workspace.read_text` | `workspace.read` | bounded UTF-8 read |
| `workspace.search_text` | `workspace.read` | deterministic text search, binary skip |
| `git.status` | `git.read` | branch and short status; no optional Git locks |
| `git.diff_stat` | `git.read` | working-tree diff summary |
| `git.log` | `git.read` | bounded recent commit log |

Workspace paths cannot escape the configured root. Git calls use fixed argv,
`shell=False`, output bounds, and a timeout. They do not mutate files.

## External adapters

External adapters receive an injected client or transport. SDKs and credentials
are host concerns:

| Adapter | Read capabilities | Writes |
| --- | --- | --- |
| GitHub | issue search | issue creation, approval required |
| Browser | bounded page text | none |
| Slack | message search | send, approval required |
| Atlassian | Jira/Confluence search | none |
| LLM-Wiki | authorized skill ingestion | ingestion contract only |

Write methods require both an effective capability and an explicit approval
callback. Read methods still require capabilities. `close()` is called through
the plugin registry when `pack.close()` runs.

## Safety boundary

The suite is a composition layer. Kogwistar remains authority for workflow
execution, ACL, budgets, provenance, persistence, and recovery. Do not turn
catalog search into an implicit tool call, or add vendor SDK imports to core.
