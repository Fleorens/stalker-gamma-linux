"""Point d'entrée console `stalker-gamma-linux-gui`.

Cible du script `[project.scripts]` (pas `gui.app`) : vérifie GTK4/libadwaita
*avant* d'importer quoi que ce soit qui déclenche `import gi` — un PyGObject
absent doit produire un message actionnable sur stderr (même détection que
la ligne « GTK GUI » de `doctor`), jamais un traceback `ModuleNotFoundError`
brut. La CLI (`cli.py`) n'importe jamais ce module ni `gui/`.
"""

from __future__ import annotations

import sys

from stalker_gamma_linux.environment.checks import check_gtk_gui
from stalker_gamma_linux.environment.distro import detect_distro
from stalker_gamma_linux.environment.models import Status


def main() -> int:
    requirement = check_gtk_gui(detect_distro().family)
    if requirement.status is not Status.OK:
        print(f"stalker-gamma-linux-gui : {requirement.detail}", file=sys.stderr)
        if requirement.install_hint is not None:
            print(f"→ {requirement.install_hint}", file=sys.stderr)
        return 1

    from stalker_gamma_linux.gui.app import run_app

    return run_app()
