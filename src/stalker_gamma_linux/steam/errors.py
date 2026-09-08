"""Exceptions typées pour l'intégration Steam (`shortcuts.vdf`, artwork)."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.i18n import _


class SteamError(Exception):
    """Erreur de base pour tout ce qui touche à l'intégration Steam."""


class VdfFormatError(SteamError):
    """`shortcuts.vdf` illisible : octet de type inconnu, bloc tronqué, imbrication absurde.

    Porte l'offset fautif : sur un format binaire, « le fichier est invalide »
    sans position ne permet ni de diagnostiquer ni de rapporter un bug utile.
    """

    def __init__(self, path: Path | None, offset: int, reason: str) -> None:
        self.path = path
        self.offset = offset
        self.reason = reason
        where = str(path) if path is not None else _("<in memory>")
        super().__init__(
            _("Unreadable shortcuts.vdf ({path}, byte {offset}): {reason}").format(
                path=where, offset=offset, reason=reason
            )
        )


class SteamWriteError(SteamError):
    """Écriture impossible (permissions, disque plein, sauvegarde `.bak` refusée)."""

    def __init__(self, path: Path, cause: OSError) -> None:
        self.path = path
        self.cause = cause
        super().__init__(_("Could not write {path}: {cause}").format(path=path, cause=cause))


class SteamRunningError(SteamError):
    """Steam tourne : il réécrira `shortcuts.vdf` en quittant et effacerait notre travail."""

    def __init__(self, pid: int, name: str) -> None:
        self.pid = pid
        self.name = name
        super().__init__(
            _(
                "Steam is running ({name}, PID {pid}). Steam keeps shortcuts.vdf in "
                "memory and rewrites it when it exits, which would silently undo this "
                "change.\nQuit Steam completely (Steam → Exit, not just the window), "
                "then run this command again — or pass --force to write anyway."
            ).format(name=name, pid=pid)
        )


class NoSteamAccountError(SteamError):
    """Aucun compte Steam trouvé : rien à quoi ajouter un raccourci."""

    def __init__(self) -> None:
        super().__init__(
            _(
                "No Steam account found on this machine.\n"
                "Steam stores its shortcuts per account, under "
                "userdata/<id>/config/ — that directory only appears once Steam has "
                "been installed and signed into at least once.\n"
                "Install Steam, sign in, quit it, then run this command again."
            )
        )
