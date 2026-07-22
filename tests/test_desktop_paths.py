from pathlib import Path

import pytest

from stalker_gamma_linux.desktop.paths import DesktopPaths


def test_default_uses_xdg_data_home_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")

    paths = DesktopPaths.default()

    assert paths.data_home == Path("/custom/data")


def test_default_falls_back_to_local_share(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    paths = DesktopPaths.default()

    assert paths.data_home == Path.home() / ".local" / "share"


def test_derived_paths() -> None:
    paths = DesktopPaths(data_home=Path("/data"))

    assert paths.applications_dir == Path("/data/applications")
    assert paths.icon_dir == Path("/data/icons/hicolor/256x256/apps")
    assert paths.desktop_file == Path("/data/applications/stalker-gamma-linux.desktop")
    assert paths.icon_file == Path("/data/icons/hicolor/256x256/apps/stalker-gamma-linux.png")
