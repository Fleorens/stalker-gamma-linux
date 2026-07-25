"""Fusionne les prérequis manquants en un plan d'action minimal.

Au lieu d'une ligne « → sudo dnf install X » par prérequis (mur illisible), on
regroupe tous les paquets natifs manquants en **une seule** commande à
copier-coller, et on liste à part ce qui n'a pas de paquet système (zipapp
umu-launcher, espace disque…). Consommé tel quel par le rendu CLI
(`report.format_report`) et par la vue Diagnostic de la GUI.
"""

from __future__ import annotations

from dataclasses import dataclass

from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS, PACKAGE_MANAGER
from stalker_gamma_linux.environment.distro import DistroFamily
from stalker_gamma_linux.environment.models import EnvironmentReport


@dataclass(frozen=True, slots=True)
class ManualStep:
    """Un remède sans paquet système : nom du prérequis + commande/instruction."""

    name: str
    command: str


@dataclass(frozen=True, slots=True)
class InstallPlan:
    package_command: str | None
    package_notes: tuple[str, ...]
    manual_steps: tuple[ManualStep, ...]

    @property
    def is_empty(self) -> bool:
        return self.package_command is None and not self.manual_steps


def build_install_plan(report: EnvironmentReport, family: DistroFamily) -> InstallPlan:
    """Assemble le plan à partir des seuls prérequis bloquants du rapport."""
    packages: list[str] = []
    notes: list[str] = []
    manual: list[ManualStep] = []

    for requirement in report.requirements:
        if not requirement.status.is_blocking:
            continue
        command = INSTALL_COMMANDS.get(requirement.key) if requirement.key else None
        native = command.packages.get(family) if command is not None else None
        if native:
            for package in native:
                if package not in packages:
                    packages.append(package)
            if command is not None and command.note and command.note not in notes:
                notes.append(command.note)
        elif requirement.install_hint is not None:
            manual.append(ManualStep(name=requirement.name, command=requirement.install_hint))

    package_command = None
    if packages and family in PACKAGE_MANAGER:
        package_command = f"{PACKAGE_MANAGER[family]} {' '.join(packages)}"

    return InstallPlan(
        package_command=package_command,
        package_notes=tuple(notes),
        manual_steps=tuple(manual),
    )


def format_install_plan(plan: InstallPlan) -> list[str]:
    """Rendu texte (CLI) du plan : bloc paquets groupé puis étapes manuelles."""
    if plan.is_empty:
        return []
    lines = ["", "Pour tout installer d'un coup :"]
    if plan.package_command is not None:
        lines.append(f"    {plan.package_command}")
        for note in plan.package_notes:
            lines.append(f"    ({note})")
    if plan.manual_steps:
        lines.append("")
        lines.append("Puis, sans paquet système :")
        for step in plan.manual_steps:
            lines.append(f"    • {step.name} : {step.command}")
    return lines
