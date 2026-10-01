"""Optional adapter from suite contact sources to a generic WorkbenchApi."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from .authorization import AclResolver
from .slack_contacts import SlackContactDirectorySource

ObservationT = TypeVar("ObservationT")
EffectiveCapabilities = Callable[[str], frozenset[str]]


def register_slack_contact_source(
    host: object,
    source: SlackContactDirectorySource[ObservationT],
    *,
    effective_capabilities: EffectiveCapabilities,
    acl: AclResolver,
    source_id: str = "slack",
) -> None:
    """Register Slack claims with host's reversible, ACL-filtered contact book.

    The application must supply capabilities and an ACL resolver evaluated in
    its authenticated principal context. This bridge never grants
    ``slack.read`` itself and writes no graph or identity-decision state.
    """
    register = getattr(host, "register_contact_observation_source", None)
    authorize_resource = getattr(host, "authorize_resource", None)
    if not callable(register) or not callable(authorize_resource):
        raise TypeError("host must expose generic contact registration and resource ACL APIs")
    if not callable(effective_capabilities) or not callable(acl):
        raise TypeError("explicit capability and ACL resolvers are required")
    if not isinstance(source, SlackContactDirectorySource):
        raise TypeError("source must be a SlackContactDirectorySource")

    def owns_stream(workspace_id: str, stream_id: str) -> bool:
        return source.stream_id_for_workspace(workspace_id) == stream_id

    def authorize_stream(workspace_id: str, stream_id: str) -> bool:
        return (
            owns_stream(workspace_id, stream_id)
            and authorize_resource(
                workspace_id, "slack_contact_directory", stream_id, "read"
            ) is True
        )

    def provide(
        workspace_id: str,
        limit: int,
        stream_authorizer: Callable[[str, str], bool],
    ) -> Sequence[ObservationT]:
        stream_id = source.stream_id_for_workspace(workspace_id)
        if stream_id is None:
            return ()
        capabilities = effective_capabilities(workspace_id)
        if not isinstance(capabilities, frozenset) or any(
            not isinstance(item, str) or not item.strip() for item in capabilities
        ):
            raise TypeError("effective capabilities must be an explicit frozenset of strings")
        observations = source.list_observations(
            workspace_id,
            {
                "workspace_id": workspace_id,
                "source_stream_ids": (stream_id,),
                "observation_limit": limit,
            },
            effective_capabilities=capabilities,
            acl=acl,
            authorize_stream=stream_authorizer,
        )
        if len(observations) > limit:
            raise ValueError("Slack contact source exceeded host observation limit")
        return observations

    register(
        source_id,
        provider=provide,
        owns_stream=owns_stream,
        authorize_stream=authorize_stream,
    )


__all__ = ["EffectiveCapabilities", "register_slack_contact_source"]
