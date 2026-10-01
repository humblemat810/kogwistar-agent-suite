"""Optional, ACL-gated Slack message source for the host notification contract.

This adapter translates bounded Slack history into host-owned notification
events. It owns no outbox, digest, graph, or memory state; the host composes
the returned events with email and other channel sources.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from .authorization import require_acl, require_capabilities
from .catalog import CapabilityDescriptor, CapabilityKind

_SLACK_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_CHANNELS = 1_000
_MAX_EVENTS = 10_000


class SlackMessageClient(Protocol):
    """Small Slack Web API subset used by the source."""

    def conversations_history(self, **kwargs: object) -> object: ...


class NotificationEventFactory(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


AuthorizeAcl = Callable[[str, Mapping[str, Any]], bool]


class SlackNotificationSource:
    """Expose explicitly bound Slack channels as bounded notification events."""

    def __init__(
        self,
        *,
        client: SlackMessageClient,
        workspaces: Mapping[str, Sequence[str]],
        event_factory: NotificationEventFactory,
        acl: AuthorizeAcl,
        effective_capabilities: frozenset[str] = frozenset({"slack.read"}),
        max_channels: int = _MAX_CHANNELS,
        max_events: int = _MAX_EVENTS,
    ) -> None:
        if not callable(getattr(client, "conversations_history", None)):
            raise TypeError("Slack client must provide conversations_history")
        if not isinstance(workspaces, Mapping) or not workspaces:
            raise ValueError("explicit workspace-to-channel bindings are required")
        if not callable(event_factory) or not callable(acl):
            raise TypeError("event factory and explicit ACL resolver are required")
        if not isinstance(effective_capabilities, frozenset):
            raise TypeError("effective_capabilities must be a frozenset")
        if type(max_channels) is not int or not 1 <= max_channels <= _MAX_CHANNELS:
            raise ValueError(f"max_channels must be between 1 and {_MAX_CHANNELS}")
        if type(max_events) is not int or not 1 <= max_events <= _MAX_EVENTS:
            raise ValueError(f"max_events must be between 1 and {_MAX_EVENTS}")
        bindings: dict[str, tuple[str, ...]] = {}
        for workspace_id, channel_ids in workspaces.items():
            if not isinstance(workspace_id, str) or not workspace_id.strip():
                raise ValueError("workspace IDs must be non-empty strings")
            if not isinstance(channel_ids, Sequence) or isinstance(channel_ids, (str, bytes)):
                raise TypeError("channel bindings must be sequences")
            normalized = tuple(dict.fromkeys(str(channel).strip() for channel in channel_ids))
            if not normalized or len(normalized) > max_channels:
                raise ValueError("workspace channel bindings are empty or exceed the bound")
            if any(not _SLACK_ID.fullmatch(channel) for channel in normalized):
                raise ValueError("channel IDs must be valid Slack identifiers")
            bindings[workspace_id.strip()] = normalized
        self._client = client
        self._workspaces = bindings
        self._make_event = event_factory
        self._acl = acl
        self._capabilities = effective_capabilities
        self._max_events = max_events

    def list_sources(self, workspace_id: str, _recipient_id: str) -> tuple[str, ...]:
        channels = self._channels(workspace_id)
        return tuple(self._source_id(workspace_id, channel) for channel in channels)

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        """Describe source discovery; descriptor is not invocation authority."""

        return (
            CapabilityDescriptor(
                capability_id="source:slack.notifications",
                name="Slack notification source",
                kind=CapabilityKind.TOOL,
                summary="Read bounded Slack channel events for host notification composition.",
                required_capabilities=frozenset({"slack.read"}),
                tags=("adapter", "notification-source", "slack", "read"),
                metadata={"side_effect": "read", "execution": "host_notification_contract"},
            ),
        )

    def read_window(
        self,
        workspace_id: str,
        recipient_id: str,
        source_ids: tuple[str, ...],
        window_start: datetime,
        window_end: datetime,
        max_events: int,
    ) -> tuple[object, ...]:
        if window_start.tzinfo is None or window_end.tzinfo is None:
            raise ValueError("notification window must be timezone-aware")
        if window_end < window_start:
            raise ValueError("notification window is reversed")
        if type(max_events) is not int or not 1 <= max_events <= self._max_events:
            raise ValueError("max_events exceeds Slack source bound")
        expected = set(self.list_sources(workspace_id, recipient_id))
        if set(source_ids) != expected or len(source_ids) != len(expected):
            raise ValueError("source IDs do not match configured Slack channels")
        events: list[object] = []
        for source_id in source_ids:
            channel_id = self._channel_for_source(workspace_id, source_id)
            cursor: str | None = None
            seen_cursors: set[str] = set()
            while True:
                request = {
                    "workspace_id": workspace_id,
                    "recipient_id": recipient_id,
                    "source_id": source_id,
                    "channel_id": channel_id,
                    "oldest": str(window_start.timestamp()),
                    "latest": str(window_end.timestamp()),
                    "limit": min(max_events - len(events), self._max_events),
                }
                if cursor is not None:
                    request["cursor"] = cursor
                require_capabilities(
                    frozenset({"slack.read"}),
                    self._capabilities,
                    action="slack.notifications.read",
                )
                require_acl(action="slack.notifications.read", request=request, acl=self._acl)
                response = self._client.conversations_history(**request)
                require_acl(action="slack.notifications.read", request=request, acl=self._acl)
                payload = _response_data(response)
                raw_messages = payload.get("messages")
                if not isinstance(raw_messages, list):
                    raise TypeError("Slack history returned malformed messages")
                for message in raw_messages:
                    if not isinstance(message, Mapping):
                        raise TypeError("Slack history contains malformed message")
                    events.append(self._event(workspace_id, source_id, channel_id, message))
                    if len(events) > max_events:
                        raise ValueError("Slack history exceeds notification event bound")
                if payload.get("has_more") is not True:
                    break
                if len(events) >= max_events:
                    raise ValueError("Slack history exceeds notification event bound")
                metadata = payload.get("response_metadata")
                next_cursor = metadata.get("next_cursor") if isinstance(metadata, Mapping) else None
                if not isinstance(next_cursor, str) or not next_cursor.strip():
                    raise ValueError("Slack history has_more response lacks a cursor")
                next_cursor = next_cursor.strip()
                if next_cursor in seen_cursors or next_cursor == cursor:
                    raise ValueError("Slack history pagination cursor repeated")
                seen_cursors.add(next_cursor)
                cursor = next_cursor
        return tuple(events)

    def _channels(self, workspace_id: str) -> tuple[str, ...]:
        if not isinstance(workspace_id, str) or workspace_id not in self._workspaces:
            raise PermissionError("Slack workspace is not configured")
        return self._workspaces[workspace_id]

    @staticmethod
    def _source_id(workspace_id: str, channel_id: str) -> str:
        return f"slack:{workspace_id}:{channel_id}:messages"

    def _channel_for_source(self, workspace_id: str, source_id: str) -> str:
        for channel_id in self._channels(workspace_id):
            if source_id == self._source_id(workspace_id, channel_id):
                return channel_id
        raise ValueError("unknown Slack notification source")

    def _event(
        self, workspace_id: str, source_id: str, channel_id: str, message: Mapping[str, object]
    ) -> object:
        ts = message.get("ts")
        text = message.get("text")
        if not isinstance(ts, str) or not ts.strip() or not isinstance(text, str) or not text.strip():
            raise TypeError("Slack message requires non-empty ts and text")
        event_id = f"{source_id}:{ts}"
        revision = hashlib.sha256(
            json.dumps(dict(message), sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        return self._make_event(
            event_id=event_id,
            workspace_id=workspace_id,
            source_id=source_id,
            source_revision_id=f"slack:{channel_id}:{ts}:{revision}",
            occurred_at=_timestamp(ts),
            title=text,
            severity="normal",
            dedupe_key=f"slack:{channel_id}:{message.get('thread_ts') or ts}",
            action_required=False,
            duplicate_key=event_id,
        )


def _response_data(response: object) -> Mapping[str, object]:
    data = getattr(response, "data", response)
    if not isinstance(data, Mapping) or data.get("ok") is not True:
        raise ValueError("Slack history returned an unsuccessful response")
    return data


def _timestamp(value: str) -> datetime:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise ValueError("Slack message timestamp is invalid") from exc
    from datetime import UTC

    return datetime.fromtimestamp(seconds, UTC)


__all__ = ["NotificationEventFactory", "SlackMessageClient", "SlackNotificationSource"]
