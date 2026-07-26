"""Exceptions typées pour le raccourci bureau."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.i18n import _


class DesktopError(Exception):
    """Erreur de base pour l'installation du raccourci bureau."""


class DesktopWriteError(DesktopError):
    """Écriture de l'icône ou du fichier `.desktop` impossible (permissions, disque plein…)."""

    def __init__(self, path: Path, cause: OSError) -> None:
        self.path = path
        self.cause = cause
        super().__init__(_("Could not write {path}: {cause}").format(path=path, cause=cause))
