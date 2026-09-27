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

Search supports deterministic `lexical`, `bm25`, and `semantic` modes. The
suite has no mandatory embedding dependency, so `semantic` falls back to BM25
rather than pretending lexical data was vector-ranked. Exact and prefix hits
rank before token matches; substring matches remain a final partial fallback.
Capability ID is the stable tie-breaker. ACL filtering always happens before
ranking.

Hosts may inject `semantic_ranker(query, acl_visible_semantic_ready_descriptors)` when a
vector or other semantic index is available. The ranker returns a mapping of
capability ID to score. It receives only ACL-visible descriptors whose derived
semantic projection is marked `semantic_ready`; pending or failed projections
are excluded. Missing or failed scores fall back to BM25. Thus semantic search
is supported without making embeddings, Chroma, or a vendor model compulsory.

The agent should reveal only descriptors whose
`required_capabilities` are present. The host may apply a stricter `acl` check.
The returned descriptor is a proposal for discovery, not proof that invocation
is allowed.

`pack.search_ranked()` additionally returns `score` and `match`, useful for
Hermes-style progressive disclosure. The CLI equivalent is:

```text
kogwistar-agent-suite --workspace . search "github issue" \
  --capability github.read --mode bm25 --ranked
```

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

## Skill ingestion graph

`SkillDescriptor` is only a lightweight suite catalog entry. Actual ingestion
uses Kogwistar core's provider-neutral graph contract:

```text
source text / LLM-Wiki adapter
    -> SkillGraphArtifact
       -> SkillGraphNode[] + SkillGraphEdge[]
       -> source_fingerprint + parser provenance + scope
    -> validation / optional projection
    -> catalog descriptor and ordinary workflow execution
```

Semantic ranking may index the resulting catalog descriptors or a separate
durable skill projection. It must not replace the graph artifact, provenance,
ACL scope, or ordinary workflow authority.

Nodes carry step kind, source reference, required capabilities, and binding
status. Edges preserve explicit graph relations; inferred edges remain
candidate/provenance-bearing until policy approves them. The suite adapter
does not silently persist or execute the artifact. A host chooses an in-memory
or durable core projection store, then invokes through ordinary workflow and
ACL checks.

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
callback. Every direct tool/adapter method also requires an explicit host ACL
resolver; omission denies before capability checks or provider transport.
Order is ACL -> effective capability -> approval for mutation -> action. No
implicit role is supplied. Custom tools must explicitly declare
`side_effect="read"` or `side_effect="write"`; write values must declare a
non-empty required-capability set. `close()` is called through
the plugin registry when `pack.close()` runs.

## Safety boundary

The suite is a composition layer. Kogwistar remains authority for workflow
execution, ACL, budgets, provenance, persistence, and recovery. Do not turn
catalog search into an implicit tool call, or add vendor SDK imports to core.
