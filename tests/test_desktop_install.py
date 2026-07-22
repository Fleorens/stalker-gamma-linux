from pathlib import Path

import pytest

from stalker_gamma_linux.desktop import install
from stalker_gamma_linux.desktop.errors import DesktopWriteError
from stalker_gamma_linux.desktop.paths import DesktopPaths
from stalker_gamma_linux.environment import system


def test_launch_command_uses_absolute_console_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install.sys, "executable", "/opt/venv/bin/python")

    command = install.launch_command(Path("/games/gamma"))

    assert command == [
        "/opt/venv/bin/stalker-gamma-linux",
        "play",
        "--target",
        "/games/gamma",
    ]


def _no_cache_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda command: None)


def test_install_shortcut_writes_icon_and_desktop_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_cache_tools(monkeypatch)
    paths = DesktopPaths(data_home=tmp_path / "data")
    target = tmp_path / "gamma"

    result = install.install_shortcut(target, paths=paths)

    assert result is paths
    assert paths.icon_file.read_bytes() == install._bundled_icon_bytes()
    content = paths.desktop_file.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert f"Icon={paths.icon_file}" in content
    assert f"Path={target}" in content


def test_install_shortcut_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_cache_tools(monkeypatch)
    paths = DesktopPaths(data_home=tmp_path / "data")

    install.install_shortcut(tmp_path / "gamma", paths=paths)
    install.install_shortcut(tmp_path / "gamma-v2", paths=paths)

    assert list(paths.applications_dir.iterdir()) == [paths.desktop_file]
    assert f"Path={tmp_path / 'gamma-v2'}" in paths.desktop_file.read_text(encoding="utf-8")


def test_install_shortcut_refreshes_caches_when_tools_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(system, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(system, "run", lambda command: calls.append(command))
    paths = DesktopPaths(data_home=tmp_path / "data")

    install.install_shortcut(tmp_path / "gamma", paths=paths)

    assert calls == [
        ["update-desktop-database", str(paths.applications_dir)],
        ["gtk-update-icon-cache", "-f", "-t", str(paths.icon_theme_root)],
    ]


def test_install_shortcut_wraps_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_cache_tools(monkeypatch)
    # Un fichier à la place du dossier attendu fait échouer le `mkdir` sous-jacent.
    data_home = tmp_path / "data"
    data_home.mkdir()
    (data_home / "applications").write_text("not a directory", encoding="utf-8")
    paths = DesktopPaths(data_home=data_home)

    with pytest.raises(DesktopWriteError):
        install.install_shortcut(tmp_path / "gamma", paths=paths)
