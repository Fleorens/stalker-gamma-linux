"""Lancement d'exécutables Windows dans le préfixe partagé via umu-run.

Isolé dans ce module pour que les tests puissent monkeypatcher `subprocess.Popen`
sans jamais lancer un vrai processus (même approche que `engine.process`).
Pas de timeout : un premier lancement télécharge le runtime umu et compile des
shaders, ça peut durer très longtemps.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from stalker_gamma_linux.environment import gamemode as gamemode_tool
from stalker_gamma_linux.environment import system
from stalker_gamma_linux.prefix.errors import (
    PrefixCancelledError,
    PrefixCommandError,
    UmuNotFoundError,
)
from stalker_gamma_linux.prefix.paths import PrefixPaths

ProgressCallback = Callable[[str], None]

# Identifiant umu du jeu (docs/INSTALL-MANUAL.md §6.3) : sert de clé protonfixes.
UMU_GAME_ID = "umu-stalkergamma"

_UMU_BINARY = "umu-run"
_OUTPUT_TAIL_LINES = 20
_TERMINATE_GRACE_SECONDS = 5

# Taille au-delà de laquelle le journal de lancement détaché (`run_detached`)
# est tourné (1 backup) plutôt que de croître indéfiniment : contrairement à
# `run_in_prefix`, ce journal est unique par `log_label` et ré-ouvert en
# append à chaque lancement (append-only entre les sessions, cf. docstring).
_DETACHED_LOG_MAX_BYTES = 5 * 1024 * 1024
_DETACHED_BACKUP_SUFFIX = ".1"


def _noop(_: str) -> None:
    return None


def _watch_cancellation(process: subprocess.Popen[str], cancel_event: threading.Event) -> None:
    """Tue `process` dès que `cancel_event` est levé (voir `engine.process`, même approche)."""
    while not cancel_event.wait(timeout=0.2):
        if process.poll() is not None:
            return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()


def _slug(exe: Path | str) -> str:
    stem = Path(str(exe)).stem.lower()
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", stem).strip("-")
    return cleaned or "run"


def _prefix_environment(
    paths: PrefixPaths, proton_path: Path, extra: Mapping[str, str] | None
) -> dict[str, str]:
    env = dict(os.environ)
    if extra:
        env.update(extra)
    # Les variables structurelles en dernier : l'appelant ne peut pas casser
    # l'invariant « un seul préfixe partagé MO2 + jeu ».
    env.update(
        {
            "WINEPREFIX": str(paths.prefix),
            "GAMEID": UMU_GAME_ID,
            "PROTONPATH": str(proton_path),
        }
    )
    return env


def run_in_prefix(
    exe: Path | str,
    args: Sequence[str] = (),
    *,
    paths: PrefixPaths,
    proton_path: Path,
    env: Mapping[str, str] | None = None,
    log_label: str | None = None,
    gamemode: bool = False,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Lance `umu-run <exe> <args>` dans le préfixe partagé et journalise sa sortie.

    `exe` est un exécutable Windows ou une sentinelle umu (`winetricks`,
    `createprefix`). `env` ajoute des variables d'environnement ; les variables
    structurelles (WINEPREFIX, GAMEID, PROTONPATH) restent toujours imposées.
    `gamemode` (réservé aux lancements de *jeu*, pas aux étapes d'installation)
    enveloppe la commande dans `gamemoderun` si GameMode est installé — sans
    effet sinon, cf. `environment.gamemode`. Toute la sortie (stdout + stderr)
    est capturée dans un fichier de `paths.logs`, dont le chemin est retourné.
    Lève `UmuNotFoundError` si umu-run est absent du PATH, `PrefixCommandError`
    (journal joint) si le code de retour est non nul. `cancel_event`
    (optionnel, GUI) : voir `engine.process.run`, même comportement
    d'annulation propre — lève `PrefixCancelledError` au lieu de
    `PrefixCommandError`.
    """
    binary = system.which(_UMU_BINARY)
    if binary is None:
        raise UmuNotFoundError

    paths.ensure_directories()
    label = log_label or _slug(exe)
    log_path = paths.logs / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    command = [binary, str(exe), *args]
    if gamemode:
        command = gamemode_tool.wrap(command)
    progress = on_progress or _noop
    tail: deque[str] = deque(maxlen=_OUTPUT_TAIL_LINES)

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"$ {' '.join(command)}\n")
        process = subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # Wine émet des octets non-UTF-8 (constaté en réel : 0x88) ; sans
            # errors="replace", le décodage strict crashe le lecteur en plein vol.
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_prefix_environment(paths, proton_path, env),
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
                log_file.write(f"{line}\n")
                tail.append(line)
                progress(line)
        returncode = process.wait()
        if watcher is not None:
            watcher.join(timeout=_TERMINATE_GRACE_SECONDS)

    if cancel_event is not None and cancel_event.is_set():
        raise PrefixCancelledError(" ".join(command))
    if returncode != 0:
        raise PrefixCommandError(" ".join(command), returncode, log_path, "\n".join(tail))
    return log_path


def _rotate_detached_log(log_path: Path, max_bytes: int) -> None:
    """Renomme `log_path` en backup s'il dépasse `max_bytes` (1 seul backup, écrasé)."""
    if not log_path.exists() or log_path.stat().st_size < max_bytes:
        return
    backup = log_path.with_name(log_path.name + _DETACHED_BACKUP_SUFFIX)
    backup.unlink(missing_ok=True)
    log_path.rename(backup)


def run_detached(
    exe: Path | str,
    args: Sequence[str] = (),
    *,
    paths: PrefixPaths,
    proton_path: Path,
    env: Mapping[str, str] | None = None,
    log_label: str | None = None,
    gamemode: bool = False,
) -> Path:
    """Lance `umu-run <exe> <args>` **détaché** du terminal appelant (survit à
    sa fermeture) : c'est le mode dédié aux lancements de *jeu* (`play`), par
    opposition à `run_in_prefix` que garde le pipeline d'installation
    (progression, `cancel_event`, sortie pompée ligne à ligne).

    Trois différences avec `run_in_prefix`, toutes liées au même constat — une
    fois cette fonction revenue, plus personne ne lit la sortie du process ni
    n'attend sa fin :
    1. `start_new_session=True` : le process rejoint sa propre session/groupe
       de processus au lieu d'hériter de celui de l'appelant, donc un SIGHUP
       envoyé au terminal (fermeture de la fenêtre) ne l'atteint plus.
    2. La sortie est redirigée **directement** dans le fichier de log (pas de
       pompage ligne à ligne, donc pas de `on_progress`/`cancel_event` : rien
       ne serait plus là pour les consommer). Le descripteur est refermé côté
       parent dès le retour de `Popen` — l'enfant a dupliqué le sien, il garde
       la sortie ; sans cette fermeture, le fd fuirait dans ce process à
       chaque lancement.
    3. Le journal n'est pas horodaté par lancement : un seul fichier par
       `log_label`, ouvert en append et tourné (1 backup) au-delà de
       `_DETACHED_LOG_MAX_BYTES`, pour rester exploitable après plusieurs
       sessions sans grossir sans limite.

    Retourne le chemin du journal immédiatement (le process tourne encore) :
    à afficher côté `play`, et à lire après coup pour diagnostic (voir
    `mo2.diagnostics`). Lève `UmuNotFoundError` si umu-run est absent du PATH.
    Ne lève rien sur le code de retour du jeu : personne ne l'attend ici.
    """
    binary = system.which(_UMU_BINARY)
    if binary is None:
        raise UmuNotFoundError

    paths.ensure_directories()
    label = log_label or _slug(exe)
    log_path = paths.logs / f"{label}.log"
    _rotate_detached_log(log_path, _DETACHED_LOG_MAX_BYTES)
    command = [binary, str(exe), *args]
    if gamemode:
        command = gamemode_tool.wrap(command)

    log_file = log_path.open("a", encoding="utf-8")
    try:
        log_file.write(f"$ {' '.join(command)}\n")
        log_file.flush()
        subprocess.Popen(  # noqa: S603
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=_prefix_environment(paths, proton_path, env),
            start_new_session=True,
        )
    finally:
        log_file.close()
    return log_path
