"""Périmètre des sauvegardes — voir tasks/T17-sauvegarde-restauration-modlist.md.

Le point délicat est l'emplacement des sauvegardes de partie : constaté sur
l'install réelle (voir l'en-tête de `backups/paths.py`), le jeu écrit dans
`anomaly/appdata/savedgames`, mais deux autres emplacements restent
atteignables par configuration. Les trois sont couverts ici.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.backups import paths


def _touch(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _destinations(entries: tuple[paths.SourceEntry, ...]) -> list[str]:
    return [entry.destination for entry in entries]


class TestCandidateSources:
    def test_les_trois_emplacements_de_parties_sont_candidats(self, tmp_path: Path) -> None:
        (tmp_path / "gamma" / "profiles" / "G.A.M.M.A").mkdir(parents=True)

        found = _destinations(paths.candidate_sources(tmp_path, (paths.BackupSet.SAVES,)))

        assert found == [
            "anomaly/appdata/savedgames",
            "gamma/overwrite/appdata/savedgames",
            "gamma/profiles/G.A.M.M.A/saves",
        ]

    def test_chaque_profil_a_ses_parties_locales(self, tmp_path: Path) -> None:
        """`LocalSaves=true` range les parties par profil : un joueur peut en avoir deux."""
        for name in ("G.A.M.M.A", "Test"):
            (tmp_path / "gamma" / "profiles" / name).mkdir(parents=True)

        found = _destinations(paths.candidate_sources(tmp_path, (paths.BackupSet.SAVES,)))

        assert "gamma/profiles/G.A.M.M.A/saves" in found
        assert "gamma/profiles/Test/saves" in found

    def test_un_ensemble_inclus_dans_un_autre_nest_pas_copie_deux_fois(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "gamma" / "profiles" / "G.A.M.M.A").mkdir(parents=True)

        found = _destinations(paths.candidate_sources(tmp_path, paths.ALL_SETS))

        assert found == ["gamma/profiles", "gamma/overwrite", "anomaly/appdata/savedgames"]

    def test_sans_ensemble_demande_il_ny_a_rien_a_faire(self, tmp_path: Path) -> None:
        assert paths.candidate_sources(tmp_path, ()) == ()


class TestExistingSources:
    def test_seuls_les_dossiers_reellement_peuples_sont_retenus(self, tmp_path: Path) -> None:
        """`overwrite/` est vide sur l'install de test : l'annoncer sauvegardé serait faux."""
        _touch(tmp_path / "anomaly" / "appdata" / "savedgames" / "sauce.scop")
        (tmp_path / "gamma" / "overwrite").mkdir(parents=True)

        found = _destinations(paths.existing_sources(tmp_path, paths.ALL_SETS))

        assert found == ["anomaly/appdata/savedgames"]

    def test_un_dossier_absent_nest_pas_retenu(self, tmp_path: Path) -> None:
        assert paths.existing_sources(tmp_path, paths.ALL_SETS) == ()

    def test_les_profils_sont_retenus_des_quils_portent_un_fichier(self, tmp_path: Path) -> None:
        _touch(tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt", "+A\n")

        found = _destinations(paths.existing_sources(tmp_path, (paths.BackupSet.PROFILES,)))

        assert found == ["gamma/profiles"]


def test_linstantane_amont_vit_sous_backups(tmp_path: Path) -> None:
    assert paths.upstream_modlist_snapshot(tmp_path) == (
        tmp_path / "backups" / "upstream-modlist.txt"
    )
