"""Orchestration des commandes utilisateur `mo2` et `play`.

Enchaîne : préfixe prêt (T04) → instance MO2 configurée → lancement (MO2 ou
jeu via USVFS) → diagnostic post-lancement. Le mode flat est le fallback
explicite (`play --flat`).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux import engine
from stalker_gamma_linux.engine.errors import EngineError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.mo2 import diagnostics, flat, instance, launch
from stalker_gamma_linux.mo2.errors import AnomalyNotFoundError, Mo2Error
from stalker_gamma_linux.mo2.launch import DEFAULT_EXECUTABLE
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.prefix import provision
from stalker_gamma_linux.prefix.errors import PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.proton import ProtonBuild

_ANOMALY_MARKER = "AnomalyLauncher.exe"


def _resolve_root(target: Path | None) -> Path:
    return target if target is not None else DEFAULT_INSTALL_TARGET


def resolve_anomaly(mo2: Mo2Paths, install: InstallPaths) -> Path:
    """Dossier Anomaly réel, tolérant à deux layouts.

    Défaut = layout du projet `<root>/anomaly` (sibling de `gamma/`). Repli =
    layout GAMMA « Anomaly imbriqué dans l'instance » `<gamma>/anomaly` (constaté
    sur une vraie install), retenu seulement si le sibling est absent et que
    l'imbriqué contient bien `AnomalyLauncher.exe`.
    """
    nested = mo2.instance / "anomaly"
    sibling_ok = system.path_exists(install.anomaly / _ANOMALY_MARKER)
    if not sibling_ok and system.path_exists(nested / _ANOMALY_MARKER):
        return nested
    return install.anomaly


def run_mo2(target: Path | None = None, *, search_dirs: Sequence[Path] | None = None) -> int:
    """Ouvre l'interface Mod Organizer 2 (préfixe prêt, instance configurée)."""
    root = _resolve_root(target)
    mo2 = Mo2Paths.under(root)
    prefix = PrefixPaths.under(root)
    anomaly = resolve_anomaly(mo2, InstallPaths.under(root))
    try:
        build = provision.ensure_prefix(prefix, search_dirs=search_dirs, on_progress=print)
        _configure_best_effort(mo2, anomaly)
        print("Lancement de Mod Organizer 2…")
        launch.launch_mo2(mo2, prefix, build.path, on_progress=print)
    except (PrefixError, Mo2Error) as error:
        print(f"Erreur : {error}")
        return 1
    return 0


def run_play(
    target: Path | None = None,
    *,
    flat_mode: bool = False,
    executable: str = DEFAULT_EXECUTABLE,
    diagnose: bool = True,
    search_dirs: Sequence[Path] | None = None,
) -> int:
    """Lance le jeu. Mode nominal : via MO2 (USVFS) + diagnostic. `flat_mode` : fallback."""
    root = _resolve_root(target)
    mo2 = Mo2Paths.under(root)
    prefix = PrefixPaths.under(root)
    install = InstallPaths.under(root)
    try:
        build = provision.ensure_prefix(prefix, search_dirs=search_dirs, on_progress=print)
        if flat_mode:
            return _run_flat(root, install, prefix, build)
        instance.configure_instance(mo2, resolve_anomaly(mo2, install))
        print(f"Lancement d'Anomaly via MO2 (« {executable} », USVFS)…")
        launch.launch_game(mo2, prefix, build.path, executable=executable, on_progress=print)
    except (PrefixError, EngineError, Mo2Error) as error:
        print(f"Erreur : {error}")
        return 1

    if not diagnose:
        return 0
    result = diagnostics.diagnose_usvfs(mo2)
    print(f"\n{result.message}")
    return 0 if result.active else 1


def _configure_best_effort(mo2: Mo2Paths, anomaly: Path) -> None:
    """Configure l'instance pour `mo2` ; tolère un jeu encore absent (on ouvre MO2 quand même)."""
    try:
        instance.configure_instance(mo2, anomaly)
    except AnomalyNotFoundError as error:
        print(f"Avertissement : {error}\nOuverture de MO2 sans configurer le chemin du jeu.")


def _run_flat(
    root: Path, install: InstallPaths, prefix: PrefixPaths, build: ProtonBuild
) -> int:
    final = flat.flat_dir(root)
    print(
        "⚠ Mode flat (fallback) : USVFS contourné, Anomaly et les mods sont fusionnés. "
        "Tu PERDS la flexibilité des mods (plus d'activation/désactivation via MO2). "
        "Voir docs/INSTALL-MANUAL.md annexe A.\n"
    )
    engine.build_flat_install(install, final, on_progress=print)
    print("Lancement de l'installation flat…")
    flat.launch_flat(final, prefix, build.path, on_progress=print)
    return 0
