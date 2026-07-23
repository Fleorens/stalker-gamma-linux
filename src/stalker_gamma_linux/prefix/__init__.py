"""Gestion du préfixe Proton unique et partagé (MO2 + jeu).

Voie principale : **umu-launcher** — scriptable hors Steam, préfixe à
l'emplacement de notre choix (`<install>/prefix/`), Proton-GE téléchargé et
vérifié par nos soins. Fallback documenté si umu est indisponible : la voie
protontricks via une entrée Steam (docs/INSTALL-MANUAL.md §6.1-6.2) — non
scriptable ici car elle exige un APPID Steam, créé seulement en T06.
"""

from stalker_gamma_linux.prefix.doctor import (
    PrefixReport,
    build_prefix_report,
    format_prefix_report,
    run_prefix_doctor,
)
from stalker_gamma_linux.prefix.download import (
    FALLBACK_GE_RELEASE,
    download_proton_ge,
    resolve_latest_ge_release,
)
from stalker_gamma_linux.prefix.errors import (
    ChecksumMismatchError,
    PrefixCancelledError,
    PrefixCommandError,
    PrefixError,
    ProtonDownloadError,
    UmuNotFoundError,
    WinetricksVerbError,
)
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.process import UMU_GAME_ID, run_in_prefix
from stalker_gamma_linux.prefix.proton import (
    PROTON_EXPERIMENTAL,
    ProtonBuild,
    ensure_proton,
    find_proton_builds,
    select_proton_build,
)
from stalker_gamma_linux.prefix.provision import create_prefix, ensure_prefix, is_initialized
from stalker_gamma_linux.prefix.verbs import (
    REQUIRED_VERBS,
    apply_missing_verbs,
    installed_verbs,
    missing_verbs,
)

__all__ = [
    "FALLBACK_GE_RELEASE",
    "PROTON_EXPERIMENTAL",
    "REQUIRED_VERBS",
    "UMU_GAME_ID",
    "ChecksumMismatchError",
    "PrefixCancelledError",
    "PrefixCommandError",
    "PrefixError",
    "PrefixPaths",
    "PrefixReport",
    "ProtonBuild",
    "ProtonDownloadError",
    "UmuNotFoundError",
    "WinetricksVerbError",
    "apply_missing_verbs",
    "build_prefix_report",
    "create_prefix",
    "download_proton_ge",
    "ensure_prefix",
    "ensure_proton",
    "find_proton_builds",
    "format_prefix_report",
    "installed_verbs",
    "is_initialized",
    "missing_verbs",
    "resolve_latest_ge_release",
    "run_in_prefix",
    "run_prefix_doctor",
    "select_proton_build",
]
