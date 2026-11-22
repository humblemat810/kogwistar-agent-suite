"""Versioned bridge to the optional native Rust agent-suite extension."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .errors import SuiteImplementationUnavailable


class RustAgentSuiteExtension:
    """JSON-string ABI for the native implementation."""

    def __init__(self) -> None:
        try:
            from ._rust import capability_search_json
            from ._rust import core_runtime_resume_json
            from ._rust import core_runtime_run_json
            from ._rust import git_status_json
            from ._rust import implementation_version
            from ._rust import workspace_list_files_json
            from ._rust import workspace_read_text_json
            from ._rust import workspace_search_text_json
        except ImportError as error:
            raise SuiteImplementationUnavailable(
                "kogwistar_agent_suite._rust extension is required for Rust selection"
            ) from error
        self.capability_search_json = capability_search_json
        self.core_runtime_resume_json = core_runtime_resume_json
        self.core_runtime_run_json = core_runtime_run_json
        self.git_status_json = git_status_json
        self.implementation_version = implementation_version
        self.workspace_list_files_json = workspace_list_files_json
        self.workspace_read_text_json = workspace_read_text_json
        self.workspace_search_text_json = workspace_search_text_json

    @staticmethod
    def payload(data: Mapping[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    def search(
        self,
        descriptors: list[Mapping[str, Any]],
        *,
        query: str,
        allowed_capabilities: frozenset[str],
        mode: str,
        limit: int,
    ) -> list[Mapping[str, Any]]:
        result = json.loads(
            self.capability_search_json(
                self.payload(
                    {
                        "descriptors": descriptors,
                        "query": query,
                        "allowed_capabilities": sorted(allowed_capabilities),
                        "mode": mode,
                        "limit": limit,
                    }
                )
            )
        )
        return result

    def list_files(
        self, workspace_root: str, relative_path: str, limit: int
    ) -> list[str]:
        return json.loads(
            self.workspace_list_files_json(
                self.payload(
                    {
                        "workspace_root": workspace_root,
                        "relative_path": relative_path,
                        "limit": limit,
                    }
                )
            )
        )

    def read_text(
        self, workspace_root: str, relative_path: str, max_bytes: int
    ) -> str:
        return json.loads(
            self.workspace_read_text_json(
                self.payload(
                    {
                        "workspace_root": workspace_root,
                        "relative_path": relative_path,
                        "max_bytes": max_bytes,
                    }
                )
            )
        )

    def search_text(
        self,
        workspace_root: str,
        query: str,
        limit: int,
        max_file_bytes: int,
    ) -> list[Mapping[str, Any]]:
        return json.loads(
            self.workspace_search_text_json(
                self.payload(
                    {
                        "workspace_root": workspace_root,
                        "query": query,
                        "limit": limit,
                        "max_file_bytes": max_file_bytes,
                    }
                )
            )
        )

    def git_status(self, workspace_root: str) -> Mapping[str, Any]:
        return json.loads(
            self.git_status_json(self.payload({"workspace_root": workspace_root}))
        )

    def core_runtime_run(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return json.loads(self.core_runtime_run_json(self.payload(request)))

    def core_runtime_resume(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return json.loads(self.core_runtime_resume_json(self.payload(request)))
