"""Application idempotente des verbs winetricks dans le préfixe partagé."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.errors import PrefixCommandError, WinetricksVerbError
from stalker_gamma_linux.prefix.paths import PrefixPaths

# Liste actée en T04 (docs/ARCHITECTURE.md, décision 3). `dx8vb`/`quartz`,
# présents chez v1ld uniquement, restent ⚠ À VALIDER → matrice T05.
# vcrun2022 en premier : c'est le prérequis le plus structurant pour MO2.
REQUIRED_VERBS: tuple[str, ...] = (
    "vcrun2022",
    "d3dcompiler_43",
    "d3dcompiler_47",
    "d3dx9",
    "d3dx10",
    "d3dx11_43",
)


def installed_verbs(paths: PrefixPaths) -> frozenset[str]:
    """Verbs déjà installés, d'après le `winetricks.log` tenu par winetricks.

    C'est le même mécanisme que winetricks utilise lui-même pour savoir quoi
    sauter — y compris si les verbs ont été posés par protontricks (qui
    délègue à winetricks). Fichier absent = préfixe vierge = aucun verb.
    """
    content = system.read_text(paths.winetricks_log)
    if content is None:
        return frozenset()
    return frozenset(line.strip() for line in content.splitlines() if line.strip())


def missing_verbs(
    paths: PrefixPaths, required: Sequence[str] = REQUIRED_VERBS
) -> tuple[str, ...]:
    """Verbs de `required` absents du préfixe, dans l'ordre de `required`."""
    installed = installed_verbs(paths)
    return tuple(verb for verb in required if verb not in installed)


def apply_missing_verbs(
    paths: PrefixPaths,
    proton_path: Path,
    *,
    required: Sequence[str] = REQUIRED_VERBS,
    on_progress: process.ProgressCallback | None = None,
) -> tuple[str, ...]:
    """Applique les verbs manquants, un à la fois. Retourne ceux appliqués.

    Un verb à la fois : l'échec est attribuable sans ambiguïté, et chaque verb
    réussi est acté dans `winetricks.log` — une relance après échec ne rejoue
    que le reste. Lève `WinetricksVerbError` (journal joint) au premier échec.
    """
    to_apply = missing_verbs(paths, required)
    for verb in to_apply:
        try:
            process.run_in_prefix(
                "winetricks",
                ["-q", verb],
                paths=paths,
                proton_path=proton_path,
                log_label=f"winetricks-{verb}",
                on_progress=on_progress,
            )
        except PrefixCommandError as error:
            raise WinetricksVerbError(
                verb, error.returncode, error.log_path, error.output_tail
            ) from error
    return to_apply
