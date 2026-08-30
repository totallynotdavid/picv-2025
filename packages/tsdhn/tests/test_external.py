import shutil
from pathlib import Path

import pytest

from tsdhn.external import ensure_executables, resolve


def test_resolve_returns_the_path_when_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    resolve.cache_clear()

    assert resolve("gmt") == Path("/usr/bin/gmt")


def test_resolve_raises_when_not_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    resolve.cache_clear()

    with pytest.raises(RuntimeError, match="not found on PATH"):
        resolve("missing_tool")


def test_ensure_executables_raises_on_the_first_missing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    resolve.cache_clear()

    with pytest.raises(RuntimeError, match="missing_tool"):
        ensure_executables(("missing_tool",))
