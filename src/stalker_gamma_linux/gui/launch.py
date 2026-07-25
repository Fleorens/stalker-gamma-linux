"""Point d'entrée console `stalker-gamma-linux-gui`.

Cible du script `[project.scripts]` (pas `gui.app`) : vérifie GTK4/libadwaita
*avant* d'importer quoi que ce soit qui déclenche `import gi` — un PyGObject
absent doit produire un message actionnable sur stderr (même détection que
la ligne « GTK GUI » de `doctor`), jamais un traceback `ModuleNotFoundError`
brut. La CLI (`cli.py`) n'importe jamais ce module ni `gui/`.
"""

from __future__ import annotations

import os
import sys

from stalker_gamma_linux.environment.checks import check_gtk_gui
from stalker_gamma_linux.environment.distro import detect_distro
from stalker_gamma_linux.environment.models import Status


def main() -> int:
    # GTK4 dessine via un renderer GL/Vulkan par défaut. Sur une machine sans
    # GPU utilisable — VM sans accélération 3D, pilote GL cassé, session
    # distante — la fenêtre échoue silencieusement à s'afficher (« rien ne se
    # passe » au clic). Un installeur n'a besoin d'aucune accélération : on
    # bascule sur le renderer logiciel (cairo) par défaut, tout en laissant
    # l'utilisateur forcer autre chose via GSK_RENDERER s'il le souhaite.
    os.environ.setdefault("GSK_RENDERER", "cairo")

    # Même journal rotatif que la CLI (~/.local/state/stalker-gamma-linux/) :
    # sans ça, « voir le journal » après un échec GUI menait à un fichier vide.
    from stalker_gamma_linux import logging_setup

    logging_setup.configure_logging()

    requirement = check_gtk_gui(detect_distro().family)
    if requirement.status is not Status.OK:
        print(f"stalker-gamma-linux-gui : {requirement.detail}", file=sys.stderr)
        if requirement.install_hint is not None:
            print(f"→ {requirement.install_hint}", file=sys.stderr)
        return 1

    from stalker_gamma_linux.gui.app import run_app

    return run_app()
