"""Lancement du binaire `gamma-launcher` en sous-processus.

Isolé dans ce module pour que les tests puissent monkeypatcher `subprocess.Popen`
sans jamais lancer un vrai processus. On ne réutilise pas `environment.system.run` :
il impose un timeout de 10s, incompatible avec un `full-install` qui peut durer
des heures.
"""

from __future__ import annotations

import os
import subprocess
from collections import deque
from collections.abc import Callable, Sequence

from stalker_gamma_linux.engine.errors import EngineExecutionError, EngineNotFoundError
from stalker_gamma_linux.environment import system

ProgressCallback = Callable[[str], None]

_ENGINE_BINARY = "gamma-launcher"
_OUTPUT_TAIL_LINES = 20


def _noop(_: str) -> None:
    return None


def _engine_environment() -> dict[str, str]:
    env = dict(os.environ)
    # Neutralise le config.ini persistant de gamma-launcher (voir docs/ARCHITECTURE.md) :
    # nos chemins explicites doivent rester la seule source de vérité.
    env["GAMMA_LAUNCHER_NO_CONFIG"] = "1"
    return env


def run(
    subcommand: str, args: Sequence[str], *, on_progress: ProgressCallback | None = None
) -> None:
    """Lance `gamma-launcher <subcommand> <args>` et suit sa progression ligne à ligne.

    Chaque ligne de stdout est transmise à `on_progress`. Lève `EngineNotFoundError`
    si le binaire est absent du PATH, `EngineExecutionError` si le code de retour
    est non nul (les dernières lignes de sortie sont jointes au message).
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

    if process.stdout is not None:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            tail.append(line)
            progress(line)

    returncode = process.wait()
    if returncode != 0:
        raise EngineExecutionError(subcommand, returncode, "\n".join(tail))
