"""Tâches longues de la GUI, décrites hors de GTK.

Chaque fonction rend un `Job` : un titre, la fonction à exécuter dans le thread
de `gui.worker.BackgroundTask`, l'annulabilité, et les libellés d'étapes quand
la tâche est un pipeline. La fenêtre principale se contente de pousser le `Job`
sur la vue progression.

Rien n'est décidé ici non plus : chaque `run` appelle exactement la fonction
qu'appelle la commande CLI correspondante (`orchestrator.run_install`,
`integrity.run_verify`, `backups.run_backup`, `mo2.session.run_play`…). Le seul
intérêt du module est de rendre ces sept branchements lisibles et testables
sans afficher une fenêtre — `main_window.py` les portait au milieu du câblage
des widgets, ce qui faisait de lui le plus gros fichier de la GUI.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux import backups, integrity, orchestrator
from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.environment.performance import Settings
from stalker_gamma_linux.gui.worker import QueueReporter, ReporterEvent, WorkerEvent
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2 import session as mo2_session

JobFunc = Callable[["queue.Queue[WorkerEvent]", threading.Event], int]


@dataclass(frozen=True, slots=True)
class Job:
    """Une tâche prête à pousser sur la vue progression."""

    title: str
    run: JobFunc
    cancellable: bool
    # `None` = pas un pipeline : barre en pulsation, console seule.
    phase_labels: tuple[str, ...] | None = None


def install_phase_labels(*, shortcut: bool, steam: bool) -> tuple[str, ...]:
    """Libellés du pipeline `run_install`, alignés sur sa numérotation n/total.

    La liste vient de `state.planned_steps`, celle-là même que l'orchestrateur
    utilise pour numéroter : un `STEPS[:-1]` recopié ici décrochait dès qu'une
    seconde étape optionnelle est apparue (T19).
    """
    steps = state_module.planned_steps(shortcut=shortcut, steam=steam)
    return tuple(state_module.STEP_LABELS[step] for step in steps)


def install(target: Path, *, shortcut: bool, steam: bool, proton_release: str | None) -> Job:
    def run(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        return orchestrator.run_install(
            target,
            shortcut=shortcut,
            steam=steam,
            reporter=QueueReporter(events),
            cancel_event=cancel_event,
            proton_release=proton_release,
        )

    return Job(
        title=_("Installation"),
        run=run,
        cancellable=True,
        phase_labels=install_phase_labels(shortcut=shortcut, steam=steam),
    )


def update(target: Path) -> Job:
    def run(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        return orchestrator.run_update(
            target, reporter=QueueReporter(events), cancel_event=cancel_event
        )

    # Les libellés viennent d'`orchestrator` : la GUI ne redérive pas la liste
    # des étapes, elle la lit là où la numérotation est décidée.
    return Job(
        title=_("Update"),
        run=run,
        cancellable=True,
        phase_labels=tuple(orchestrator.update_phase_labels()),
    )


def verify(target: Path, *, repair: bool) -> Job:
    def run(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        return integrity.run_verify(
            target,
            repair_damaged=repair,
            reporter=QueueReporter(events),
            cancel_event=cancel_event,
        )

    return Job(
        title=_("Repairing the mods") if repair else _("Checking the mods"),
        run=run,
        cancellable=True,
        phase_labels=tuple(integrity.verify_phase_labels(repair_damaged=repair)),
    )


def backup(target: Path) -> Job:
    def run(events: queue.Queue[WorkerEvent], _cancel: threading.Event) -> int:
        return backups.run_backup(target, reporter=QueueReporter(events))

    return Job(title=_("Backing up"), run=run, cancellable=False)


def restore(identifier: str, target: Path) -> Job:
    def run(events: queue.Queue[WorkerEvent], _cancel: threading.Event) -> int:
        return backups.run_restore(identifier, target, reporter=QueueReporter(events))

    return Job(title=_("Restoring"), run=run, cancellable=False)


def play(target: Path, *, performance: Settings) -> Job:
    def run(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        return mo2_session.run_play(
            target,
            performance=performance,
            on_progress=lambda message: events.put(ReporterEvent("progress", message)),
            cancel_event=cancel_event,
        )

    # Annulable : un premier lancement télécharge le runtime umu et compile des
    # shaders — ça peut durer très longtemps, et si MO2 ne rend jamais la main,
    # tuer la fenêtre était la seule issue.
    return Job(title=_("Launching the game"), run=run, cancellable=True)


def mod_organizer(target: Path) -> Job:
    def run(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        return mo2_session.run_mo2(
            target,
            on_progress=lambda message: events.put(ReporterEvent("progress", message)),
            cancel_event=cancel_event,
        )

    return Job(title=_("Opening Mod Organizer 2"), run=run, cancellable=True)
