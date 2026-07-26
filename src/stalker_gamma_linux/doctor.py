"""Rapport de diagnostic global (commande `doctor`) : environnement + préfixe + installation.

Compose les rapports déjà produits par `environment.report` (T02) et
`prefix.doctor` (T04), et y ajoute l'état d'installation persisté (`state.py`,
T07). Le code de retour ne reflète que les prérequis système
(`environment.report.build_report`) : le préfixe et l'installation peuvent
être légitimement incomplets sur une machine neuve avant `install`, ce n'est
pas un échec de `doctor` — pour ça, `prefix-doctor` reste l'outil de vérité.

`build_full_report` (T08) sépare la collecte (réutilisée telle quelle par la
vue Diagnostic de la GUI, `Requirement` par `Requirement`, avec ses
`install_hint` copiables) du rendu texte : `run_doctor` (CLI) est la seule
fonction de ce module qui imprime quoi que ce soit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux import presence
from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.environment.models import EnvironmentReport
from stalker_gamma_linux.environment.report import (
    DEFAULT_INSTALL_TARGET,
    build_report,
    format_report,
)
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.output import console
from stalker_gamma_linux.prefix.doctor import (
    PrefixReport,
    build_prefix_report,
    format_prefix_report,
)
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.state import InstallState


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Rapport composite prêt à être rendu par la CLI (texte) ou la GUI (widgets)."""

    target: Path
    environment: EnvironmentReport
    prefix: PrefixReport
    install: InstallState
    # Install GAMMA réellement présente sur le disque (fichiers du jeu), même si
    # elle n'est pas passée par notre pipeline (`install` vide dans ce cas).
    installed_on_disk: bool = False

    @property
    def is_ready(self) -> bool:
        """Reflète uniquement les prérequis système, comme `run_doctor` historiquement."""
        return self.environment.is_ready


def build_full_report(target: Path | None = None) -> DoctorReport:
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    return DoctorReport(
        target=root,
        environment=build_report(root),
        prefix=build_prefix_report(PrefixPaths.under(root)),
        install=state_module.load_state(root),
        installed_on_disk=presence.is_installed_on_disk(root),
    )


def run_doctor(target: Path | None = None) -> int:
    report = build_full_report(target)

    console.print(f"[bold]=== {_('Environment')} ===[/bold]")
    console.print(format_report(report.environment))

    console.print(f"\n[bold]=== {_('Proton prefix')} ===[/bold]")
    console.print(format_prefix_report(report.prefix))

    console.print(f"\n[bold]=== {_('Installation')} ===[/bold]")
    console.print(state_module.format_state(report.install, report.target))
    if report.installed_on_disk:
        console.print(
            "[green]"
            + _(
                "GAMMA install detected on disk (Anomaly + Mod Organizer 2 "
                "present) — usable even if the steps above aren't checked "
                "off (install outside the pipeline)."
            )
            + "[/green]"
        )

    return 0 if report.is_ready else 1
