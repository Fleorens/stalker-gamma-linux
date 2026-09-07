"""Création, inventaire et rotation des sauvegardes (T17).

La rotation supprime réellement des dossiers : c'est un `rmtree` sur un chemin
dérivé de `--target`, donc le périmètre exact de T11. Les deux garanties
testées ici sont celles qui ne se négocient pas — une sauvegarde explicite
n'en fait jamais les frais, et rien ne sort de `<root>/backups/`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from stalker_gamma_linux.backups import create, listing, rotation
from stalker_gamma_linux.backups.errors import NothingToBackUpError
from stalker_gamma_linux.backups.paths import ALL_SETS, BackupSet
from stalker_gamma_linux.paths_safety import UnsafeWipeTargetError

_WHEN = datetime(2026, 9, 7, 14, 25, 30, tzinfo=UTC)


def _install(root: Path) -> Path:
    """Une install plausible : profils, parties, et un `overwrite/` vide (cas réel)."""
    profile = root / "gamma" / "profiles" / "G.A.M.M.A"
    profile.mkdir(parents=True)
    (profile / "modlist.txt").write_text("+MonMod\n-ModDesactive\n", encoding="utf-8")
    (profile / "settings.ini").write_text("[General]\nLocalSaves=false\n", encoding="utf-8")
    saves = root / "anomaly" / "appdata" / "savedgames"
    saves.mkdir(parents=True)
    (saves / "sauce.scop").write_bytes(b"\x00" * 2048)
    (root / "gamma" / "overwrite").mkdir(parents=True)
    return root


def _make(root: Path, *, explicit: bool, when: datetime) -> str:
    _, manifest = create.create_backup(
        root, sets=(BackupSet.PROFILES,), explicit=explicit, now=when
    )
    return manifest.identifier


class TestCreateBackup:
    def test_les_ensembles_demandes_sont_copies_a_leur_place(self, tmp_path: Path) -> None:
        _install(tmp_path)

        directory, manifest = create.create_backup(tmp_path, sets=ALL_SETS, now=_WHEN)

        assert directory.name == "profiles-20260907-142530"
        assert (directory / "profiles" / "G.A.M.M.A" / "modlist.txt").read_text() == (
            "+MonMod\n-ModDesactive\n"
        )
        assert (directory / "saves" / "anomaly-appdata" / "sauce.scop").is_file()
        assert manifest.sets == (BackupSet.PROFILES, BackupSet.SAVES)

    def test_un_dossier_vide_nest_pas_annonce_comme_sauvegarde(self, tmp_path: Path) -> None:
        """`overwrite/` est vide sur l'install de test : le dire copié serait faux."""
        _install(tmp_path)

        _directory, manifest = create.create_backup(tmp_path, sets=ALL_SETS, now=_WHEN)

        assert BackupSet.OVERWRITE not in manifest.sets

    def test_le_manifeste_dit_la_taille_et_la_version(self, tmp_path: Path) -> None:
        _install(tmp_path)
        version = tmp_path / "gamma" / ".Grok's Modpack Installer"
        version.mkdir(parents=True)
        (version / "G.A.M.M.A_definition_version.txt").write_text("920\n", encoding="utf-8")

        _directory, manifest = create.create_backup(tmp_path, now=_WHEN)

        assert manifest.gamma_version == "920"
        assert manifest.file_count == 3
        assert manifest.size_bytes > 2048

    def test_sans_rien_a_copier_on_le_dit(self, tmp_path: Path) -> None:
        with pytest.raises(NothingToBackUpError):
            create.create_backup(tmp_path, now=_WHEN)

    def test_deux_sauvegardes_dans_la_meme_seconde_ne_se_marchent_pas_dessus(
        self, tmp_path: Path
    ) -> None:
        _install(tmp_path)

        first, _ = create.create_backup(tmp_path, now=_WHEN)
        second, _ = create.create_backup(tmp_path, now=_WHEN)

        assert first != second
        assert second.name == "profiles-20260907-142530-2"

    def test_une_copie_qui_echoue_ne_laisse_pas_de_sauvegarde_tronquee(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Une sauvegarde à moitié écrite est pire que pas de sauvegarde du tout."""
        _install(tmp_path)

        def explode(*_args: object, **_kwargs: object) -> None:
            raise OSError("No space left on device")

        monkeypatch.setattr(create.shutil, "copytree", explode)

        with pytest.raises(create.BackupWriteError):
            create.create_backup(tmp_path, now=_WHEN)
        assert list((tmp_path / "backups").iterdir()) == []


class TestListing:
    def test_les_sauvegardes_sortent_de_la_plus_recente_a_la_plus_ancienne(
        self, tmp_path: Path
    ) -> None:
        _install(tmp_path)
        old = _make(tmp_path, explicit=False, when=_WHEN - timedelta(days=2))
        recent = _make(tmp_path, explicit=False, when=_WHEN)

        found = listing.list_backups(tmp_path)

        assert [backup.identifier for backup in found.backups] == [recent, old]

    def test_un_dossier_illisible_est_signale_pas_masque(self, tmp_path: Path) -> None:
        _install(tmp_path)
        _make(tmp_path, explicit=False, when=_WHEN)
        (tmp_path / "backups" / "un-dossier-a-moi").mkdir()

        found = listing.list_backups(tmp_path)

        assert len(found.backups) == 1
        assert [path.name for path, _reason in found.unreadable] == ["un-dossier-a-moi"]

    def test_linstantane_amont_nest_pas_pris_pour_une_sauvegarde(self, tmp_path: Path) -> None:
        _install(tmp_path)
        _make(tmp_path, explicit=False, when=_WHEN)
        (tmp_path / "backups" / "upstream-modlist.txt").write_text("+A\n", encoding="utf-8")

        found = listing.list_backups(tmp_path)

        assert len(found.backups) == 1
        assert found.unreadable == ()

    def test_sans_dossier_backups_linventaire_est_vide(self, tmp_path: Path) -> None:
        assert listing.list_backups(tmp_path).backups == ()

    def test_le_rendu_texte_annonce_ce_quil_faut_taper(self, tmp_path: Path) -> None:
        _install(tmp_path)
        identifier = _make(tmp_path, explicit=True, when=_WHEN)

        rendered = listing.format_listing(tmp_path, listing.list_backups(tmp_path))

        assert identifier in rendered
        assert "stalker-gamma-linux restore" in rendered

    def test_un_identifiant_qui_sort_du_dossier_est_introuvable(self, tmp_path: Path) -> None:
        _install(tmp_path)
        _make(tmp_path, explicit=False, when=_WHEN)

        with pytest.raises(listing.BackupNotFoundError):
            listing.find_backup(tmp_path, "../../etc")


class TestRotation:
    def test_au_dela_du_plafond_la_plus_ancienne_part(self, tmp_path: Path) -> None:
        _install(tmp_path)
        identifiers = [
            _make(tmp_path, explicit=False, when=_WHEN + timedelta(minutes=index))
            for index in range(7)
        ]

        result = rotation.rotate(tmp_path, keep=5)

        assert result.removed == (identifiers[0], identifiers[1])
        assert sorted(path.name for path in (tmp_path / "backups").iterdir()) == sorted(
            identifiers[2:]
        )

    def test_une_sauvegarde_explicite_nentre_jamais_dans_la_rotation(self, tmp_path: Path) -> None:
        _install(tmp_path)
        kept = _make(tmp_path, explicit=True, when=_WHEN)
        automatic = [
            _make(tmp_path, explicit=False, when=_WHEN + timedelta(minutes=index))
            for index in range(1, 8)
        ]

        result = rotation.rotate(tmp_path, keep=2)

        assert kept not in result.removed
        assert (tmp_path / "backups" / kept).is_dir()
        assert set(result.removed) == set(automatic[:5])

    def test_les_sauvegardes_davant_le_manifeste_comptent_comme_automatiques(
        self, tmp_path: Path
    ) -> None:
        """Ce sont elles qui se sont accumulées : les épargner raterait la cible."""
        _install(tmp_path)
        for day in range(1, 5):
            legacy = tmp_path / "backups" / f"profiles-2026080{day}-120000"
            (legacy / "G.A.M.M.A").mkdir(parents=True)
            (legacy / "G.A.M.M.A" / "modlist.txt").write_text("+A\n", encoding="utf-8")

        result = rotation.rotate(tmp_path, keep=2)

        assert result.removed == ("profiles-20260801-120000", "profiles-20260802-120000")

    def test_sous_le_plafond_rien_ne_bouge(self, tmp_path: Path) -> None:
        _install(tmp_path)
        _make(tmp_path, explicit=False, when=_WHEN)

        assert rotation.rotate(tmp_path, keep=5).is_empty

    def test_un_lien_symbolique_dans_backups_ne_fait_pas_sortir_la_suppression(
        self, tmp_path: Path
    ) -> None:
        """Même famille de risque que T11 : `paths_safety` est le seul garde-fou."""
        _install(tmp_path)
        for index in range(3):
            _make(tmp_path, explicit=False, when=_WHEN + timedelta(minutes=index + 1))
        elsewhere = tmp_path / "precieux"
        elsewhere.mkdir()
        (elsewhere / "these.txt").write_text("ne pas perdre", encoding="utf-8")
        (tmp_path / "backups" / "profiles-20260101-000000").symlink_to(elsewhere)

        with pytest.raises(UnsafeWipeTargetError):
            rotation.rotate(tmp_path, keep=1)
        assert (elsewhere / "these.txt").is_file()
