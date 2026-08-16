"""Fusion flat par liens durs (`mo2.merge`)."""

from __future__ import annotations

import errno
import os
import threading
from pathlib import Path

import pytest

from stalker_gamma_linux.mo2 import merge
from stalker_gamma_linux.mo2.errors import Mo2CancelledError, Mo2InstanceError
from stalker_gamma_linux.mo2.instance import GAMMA_PROFILE
from stalker_gamma_linux.mo2.paths import Mo2Paths


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _install(
    tmp_path: Path, modlist: str, mods: dict[str, dict[str, str]]
) -> tuple[Path, Mo2Paths]:
    """Anomaly minimal + instance MO2 avec les mods donnés (`{mod: {chemin: contenu}}`)."""
    anomaly = tmp_path / "anomaly"
    _write(anomaly / "AnomalyLauncher.exe", "exe")
    _write(anomaly / "bin" / "AnomalyDX11AVX.exe", "moteur")
    _write(anomaly / "gamedata" / "base.ltx", "vanilla")
    _write(anomaly / "appdata" / "user.ltx", "réglages")

    mo2 = Mo2Paths.under(tmp_path)
    _write(mo2.profile(GAMMA_PROFILE) / "modlist.txt", modlist)
    for name, files in mods.items():
        for relative, content in files.items():
            _write(mo2.mods / name / relative, content)
    return anomaly, mo2


def test_merge_applies_mods_bottom_up_so_the_top_one_wins(tmp_path: Path) -> None:
    # modlist.txt est écrit par priorité croissante de bas en haut : « Haut »
    # est prioritaire et doit donc l'emporter sur « Bas ».
    anomaly, mo2 = _install(
        tmp_path,
        "+Haut\n+Bas\n",
        {
            "Haut": {"gamedata/conflit.ltx": "haut"},
            "Bas": {"gamedata/conflit.ltx": "bas", "gamedata/seul.ltx": "bas"},
        },
    )
    final = tmp_path / "flat"

    merge.build_merged_install(anomaly, mo2, final)

    assert (final / "gamedata" / "conflit.ltx").read_text(encoding="utf-8") == "haut"
    assert (final / "gamedata" / "seul.ltx").read_text(encoding="utf-8") == "bas"


def test_merge_uses_hardlinks_not_copies(tmp_path: Path) -> None:
    anomaly, mo2 = _install(tmp_path, "+Mod\n", {"Mod": {"gamedata/arme.ltx": "mod"}})
    final = tmp_path / "flat"

    report = merge.build_merged_install(anomaly, mo2, final)

    source = mo2.mods / "Mod" / "gamedata" / "arme.ltx"
    assert (final / "gamedata" / "arme.ltx").stat().st_ino == source.stat().st_ino
    assert report.linked > 0
    assert report.shared_bytes > 0


def test_merge_copies_appdata_so_the_game_cannot_write_into_the_mods(tmp_path: Path) -> None:
    # Le jeu réécrit ses réglages et ses sauvegardes : un lien dur y ferait
    # remonter les modifications dans l'installation MO2 d'origine.
    anomaly, mo2 = _install(tmp_path, "+Mod\n", {"Mod": {"gamedata/arme.ltx": "mod"}})
    final = tmp_path / "flat"

    merge.build_merged_install(anomaly, mo2, final)

    merged = final / "appdata" / "user.ltx"
    assert merged.read_text(encoding="utf-8") == "réglages"
    assert merged.stat().st_ino != (anomaly / "appdata" / "user.ltx").stat().st_ino


def test_merge_restores_anomaly_binaries_last(tmp_path: Path) -> None:
    # Un mod qui dépose un fichier dans bin/ ne doit pas remplacer le moteur.
    anomaly, mo2 = _install(
        tmp_path, "+Mod\n", {"Mod": {"bin/AnomalyDX11AVX.exe": "moteur du mod"}}
    )
    final = tmp_path / "flat"

    merge.build_merged_install(anomaly, mo2, final)

    assert (final / "bin" / "AnomalyDX11AVX.exe").read_text(encoding="utf-8") == "moteur"


def test_merge_skips_disabled_mods(tmp_path: Path) -> None:
    anomaly, mo2 = _install(
        tmp_path,
        "+Actif\n-Inactif\n",
        {"Actif": {"gamedata/a.ltx": "a"}, "Inactif": {"gamedata/b.ltx": "b"}},
    )
    final = tmp_path / "flat"

    merge.build_merged_install(anomaly, mo2, final)

    assert (final / "gamedata" / "a.ltx").is_file()
    assert not (final / "gamedata" / "b.ltx").exists()


def test_merge_reports_enabled_mods_without_a_folder(tmp_path: Path) -> None:
    anomaly, mo2 = _install(tmp_path, "+Present\n+Fantome\n", {"Present": {"gamedata/a.ltx": "a"}})
    final = tmp_path / "flat"

    report = merge.build_merged_install(anomaly, mo2, final)

    assert report.missing == ("Fantome",)
    assert report.mods == 1


def test_merge_falls_back_to_copy_when_hardlinks_are_impossible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dossier final sur un autre système de fichiers (EXDEV) : la fusion doit
    # rester correcte, seulement plus coûteuse.
    anomaly, mo2 = _install(tmp_path, "+Mod\n", {"Mod": {"gamedata/arme.ltx": "mod"}})
    final = tmp_path / "flat"

    def refuse(source: str | Path, destination: str | Path) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", refuse)

    report = merge.build_merged_install(anomaly, mo2, final)

    assert report.linked == 0
    assert report.copied > 0
    assert (final / "gamedata" / "arme.ltx").read_text(encoding="utf-8") == "mod"


def test_merge_propagates_unexpected_os_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Un disque plein ne doit pas être silencieusement transformé en copie.
    anomaly, mo2 = _install(tmp_path, "+Mod\n", {"Mod": {"gamedata/arme.ltx": "mod"}})

    def full_disk(source: str | Path, destination: str | Path) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "link", full_disk)

    with pytest.raises(OSError, match="No space left"):
        merge.build_merged_install(anomaly, mo2, tmp_path / "flat")


def test_merge_is_replayable(tmp_path: Path) -> None:
    # Une fusion interrompue se complète en relançant : les fichiers déjà posés
    # sont remplacés, pas dupliqués ni refusés.
    anomaly, mo2 = _install(tmp_path, "+Mod\n", {"Mod": {"gamedata/arme.ltx": "mod"}})
    final = tmp_path / "flat"

    merge.build_merged_install(anomaly, mo2, final)
    report = merge.build_merged_install(anomaly, mo2, final)

    assert report.linked > 0
    assert (final / "gamedata" / "arme.ltx").read_text(encoding="utf-8") == "mod"


def test_merge_requires_an_anomaly_folder(tmp_path: Path) -> None:
    _anomaly, mo2 = _install(tmp_path, "+Mod\n", {"Mod": {"gamedata/a.ltx": "a"}})

    with pytest.raises(Mo2InstanceError):
        merge.build_merged_install(tmp_path / "absent", mo2, tmp_path / "flat")


def test_merge_refuses_an_empty_modlist(tmp_path: Path) -> None:
    # Fusionner Anomaly seul produirait un Anomaly vanilla déguisé en GAMMA.
    anomaly, mo2 = _install(tmp_path, "", {})

    with pytest.raises(Mo2InstanceError) as excinfo:
        merge.build_merged_install(anomaly, mo2, tmp_path / "flat")

    assert "vanilla" in str(excinfo.value)


def test_merge_honours_cancellation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    anomaly, mo2 = _install(tmp_path, "+Mod\n", {"Mod": {"gamedata/arme.ltx": "mod"}})
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(merge, "_CANCEL_CHECK_EVERY", 1)

    with pytest.raises(Mo2CancelledError):
        merge.build_merged_install(anomaly, mo2, tmp_path / "flat", cancel_event=cancel)
