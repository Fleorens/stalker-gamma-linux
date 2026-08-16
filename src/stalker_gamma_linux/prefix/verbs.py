"""Application idempotente des verbs winetricks dans le préfixe partagé."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.errors import PrefixCommandError, WinetricksVerbError
from stalker_gamma_linux.prefix.paths import PrefixPaths

# Liste actée en T04 (docs/ARCHITECTURE.md, décision 3).
# vcrun2022 en premier : c'est le prérequis le plus structurant pour MO2.
#
# `dx8vb` et `quartz` (présents dans le guide v1ld, absents des deux autres
# sources) : tranché le 2026-08-15, ils **ne sont pas requis**.
# - `dx8vb` est la bibliothèque de types DirectX 8 pour **Visual Basic**, pas
#   le runtime D3D8. X-Ray est du C++ et embarque ses propres rendus
#   DX8/9/10/11 (`bin/AnomalyDX*.exe`) : rien n'y consomme une typelib VB. La
#   confusion vient probablement du « DX8 » présent dans les deux noms.
# - `quartz` est le runtime DirectShow, pour la lecture vidéo. Vérifié sur une
#   installation réelle : Anomaly ne livre aucun `.ogm`/`.ogv`/`.avi` ni
#   aucune DLL de codec — DirectShow n'a rien à décoder ici.
# Confirmé à l'usage : le préfixe du mainteneur tourne avec ces 6 verbs et
# rien d'autre. Si un jour une vidéo refuse de se lire, `quartz` reste le
# premier remède à tenter — c'est du dépannage, pas un prérequis.
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


def missing_verbs(paths: PrefixPaths, required: Sequence[str] = REQUIRED_VERBS) -> tuple[str, ...]:
    """Verbs de `required` absents du préfixe, dans l'ordre de `required`."""
    installed = installed_verbs(paths)
    return tuple(verb for verb in required if verb not in installed)


def apply_missing_verbs(
    paths: PrefixPaths,
    proton_path: Path,
    *,
    required: Sequence[str] = REQUIRED_VERBS,
    on_progress: process.ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[str, ...]:
    """Applique les verbs manquants, un à la fois. Retourne ceux appliqués.

    Un verb à la fois : l'échec est attribuable sans ambiguïté, et chaque verb
    réussi est acté dans `winetricks.log` — une relance après échec ne rejoue
    que le reste. Lève `WinetricksVerbError` (journal joint) au premier échec,
    ou laisse remonter `PrefixCancelledError` si `cancel_event` (GUI) est levé
    pendant l'application d'un verb.
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
                cancel_event=cancel_event,
            )
        except PrefixCommandError as error:
            raise WinetricksVerbError(
                verb, error.returncode, error.log_path, error.output_tail
            ) from error
    return to_apply
