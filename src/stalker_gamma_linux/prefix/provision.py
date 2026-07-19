"""Création et mise à l'état nominal du préfixe partagé (Proton + verbs)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.prefix import process, proton, verbs
from stalker_gamma_linux.prefix.errors import PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.process import ProgressCallback
from stalker_gamma_linux.prefix.proton import ProtonBuild

# Sentinelle umu-run : initialise le préfixe sans lancer d'exécutable.
# ⚠ À VALIDER sur machine réelle (docs/INSTALL-MANUAL.md §6.3).
_CREATE_PREFIX_EXE = "createprefix"


def is_initialized(paths: PrefixPaths) -> bool:
    """Un préfixe Wine initialisé contient `system.reg` à sa racine."""
    return system.path_exists(paths.wine_root / "system.reg")


def create_prefix(
    paths: PrefixPaths, proton_path: Path, *, on_progress: ProgressCallback | None = None
) -> None:
    """Crée le préfixe s'il n'existe pas encore. Idempotent : ne touche jamais
    à un préfixe déjà initialisé."""
    if is_initialized(paths):
        return
    log_path = process.run_in_prefix(
        _CREATE_PREFIX_EXE,
        paths=paths,
        proton_path=proton_path,
        log_label="createprefix",
        on_progress=on_progress,
    )
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
) -> ProtonBuild:
    """Amène le préfixe partagé à l'état nominal : Proton présent, préfixe créé,
    verbs winetricks appliqués.

    Totalement idempotent : sur un préfixe sain, aucune commande externe n'est
    relancée. Retourne le build Proton utilisé (T05/T06/T07 en ont besoin pour
    `run_in_prefix`).
    """
    build = proton.ensure_proton(search_dirs, on_progress=on_progress)
    create_prefix(paths, build.path, on_progress=on_progress)
    verbs.apply_missing_verbs(paths, build.path, on_progress=on_progress)
    return build
