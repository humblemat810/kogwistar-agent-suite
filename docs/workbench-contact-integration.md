# Shared Contact Book Integration

Contact-source adapters can feed the host's generic reversible address book.
This composes source claims; it does not merge identities or write canonical
graph facts. Review and explicit `SAME_ENTITY` / `DISTINCT_ENTITIES` decisions
remain host responsibilities.

The Slack adapter is optional and remains independent of both Kogwistar core
and LLM-Wiki imports. Install the suite's Slack extra, create an authenticated
Slack client, construct `SlackContactDirectorySource` with host observation
factories, then register it during `WorkbenchApi` extension bootstrap:

```python
from kogwistar_agent_suite import (
    SlackContactDirectorySource,
    register_slack_contact_source,
)

source = SlackContactDirectorySource(
    client=authenticated_slack_client,
    workspaces={"workspace-1": "T123"},
    contact_point_factory=ContactPointClaim,
    observation_factory=ContactIdentityObservation,
)

register_slack_contact_source(
    host_api,
    source,
    effective_capabilities=application_capabilities_for_workspace,
    acl=application_acl_resolver,
)
```

Both callbacks must resolve the authenticated user/agent policy. The adapter
does not infer `slack.read` from workspace membership, a Slack profile, or
extension installation. Host resource ACL separately checks
`slack_contact_directory` read on the exact `slack:<team>:directory` stream.
Missing capability or ACL fails closed before Slack API access; stream ACL is
rechecked for every page and after the scan.

At the boundary, the suite maps Slack users into host-supplied generic
`ContactIdentityObservation` and `ContactPointClaim` factories. Email and phone
values remain unverified source claims. The shared host contact provider can
then compare them with observations from the email plugin or other adapters;
only the host's review workflow may link or separate people.
