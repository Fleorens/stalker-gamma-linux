"""Restauration : `restore <id>`, son plan, et le filet qu'elle pose avant d'écrire.

Trois promesses vérifiées ici : la destination vient du manifeste, l'état
courant est sauvegardé **avant** d'être remplacé, et rien n'est écrit pendant
que MO2 ou le jeu tournent (`prefix.session`, T13).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from stalker_gamma_linux.backups import create, listing, restore, session
from stalker_gamma_linux.backups.errors import ManifestError
from stalker_gamma_linux.backups.paths import ALL_SETS, BackupSet
from stalker_gamma_linux.prefix import session as prefix_session
from tests.conftest import RecordingReporter

_WHEN = datetime(2026, 9, 7, 14, 25, 30, tzinfo=UTC)


def _install(root: Path, *, modlist: str = "+MonMod\n-ModDesactive\n") -> Path:
    profile = root / "gamma" / "profiles" / "G.A.M.M.A"
    profile.mkdir(parents=True)
    (profile / "modlist.txt").write_text(modlist, encoding="utf-8")
    saves = root / "anomaly" / "appdata" / "savedgames"
    saves.mkdir(parents=True)
    (saves / "sauce.scop").write_bytes(b"partie")
    return root


@pytest.fixture(autouse=True)
def _prefix_is_free(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le préfixe est libre par défaut : les tests qui veulent l'inverse le disent."""
    monkeypatch.setattr(prefix_session, "prefix_in_use", lambda _paths: None)


class TestPlan:
    def test_le_plan_vise_la_destination_du_manifeste(self, tmp_path: Path) -> None:
        _install(tmp_path)
        create.create_backup(tmp_path, sets=ALL_SETS, now=_WHEN)
        backup = listing.find_backup(tmp_path, "profiles-20260907-142530")

        plan = restore.build_restore_plan(tmp_path, backup)

        assert [action.destination for action in plan.actions] == [
            tmp_path / "gamma" / "profiles",
            tmp_path / "anomaly" / "appdata" / "savedgames",
        ]
        assert all(action.replaces_existing for action in plan.actions)

    def test_une_sauvegarde_amputee_de_son_contenu_est_refusee(self, tmp_path: Path) -> None:
        _install(tmp_path)
        directory, _manifest = create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)
        (directory / "profiles").rename(directory / "ailleurs")
        backup = listing.find_backup(tmp_path, directory.name)

        with pytest.raises(ManifestError, match="missing"):
            restore.build_restore_plan(tmp_path, backup)


class TestApply:
    def test_le_contenu_sauvegarde_reprend_sa_place(self, tmp_path: Path) -> None:
        _install(tmp_path)
        create.create_backup(tmp_path, sets=ALL_SETS, now=_WHEN)
        modlist = tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt"
        modlist.write_text("+ListeAmont\n", encoding="utf-8")
        (tmp_path / "anomaly" / "appdata" / "savedgames" / "sauce.scop").unlink()

        backup = listing.find_backup(tmp_path, "profiles-20260907-142530")
        restore.apply_restore_plan(restore.build_restore_plan(tmp_path, backup))

        assert modlist.read_text() == "+MonMod\n-ModDesactive\n"
        assert (tmp_path / "anomaly" / "appdata" / "savedgames" / "sauce.scop").is_file()

    def test_ce_que_lancien_dossier_contenait_en_trop_disparait(self, tmp_path: Path) -> None:
        """Remplacement, pas fusion : sinon un mod retiré resterait listé pour toujours."""
        _install(tmp_path)
        create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)
        (tmp_path / "gamma" / "profiles" / "Nouveau").mkdir()

        backup = listing.find_backup(tmp_path, "profiles-20260907-142530")
        restore.apply_restore_plan(restore.build_restore_plan(tmp_path, backup))

        assert not (tmp_path / "gamma" / "profiles" / "Nouveau").exists()

    def test_aucun_residu_dechange_ne_reste_derriere(self, tmp_path: Path) -> None:
        _install(tmp_path)
        create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)

        backup = listing.find_backup(tmp_path, "profiles-20260907-142530")
        restore.apply_restore_plan(restore.build_restore_plan(tmp_path, backup))

        leftovers = [
            path.name
            for path in (tmp_path / "gamma").iterdir()
            if path.name.startswith("profiles.")
        ]
        assert leftovers == []

    def test_une_destination_absente_est_creee(self, tmp_path: Path) -> None:
        _install(tmp_path)
        create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)
        import shutil

        shutil.rmtree(tmp_path / "gamma" / "profiles")

        backup = listing.find_backup(tmp_path, "profiles-20260907-142530")
        restore.apply_restore_plan(restore.build_restore_plan(tmp_path, backup))

        assert (tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt").is_file()

    def test_une_sauvegarde_historique_se_restaure_aussi(self, tmp_path: Path) -> None:
        """Celles déjà sur les disques des utilisateurs : le nom seul suffit."""
        _install(tmp_path, modlist="+ListeAmont\n")
        legacy = tmp_path / "backups" / "profiles-20260822-143400" / "G.A.M.M.A"
        legacy.mkdir(parents=True)
        (legacy / "modlist.txt").write_text("+MaVieilleListe\n", encoding="utf-8")

        backup = listing.find_backup(tmp_path, "profiles-20260822-143400")
        restore.apply_restore_plan(restore.build_restore_plan(tmp_path, backup))

        modlist = tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt"
        assert modlist.read_text() == "+MaVieilleListe\n"


class TestRunRestore:
    def test_lidentifiant_inconnu_echoue_proprement(self, tmp_path: Path) -> None:
        reporter = RecordingReporter()

        assert session.run_restore("profiles-19700101-000000", tmp_path, reporter=reporter) == 1
        assert "No backup named" in reporter.text

    def test_le_dry_run_necrit_rien(self, tmp_path: Path) -> None:
        _install(tmp_path)
        create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)
        modlist = tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt"
        modlist.write_text("+ListeAmont\n", encoding="utf-8")
        reporter = RecordingReporter()

        code = session.run_restore(
            "profiles-20260907-142530", tmp_path, dry_run=True, reporter=reporter
        )

        assert code == 0
        assert modlist.read_text() == "+ListeAmont\n"
        assert "would be replaced" in reporter.text
        assert len(list((tmp_path / "backups").iterdir())) == 1

    def test_letat_courant_est_sauvegarde_avant_detre_remplace(self, tmp_path: Path) -> None:
        """Une restauration ratée ne doit pas être un aller simple."""
        _install(tmp_path)
        create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)
        modlist = tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt"
        modlist.write_text("+CeQuiVaEtreEcrase\n", encoding="utf-8")
        reporter = RecordingReporter()

        code = session.run_restore("profiles-20260907-142530", tmp_path, reporter=reporter)

        assert code == 0
        assert modlist.read_text() == "+MonMod\n-ModDesactive\n"
        safety = [
            backup
            for backup in listing.list_backups(tmp_path).backups
            if backup.identifier != "profiles-20260907-142530"
        ]
        assert len(safety) == 1
        rescued = safety[0].directory / "profiles" / "G.A.M.M.A" / "modlist.txt"
        assert rescued.read_text() == "+CeQuiVaEtreEcrase\n"

    def test_mo2_ouvert_bloque_la_restauration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install(tmp_path)
        create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)
        modlist = tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt"
        modlist.write_text("+ListeAmont\n", encoding="utf-8")
        monkeypatch.setattr(
            prefix_session,
            "prefix_in_use",
            lambda _paths: prefix_session.ProcessHold(
                pid=42, name="Mod Organizer 2", what_to_close="it"
            ),
        )
        reporter = RecordingReporter()

        code = session.run_restore("profiles-20260907-142530", tmp_path, reporter=reporter)

        assert code == 1
        assert modlist.read_text() == "+ListeAmont\n"

    def test_force_passe_outre(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(tmp_path)
        create.create_backup(tmp_path, sets=(BackupSet.PROFILES,), now=_WHEN)
        modlist = tmp_path / "gamma" / "profiles" / "G.A.M.M.A" / "modlist.txt"
        modlist.write_text("+ListeAmont\n", encoding="utf-8")
        monkeypatch.setattr(
            prefix_session,
            "prefix_in_use",
            lambda _paths: prefix_session.ProcessHold(
                pid=42, name="Mod Organizer 2", what_to_close="it"
            ),
        )

        code = session.run_restore(
            "profiles-20260907-142530", tmp_path, force=True, reporter=RecordingReporter()
        )

        assert code == 0
        assert modlist.read_text() == "+MonMod\n-ModDesactive\n"


class TestRunBackup:
    def test_une_sauvegarde_demandee_est_explicite(self, tmp_path: Path) -> None:
        _install(tmp_path)

        assert session.run_backup(tmp_path, reporter=RecordingReporter()) == 0
        assert listing.list_backups(tmp_path).explicit != ()
        assert listing.list_backups(tmp_path).automatic == ()

    def test_sans_rien_a_sauvegarder_la_commande_echoue_en_le_disant(self, tmp_path: Path) -> None:
        reporter = RecordingReporter()

        assert session.run_backup(tmp_path, reporter=reporter) == 1
        assert "Nothing to back up" in reporter.text

    def test_la_liste_ninvente_rien_quand_il_ny_a_rien(self, tmp_path: Path) -> None:
        reporter = RecordingReporter()

        assert session.run_backup(tmp_path, list_only=True, reporter=reporter) == 0
        assert "No backup" in reporter.text

    def test_la_sauvegarde_avant_update_couvre_profils_et_parties(self, tmp_path: Path) -> None:
        """Le moteur `purge-shader-cache` fait un rmtree dans `appdata/`, à côté des parties."""
        _install(tmp_path)

        manifest = session.protect_before_update(tmp_path, reporter=RecordingReporter())

        assert manifest is not None
        assert manifest.sets == (BackupSet.PROFILES, BackupSet.SAVES)
        assert manifest.explicit is False

    def test_sans_installation_la_sauvegarde_avant_update_ne_bloque_pas(
        self, tmp_path: Path
    ) -> None:
        assert session.protect_before_update(tmp_path, reporter=RecordingReporter()) is None
