"""Construction et rendu du rapport d'environnement (commande `doctor`)."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.environment import checks
from stalker_gamma_linux.environment.distro import detect_distro
from stalker_gamma_linux.environment.models import EnvironmentReport, Status
from stalker_gamma_linux.environment.plan import build_install_plan, format_install_plan

DEFAULT_INSTALL_TARGET = Path.home() / "Games" / "stalker-gamma"

_STATUS_LABEL = {
    Status.OK: "[ OK ]",
    Status.MISSING: "[MANQUANT]",
    Status.OUTDATED: "[ANCIEN]",
    Status.UNAVAILABLE: "[ INFO ]",
    Status.OPTIONAL: "[ OPTION ]",
}


def build_report(target: Path | None = None) -> EnvironmentReport:
    distro = detect_distro()
    family = distro.family
    resolved_target = target if target is not None else DEFAULT_INSTALL_TARGET
    requirements = (
        checks.check_steam(family),
        checks.check_umu(family),
        checks.check_protontricks(family),
        checks.check_7z(family),
        checks.check_libunrar(family),
        checks.check_disk_space(resolved_target),
        checks.check_vulkan(family),
    )
    return EnvironmentReport(distro=distro, requirements=requirements)


def format_report(report: EnvironmentReport) -> str:
    lines = [f"Distribution : {report.distro.pretty_name} ({report.distro.family.value})", ""]
    for requirement in report.requirements:
        label = _STATUS_LABEL[requirement.status]
        lines.append(f"{label} {requirement.name} — {requirement.detail}")
    lines.append("")
    if report.is_ready:
        lines.append("Tous les prérequis sont satisfaits.")
    else:
        # Un seul bloc « voici la commande à lancer » plutôt qu'une ligne de
        # remède éparpillée sous chaque prérequis (cf. environment.plan).
        lines.append("Prérequis manquants.")
        lines.extend(format_install_plan(build_install_plan(report, report.distro.family)))
    return "\n".join(lines)


def run_doctor(target: Path | None = None) -> int:
    report = build_report(target)
    print(format_report(report))
    return 0 if report.is_ready else 1
