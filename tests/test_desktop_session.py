from pathlib import Path

import pytest

from stalker_gamma_linux.desktop import session
from stalker_gamma_linux.desktop.errors import DesktopWriteError
from stalker_gamma_linux.desktop.paths import DesktopPaths


def test_run_shortcut_success_prints_steam_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = DesktopPaths(data_home=tmp_path / "data")
    monkeypatch.setattr(session, "install_shortcut", lambda target: paths)
    monkeypatch.setattr(
        session,
        "launch_command",
        lambda target: ["/bin/stalker-gamma-linux", "play", "--target", str(target)],
    )

    exit_code = session.run_shortcut(tmp_path / "gamma")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert str(paths.desktop_file) in out
    assert "Ajouter un jeu non-Steam" in out
    assert "/bin/stalker-gamma-linux" in out
    assert f"play --target {tmp_path / 'gamma'}" in out


def test_run_shortcut_uses_default_target(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Path | None] = []

    def fake_install_shortcut(target: Path) -> DesktopPaths:
        captured.append(target)
        return DesktopPaths(data_home=Path("/data"))

    monkeypatch.setattr(session, "install_shortcut", fake_install_shortcut)
    monkeypatch.setattr(session, "launch_command", lambda target: ["x"])

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
    assert "Erreur" in capsys.readouterr().out
