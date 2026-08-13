"""Lancement de MO2 et du jeu **à travers** MO2 (pour que l'USVFS monte les mods).

Seuls les processus lancés depuis MO2 voient le VFS des mods : on ne lance donc
jamais l'exécutable du jeu directement, mais on passe à `ModOrganizer.exe` un
URI `moshortcut://` désignant l'exécutable configuré. Format (SteamTinkerLaunch,
wiki MO2) : `moshortcut://<instance>:<exécutable>` ; pour une instance portable,
la partie instance est vide → `moshortcut://:Anomaly (DX11)`.
"""

from __future__ import annotations

import threading
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.mo2.errors import Mo2NotInstalledError
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.process import ProgressCallback

# Exécutable GAMMA par défaut (rendu DX11), tel que nommé dans l'instance MO2.
DEFAULT_EXECUTABLE = "Anomaly (DX11)"
MOSHORTCUT_SCHEME = "moshortcut://"


def moshortcut(executable: str, instance: str = "") -> str:
    """URI de lancement d'un exécutable configuré dans MO2 (`instance` vide = portable)."""
    return f"{MOSHORTCUT_SCHEME}{instance}:{executable}"


def _require_executable(mo2: Mo2Paths) -> None:
    if not system.path_exists(mo2.executable):
        raise Mo2NotInstalledError(mo2.executable)


def launch_mo2(
    mo2: Mo2Paths,
    prefix: PrefixPaths,
    proton_path: Path,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Ouvre l'interface MO2 dans le préfixe partagé. Retourne le chemin du journal."""
    _require_executable(mo2)
    return process.run_in_prefix(
        mo2.executable,
        paths=prefix,
        proton_path=proton_path,
        log_label="mo2",
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def launch_game(
    mo2: Mo2Paths,
    prefix: PrefixPaths,
    proton_path: Path,
    *,
    executable: str = DEFAULT_EXECUTABLE,
    gamemode: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Lance le jeu via MO2 (`moshortcut://`) pour monter l'USVFS. Bloque jusqu'à
    la fermeture du jeu ; retourne le chemin du journal.

    `gamemode` (par défaut actif) enveloppe le lancement dans `gamemoderun` :
    MO2 démarre le jeu comme processus fils, et le `LD_PRELOAD` posé par
    GameMode se propage à toute la descendance — c'est bien la partie qui en
    profite, pas seulement l'interface de MO2 (cf. `environment.gamemode`).
    """
    _require_executable(mo2)
    return process.run_in_prefix(
        mo2.executable,
        [moshortcut(executable)],
        paths=prefix,
        proton_path=proton_path,
        log_label="mo2-game",
        gamemode=gamemode,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )
