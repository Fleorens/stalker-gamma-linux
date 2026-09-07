"""Exceptions typées pour le mode principal (MO2 sous Proton)."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.i18n import _


class Mo2Error(Exception):
    """Erreur de base pour tout ce qui concerne Mod Organizer 2."""


class Mo2NotInstalledError(Mo2Error):
    """L'instance MO2 livrée par GAMMA est absente (`ModOrganizer.exe` manquant)."""

    def __init__(self, executable: Path) -> None:
        self.executable = executable
        super().__init__(
            _(
                "Mod Organizer 2 not found: {executable} does not exist.\n"
                "The MO2 instance is built by gamma-launcher during the modpack "
                "install. Run the install (full-install) first before playing."
            ).format(executable=executable)
        )


class Mo2CancelledError(Mo2Error):
    """Opération MO2 longue interrompue via `cancel_event` (fusion du mode flat)."""


class Mo2InstanceError(Mo2Error):
    """L'instance MO2 ne peut pas être configurée (jeu, profil ou `.ini` invalide)."""


class AnomalyNotFoundError(Mo2InstanceError):
    """Le dossier du jeu de base Anomaly est absent ou incomplet."""

    def __init__(self, anomaly_dir: Path) -> None:
        self.anomaly_dir = anomaly_dir
        super().__init__(
            _(
                "Invalid Anomaly folder: {directory} does not contain "
                "AnomalyLauncher.exe.\n"
                "Install the base game first (anomaly-install) — it's the path "
                "MO2 needs to know as `gamePath`."
            ).format(directory=anomaly_dir)
        )


class ModlistSyncError(Mo2Error):
    """Le `modlist.txt` du profil (ou son instantané amont) n'a pas pu être lu/écrit.

    Jamais fatale pour la mise à jour qui l'entoure : quand elle survient,
    l'amont est déjà en place et la sauvegarde d'avant-update aussi — c'est un
    confort perdu, pas une donnée. L'appelant la rapporte en avertissement.
    """

    def __init__(self, path: Path, error: OSError) -> None:
        self.path = path
        self.error = error
        super().__init__(
            _("Could not read or write the mod list {path}: {error}").format(path=path, error=error)
        )
