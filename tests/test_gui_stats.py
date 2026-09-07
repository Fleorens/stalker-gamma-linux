"""Chiffres des tuiles de l'accueil (`gui.stats`) — sans GTK."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.gui import stats
from stalker_gamma_linux.gui.format import UNKNOWN


def _mods_dir(root: Path) -> Path:
    mods = root / "gamma" / "mods"
    mods.mkdir(parents=True)
    return mods


class TestCountMods:
    def test_compte_les_dossiers_de_mods(self, tmp_path: Path) -> None:
        mods = _mods_dir(tmp_path)
        for name in ("100- Base", "200- Weapons", "300- Graphics"):
            (mods / name).mkdir()

        assert stats.count_mods(tmp_path) == 3

    def test_ignore_les_fichiers_poses_a_cote_des_mods(self, tmp_path: Path) -> None:
        """MO2 laisse des fichiers à la racine de `mods/` : ce ne sont pas des mods."""
        mods = _mods_dir(tmp_path)
        (mods / "100- Base").mkdir()
        (mods / "meta.ini").write_text("", encoding="utf-8")

        assert stats.count_mods(tmp_path) == 1

    def test_dossier_absent_rend_inconnu_et_pas_zero(self, tmp_path: Path) -> None:
        """« 0 mod » et « je ne sais pas » ne disent pas la même chose à l'écran."""
        assert stats.count_mods(tmp_path / "rien") is None

    def test_install_vide_rend_bien_zero(self, tmp_path: Path) -> None:
        _mods_dir(tmp_path)

        assert stats.count_mods(tmp_path) == 0


class TestInstallStats:
    def test_libelle_des_mods_connus(self) -> None:
        assert stats.InstallStats(mod_count=412, version="0.6.0").mods_label == "412"

    def test_libelle_des_mods_inconnus(self) -> None:
        assert stats.InstallStats(mod_count=None, version="0.6.0").mods_label == UNKNOWN


class TestCollect:
    def test_une_seule_passe_pour_les_deux_valeurs(self, tmp_path: Path) -> None:
        mods = _mods_dir(tmp_path)
        (mods / "100- Base").mkdir()

        collected = stats.collect(tmp_path)

        assert collected.mod_count == 1
        assert collected.version  # jamais vide : la version ou le marqueur d'inconnu
