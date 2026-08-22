"""Désinstallation (`uninstall`) — et surtout ce qu'elle ne doit **pas** effacer."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from stalker_gamma_linux import logging_setup, state, uninstall
from stalker_gamma_linux.desktop.paths import DesktopPaths
from stalker_gamma_linux.prefix import session


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un faux HOME complet : XDG redirigé, rien ne touche la vraie machine."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / ".local" / "state"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _populate(home: Path) -> tuple[DesktopPaths, Path]:
    """Recrée ce qu'`install.sh` + l'application posent sur un poste réel."""
    desktop = DesktopPaths.default()
    desktop.applications_dir.mkdir(parents=True, exist_ok=True)
    desktop.icon_dir.mkdir(parents=True, exist_ok=True)
    desktop.desktop_file.write_text("[Desktop Entry]\n")
    (desktop.applications_dir / "stalker-gamma-linux-gui.desktop").write_text("[Desktop Entry]\n")
    desktop.icon_file.write_bytes(b"png")

    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    (local_bin / "stalker-gamma-linux").write_text("#!/bin/sh\n")
    (local_bin / "stalker-gamma-linux-gui").write_text("#!/bin/sh\n")
    (local_bin / "umu-run").write_text("#!/bin/sh\n")

    state.config_dir().mkdir(parents=True, exist_ok=True)
    (state.config_dir() / "install-state.toml").write_text("[installs]\n")
    logging_setup.state_dir().mkdir(parents=True, exist_ok=True)
    (logging_setup.state_dir() / "app.log").write_text("log\n")

    target = home / "Games" / "stalker-gamma"
    (target / "anomaly").mkdir(parents=True, exist_ok=True)
    (target / "anomaly" / "AnomalyLauncher.exe").write_text("jeu")
    return desktop, target


class TestBuildPlan:
    def test_ne_liste_que_ce_qui_existe(self, home: Path) -> None:
        plan = uninstall.build_plan(home / "Games" / "stalker-gamma")

        assert plan.is_empty  # rien n'a été posé

    def test_liste_lintegration_posee(self, home: Path) -> None:
        _, target = _populate(home)

        plan = uninstall.build_plan(target)

        labels = " ".join(removal.label for removal in plan.present)
        assert "desktop entry" in labels
        assert "logs" in labels
        assert not any(removal.is_game_data for removal in plan.present)

    def test_les_donnees_de_jeu_exigent_le_drapeau(self, home: Path) -> None:
        _, target = _populate(home)

        sans = uninstall.build_plan(target)
        avec = uninstall.build_plan(target, game_data=True)

        assert target not in [removal.path for removal in sans.present]
        assert target in [removal.path for removal in avec.present]

    def test_construire_un_plan_neffance_rien(self, home: Path) -> None:
        desktop, target = _populate(home)

        uninstall.build_plan(target, game_data=True)

        assert desktop.desktop_file.exists()
        assert (target / "anomaly" / "AnomalyLauncher.exe").exists()


class TestApplyPlan:
    def test_retire_lintegration_et_garde_le_jeu(self, home: Path) -> None:
        desktop, target = _populate(home)

        removed = uninstall.apply_plan(uninstall.build_plan(target))

        assert removed
        assert not desktop.desktop_file.exists()
        assert not state.config_dir().exists()
        assert not logging_setup.state_dir().exists()
        # Le point qui compte : 146 Gio de jeu ne partent jamais par défaut.
        assert (target / "anomaly" / "AnomalyLauncher.exe").exists()

    def test_umu_run_est_epargne(self, home: Path) -> None:
        """Il sert à d'autres jeux et n'appartient pas à ce projet."""
        _populate(home)

        uninstall.apply_plan(uninstall.build_plan(home / "Games" / "stalker-gamma"))

        assert (home / ".local" / "bin" / "umu-run").exists()

    def test_avec_game_data_le_jeu_part(self, home: Path) -> None:
        _, target = _populate(home)

        uninstall.apply_plan(uninstall.build_plan(target, game_data=True))

        assert not target.exists()

    def test_cible_dangereuse_leve_meme_appele_directement(self, home: Path) -> None:
        """`apply_plan` valide aussi — un appelant (GUI, script) ne peut pas contourner T11.

        Les éléments d'intégration sont listés avant les données de jeu dans le
        plan (voir `build_plan`) : seule la cible de jeu elle-même est refusée
        ici, et le refus doit interrompre au lieu d'être avalé.
        """
        with pytest.raises(uninstall.UnsafeWipeTargetError):
            uninstall.apply_plan(uninstall.build_plan(home, game_data=True))

        assert home.exists()

    def test_idempotent(self, home: Path) -> None:
        _, target = _populate(home)
        uninstall.apply_plan(uninstall.build_plan(target))

        assert uninstall.apply_plan(uninstall.build_plan(target)) == ()

    def test_un_lien_casse_est_quand_meme_retire(self, home: Path) -> None:
        """Cas réel : `install.sh --uninstall` a supprimé le venv avant nous."""
        _populate(home)
        link = home / ".local" / "bin" / "stalker-gamma-linux"
        link.unlink()
        link.symlink_to(home / "disparu" / "stalker-gamma-linux")

        uninstall.apply_plan(uninstall.build_plan(home / "Games" / "stalker-gamma"))

        assert not link.is_symlink()


class TestRunUninstall:
    def test_dry_run_neffance_rien(self, home: Path) -> None:
        desktop, target = _populate(home)

        assert uninstall.run_uninstall(target, dry_run=True) == 0
        assert desktop.desktop_file.exists()

    def test_sortie_zero_quand_il_ny_a_rien(self, home: Path) -> None:
        assert uninstall.run_uninstall(home / "Games" / "stalker-gamma") == 0

    def test_nominal(self, home: Path) -> None:
        desktop, target = _populate(home)

        assert uninstall.run_uninstall(target) == 0
        assert not desktop.desktop_file.exists()
        assert (target / "anomaly" / "AnomalyLauncher.exe").exists()


class TestRunUninstallGameData:
    """`--game-data --target ~` et consorts (T11) : voir aussi test_paths_safety.py."""

    def test_cible_dangereuse_echoue_et_ne_supprime_rien(self, home: Path) -> None:
        """`--target ~` : `home` ici est exactement `Path.home()` (voir la fixture)."""
        desktop, target = _populate(home)

        assert uninstall.run_uninstall(home, game_data=True) == 1
        assert desktop.desktop_file.exists()
        assert (target / "anomaly" / "AnomalyLauncher.exe").exists()

    def test_dry_run_signale_aussi_une_cible_dangereuse(self, home: Path) -> None:
        assert uninstall.run_uninstall(home, game_data=True, dry_run=True) == 1

    def test_installation_reelle_fonctionne_avec_confirmation(
        self, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        desktop, target = _populate(home)
        monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

        assert uninstall.run_uninstall(target, game_data=True) == 0
        assert not target.exists()
        assert not desktop.desktop_file.exists()

    def test_confirmation_refusee_ne_supprime_rien(
        self, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        desktop, target = _populate(home)
        monkeypatch.setattr("builtins.input", lambda _prompt: "no")

        assert uninstall.run_uninstall(target, game_data=True) == 1
        assert target.exists()
        assert desktop.desktop_file.exists()

    def test_yes_saute_la_confirmation(self, home: Path) -> None:
        _, target = _populate(home)

        assert uninstall.run_uninstall(target, game_data=True, assume_yes=True) == 0
        assert not target.exists()

    def test_cible_de_jeu_deja_absente_nettoie_quand_meme_lintegration(self, home: Path) -> None:
        """Le jeu a déjà été effacé à la main : rien à valider, le reste de l'intégration part."""
        desktop, target = _populate(home)
        shutil.rmtree(target)

        assert uninstall.run_uninstall(target, game_data=True) == 0
        assert not desktop.desktop_file.exists()

    def test_refuse_quand_mo2_tourne_encore(
        self, home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        desktop, target = _populate(home)
        monkeypatch.setattr(
            session,
            "prefix_in_use",
            lambda paths: session.ProcessHold(pid=321, name="Mod Organizer 2", what_to_close="it"),
        )

        assert uninstall.run_uninstall(target, game_data=True, assume_yes=True) == 1

        assert target.exists()
        assert desktop.desktop_file.exists()
        output = capsys.readouterr().out
        assert "321" in output
        assert "Mod Organizer 2" in output

    def test_force_passe_outre_mo2_en_cours(
        self, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, target = _populate(home)
        monkeypatch.setattr(
            session,
            "prefix_in_use",
            lambda paths: session.ProcessHold(pid=321, name="Mod Organizer 2", what_to_close="it"),
        )

        assert uninstall.run_uninstall(target, game_data=True, assume_yes=True, force=True) == 0
        assert not target.exists()

    def test_le_garde_ne_sapplique_pas_sans_game_data(self, home: Path) -> None:
        """Sans `--game-data`, le préfixe n'est jamais touché — pas la peine de bloquer."""
        desktop, target = _populate(home)

        assert uninstall.run_uninstall(target) == 0
        assert not desktop.desktop_file.exists()
        assert target.exists()
