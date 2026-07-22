"""Exceptions typées pour le mode principal (MO2 sous Proton)."""

from __future__ import annotations

from pathlib import Path


class Mo2Error(Exception):
    """Erreur de base pour tout ce qui concerne Mod Organizer 2."""


class Mo2NotInstalledError(Mo2Error):
    """L'instance MO2 livrée par GAMMA est absente (`ModOrganizer.exe` manquant)."""

    def __init__(self, executable: Path) -> None:
        self.executable = executable
        super().__init__(
            f"Mod Organizer 2 introuvable : {executable} n'existe pas.\n"
            "L'instance MO2 est construite par gamma-launcher pendant l'installation "
            "du modpack. Lance d'abord l'installation (full-install) avant de jouer."
        )


class Mo2InstanceError(Mo2Error):
    """L'instance MO2 ne peut pas être configurée (jeu, profil ou `.ini` invalide)."""


class AnomalyNotFoundError(Mo2InstanceError):
    """Le dossier du jeu de base Anomaly est absent ou incomplet."""

    def __init__(self, anomaly_dir: Path) -> None:
        self.anomaly_dir = anomaly_dir
        super().__init__(
            f"Dossier Anomaly invalide : {anomaly_dir} ne contient pas "
            "AnomalyLauncher.exe.\n"
            "Installe d'abord le jeu de base (anomaly-install) — c'est le chemin "
            "que MO2 doit connaître comme `gamePath`."
        )
