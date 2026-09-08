"""Raccourci bureau (T06) : entrée freedesktop `.desktop` + icône.

Ce module se limite au menu applications. L'ajout à la **bibliothèque Steam**
(entrée + artwork, utile pour Steam Input et le mode Gaming sur Deck) a son
propre paquet depuis T19 : `stalker_gamma_linux.steam`. Les deux restent
distincts — puits différents, échecs différents — et l'entrée `.desktop`
« jouer en direct » garde son intérêt propre, y compris comme cible du bouton
natif *Ajouter un jeu non-Steam*.
"""

from stalker_gamma_linux.desktop.errors import DesktopError, DesktopWriteError
from stalker_gamma_linux.desktop.install import install_shortcut, launch_command
from stalker_gamma_linux.desktop.paths import DesktopPaths
from stalker_gamma_linux.desktop.session import run_shortcut

__all__ = [
    "DesktopError",
    "DesktopPaths",
    "DesktopWriteError",
    "install_shortcut",
    "launch_command",
    "run_shortcut",
]
