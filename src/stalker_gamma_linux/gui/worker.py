"""Pont thread ↔ GUI pour les opérations longues (install/update/mo2/play).

Indépendant de GTK : produit des événements sur une `queue.Queue` thread-safe
que l'appelant GTK draine depuis le fil principal (`GLib.timeout_add`), et
lève un `threading.Event` de son côté pour demander une annulation propre.
Aucune logique métier ici — seulement le pont ; les opérations elles-mêmes
(install/update/play/mo2) restent dans `orchestrator`/`mo2.session`, appelées
par le code GTK (`app.py`) via `output.Reporter`/`on_progress` déjà exposés
par ces modules.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

from stalker_gamma_linux.logging_setup import LOGGER_NAME

_logger = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True, slots=True)
class ReporterEvent:
    """Un appel `Reporter.*` capturé, prêt à être rendu par la vue progression."""

    kind: str  # "header" | "step" | "skip" | "progress" | "success" | "warn" | "error"
    message: str
    index: str | None = None
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """L'opération est allée à son terme (avec succès ou échec porté par `exit_code`)."""

    exit_code: int


@dataclass(frozen=True, slots=True)
class FailedEvent:
    """L'opération a levé une exception inattendue (bug, pas un `EngineError` géré)."""

    error: Exception


WorkerEvent = ReporterEvent | DoneEvent | FailedEvent


class QueueReporter:
    """`output.Reporter` qui pousse chaque événement sur une queue au lieu d'imprimer.

    Utilisé par la vue progression de la GUI pour piloter `orchestrator.run_install`/
    `run_update` sans dupliquer leur logique — seul le rendu diffère de la CLI.
    Chaque événement est aussi doublé vers le journal applicatif (mêmes niveaux
    que `output.py`) : le fichier sous `~/.local/state/` reste la trace complète
    même quand tout passe par la GUI.
    """

    def __init__(self, events: queue.Queue[WorkerEvent]) -> None:
        self._events = events

    def header(self, message: str) -> None:
        _logger.info(message)
        self._events.put(ReporterEvent("header", message))

    def step(self, index: str, message: str) -> None:
        _logger.info("étape %s : %s", index, message)
        self._events.put(ReporterEvent("step", message, index=index))

    def skip(self, index: str, message: str) -> None:
        _logger.debug("étape sautée %s : %s", index, message)
        self._events.put(ReporterEvent("skip", message, index=index))

    def progress(self, message: str) -> None:
        _logger.debug(message)
        self._events.put(ReporterEvent("progress", message))

    def success(self, message: str) -> None:
        _logger.info(message)
        self._events.put(ReporterEvent("success", message))

    def warn(self, message: str) -> None:
        _logger.warning(message)
        self._events.put(ReporterEvent("warn", message))

    def error(self, message: str, *, hint: str | None = None) -> None:
        _logger.error(message)
        if hint is not None:
            _logger.info("suggestion : %s", hint)
        self._events.put(ReporterEvent("error", message, hint=hint))


class BackgroundTask:
    """Lance `func(events, cancel_event) -> exit_code` dans un thread démon.

    `func` est responsable de brancher `events`/`cancel_event` sur l'appel
    `orchestrator`/`mo2.session` de son choix (voir `QueueReporter` pour le
    cas `Reporter`, ou un simple `lambda msg: events.put(...)` pour
    `on_progress`). Ce découplage évite à `BackgroundTask` de connaître quoi
    que ce soit sur l'opération en cours.
    """

    def __init__(self, func: Callable[[queue.Queue[WorkerEvent], threading.Event], int]) -> None:
        self._func = func
        self.events: queue.Queue[WorkerEvent] = queue.Queue()
        self.cancel_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self.cancel_event.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        try:
            exit_code = self._func(self.events, self.cancel_event)
        except Exception as error:  # noqa: BLE001 - remonté tel quel à la GUI, pas avalé
            self.events.put(FailedEvent(error))
            return
        self.events.put(DoneEvent(exit_code))
