"""Création et mise à l'état nominal du préfixe partagé (Proton + verbs)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.prefix import process, proton, verbs
from stalker_gamma_linux.prefix.errors import PrefixCommandError, PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.process import ProgressCallback
from stalker_gamma_linux.prefix.proton import ProtonBuild

# Sentinelle umu-run : initialise le préfixe sans lancer d'exécutable.
_CREATE_PREFIX_EXE = "createprefix"


def is_initialized(paths: PrefixPaths) -> bool:
    """Un préfixe Wine initialisé contient `system.reg` à sa racine."""
    return system.path_exists(paths.wine_root / "system.reg")


def create_prefix(
    paths: PrefixPaths,
    proton_path: Path,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Crée le préfixe s'il n'existe pas encore. Idempotent : ne touche jamais
    à un préfixe déjà initialisé.

    La **vérité** est l'initialisation du préfixe (`system.reg`), pas le code de
    retour d'umu. Constaté en réel (umu 1.4.1 + GE-Proton11-1, préfixe neuf) : la
    sentinelle `createprefix` **crée bien** le préfixe (« Upgrading prefix from
    None… ») mais umu tente ensuite de la *lancer* comme un exécutable et sort en
    code non nul (`ShellExecuteEx: Fichier introuvable`). On traite donc un échec
    de commande comme un succès **si et seulement si** le préfixe est initialisé.
    """
    if is_initialized(paths):
        return
    try:
        log_path = process.run_in_prefix(
            _CREATE_PREFIX_EXE,
            paths=paths,
            proton_path=proton_path,
            log_label="createprefix",
            on_progress=on_progress,
            cancel_event=cancel_event,
        )
    except PrefixCommandError as error:
        if is_initialized(paths):
            return
        raise PrefixError(
            f"La création du préfixe {paths.prefix} a échoué : la commande a rendu "
            f"un code non nul et le préfixe n'est pas initialisé (system.reg absent)."
            f"\n{error}"
        ) from error
    if not is_initialized(paths):
        raise PrefixError(
            f"umu-run a terminé sans erreur mais le préfixe {paths.prefix} n'est "
            f"toujours pas initialisé (system.reg absent).\nJournal : {log_path}"
        )


def ensure_prefix(
    paths: PrefixPaths,
    *,
    search_dirs: Sequence[Path] | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    proton_release: str | None = None,
) -> ProtonBuild:
    """Amène le préfixe partagé à l'état nominal : Proton présent, préfixe créé,
    verbs winetricks appliqués.

    Totalement idempotent : sur un préfixe sain, aucune commande externe n'est
    relancée. Retourne le build Proton utilisé (T05/T06/T07 en ont besoin pour
    `run_in_prefix`). `cancel_event` (optionnel, GUI) : propagé à chaque étape
    (téléchargement Proton, création, verbs) ; laisse remonter
    `PrefixCancelledError` si levé pendant l'une d'elles. `proton_release`
    (optionnel, préférence GUI) : voir `proton.ensure_proton`.
    """
    build = proton.ensure_proton(
        search_dirs, on_progress=on_progress, cancel_event=cancel_event, release=proton_release
    )
    create_prefix(paths, build.path, on_progress=on_progress, cancel_event=cancel_event)
    verbs.apply_missing_verbs(
        paths, build.path, on_progress=on_progress, cancel_event=cancel_event
    )
    return build
