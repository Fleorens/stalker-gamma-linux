"""Détection d'une install GAMMA **réelle sur le disque**, indépendante de notre `state.toml`.

`state.py` ne reflète que ce que *notre* pipeline `install` a fait : une install
GAMMA posée à la main (ou par une version antérieure de l'outil) n'y figure pas,
et la GUI affichait alors « GAMMA n'est pas installé » avec le jeu sous le nez.
Ce module regarde les vrais fichiers (`AnomalyLauncher.exe` + `ModOrganizer.exe`)
pour reconnaître une install existante, quel que soit qui l'a posée.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment import system
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.session import ANOMALY_MARKER, resolve_anomaly


def is_installed_on_disk(target: Path) -> bool:
    """True si une install GAMMA jouable existe déjà à `target` : Anomaly (base)
    **et** l'instance Mod Organizer 2 présents. Tolère les deux layouts d'Anomaly
    (sibling `<root>/anomaly` ou imbriqué `<gamma>/anomaly`) via `resolve_anomaly`.
    """
    mo2 = Mo2Paths.under(target)
    anomaly = resolve_anomaly(mo2, InstallPaths.under(target))
    return system.path_exists(anomaly / ANOMALY_MARKER) and system.path_exists(mo2.executable)
