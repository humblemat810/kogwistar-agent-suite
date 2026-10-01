from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from kogwistar_agent_suite import SlackNotificationSource
from kogwistar_agent_suite import CapabilityCatalog

pytestmark = pytest.mark.ci


@dataclass(frozen=True)
class Event:
    event_id: str
    workspace_id: str
    source_id: str
    source_revision_id: str
    occurred_at: datetime
    title: str
    severity: str
    dedupe_key: str
    action_required: bool
    duplicate_key: str


class Response:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data


class Slack:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def conversations_history(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected history call")
        return self.responses.pop(0)


def _source(slack: Slack, *, acl=lambda _action, _request: True, **kwargs: object) -> SlackNotificationSource:
    return SlackNotificationSource(
        client=slack,
        workspaces={"workspace-a": ("C123", "C456")},
        event_factory=Event,
        acl=acl,
        **kwargs,
    )


def test_slack_history_maps_to_bounded_host_events() -> None:
    slack = Slack(
        [
            Response(
                {
                    "ok": True,
                    "messages": [
                        {"ts": "1700000000.000001", "text": "deploy completed", "thread_ts": "1700000000.0"}
                    ],
                }
            ),
            Response({"ok": True, "messages": []}),
        ]
    )
    source = _source(slack)
    sources = source.list_sources("workspace-a", "recipient-a")
    events = source.read_window(
        "workspace-a",
        "recipient-a",
        sources,
        datetime.fromtimestamp(1699999999, UTC),
        datetime.fromtimestamp(1700000001, UTC),
        10,
    )

    assert len(events) == 1
    assert events[0].source_id == "slack:workspace-a:C123:messages"
    assert events[0].dedupe_key == "slack:C123:1700000000.0"
    assert slack.calls[0]["oldest"] == "1699999999.0"
    assert slack.calls[0]["latest"] == "1700000001.0"


def test_slack_notification_source_is_searchable_but_not_invocation_authority() -> None:
    source = _source(Slack([]))
    catalog = CapabilityCatalog(source.descriptors())

    result = catalog.search("Slack notification events", allowed_capabilities=frozenset({"slack.read"}))

    assert [item.capability_id for item in result] == ["source:slack.notifications"]


def test_slack_history_rechecks_acl_after_each_read() -> None:
    slack = Slack([Response({"ok": True, "messages": []})])
    calls: list[str] = []

    def acl(action: str, _request: object) -> bool:
        calls.append(action)
        return len(calls) == 1

    source = _source(slack, acl=acl)
    with pytest.raises(PermissionError, match="ACL denied"):
        source.read_window(
            "workspace-a",
            "recipient-a",
            ("slack:workspace-a:C123:messages", "slack:workspace-a:C456:messages"),
            datetime.fromtimestamp(0, UTC),
            datetime.fromtimestamp(1, UTC),
            10,
        )
    assert len(slack.calls) == 1
    assert calls == ["slack.notifications.read", "slack.notifications.read"]


def test_slack_history_rejects_pagination_beyond_bound() -> None:
    slack = Slack(
        [
            Response(
                {
                    "ok": True,
                    "has_more": True,
                    "response_metadata": {"next_cursor": "next"},
                    "messages": [{"ts": "1.0", "text": "one"}],
                }
            )
        ]
    )
    source = SlackNotificationSource(
        client=slack,
        workspaces={"workspace-a": ("C123",)},
        event_factory=Event,
        acl=lambda _action, _request: True,
    )
    with pytest.raises(ValueError, match="exceeds notification event bound"):
        source.read_window(
            "workspace-a",
            "recipient-a",
            ("slack:workspace-a:C123:messages",),
            datetime.fromtimestamp(0, UTC),
            datetime.fromtimestamp(2, UTC),
            1,
        )


def test_slack_history_requires_explicit_success_response() -> None:
    source = SlackNotificationSource(
        client=Slack([{"messages": []}]),
        workspaces={"workspace-a": ("C123",)},
        event_factory=Event,
        acl=lambda _action, _request: True,
    )
    with pytest.raises(ValueError, match="unsuccessful response"):
        source.read_window(
            "workspace-a",
            "recipient-a",
            ("slack:workspace-a:C123:messages",),
            datetime.fromtimestamp(0, UTC),
            datetime.fromtimestamp(1, UTC),
            10,
        )


def test_slack_history_does_not_call_next_channel_with_zero_limit() -> None:
    slack = Slack(
        [
            {"ok": True, "messages": [{"ts": "1.0", "text": "one"}]},
        ]
    )
    source = _source(slack)
    events = source.read_window(
        "workspace-a",
        "recipient-a",
        ("slack:workspace-a:C123:messages", "slack:workspace-a:C456:messages"),
        datetime.fromtimestamp(0, UTC),
        datetime.fromtimestamp(2, UTC),
        1,
    )

    assert len(events) == 1
    assert len(slack.calls) == 1


def test_slack_history_follows_bounded_cursors() -> None:
    slack = Slack(
        [
            Response(
                {
                    "ok": True,
                    "has_more": True,
                    "response_metadata": {"next_cursor": "next"},
                    "messages": [{"ts": "1.0", "text": "one"}],
                }
            ),
            Response(
                {
                    "ok": True,
                    "has_more": False,
                    "messages": [{"ts": "1.1", "text": "two"}],
                }
            ),
        ]
    )
    source = SlackNotificationSource(
        client=slack,
        workspaces={"workspace-a": ("C123",)},
        event_factory=Event,
        acl=lambda _action, _request: True,
    )
    events = source.read_window(
        "workspace-a",
        "recipient-a",
        ("slack:workspace-a:C123:messages",),
        datetime.fromtimestamp(0, UTC),
        datetime.fromtimestamp(2, UTC),
        2,
    )

    assert [event.title for event in events] == ["one", "two"]
    assert slack.calls[1]["cursor"] == "next"
