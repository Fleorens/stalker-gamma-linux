"""Lancement du binaire `gamma-launcher` en sous-processus.

Isolé dans ce module pour que les tests puissent monkeypatcher `subprocess.Popen`
sans jamais lancer un vrai processus. On ne réutilise pas `environment.system.run` :
il impose un timeout de 10s, incompatible avec un `full-install` qui peut durer
des heures.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Sequence

from stalker_gamma_linux.engine.errors import (
    EngineCancelledError,
    EngineExecutionError,
    EngineNotFoundError,
)
from stalker_gamma_linux.environment import system

ProgressCallback = Callable[[str], None]

_ENGINE_BINARY = "gamma-launcher"
_OUTPUT_TAIL_LINES = 20
_TERMINATE_GRACE_SECONDS = 5


def _noop(_: str) -> None:
    return None


def _watch_cancellation(process: subprocess.Popen[str], cancel_event: threading.Event) -> None:
    """Tue `process` dès que `cancel_event` est levé ; s'arrête seul si le process finit avant.

    Tourne dans un thread dédié : la boucle `for line in process.stdout` du
    thread appelant reste inchangée (elle se termine naturellement quand la
    sortie du process tué se ferme), donc aucun appelant existant (CLI, qui ne
    passe jamais `cancel_event`) n'est affecté.
    """
    while not cancel_event.wait(timeout=0.2):
        if process.poll() is not None:
            return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()


def _engine_environment() -> dict[str, str]:
    env = dict(os.environ)
    # Neutralise le config.ini persistant de gamma-launcher (voir docs/ARCHITECTURE.md) :
    # nos chemins explicites doivent rester la seule source de vérité.
    env["GAMMA_LAUNCHER_NO_CONFIG"] = "1"
    return env


def run(
    subcommand: str,
    args: Sequence[str],
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Lance `gamma-launcher <subcommand> <args>` et suit sa progression ligne à ligne.

    Chaque ligne de stdout est transmise à `on_progress`. Lève `EngineNotFoundError`
    si le binaire est absent du PATH, `EngineExecutionError` si le code de retour
    est non nul (les dernières lignes de sortie sont jointes au message).
    `cancel_event` (optionnel, GUI) : s'il est levé pendant l'exécution, le
    process est terminé proprement (`terminate`, puis `kill` après
    `_TERMINATE_GRACE_SECONDS`) et `EngineCancelledError` est levée.
    """
    binary = system.which(_ENGINE_BINARY)
    if binary is None:
        raise EngineNotFoundError

    progress = on_progress or _noop
    tail: deque[str] = deque(maxlen=_OUTPUT_TAIL_LINES)

    process = subprocess.Popen(  # noqa: S603
        [binary, subcommand, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        # Décodage tolérant : un octet non-UTF-8 dans la sortie ne doit jamais
        # crasher le lecteur (constaté en réel avec Wine côté prefix/).
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=_engine_environment(),
    )

    watcher: threading.Thread | None = None
    if cancel_event is not None:
        watcher = threading.Thread(
            target=_watch_cancellation, args=(process, cancel_event), daemon=True
        )
        watcher.start()

    if process.stdout is not None:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            tail.append(line)
            progress(line)

    returncode = process.wait()
    if watcher is not None:
        watcher.join(timeout=_TERMINATE_GRACE_SECONDS)
    if cancel_event is not None and cancel_event.is_set():
        raise EngineCancelledError(subcommand)
    if returncode != 0:
        raise EngineExecutionError(subcommand, returncode, "\n".join(tail))
