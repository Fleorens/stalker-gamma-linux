"""État de l'installation pour la fenêtre principale — indépendant de GTK.

Ne lit que `state.py` (un petit TOML local, quasi instantané) : le rapport
complet (`doctor.build_full_report`, plusieurs sous-process — `which`,
`ldconfig`, `vulkaninfo`…) n'est nécessaire qu'à l'ouverture de la vue
Diagnostic, jamais pour rafraîchir la fenêtre principale — sinon chaque
rafraîchissement du statut ferait geler l'UI le temps de ces sous-process.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET

# `shortcut` (T06) est optionnelle : son absence ne doit jamais empêcher `play`.
_CORE_STEPS: tuple[str, ...] = tuple(step for step in state_module.STEPS if step != "shortcut")


class InstallStatus(Enum):
    NOT_INSTALLED = auto()
    INSTALLED = auto()


def install_status(install_state: state_module.InstallState) -> InstallStatus:
    if all(install_state.is_done(step) for step in _CORE_STEPS):
        return InstallStatus.INSTALLED
    return InstallStatus.NOT_INSTALLED


@dataclass(frozen=True, slots=True)
class MainWindowState:
    """Ce qu'affiche la fenêtre principale : cible résolue, statut, étapes brutes."""

    target: Path
    status: InstallStatus
    install: state_module.InstallState

    @property
    def primary_action_label(self) -> str:
        return "Jouer" if self.status is InstallStatus.INSTALLED else "Installer"

    @property
    def is_installed(self) -> bool:
        return self.status is InstallStatus.INSTALLED


def load_main_window_state(target: Path | None) -> MainWindowState:
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install_state = state_module.load_state(root)
    return MainWindowState(
        target=root, status=install_status(install_state), install=install_state
    )
