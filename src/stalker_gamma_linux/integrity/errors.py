"""Exceptions typées pour la vérification d'intégrité des mods installés."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.i18n import _


class IntegrityError(Exception):
    """Erreur de base pour tout ce qui concerne l'intégrité de l'install."""


class ModsDirectoryMissingError(IntegrityError):
    """`<install>/gamma/mods` est absent : il n'y a rien à vérifier."""

    def __init__(self, mods_dir: Path) -> None:
        self.mods_dir = mods_dir
        super().__init__(
            _(
                "No mods directory at {path}.\n"
                "→ Nothing to check yet: install GAMMA first "
                "(`stalker-gamma-linux install`), or point --target at the right "
                "install directory."
            ).format(path=mods_dir)
        )


class BaselineReadError(IntegrityError):
    """Le fichier de référence existe mais n'a pas pu être lu."""

    def __init__(self, path: Path, error: OSError) -> None:
        self.path = path
        self.error = error
        super().__init__(
            _(
                "Could not read the reference fingerprint {path}: {error}.\n"
                "→ Check the file's permissions, or delete it to record a new "
                "reference on the next run."
            ).format(path=path, error=error)
        )


class BaselineWriteError(IntegrityError):
    """Le fichier de référence n'a pas pu être écrit (disque plein, droits)."""

    def __init__(self, path: Path, error: OSError) -> None:
        self.path = path
        self.error = error
        super().__init__(
            _(
                "Could not write the reference fingerprint {path}: {error}.\n"
                "→ The previous reference, if any, is left untouched. Free some "
                "space or check permissions, then run the check again."
            ).format(path=path, error=error)
        )


class IntegrityCancelledError(IntegrityError):
    """Le scan a été interrompu via `cancel_event` (GUI) ou Ctrl-C.

    Levée plutôt que retournée : c'est ce qui garantit structurellement qu'un
    scan partiel ne peut pas atteindre `write_baseline` et figer une install
    potentiellement cassée comme nouvelle référence.
    """

    def __init__(self) -> None:
        super().__init__(_("Integrity check cancelled — the reference was left untouched."))


class RepairFailedError(IntegrityError):
    """La suppression d'un mod (ou de son archive) a échoué : on n'enchaîne pas.

    Enchaîner sur le moteur après un retrait raté produirait une install dans
    un état intermédiaire sans que personne l'ait décidé.
    """

    def __init__(self, mod: str, reason: str) -> None:
        self.mod = mod
        self.reason = reason
        super().__init__(
            _(
                "Could not repair « {mod} »: {reason}.\n"
                "→ The repair stopped there and the engine was not re-run. Check "
                "the permissions on the mods and downloads directories, then run "
                "the repair again."
            ).format(mod=mod, reason=reason)
        )


class ModpackDefinitionMissingError(IntegrityError):
    """Pas de liste modpack amont locale : impossible de savoir quoi est réparable."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            _(
                "No local modpack definition at {path}.\n"
                "→ Without the upstream mod list, no mod folder can be told apart "
                "from one you added yourself, so nothing is repaired. Run "
                "`stalker-gamma-linux update` once to fetch it."
            ).format(path=path)
        )
