"""Mode principal : Mod Organizer 2 sous Proton, avec USVFS actif.

C'est la raison d'être du projet côté jeu : préserver la flexibilité des mods
(activer/désactiver/ajouter) comme sous Windows. Ce package :

- configure automatiquement l'instance MO2 livrée par GAMMA (`instance`) —
  l'étape que gamma-launcher ne fait pas ;
- lance MO2 et le jeu **à travers** MO2 (`launch`) pour que l'USVFS monte les
  mods ;
- diagnostique un USVFS mort (`diagnostics`, jeu lancé « vanilla ») et renvoie
  vers `docs/MO2-PROTON-COMPAT.md` ;
- expose le fallback flat sans MO2 (`flat`), au prix de la flexibilité.
"""

from stalker_gamma_linux.mo2.diagnostics import (
    UsvfsDiagnosis,
    diagnose_usvfs,
    latest_usvfs_log,
    usvfs_active_in,
)
from stalker_gamma_linux.mo2.errors import (
    AnomalyNotFoundError,
    Mo2Error,
    Mo2InstanceError,
    Mo2NotInstalledError,
)
from stalker_gamma_linux.mo2.flat import FLAT_LAUNCHER, flat_dir, launch_flat
from stalker_gamma_linux.mo2.instance import (
    ANOMALY_GAME_NAME,
    GAMMA_PROFILE,
    InstanceConfig,
    configure_instance,
    is_configured,
    read_game_path,
)
from stalker_gamma_linux.mo2.launch import (
    DEFAULT_EXECUTABLE,
    MOSHORTCUT_SCHEME,
    launch_game,
    launch_mo2,
    moshortcut,
)
from stalker_gamma_linux.mo2.modlist import ModEntry, enabled_mods, parse_modlist, read_modlist
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.session import resolve_anomaly, run_mo2, run_play
from stalker_gamma_linux.mo2.winepath import to_windows_path

__all__ = [
    "ANOMALY_GAME_NAME",
    "DEFAULT_EXECUTABLE",
    "FLAT_LAUNCHER",
    "GAMMA_PROFILE",
    "MOSHORTCUT_SCHEME",
    "AnomalyNotFoundError",
    "InstanceConfig",
    "ModEntry",
    "Mo2Error",
    "Mo2InstanceError",
    "Mo2NotInstalledError",
    "Mo2Paths",
    "UsvfsDiagnosis",
    "configure_instance",
    "diagnose_usvfs",
    "enabled_mods",
    "flat_dir",
    "is_configured",
    "latest_usvfs_log",
    "launch_flat",
    "launch_game",
    "launch_mo2",
    "moshortcut",
    "parse_modlist",
    "read_game_path",
    "read_modlist",
    "resolve_anomaly",
    "run_mo2",
    "run_play",
    "to_windows_path",
    "usvfs_active_in",
]
