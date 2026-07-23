from pathlib import Path

import pytest

from stalker_gamma_linux import state
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.gui import prefs


def test_load_preferences_defaults_when_file_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(state, "config_dir", lambda: tmp_path / "config")

    loaded = prefs.load_preferences()

    assert loaded == prefs.Preferences()
    assert loaded.install_path == DEFAULT_INSTALL_TARGET
    assert loaded.proton_release is None
    assert loaded.create_steam_shortcut is True


def test_load_preferences_defaults_when_file_corrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setattr(state, "config_dir", lambda: config_dir)
    config_dir.mkdir(parents=True)
    prefs.prefs_file().write_text("not = [valid toml", encoding="utf-8")

    assert prefs.load_preferences() == prefs.Preferences()


def test_save_then_load_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "config_dir", lambda: tmp_path / "config")
    original = prefs.Preferences(
        install_path=tmp_path / "Games" / "gamma",
        proton_release="GE-Proton10-8",
        create_steam_shortcut=False,
    )

    prefs.save_preferences(original)
    loaded = prefs.load_preferences()

    assert loaded == original


def test_save_preferences_creates_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "does" / "not" / "exist"
    monkeypatch.setattr(state, "config_dir", lambda: config_dir)

    prefs.save_preferences(prefs.Preferences())

    assert prefs.prefs_file().is_file()


def test_with_helpers_return_new_instances() -> None:
    base = prefs.Preferences()

    updated = base.with_install_path(Path("/mnt/games")).with_proton_release(
        "GE-Proton10-8"
    ).with_create_steam_shortcut(False)

    assert base == prefs.Preferences()
    assert updated.install_path == Path("/mnt/games")
    assert updated.proton_release == "GE-Proton10-8"
    assert updated.create_steam_shortcut is False


def test_with_proton_release_empty_string_means_auto() -> None:
    updated = prefs.Preferences(proton_release="GE-Proton10-8").with_proton_release("")

    assert updated.proton_release is None
