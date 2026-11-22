from __future__ import annotations

import pytest

from kogwistar_agent_suite import developer_profile
from kogwistar_agent_suite.implementation_selection import selection_from_env


@pytest.mark.ci
def test_default_selection_is_python() -> None:
    assert selection_from_env().mode == "python"


@pytest.mark.ci
def test_invalid_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KOGWISTAR_AGENT_IMPL_MODE", "javascript")
    with pytest.raises(ValueError, match="implementation must be"):
        selection_from_env()


@pytest.mark.ci
def test_seam_overrides_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KOGWISTAR_AGENT_IMPL_MODE", "rust")
    monkeypatch.setenv("KOGWISTAR_AGENT_IMPL_TOOLS", "python")
    monkeypatch.setenv("KOGWISTAR_AGENT_IMPL_CATALOG", "rust")
    selection = selection_from_env()
    assert selection.mode == "rust"
    assert selection.selected("tools") == "python"
    assert selection.selected("catalog") == "rust"


@pytest.mark.ci
def test_rust_mode_requires_native_extension(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="_rust extension is required"):
        developer_profile(str(tmp_path), implementation="rust")


@pytest.mark.ci
def test_python_profile_removes_available(tmp_path) -> None:
    pack = developer_profile(str(tmp_path))
    assert pack.implementation == "python"
