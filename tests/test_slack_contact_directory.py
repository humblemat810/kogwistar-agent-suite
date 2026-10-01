from __future__ import annotations

from dataclasses import dataclass

import pytest

from kogwistar_agent_suite import SlackContactDirectorySource
from kogwistar_agent_suite.catalog import CapabilityCatalog
from kogwistar_agent_suite.adapters import adapter_descriptors

pytestmark = pytest.mark.ci


@dataclass(frozen=True)
class ContactPoint:
    channel: str
    provider: str
    value: str
    verification: str


@dataclass(frozen=True)
class ContactObservation:
    workspace_id: str
    stream_id: str
    entity_id: str
    source_document_ids: tuple[str, ...]
    evidence_revision_ids: tuple[str, ...]
    observed_at_ms: int
    display_names: tuple[str, ...]
    contact_points: tuple[ContactPoint, ...]


class FakeSlackDirectory:
    def __init__(self, pages: list[dict[str, object]]) -> None:
        self.pages = list(pages)
        self.calls: list[dict[str, object]] = []

    def users_list(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if not self.pages:
            raise AssertionError("unexpected users.list call")
        return self.pages.pop(0)


@dataclass
class SlackSdkResponse:
    """Mirror SlackResponse: dictionary payload on .data, not Mapping."""

    data: dict[str, object]

    def __iter__(self):
        raise AssertionError("SlackResponse iteration would issue another API call")


def _page(members: list[dict[str, object]], cursor: str = "") -> dict[str, object]:
    return {
        "ok": True,
        "members": members,
        "response_metadata": {"next_cursor": cursor},
    }


def _source(client: FakeSlackDirectory, **kwargs: object) -> SlackContactDirectorySource[ContactObservation]:
    return SlackContactDirectorySource(
        client=client,
        workspaces={"workspace-a": "T123"},
        contact_point_factory=ContactPoint,
        observation_factory=ContactObservation,
        clock_ms=lambda: 123456,
        **kwargs,
    )


def _read(
    source: SlackContactDirectorySource[ContactObservation],
    *,
    acl=lambda _action, _request: True,
    authorize_stream=lambda _workspace, _stream: True,
    capabilities=frozenset({"slack.read"}),
):
    return source.list_observations(
        "workspace-a",
        {
            "workspace_id": "workspace-a",
            "source_stream_ids": ("slack:T123:directory",),
        },
        effective_capabilities=capabilities,
        acl=acl,
        authorize_stream=authorize_stream,
    )


def test_directory_reads_bounded_cursor_pages_and_returns_unverified_claims() -> None:
    client = FakeSlackDirectory(
        [
            _page(
                [
                    {
                        "id": "U001",
                        "team_id": "T123",
                        "name": "morgan",
                        "real_name": "Morgan Lee",
                        "deleted": False,
                        "is_bot": False,
                        "profile": {
                            "display_name": "Morgan",
                            "email": "Morgan@Example.test",
                            "phone": "+1 (415) 555-0100",
                        },
                    },
                    {"id": "U002", "deleted": False, "is_bot": True},
                ],
                "cursor-1",
            ),
            _page([{"id": "U003", "deleted": True, "is_bot": False}]),
        ]
    )
    source = _source(client, page_size=2, max_users=10)
    acl_calls: list[tuple[str, dict[str, object]]] = []
    stream_calls: list[tuple[str, str]] = []

    result = _read(
        source,
        acl=lambda action, request: acl_calls.append((action, dict(request))) or True,
        authorize_stream=lambda workspace, stream: stream_calls.append((workspace, stream)) or True,
    )

    assert len(result) == 1
    observation = result[0]
    assert observation.entity_id == "slack-user:T123:U001"
    assert observation.stream_id == "slack:T123:directory"
    assert observation.source_document_ids == ("slack-user-record:T123:U001",)
    assert observation.evidence_revision_ids[0].startswith("sha256:")
    assert observation.display_names == ("Morgan Lee", "Morgan", "morgan")
    assert [(point.channel, point.value, point.verification) for point in observation.contact_points] == [
        ("im", "U001", "claimed"),
        ("email", "Morgan@Example.test", "claimed"),
        ("phone", "+14155550100", "claimed"),
    ]
    assert [call.get("cursor") for call in client.calls] == [None, "cursor-1"]
    assert len(acl_calls) == len(stream_calls) == 4


def test_directory_reads_slack_sdk_response_data_without_auto_pagination() -> None:
    client = FakeSlackDirectory([SlackSdkResponse(_page([{"id": "U001"}]))])
    source = _source(client)

    (observation,) = _read(source)

    assert observation.entity_id == "slack-user:T123:U001"
    assert len(client.calls) == 1


def test_directory_requires_capability_and_host_acl_before_network() -> None:
    client = FakeSlackDirectory([_page([{"id": "U001"}])])
    source = _source(client)

    with pytest.raises(PermissionError, match="explicit ACL resolver required"):
        _read(source, acl=None)
    assert client.calls == []

    with pytest.raises(PermissionError, match="ACL denied"):
        _read(source, acl=lambda _action, _request: False)
    assert client.calls == []

    with pytest.raises(PermissionError, match="capabilities denied"):
        _read(source, capabilities=frozenset())
    assert client.calls == []


def test_directory_authorizes_stream_before_read_and_rechecks_after_read() -> None:
    client = FakeSlackDirectory([_page([{"id": "U001"}])])
    source = _source(client)

    with pytest.raises(PermissionError, match="not authorized"):
        _read(source, authorize_stream=lambda _workspace, _stream: False)
    assert client.calls == []

    calls = 0

    def revoked(_workspace: str, _stream: str) -> bool:
        nonlocal calls
        calls += 1
        return calls == 1

    with pytest.raises(PermissionError, match="authorization was revoked"):
        _read(source, authorize_stream=revoked)
    assert len(client.calls) == 1


def test_directory_stops_before_next_page_when_acl_is_revoked_mid_scan() -> None:
    client = FakeSlackDirectory(
        [
            _page([{"id": "U001"}], "cursor-1"),
            _page([{"id": "U002"}]),
        ]
    )
    source = _source(client)
    checks = 0

    def revoke_before_second_page(_workspace: str, _stream: str) -> bool:
        nonlocal checks
        checks += 1
        return checks < 3

    with pytest.raises(PermissionError, match="authorization was revoked"):
        _read(source, authorize_stream=revoke_before_second_page)

    assert len(client.calls) == 1


def test_directory_rejects_repeated_pagination_cursor_without_partial_result() -> None:
    client = FakeSlackDirectory(
        [
            _page([{"id": "U001"}], "same-cursor"),
            _page([{"id": "U002"}], "same-cursor"),
        ]
    )
    source = _source(client)

    with pytest.raises(ValueError, match="cursor repeated"):
        _read(source)
    assert len(client.calls) == 2


def test_directory_rejects_oversized_snapshot_instead_of_returning_partial_contacts() -> None:
    client = FakeSlackDirectory([_page([{"id": f"U00{i}"} for i in range(1, 4)])])
    source = _source(client, page_size=3, max_pages=1, max_users=2)

    with pytest.raises(ValueError, match="exceeds max_users"):
        _read(source)


def test_malformed_profile_claim_is_dropped_without_losing_slack_identity() -> None:
    client = FakeSlackDirectory(
        [
            _page(
                [
                    {
                        "id": "U001",
                        "profile": {"email": "bad\naddress@example.test", "phone": "415-555-0100"},
                    }
                ]
            )
        ]
    )

    def safe_contact_point(**kwargs: str) -> ContactPoint:
        if any(ord(char) < 0x20 for char in kwargs["value"]):
            raise ValueError("contact value contains a control character")
        return ContactPoint(**kwargs)

    source = SlackContactDirectorySource(
        client=client,
        workspaces={"workspace-a": "T123"},
        contact_point_factory=safe_contact_point,
        observation_factory=ContactObservation,
        clock_ms=lambda: 123456,
    )

    (observation,) = _read(source)

    assert observation.entity_id == "slack-user:T123:U001"
    assert [(point.channel, point.value) for point in observation.contact_points] == [
        ("im", "U001")
    ]


def test_directory_ignores_unselected_stream_without_calling_slack() -> None:
    client = FakeSlackDirectory([])
    source = _source(client)
    result = source.list_observations(
        "workspace-a",
        {"workspace_id": "workspace-a", "source_stream_ids": ("other:source",)},
        effective_capabilities=frozenset(),
        acl=None,
        authorize_stream=lambda *_: False,
    )
    assert result == ()
    assert client.calls == []


def test_directory_source_is_discoverable_only_with_slack_read_capability() -> None:
    source = _source(FakeSlackDirectory([]))
    catalog = CapabilityCatalog(adapter_descriptors((source,)))

    assert catalog.search(
        "Slack contact directory",
        allowed_capabilities=frozenset({"slack.read"}),
    )[0].capability_id == "tool:slack.list_contact_directory"
    assert catalog.search(
        "Slack contact directory",
        allowed_capabilities=frozenset(),
    ) == ()
