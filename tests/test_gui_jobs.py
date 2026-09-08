"""Description des tâches longues de la GUI (`gui.jobs`) — sans GTK.

Ce que ces tests protègent : chaque bouton doit produire la bonne tâche, avec
la bonne annulabilité et les bons libellés d'étapes. Ces trois choix vivaient
au milieu du câblage des widgets, où rien ne pouvait les vérifier.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

import pytest

from stalker_gamma_linux import orchestrator, state
from stalker_gamma_linux.environment.performance import Settings
from stalker_gamma_linux.gui import jobs
from stalker_gamma_linux.gui.worker import WorkerEvent


@pytest.fixture
def target(tmp_path: Path) -> Path:
    return tmp_path / "GAMMA"


class TestInstallPhaseLabels:
    def test_le_raccourci_ajoute_une_etape(self) -> None:
        with_shortcut = jobs.install_phase_labels(shortcut=True)
        without = jobs.install_phase_labels(shortcut=False)

        assert len(with_shortcut) == len(state.STEPS)
        assert len(without) == len(state.STEPS) - 1
        assert without == with_shortcut[:-1]

    def test_les_libelles_viennent_de_state(self) -> None:
        """La GUI ne redérive pas la liste des étapes : elle la lit là où elle est décidée."""
        assert jobs.install_phase_labels(shortcut=True)[0] == state.STEP_LABELS[state.STEPS[0]]


class TestJobs:
    def test_installation_est_un_pipeline_annulable(self, target: Path) -> None:
        job = jobs.install(target, shortcut=False, proton_release=None)

        assert job.cancellable
        assert job.phase_labels == jobs.install_phase_labels(shortcut=False)

    def test_mise_a_jour_lit_ses_etapes_dans_orchestrator(self, target: Path) -> None:
        assert jobs.update(target).phase_labels == tuple(orchestrator.update_phase_labels())

    def test_reparer_et_verifier_ne_portent_pas_le_meme_titre(self, target: Path) -> None:
        """Deux gestes de prix très différents : l'écran doit dire lequel tourne."""
        assert jobs.verify(target, repair=True).title != jobs.verify(target, repair=False).title

    def test_sauvegarde_et_restauration_ne_sont_pas_annulables(self, target: Path) -> None:
        """Interrompre une restauration à mi-chemin laisserait un profil incomplet."""
        assert not jobs.backup(target).cancellable
        assert not jobs.restore("2026-09-07T12-00-00", target).cancellable

    def test_les_sessions_nont_pas_de_timeline(self, target: Path) -> None:
        """Jouer ou ouvrir MO2 n'a pas d'étapes numérotées : barre en pulsation."""
        assert jobs.play(target, performance=Settings(gamemode=False)).phase_labels is None
        assert jobs.mod_organizer(target).phase_labels is None

    def test_lancer_le_jeu_reste_annulable(self, target: Path) -> None:
        """MO2 qui ne rend jamais la main : tuer la fenêtre était la seule issue."""
        assert jobs.play(target, performance=Settings()).cancellable
        assert jobs.mod_organizer(target).cancellable


class TestJobRun:
    def test_le_run_appelle_bien_la_fonction_metier(
        self, target: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La GUI ne réimplémente rien : elle appelle la fonction de la CLI."""
        seen: dict[str, object] = {}

        def fake_install(root: Path, **kwargs: object) -> int:
            seen["root"] = root
            seen["shortcut"] = kwargs["shortcut"]
            seen["proton_release"] = kwargs["proton_release"]
            return 0

        monkeypatch.setattr(orchestrator, "run_install", fake_install)
        job = jobs.install(target, shortcut=True, proton_release="GE-Proton10-8")

        events: queue.Queue[WorkerEvent] = queue.Queue()
        assert job.run(events, threading.Event()) == 0
        assert seen == {"root": target, "shortcut": True, "proton_release": "GE-Proton10-8"}
