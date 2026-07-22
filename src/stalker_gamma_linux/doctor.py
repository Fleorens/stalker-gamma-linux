"""Rapport de diagnostic global (commande `doctor`) : environnement + préfixe + installation.

Compose les rapports déjà produits par `environment.report` (T02) et
`prefix.doctor` (T04), et y ajoute l'état d'installation persisté (`state.py`,
T07). Le code de retour ne reflète que les prérequis système
(`environment.report.build_report`) : le préfixe et l'installation peuvent
être légitimement incomplets sur une machine neuve avant `install`, ce n'est
pas un échec de `doctor` — pour ça, `prefix-doctor` reste l'outil de vérité.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.environment.report import (
    DEFAULT_INSTALL_TARGET,
    build_report,
    format_report,
)
from stalker_gamma_linux.output import console
from stalker_gamma_linux.prefix.doctor import build_prefix_report, format_prefix_report
from stalker_gamma_linux.prefix.paths import PrefixPaths


def run_doctor(target: Path | None = None) -> int:
    root = target if target is not None else DEFAULT_INSTALL_TARGET

    env_report = build_report(root)
    console.print("[bold]=== Environnement ===[/bold]")
    console.print(format_report(env_report))

    prefix_report = build_prefix_report(PrefixPaths.under(root))
    console.print("\n[bold]=== Préfixe Proton ===[/bold]")
    console.print(format_prefix_report(prefix_report))

    install_state = state_module.load_state(root)
    console.print("\n[bold]=== Installation ===[/bold]")
    console.print(state_module.format_state(install_state, root))

    return 0 if env_report.is_ready else 1
