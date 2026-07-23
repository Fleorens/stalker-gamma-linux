"""Fonctions de haut niveau pilotant gamma-launcher : install/update/verify.

Aucune logique de résolution ModDB, de parsing de modlist ou d'extraction
n'est réimplémentée ici : tout est délégué au binaire `gamma-launcher` via
`stalker_gamma_linux.engine.process.run` (voir docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import threading
from pathlib import Path

from stalker_gamma_linux.engine.errors import EngineExecutionError, VerificationError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.engine.process import ProgressCallback, run


def install_anomaly(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Installe S.T.A.L.K.E.R.: Anomaly (`gamma-launcher anomaly-install`)."""
    paths.ensure_directories()
    run(
        "anomaly-install",
        ["--anomaly", str(paths.anomaly), "--cache-directory", str(paths.cache)],
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def install_gamma(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Installe (ou met à jour) le modpack G.A.M.M.A. (`gamma-launcher full-install`).

    `full-install` est idempotent côté gamma-launcher : rejoué sur une
    installation existante, il ne fait que la mettre à jour — voir
    `update_gamma`, qui appelle exactement cette même fonction.
    """
    paths.ensure_directories()
    run(
        "full-install",
        [
            "--anomaly",
            str(paths.anomaly),
            "--gamma",
            str(paths.gamma),
            "--cache-directory",
            str(paths.cache),
        ],
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def update_gamma(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Alias de `install_gamma`.

    gamma-launcher v3.1 n'expose pas de sous-commande `update` séparée :
    `full-install` sert aux deux usages (voir docs/ARCHITECTURE.md).
    """
    install_gamma(paths, on_progress=on_progress, cancel_event=cancel_event)


def remove_reshade(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Retire ReShade, incompatible DXVK/Proton (`gamma-launcher remove-reshade`).

    Étape **obligatoire** avant de jouer (docs/INSTALL-MANUAL.md §5) : ReShade,
    injecté par le modpack pour Windows, casse le rendu ou le lancement sous DXVK.
    """
    run(
        "remove-reshade",
        ["--anomaly", str(paths.anomaly)],
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def purge_shader_cache(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Vide le cache de shaders d'Anomaly (`gamma-launcher purge-shader-cache`).

    Complète `remove_reshade` : un cache obsolète après retrait de ReShade ou
    après une mise à jour provoque des artefacts (docs/INSTALL-MANUAL.md §5, §9).
    """
    run(
        "purge-shader-cache",
        ["--anomaly", str(paths.anomaly)],
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def build_flat_install(
    paths: InstallPaths,
    final_dir: Path,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Construit l'install fusionnée sans MO2 (`gamma-launcher usvfs-workaround`).

    Fusionne Anomaly + les mods GAMMA en une installation jouable directement
    (fallback du mode principal, cf. `mo2/flat.py` et docs/INSTALL-MANUAL.md
    annexe A). `final_dir` est le dossier de sortie (`<install>/flat`).
    """
    final_dir.mkdir(parents=True, exist_ok=True)
    run(
        "usvfs-workaround",
        [
            "--anomaly",
            str(paths.anomaly),
            "--gamma",
            str(paths.gamma),
            "--final",
            str(final_dir),
        ],
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def verify(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Vérifie l'installation (`check-anomaly` puis `check-md5`).

    Lève `VerificationError` si l'une des deux vérifications échoue.
    """
    for subcommand, args in (
        ("check-anomaly", ["--anomaly", str(paths.anomaly)]),
        ("check-md5", ["--gamma", str(paths.gamma)]),
    ):
        try:
            run(subcommand, args, on_progress=on_progress, cancel_event=cancel_event)
        except EngineExecutionError as error:
            raise VerificationError(
                error.subcommand, error.returncode, error.output_tail
            ) from error
