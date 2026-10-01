# Slack Notification Source

`SlackNotificationSource` is an optional adapter from Slack channel history to
the host's generic `NotificationSourceAdapter` contract. It complements, but
does not replace, the Email plugin.

The adapter:

- reads only explicitly bound workspace/channel IDs;
- requires effective `slack.read` and an injected ACL resolver;
- checks ACL before and after every `conversations_history` call;
- follows bounded Slack cursors and rejects missing or repeated cursors;
- rejects malformed provider responses and event windows beyond the bound;
- emits host `NotificationEvent` values through an injected factory.

It does not own Slack credentials, graph writes, contact identity, digest
grouping, outbox persistence, cursor checkpoints, or message sending. The host
should compose it with the Email plugin through
`NotificationSourceCollection`, then apply its normal digest, outbox, budget,
and provenance policy.

```python
from kogwistar_agent_suite import SlackNotificationSource

source = SlackNotificationSource(
    client=authenticated_slack_client,
    workspaces={"workspace-a": ("C123", "C456")},
    event_factory=host_notification_event_factory,
    acl=host_acl_resolver,
)

# Host composition owns the final source ACL and notification policy.
collection = NotificationSourceCollection(
    {"email": email_source, "slack": source},
    authorize_source=host_source_acl,
)
```

Catalog discovery returns `source:slack.notifications`; discovery does not
grant access or invoke Slack.
