from pathlib import Path

import pytest

from stalker_gamma_linux import state
from stalker_gamma_linux.environment import gamescope, mangohud, system
from stalker_gamma_linux.environment.performance import Settings
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.gui import prefs


@pytest.fixture(autouse=True)
def not_a_steam_deck(monkeypatch: pytest.MonkeyPatch) -> None:
    """Machine de bureau : les défauts de gamescope ne doivent pas dépendre du CI."""
    monkeypatch.setattr(system, "read_text", lambda path: None)
    monkeypatch.delenv("SteamDeck", raising=False)


def test_load_preferences_defaults_when_file_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(state, "config_dir", lambda: tmp_path / "config")

    loaded = prefs.load_preferences()

    assert loaded == prefs.Preferences()
    assert loaded.install_path == DEFAULT_INSTALL_TARGET
    assert loaded.proton_release is None
    # False par défaut : install.sh crée déjà l'icône du menu applications
    # (le launcher) — ce raccourci-ci est l'entrée « jouer en direct »
    # optionnelle, surtout utile pour Steam (voir gui/prefs.py).
    assert loaded.create_steam_shortcut is False


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


def test_defaults_follow_the_screen_on_a_steam_deck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Premier lancement sur un Deck : proposer 1920×1080 sur un écran 1280×800
    # serait un mauvais point de départ pour le seul réglage qui compte là-bas.
    monkeypatch.setattr(state, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(system, "read_text", lambda path: "Galileo\n")

    options = prefs.load_preferences().performance.gamescope_options

    assert str(options.output) == "1280x800"
    assert str(options.render) == "1024x640"


def test_the_performance_layers_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "config_dir", lambda: tmp_path / "config")
    settings = Settings(
        gamemode=False,
        mangohud=True,
        mangohud_preset=mangohud.Preset.FULL,
        gamescope=True,
        gamescope_options=gamescope.Options(render=gamescope.Resolution(1152, 720)),
        vkbasalt=True,
    )

    prefs.save_preferences(prefs.Preferences().with_performance(settings))

    assert prefs.load_preferences().performance == settings


def test_the_old_gamemode_key_is_still_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fichier écrit avant T20 : quelqu'un qui avait coupé GameMode ne doit pas
    # le voir revenir tout seul à la mise à jour.
    config_dir = tmp_path / "config"
    monkeypatch.setattr(state, "config_dir", lambda: config_dir)
    config_dir.mkdir(parents=True)
    prefs.prefs_file().write_text("use_gamemode = false\n", encoding="utf-8")

    loaded = prefs.load_preferences()

    assert loaded.performance.gamemode is False
    assert not loaded.performance.any_layer_requested


def test_the_user_global_configs_are_not_mentioned_in_our_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(state, "config_dir", lambda: tmp_path / "config")

    prefs.save_preferences(prefs.Preferences())

    written = prefs.prefs_file().read_text(encoding="utf-8")
    assert "[performance]" in written
    # L'ancienne clé n'est plus écrite : une seule source de vérité.
    assert "use_gamemode" not in written


def test_save_preferences_creates_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "does" / "not" / "exist"
    monkeypatch.setattr(state, "config_dir", lambda: config_dir)

    prefs.save_preferences(prefs.Preferences())

    assert prefs.prefs_file().is_file()


def test_with_helpers_return_new_instances() -> None:
    base = prefs.Preferences()

    updated = (
        base.with_install_path(Path("/mnt/games"))
        .with_proton_release("GE-Proton10-8")
        .with_create_steam_shortcut(False)
    )

    assert base == prefs.Preferences()
    assert updated.install_path == Path("/mnt/games")
    assert updated.proton_release == "GE-Proton10-8"
    assert updated.create_steam_shortcut is False


def test_with_proton_release_empty_string_means_auto() -> None:
    updated = prefs.Preferences(proton_release="GE-Proton10-8").with_proton_release("")

    assert updated.proton_release is None


def test_load_preferences_ignore_un_install_path_avec_caractere_de_controle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le TOML est éditable à la main : il ne doit pas rouvrir la brèche du `.desktop`.

    Repli silencieux sur le défaut, conformément au contrat « jamais d'exception »
    de `load_preferences` (cf. paths_safety.validate_install_target).
    """
    config_dir = tmp_path / "config"
    monkeypatch.setattr(state, "config_dir", lambda: config_dir)
    config_dir.mkdir(parents=True)
    prefs.prefs_file().write_text('install_path = "/tmp/a\\nExec=/bin/sh"\n', encoding="utf-8")

    assert prefs.load_preferences().install_path == DEFAULT_INSTALL_TARGET


def test_load_preferences_conserve_un_install_path_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setattr(state, "config_dir", lambda: config_dir)
    config_dir.mkdir(parents=True)
    prefs.prefs_file().write_text('install_path = "/mnt/disk/GAMMA"\n', encoding="utf-8")

    assert prefs.load_preferences().install_path == Path("/mnt/disk/GAMMA")
