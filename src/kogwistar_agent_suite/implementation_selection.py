"""Fail-closed implementation selection for the agent suite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Implementation = Literal["python", "rust", "shadow"]
SuiteSeam = Literal["catalog", "tools", "runtime", "adapters", "hooks"]

_SEAM_ENVIRONMENTS = {
    "catalog": "KOGWISTAR_AGENT_IMPL_CATALOG",
    "tools": "KOGWISTAR_AGENT_IMPL_TOOLS",
    "runtime": "KOGWISTAR_AGENT_IMPL_RUNTIME",
    "adapters": "KOGWISTAR_AGENT_IMPL_ADAPTERS",
    "hooks": "KOGWISTAR_AGENT_IMPL_HOOKS",
}


@dataclass(frozen=True)
class SuiteSelection:
    mode: Implementation = "python"
    seams: dict[SuiteSeam, Implementation] | None = None

    def selected(self, seam: SuiteSeam) -> Implementation:
        if self.seams and seam in self.seams:
            return self.seams[seam]
        return self.mode


def _implementation(value: str) -> Implementation:
    cleaned = value.strip().lower()
    if cleaned not in {"python", "rust", "shadow"}:
        raise ValueError(
            "implementation must be python, rust, or shadow: " + value
        )
    return cleaned  # type: ignore[return-value]


def selection_from_env() -> SuiteSelection:
    import os

    mode_value = os.getenv("KOGWISTAR_AGENT_IMPL_MODE")
    mode = _implementation(mode_value) if mode_value else "python"
    seams = {}
    for seam, name in _SEAM_ENVIRONMENTS.items():
        value = os.getenv(name)
        if value:
            seams[seam] = _implementation(value)
    return SuiteSelection(mode=mode, seams=seams or None)


def selected_implementation(seam: SuiteSeam) -> Implementation:
    return selection_from_env().selected(seam)
