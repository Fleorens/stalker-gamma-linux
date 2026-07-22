"""Raccourci bureau (T06) : entrée freedesktop `.desktop` + icône.

Pas d'intégration Steam automatisée (abandon de l'écriture `shortcuts.vdf` —
cf. docs/ROADMAP.md) : ce module se limite à un raccourci standard dans le
menu applications. L'ajout éventuel à Steam (utile pour Steam Input ou le
mode Gaming sur Deck) reste manuel, via le bouton natif *Ajouter un jeu
non-Steam* de Steam pointant sur la même commande.
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
