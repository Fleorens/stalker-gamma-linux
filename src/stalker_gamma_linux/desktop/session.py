"""Commande utilisateur `shortcut` : installe/actualise le raccourci bureau."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.desktop.errors import DesktopError
from stalker_gamma_linux.desktop.install import install_shortcut, launch_command
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET


def run_shortcut(target: Path | None = None) -> int:
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    try:
        paths = install_shortcut(root)
    except DesktopError as error:
        print(f"Erreur : {error}")
        return 1

    executable, *launch_options = launch_command(root)
    print(
        f"Raccourci bureau créé/actualisé : {paths.desktop_file}\n"
        "Il apparaît dans le menu applications de ton environnement de bureau.\n\n"
        "Pour l'ajouter aussi à Steam (utile pour Steam Input ou le mode Gaming sur "
        "Steam Deck) : Steam → Ajouter un jeu → Ajouter un jeu non-Steam → Parcourir, "
        f"sélectionne :\n  {executable}\n"
        "puis, dans les propriétés de cette entrée Steam, mets en options de "
        f"lancement :\n  {' '.join(launch_options)}\n"
        "Steam gère alors l'artwork et le choix du compat tool lui-même."
    )
    return 0
