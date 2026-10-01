# Slack Contact Directory Adapter

`SlackContactDirectorySource` is an optional external source adapter, separate
from the email plugin and from the suite's Slack message search/send tools. It
reads Slack `users.list` pages for explicit workspace-to-team bindings and
returns contact observations through caller-supplied factories.

## Trust Boundary

- The caller injects an authenticated Slack client and the workspace/team map;
  the suite discovers neither installations nor credentials.
- Invocation requires effective `slack.read`, a host ACL resolver, and the
  source-stream authorizer. Host ACL and stream ACL are checked before network
  access and rechecked after the read completes.
- Returned email, phone, and Slack user identifiers are unverified claims.
  This adapter creates no identity decisions, graph writes, or automatic
  merges. The host's review workflow remains responsible for matching and
  explicit same/different decisions.
- Bot, app, and deleted users are excluded. Profile fields outside stable
  names, email, and explicitly internationalized phone are not returned.
- Pagination is bounded. Repeated cursors, malformed pages, over-limit
  directories, or authorization changes fail the whole scan; partial
  observations are never returned as a complete directory.

## Host Integration

The adapter does not import host contact models. The host supplies factories
that map the generic keyword contract into its own `ContactPointClaim` and
`ContactIdentityObservation` types, then may compose `list_observations()` as a
contact scan provider. The provider only reads the selected stream:

```python
source = SlackContactDirectorySource(
    client=authenticated_slack_client,
    workspaces={"workspace-1": "T123"},
    contact_point_factory=ContactPointClaim,
    observation_factory=ContactIdentityObservation,
)

observations = source.list_observations(
    workspace_id,
    {"workspace_id": workspace_id, "source_stream_ids": ("slack:T123:directory",)},
    effective_capabilities=frozenset({"slack.read"}),
    acl=host_acl,
    authorize_stream=host_stream_acl,
)
```

Factories are explicit because identity policy and canonical data contracts
belong to the host/application. The adapter owns only Slack response
validation, safe bounded traversal, stable source IDs, and source-derived
revision fingerprints.
