from pathlib import Path

import pytest

from stalker_gamma_linux.mo2 import instance
from stalker_gamma_linux.mo2.errors import AnomalyNotFoundError, Mo2NotInstalledError
from stalker_gamma_linux.mo2.paths import Mo2Paths


def _make_instance(tmp_path: Path, *, ini_content: str | None = None) -> tuple[Mo2Paths, Path]:
    """Instance MO2 minimale + dossier Anomaly valide. Retourne (mo2, anomaly_dir)."""
    mo2 = Mo2Paths.under(tmp_path)
    mo2.instance.mkdir(parents=True)
    mo2.executable.write_text("", encoding="utf-8")
    if ini_content is not None:
        mo2.organizer_ini.write_text(ini_content, encoding="utf-8")

    anomaly = tmp_path / "anomaly"
    anomaly.mkdir()
    (anomaly / "AnomalyLauncher.exe").write_text("", encoding="utf-8")
    return mo2, anomaly


def test_configure_sets_gamepath_and_profile(tmp_path: Path) -> None:
    mo2, anomaly = _make_instance(tmp_path, ini_content="[General]\ngameName=STALKER Anomaly\n")

    config = instance.configure_instance(mo2, anomaly)

    assert config.changed is True
    assert config.profile == "G.A.M.M.A"
    assert instance.read_game_path(mo2) == config.game_path
    assert config.game_path.startswith("Z:\\")
    assert config.game_path.endswith("anomaly")
    assert instance.is_configured(mo2, anomaly)
    # gameName préexistant préservé.
    assert "gameName=STALKER Anomaly" in mo2.organizer_ini.read_text()


def test_configure_is_idempotent(tmp_path: Path) -> None:
    mo2, anomaly = _make_instance(tmp_path, ini_content="[General]\ngameName=STALKER Anomaly\n")

    instance.configure_instance(mo2, anomaly)
    second = instance.configure_instance(mo2, anomaly)

    assert second.changed is False


def test_configure_writes_backup_once(tmp_path: Path) -> None:
    original = "[General]\ngameName=STALKER Anomaly\ngamePath=@ByteArray(Z:\\\\old)\n"
    mo2, anomaly = _make_instance(tmp_path, ini_content=original)

    first = instance.configure_instance(mo2, anomaly)
    backup = mo2.instance / "ModOrganizer.ini.bak"

    assert first.backup == backup
    assert backup.read_text() == original

    # Un deuxième run qui change encore quelque chose ne doit pas écraser la
    # sauvegarde d'origine par la version déjà modifiée.
    mo2.organizer_ini.write_text(original.replace("Z:\\\\old", "Z:\\\\other"), encoding="utf-8")
    instance.configure_instance(mo2, anomaly)
    assert backup.read_text() == original


def test_configure_creates_ini_when_absent(tmp_path: Path) -> None:
    mo2, anomaly = _make_instance(tmp_path, ini_content=None)

    instance.configure_instance(mo2, anomaly)

    text = mo2.organizer_ini.read_text()
    assert "gameName=STALKER Anomaly" in text
    assert "first_start=false" in text
    assert instance.is_configured(mo2, anomaly)


def test_configure_rejects_missing_executable(tmp_path: Path) -> None:
    mo2 = Mo2Paths.under(tmp_path)
    mo2.instance.mkdir(parents=True)
    anomaly = tmp_path / "anomaly"
    anomaly.mkdir()
    (anomaly / "AnomalyLauncher.exe").write_text("", encoding="utf-8")

    with pytest.raises(Mo2NotInstalledError):
        instance.configure_instance(mo2, anomaly)


def test_configure_rejects_invalid_anomaly_dir(tmp_path: Path) -> None:
    mo2, _ = _make_instance(tmp_path, ini_content="[General]\n")
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(AnomalyNotFoundError):
        instance.configure_instance(mo2, empty)


def test_is_configured_false_when_ini_absent(tmp_path: Path) -> None:
    mo2, anomaly = _make_instance(tmp_path, ini_content=None)

    assert instance.is_configured(mo2, anomaly) is False


def test_read_game_path_none_when_ini_absent(tmp_path: Path) -> None:
    mo2, _ = _make_instance(tmp_path, ini_content=None)

    assert instance.read_game_path(mo2) is None


# ModOrganizer.ini réel d'une instance GAMMA (extrait), avec un ancien dossier
# Anomaly baked-in à la fois dans gamePath et dans les customExecutables.
_REAL_GAMMA_INI = (
    "[General]\n"
    "gameName=STALKER Anomaly\n"
    "selected_profile=@ByteArray(G.A.M.M.A)\n"
    "gamePath=@ByteArray(Z:\\\\old\\\\GAMMA\\\\gamma\\\\anomaly)\n"
    "version=2.5.2\n"
    "first_start=false\n"
    "\n"
    "[customExecutables]\n"
    "size=3\n"
    "1\\binary=Z:/old/GAMMA/gamma/anomaly/AnomalyLauncher.exe\n"
    "1\\title=Anomaly Launcher\n"
    "1\\workingDirectory=Z:/old/GAMMA/gamma/anomaly\n"
    "3\\binary=Z:/old/GAMMA/gamma/anomaly/bin/AnomalyDX11.exe\n"
    "3\\title=Anomaly (DX11)\n"
    "3\\workingDirectory=Z:/old/GAMMA/gamma/anomaly/bin\n"
    "10\\binary=Z:/old/GAMMA/gamma/gamma/explorer++/Explorer++.exe\n"
    '10\\arguments=\\"Z:\\\\old\\\\GAMMA\\\\gamma\\\\anomaly\\"\n'
    "10\\title=Explore Virtual Folder\n"
)


def test_configure_rebases_custom_executables_to_new_anomaly(tmp_path: Path) -> None:
    mo2, anomaly = _make_instance(tmp_path, ini_content=_REAL_GAMMA_INI)

    config = instance.configure_instance(mo2, anomaly)
    text = mo2.organizer_ini.read_text()
    new_fwd = config.game_path.replace("\\", "/")

    # gamePath ré-écrit et les 2 exécutables Anomaly rebasés vers le vrai dossier.
    assert instance.is_configured(mo2, anomaly)
    assert f"3\\binary={new_fwd}/bin/AnomalyDX11.exe" in text
    assert f"1\\binary={new_fwd}/AnomalyLauncher.exe" in text
    assert f"1\\workingDirectory={new_fwd}\n" in text
    # Explorer++ (hors dossier Anomaly) intact.
    assert "10\\binary=Z:/old/GAMMA/gamma/gamma/explorer++/Explorer++.exe" in text
    # gameName/profil préservés.
    assert "gameName=STALKER Anomaly" in text
    assert instance.read_game_path(mo2) == config.game_path
