"""Optional, ACL-gated Slack contact-directory source adapter.

The suite owns Slack API interpretation; the host supplies factories for its
generic contact-observation contracts. No LLM-Wiki import or graph write lives
in this adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any, Generic, Protocol, TypeVar

from .authorization import require_acl, require_capabilities
from .catalog import CapabilityDescriptor, CapabilityKind
from .plugins import PluginManifest

ObservationT = TypeVar("ObservationT")
_SLACK_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_E164 = re.compile(r"^\+[1-9][0-9]{1,14}$")
_MAX_PAGE_SIZE = 200
_MAX_PAGES = 100
_MAX_USERS = 10_000


class SlackDirectoryClient(Protocol):
    """Small Slack Web API subset used by this adapter."""

    def users_list(self, **kwargs: object) -> object: ...


class ContactPointFactory(Protocol):
    def __call__(self, *, channel: str, value: str, provider: str, verification: str) -> object: ...


class ContactObservationFactory(Protocol[ObservationT]):
    def __call__(
        self,
        *,
        workspace_id: str,
        stream_id: str,
        entity_id: str,
        source_document_ids: tuple[str, ...],
        evidence_revision_ids: tuple[str, ...],
        observed_at_ms: int,
        display_names: tuple[str, ...],
        contact_points: tuple[object, ...],
    ) -> ObservationT: ...


AuthorizeContactStream = Callable[[str, str], bool]


class SlackContactDirectorySource(Generic[ObservationT]):
    """Expose bounded Slack directory snapshots as host-owned contact claims.

    Construct with explicit workspace-to-team bindings and typed observation
    factories. Credentials/network policy belong to the injected client. The
    source is read-only: returned values are claims for review, never identity
    decisions or canonical graph mutations.
    """

    manifest = PluginManifest(
        "kogwistar-agent-suite.slack-contact-directory",
        "0.1.0",
        ("slack.read",),
    )

    def __init__(
        self,
        *,
        client: SlackDirectoryClient,
        workspaces: Mapping[str, str],
        contact_point_factory: ContactPointFactory,
        observation_factory: ContactObservationFactory[ObservationT],
        page_size: int = _MAX_PAGE_SIZE,
        max_pages: int = _MAX_PAGES,
        max_users: int = _MAX_USERS,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if not callable(getattr(client, "users_list", None)):
            raise TypeError("Slack client must provide users_list")
        if not isinstance(workspaces, Mapping) or not workspaces:
            raise ValueError("explicit workspace-to-team bindings are required")
        if not callable(contact_point_factory) or not callable(observation_factory):
            raise TypeError("host contact contract factories are required")
        bindings: dict[str, str] = {}
        for workspace_id, team_id in workspaces.items():
            if not isinstance(workspace_id, str) or not workspace_id.strip():
                raise ValueError("workspace IDs must be non-empty strings")
            if not isinstance(team_id, str) or not _SLACK_ID.fullmatch(team_id):
                raise ValueError("team IDs must be valid Slack identifiers")
            bindings[workspace_id.strip()] = team_id
        if len(bindings) != len(workspaces):
            raise ValueError("workspace IDs must be unique after normalization")
        if type(page_size) is not int or not 1 <= page_size <= _MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {_MAX_PAGE_SIZE}")
        if type(max_pages) is not int or not 1 <= max_pages <= _MAX_PAGES:
            raise ValueError(f"max_pages must be between 1 and {_MAX_PAGES}")
        if type(max_users) is not int or not 1 <= max_users <= page_size * max_pages:
            raise ValueError("max_users must fit within the configured page bound")
        if clock_ms is not None and not callable(clock_ms):
            raise TypeError("clock_ms must be callable")
        self._client = client
        self._workspaces = bindings
        self._make_contact_point = contact_point_factory
        self._make_observation = observation_factory
        self._page_size = page_size
        self._max_pages = max_pages
        self._max_users = max_users
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

    def descriptors(self) -> tuple[CapabilityDescriptor, ...]:
        return (
            CapabilityDescriptor(
                capability_id="tool:slack.list_contact_directory",
                name="Read Slack contact directory",
                kind=CapabilityKind.TOOL,
                summary="Read a bounded, explicitly authorized Slack directory as unverified contact claims.",
                required_capabilities=frozenset({"slack.read"}),
                tags=("adapter", "read", "contact-source"),
                provider_id=self.manifest.plugin_id,
                metadata={"side_effect": "read"},
            ),
        )

    def list_observations(
        self,
        workspace_id: str,
        payload: Mapping[str, object],
        *,
        effective_capabilities: frozenset[str],
        acl: Callable[[str, Mapping[str, Any]], bool] | None,
        authorize_stream: AuthorizeContactStream,
    ) -> tuple[ObservationT, ...]:
        """Read selected directory stream only after all ACL checks pass."""

        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty")
        if not isinstance(payload, Mapping) or payload.get("workspace_id") != workspace_id:
            raise ValueError("contact scan payload must match workspace")
        if not callable(authorize_stream):
            raise TypeError("contact stream authorizer is required")
        team_id = self._workspaces.get(workspace_id)
        if team_id is None:
            raise PermissionError("Slack workspace is not configured")
        stream_id = f"slack:{team_id}:directory"
        stream_ids = _requested_streams(payload.get("source_stream_ids"))
        if stream_id not in stream_ids:
            return ()

        request = {
            "workspace_id": workspace_id,
            "team_id": team_id,
            "source_id": stream_id,
            "side_effect": "read",
        }

        def authorize_page(*, after_read: bool = False) -> None:
            _authorize_directory(request, effective_capabilities, acl)
            if authorize_stream(workspace_id, stream_id) is not True:
                reason = "authorization was revoked" if after_read else "is not authorized"
                raise PermissionError(f"Slack directory source {reason}")

        users = self._read_users(team_id, authorize_page=authorize_page)

        observed_at_ms = self._clock_ms()
        if type(observed_at_ms) is not int or observed_at_ms < 0:
            raise ValueError("clock_ms must return a non-negative integer")
        observations: list[ObservationT] = []
        for user in users:
            if _is_non_person_account(user):
                continue
            observations.append(
                self._observation(workspace_id, team_id, user, observed_at_ms)
            )
        return tuple(observations)

    def _read_users(
        self, team_id: str, *, authorize_page: Callable[..., None]
    ) -> tuple[Mapping[str, object], ...]:
        users: dict[str, Mapping[str, object]] = {}
        seen_cursors: set[str] = set()
        cursor: str | None = None
        has_read_page = False
        for page_number in range(self._max_pages):
            authorize_page(after_read=has_read_page)
            kwargs: dict[str, object] = {"team_id": team_id, "limit": self._page_size}
            if cursor is not None:
                kwargs["cursor"] = cursor
            response = _response_payload(self._client.users_list(**kwargs))
            # A revoked stream must not trigger another request or be consumed.
            authorize_page(after_read=True)
            has_read_page = True
            if response.get("ok") is not True:
                raise ValueError("Slack users.list returned an unsuccessful response")
            members = response.get("members")
            metadata = response.get("response_metadata", {})
            if not isinstance(members, list) or not isinstance(metadata, Mapping):
                raise TypeError("Slack users.list returned a malformed page")
            for member in members:
                if not isinstance(member, Mapping):
                    raise TypeError("Slack users.list contains a malformed member")
                _validate_user_flags(member)
                user_id = member.get("id")
                if not isinstance(user_id, str) or not _SLACK_ID.fullmatch(user_id):
                    raise ValueError("Slack member has an invalid user ID")
                previous = users.get(user_id)
                if previous is not None and previous != member:
                    raise ValueError("Slack users.list returned conflicting duplicate users")
                users[user_id] = member
                if len(users) > self._max_users:
                    raise ValueError("Slack directory exceeds max_users")

            next_cursor = metadata.get("next_cursor", "")
            if not isinstance(next_cursor, str):
                raise TypeError("Slack users.list returned an invalid pagination cursor")
            next_cursor = next_cursor.strip()
            if not next_cursor:
                return tuple(users[key] for key in sorted(users))
            if next_cursor in seen_cursors or next_cursor == cursor:
                raise ValueError("Slack users.list pagination cursor repeated")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise ValueError("Slack directory exceeds max_pages")

    def _observation(
        self,
        workspace_id: str,
        team_id: str,
        user: Mapping[str, object],
        observed_at_ms: int,
    ) -> ObservationT:
        user_id = str(user["id"])
        returned_team = user.get("team_id")
        if returned_team is not None and returned_team != team_id:
            raise ValueError("Slack users.list returned a member from another team")
        profile = user.get("profile", {})
        if not isinstance(profile, Mapping):
            raise TypeError("Slack member profile is malformed")
        names = _display_names(user, profile)
        points: list[object] = []
        point_fingerprint: list[dict[str, str]] = []
        points.append(
            self._make_contact_point(
                channel="im", provider="slack", value=user_id, verification="claimed"
            )
        )
        point_fingerprint.append({"channel": "im", "value": user_id})
        email = profile.get("email")
        if isinstance(email, str) and email.strip():
            try:
                email_claim = self._make_contact_point(
                    channel="email", provider="slack", value=email.strip(), verification="claimed"
                )
            except ValueError:
                email_claim = None
            if email_claim is not None:
                points.append(email_claim)
                point_fingerprint.append({"channel": "email", "value": email.strip()})
        phone = profile.get("phone")
        if isinstance(phone, str) and phone.strip():
            normalized_phone = _normalize_explicit_e164(phone)
            if normalized_phone is not None:
                phone_claim = self._make_contact_point(
                    channel="phone",
                    provider="slack",
                    value=normalized_phone,
                    verification="claimed",
                )
                points.append(phone_claim)
                point_fingerprint.append({"channel": "phone", "value": normalized_phone})
        revision_payload = {
            "team_id": team_id,
            "user_id": user_id,
            "names": names,
            "contact_points": point_fingerprint,
            "deleted": user.get("deleted", False),
            "is_bot": user.get("is_bot", False),
            "is_app_user": user.get("is_app_user", False),
        }
        revision = hashlib.sha256(
            json.dumps(revision_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return self._make_observation(
            workspace_id=workspace_id,
            stream_id=f"slack:{team_id}:directory",
            entity_id=f"slack-user:{team_id}:{user_id}",
            source_document_ids=(f"slack-user-record:{team_id}:{user_id}",),
            evidence_revision_ids=(f"sha256:{revision}",),
            observed_at_ms=observed_at_ms,
            display_names=names,
            contact_points=tuple(points),
        )

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()


def _requested_streams(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("contact scan requires source_stream_ids")
    streams: list[str] = []
    for stream_id in value:
        if not isinstance(stream_id, str) or not stream_id.strip():
            raise ValueError("source_stream_ids must contain non-empty strings")
        streams.append(stream_id.strip())
    if len(set(streams)) != len(streams):
        raise ValueError("source_stream_ids must be unique")
    return tuple(streams)


def _response_payload(response: object) -> Mapping[str, object]:
    """Read Slack SDK responses without iterating their auto-paging protocol."""

    if isinstance(response, Mapping):
        return response
    # slack_sdk.web.slack_response.SlackResponse exposes its JSON payload as
    # ``data``; iterating the response itself performs more network requests.
    payload = getattr(response, "data", None)
    if isinstance(payload, Mapping):
        return payload
    raise TypeError("Slack users.list returned a malformed response")


def _authorize_directory(
    request: Mapping[str, Any],
    effective_capabilities: frozenset[str],
    acl: Callable[[str, Mapping[str, Any]], bool] | None,
) -> None:
    require_acl(action="slack.contact_directory.read", request=request, acl=acl)
    require_capabilities(
        frozenset({"slack.read"}),
        effective_capabilities,
        action="slack.contact_directory.read",
    )


def _display_names(
    user: Mapping[str, object], profile: Mapping[str, object]
) -> tuple[str, ...]:
    values = (
        profile.get("real_name"),
        user.get("real_name"),
        profile.get("display_name"),
        user.get("name"),
    )
    names: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        name = value.strip()
        if len(name) > 256 or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name):
            raise ValueError("Slack profile contains an invalid display name")
        if name not in names:
            names.append(name)
    return tuple(names)


def _normalize_explicit_e164(value: str) -> str | None:
    """Remove punctuation only; never infer country codes."""

    candidate = value.strip()
    if (
        not candidate.startswith("+")
        or candidate.count("+") != 1
        or any(char not in "+0123456789 ().-" for char in candidate)
    ):
        return None
    normalized = "+" + "".join(char for char in candidate if "0" <= char <= "9")
    return normalized if _E164.fullmatch(normalized) else None


def _is_non_person_account(user: Mapping[str, object]) -> bool:
    return any(
        user.get(flag) is True for flag in ("deleted", "is_bot", "is_app_user")
    )


def _validate_user_flags(user: Mapping[str, object]) -> None:
    for flag in ("deleted", "is_bot", "is_app_user"):
        value = user.get(flag)
        if value is not None and type(value) is not bool:
            raise ValueError(f"Slack member field {flag} must be boolean")


__all__ = [
    "ContactObservationFactory",
    "ContactPointFactory",
    "SlackContactDirectorySource",
    "SlackDirectoryClient",
]
