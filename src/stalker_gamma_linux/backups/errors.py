"""Exceptions typées de la sauvegarde/restauration.

Toutes portent le chemin ou l'identifiant concerné : l'appelant (CLI, GUI)
affiche `str(error)` sans avoir à reconstruire le contexte, exactement comme
`mo2.errors` et `integrity.errors`.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.i18n import _


class BackupError(Exception):
    """Erreur de base pour tout ce qui concerne les sauvegardes."""


class NothingToBackUpError(BackupError):
    """Aucun des ensembles demandés n'existe (ou tous sont vides) sous la racine."""

    def __init__(self, root: Path, sets: tuple[str, ...]) -> None:
        self.root = root
        self.sets = sets
        super().__init__(
            _(
                "Nothing to back up under {root}: none of the selected sets "
                "({sets}) holds any file.\n"
                "Install the modpack first, or pick another --target."
            ).format(root=root, sets=", ".join(sets))
        )


class BackupWriteError(BackupError):
    """La sauvegarde n'a pas pu être écrite (disque plein, permissions)."""

    def __init__(self, destination: Path, error: OSError) -> None:
        self.destination = destination
        self.error = error
        super().__init__(
            _("Could not write the backup to {path}: {error}").format(path=destination, error=error)
        )


class ManifestError(BackupError):
    """Le manifeste d'une sauvegarde est illisible ou incohérent.

    Volontairement fatal pour la sauvegarde concernée plutôt que « réparé » au
    jugé : c'est lui qui dit où chaque ensemble doit être remis, et une
    destination inventée écrirait à côté de l'endroit prévu.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(
            _("Unusable backup manifest {path}: {reason}").format(path=path, reason=reason)
        )


class BackupNotFoundError(BackupError):
    """L'identifiant donné à `restore` ne désigne aucune sauvegarde."""

    def __init__(self, identifier: str, root: Path) -> None:
        self.identifier = identifier
        self.root = root
        super().__init__(
            _(
                "No backup named « {identifier} » under {root}.\n"
                "List what is available with `stalker-gamma-linux backup --list`."
            ).format(identifier=identifier, root=root)
        )


class RestoreError(BackupError):
    """La remise en place a échoué en cours de route."""

    def __init__(self, destination: Path, error: OSError) -> None:
        self.destination = destination
        self.error = error
        super().__init__(
            _("Could not restore {path}: {error}").format(path=destination, error=error)
        )
