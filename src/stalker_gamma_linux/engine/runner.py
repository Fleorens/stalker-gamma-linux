"""Fonctions de haut niveau pilotant gamma-launcher : install/update/verify.

Aucune logique de résolution ModDB, de parsing de modlist ou d'extraction
n'est réimplémentée ici : tout est délégué au binaire `gamma-launcher` via
`stalker_gamma_linux.engine.process.run` (voir docs/ARCHITECTURE.md).
"""

from __future__ import annotations

from stalker_gamma_linux.engine.errors import EngineExecutionError, VerificationError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.engine.process import ProgressCallback, run


def install_anomaly(paths: InstallPaths, *, on_progress: ProgressCallback | None = None) -> None:
    """Installe S.T.A.L.K.E.R.: Anomaly (`gamma-launcher anomaly-install`)."""
    paths.ensure_directories()
    run(
        "anomaly-install",
        ["--anomaly", str(paths.anomaly), "--cache-directory", str(paths.cache)],
        on_progress=on_progress,
    )


def install_gamma(paths: InstallPaths, *, on_progress: ProgressCallback | None = None) -> None:
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
    )


def update_gamma(paths: InstallPaths, *, on_progress: ProgressCallback | None = None) -> None:
    """Alias de `install_gamma`.

    gamma-launcher v3.1 n'expose pas de sous-commande `update` séparée :
    `full-install` sert aux deux usages (voir docs/ARCHITECTURE.md).
    """
    install_gamma(paths, on_progress=on_progress)


def verify(paths: InstallPaths, *, on_progress: ProgressCallback | None = None) -> None:
    """Vérifie l'installation (`check-anomaly` puis `check-md5`).

    Lève `VerificationError` si l'une des deux vérifications échoue.
    """
    for subcommand, args in (
        ("check-anomaly", ["--anomaly", str(paths.anomaly)]),
        ("check-md5", ["--gamma", str(paths.gamma)]),
    ):
        try:
            run(subcommand, args, on_progress=on_progress)
        except EngineExecutionError as error:
            raise VerificationError(
                error.subcommand, error.returncode, error.output_tail
            ) from error
