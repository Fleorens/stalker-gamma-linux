"""Manifeste d'une sauvegarde : ce qu'il dit, et ce qu'il refuse de dire.

Le manifeste est un fichier sur le disque de l'utilisateur — tronqué par un
disque plein, réécrit à la main, ou recopié depuis ailleurs. C'est lui qui
décide où la restauration écrit : les refus testés ici sont donc du même
ordre que ceux de `paths_safety`, appliqués au chemin qui *sort* d'un fichier.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from stalker_gamma_linux.backups import manifest as manifest_module
from stalker_gamma_linux.backups.errors import ManifestError
from stalker_gamma_linux.backups.paths import BackupSet

_WHEN = datetime(2026, 9, 7, 14, 25, 30, tzinfo=UTC)


def _manifest(**overrides: object) -> manifest_module.Manifest:
    defaults: dict[str, object] = {
        "identifier": "profiles-20260907-142530",
        "created_at": _WHEN,
        "entries": (
            manifest_module.ManifestEntry(
                set_name=BackupSet.PROFILES,
                slot="profiles",
                destination="gamma/profiles",
                files=6,
                size_bytes=31068,
            ),
        ),
    }
    defaults.update(overrides)
    return manifest_module.Manifest(**defaults)  # type: ignore[arg-type]


class TestAllerRetour:
    def test_un_manifeste_ecrit_se_relit_a_lidentique(self, tmp_path: Path) -> None:
        written = _manifest(explicit=True, gamma_version="920", tool_version="0.6.0")
        manifest_module.write_manifest(tmp_path, written)

        assert manifest_module.read_manifest(tmp_path) == written

    def test_plusieurs_ensembles_gardent_leur_ordre(self, tmp_path: Path) -> None:
        entries = (
            manifest_module.ManifestEntry(BackupSet.PROFILES, "profiles", "gamma/profiles"),
            manifest_module.ManifestEntry(
                BackupSet.SAVES, "saves/anomaly-appdata", "anomaly/appdata/savedgames"
            ),
        )
        manifest_module.write_manifest(tmp_path, _manifest(entries=entries))

        assert manifest_module.read_manifest(tmp_path).sets == (
            BackupSet.PROFILES,
            BackupSet.SAVES,
        )


class TestRefus:
    @pytest.mark.parametrize(
        "destination",
        ["/etc/passwd", "../../.bashrc", "gamma/../../ailleurs", "", "gamma\\profiles"],
    )
    def test_une_destination_qui_sort_de_la_racine_est_refusee(
        self, tmp_path: Path, destination: str
    ) -> None:
        (tmp_path / "backup.toml").write_text(
            "[backup]\n"
            'created_at = "2026-09-07T14:25:30+00:00"\n'
            "[[backup.entries]]\n"
            'set = "profiles"\n'
            'slot = "profiles"\n'
            f'destination = "{destination}"\n',
            encoding="utf-8",
        )

        with pytest.raises(ManifestError):
            manifest_module.read_manifest(tmp_path)

    def test_un_toml_invalide_est_refuse(self, tmp_path: Path) -> None:
        (tmp_path / "backup.toml").write_text("[backup\n", encoding="utf-8")

        with pytest.raises(ManifestError, match="TOML"):
            manifest_module.read_manifest(tmp_path)

    def test_un_manifeste_sans_entree_est_refuse(self, tmp_path: Path) -> None:
        """Une sauvegarde qui ne dit pas ce qu'elle contient n'est pas restaurable."""
        (tmp_path / "backup.toml").write_text(
            '[backup]\ncreated_at = "2026-09-07T14:25:30+00:00"\n', encoding="utf-8"
        )

        with pytest.raises(ManifestError, match="does not say what it holds"):
            manifest_module.read_manifest(tmp_path)

    def test_un_ensemble_inconnu_est_refuse(self, tmp_path: Path) -> None:
        (tmp_path / "backup.toml").write_text(
            "[backup]\n"
            'created_at = "2026-09-07T14:25:30+00:00"\n'
            "[[backup.entries]]\n"
            'set = "everything"\n'
            'slot = "x"\n'
            'destination = "gamma/profiles"\n',
            encoding="utf-8",
        )

        with pytest.raises(ManifestError, match="unknown set"):
            manifest_module.read_manifest(tmp_path)

    def test_un_dossier_quelconque_nest_pas_une_sauvegarde(self, tmp_path: Path) -> None:
        directory = tmp_path / "mes-photos"
        directory.mkdir()

        with pytest.raises(ManifestError, match="carries no date"):
            manifest_module.read_manifest(directory)


class TestSauvegardesHistoriques:
    """Celles qu'`orchestrator.backup_mo2_profiles` a laissées sur les disques."""

    def test_le_nom_horodate_suffit_a_les_lire(self, tmp_path: Path) -> None:
        directory = tmp_path / "profiles-20260822-143400"
        (directory / "G.A.M.M.A").mkdir(parents=True)

        found = manifest_module.read_manifest(directory)

        assert found.legacy is True
        assert found.created_at == datetime(2026, 8, 22, 14, 34, 0, tzinfo=UTC)
        assert found.sets == (BackupSet.PROFILES,)
        assert found.entries[0].slot == manifest_module.LEGACY_SLOT
        assert found.entries[0].destination == "gamma/profiles"

    def test_elles_ne_sont_jamais_marquees_explicites(self, tmp_path: Path) -> None:
        """Elles étaient posées avant chaque update : ce sont bien des automatiques."""
        directory = tmp_path / "profiles-20260822-143400"
        directory.mkdir()

        assert manifest_module.read_manifest(directory).explicit is False

    def test_aucune_taille_nest_inventee(self, tmp_path: Path) -> None:
        directory = tmp_path / "profiles-20260822-143400"
        (directory / "G.A.M.M.A").mkdir(parents=True)
        (directory / "G.A.M.M.A" / "modlist.txt").write_text("+A\n", encoding="utf-8")

        assert manifest_module.read_manifest(directory).size_bytes == 0


class TestParseBackupName:
    def test_le_suffixe_de_desambiguisation_est_tolere(self) -> None:
        assert manifest_module.parse_backup_name("profiles-20260907-142530-2") == _WHEN

    @pytest.mark.parametrize(
        "name", ["backups", "profiles-", "profiles-not-a-date", "autre-20260907-142530"]
    )
    def test_un_nom_qui_ne_porte_pas_de_date_ne_ment_pas(self, name: str) -> None:
        assert manifest_module.parse_backup_name(name) is None
