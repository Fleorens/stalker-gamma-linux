"""Commande utilisateur `shortcut` : installe/actualise le raccourci bureau."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.desktop.errors import DesktopError
from stalker_gamma_linux.desktop.install import install_shortcut
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET as DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.i18n import _


def run_shortcut(target: Path | None = None) -> int:
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    try:
        paths = install_shortcut(root)
    except DesktopError as error:
        print(_("Error: {error}").format(error=error))
        return 1

    print(
        _(
            "Desktop shortcut created/updated: {desktop_file}\n"
            "It shows up in your desktop environment's application menu.\n\n"
            "To also add GAMMA to your Steam library (Steam Input, Gaming Mode on "
            "the Steam Deck), artwork included, with Steam closed:\n"
            "  stalker-gamma-linux steam-shortcut\n"
            "`--remove` takes it back out."
        ).format(desktop_file=paths.desktop_file)
    )
    return 0
