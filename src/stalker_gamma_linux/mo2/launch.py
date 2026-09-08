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
from stalker_gamma_linux.environment.performance import Settings
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
    performance: Settings | None = None,
) -> Path:
    """Lance le jeu via MO2 (`moshortcut://`) pour monter l'USVFS, **détaché**
    du terminal appelant (`process.run_detached`) : la fermeture du terminal
    ne tue plus le jeu. Retourne immédiatement le chemin du journal — le jeu
    tourne encore à ce moment-là (pas de `on_progress`/`cancel_event` : plus
    personne ne consommerait la sortie ligne à ligne).

    `performance` (défaut : GameMode seul, cf. `environment.performance`)
    emboîte les couches demandées autour de la commande. Elles s'appliquent
    bien au *jeu* et pas seulement à l'interface de MO2 : MO2 démarre le jeu
    comme processus fils, et aussi bien le `LD_PRELOAD` de GameMode que les
    variables des couches Vulkan se propagent à toute la descendance.
    """
    _require_executable(mo2)
    return process.run_detached(
        mo2.executable,
        [moshortcut(executable)],
        paths=prefix,
        proton_path=proton_path,
        log_label="mo2-game",
        performance=performance if performance is not None else Settings(),
    )
