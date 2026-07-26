"""Commande utilisateur `shortcut` : installe/actualise le raccourci bureau."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.desktop.errors import DesktopError
from stalker_gamma_linux.desktop.install import install_shortcut, launch_command
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET as DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.i18n import _


def run_shortcut(target: Path | None = None) -> int:
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    try:
        paths = install_shortcut(root)
    except DesktopError as error:
        print(_("Error: {error}").format(error=error))
        return 1

    executable, *launch_options = launch_command(root)
    print(
        _(
            "Desktop shortcut created/updated: {desktop_file}\n"
            "It shows up in your desktop environment's application menu.\n\n"
            "To also add it to Steam (useful for Steam Input or Gaming Mode on "
            "the Steam Deck): Steam → Add a Game → Add a Non-Steam Game → Browse, "
            "select:\n  {executable}\n"
            "then, in that Steam entry's properties, set the launch options "
            "to:\n  {launch_options}\n"
            "Steam then handles the artwork and compat tool choice itself."
        ).format(
            desktop_file=paths.desktop_file,
            executable=executable,
            launch_options=" ".join(launch_options),
        )
    )
    return 0
