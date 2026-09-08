from pathlib import Path

import pytest

from stalker_gamma_linux.desktop import session
from stalker_gamma_linux.desktop.errors import DesktopWriteError
from stalker_gamma_linux.desktop.paths import DesktopPaths


def test_run_shortcut_success_points_at_the_steam_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Depuis T19, l'ajout à Steam est une commande — plus une marche à suivre manuelle."""
    paths = DesktopPaths(data_home=tmp_path / "data")
    monkeypatch.setattr(session, "install_shortcut", lambda target: paths)

    exit_code = session.run_shortcut(tmp_path / "gamma")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert str(paths.desktop_file) in out
    assert "stalker-gamma-linux steam-shortcut" in out
    assert "Add a Non-Steam Game" not in out


def test_run_shortcut_uses_default_target(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Path | None] = []

    def fake_install_shortcut(target: Path) -> DesktopPaths:
        captured.append(target)
        return DesktopPaths(data_home=Path("/data"))

    monkeypatch.setattr(session, "install_shortcut", fake_install_shortcut)

    session.run_shortcut(None)

    assert captured == [session.DEFAULT_INSTALL_TARGET]


def test_run_shortcut_reports_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raise_error(target: Path) -> DesktopPaths:
        raise DesktopWriteError(Path("/data/x.desktop"), OSError("disque plein"))

    monkeypatch.setattr(session, "install_shortcut", raise_error)

    exit_code = session.run_shortcut(Path("/games/gamma"))

    assert exit_code == 1
    assert "Error" in capsys.readouterr().out
