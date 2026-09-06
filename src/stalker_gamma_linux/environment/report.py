"""Construction et rendu du rapport d'environnement (commande `doctor`)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from stalker_gamma_linux.environment import checks
from stalker_gamma_linux.environment.distro import detect_distro
from stalker_gamma_linux.environment.models import EnvironmentReport, Requirement, Status
from stalker_gamma_linux.environment.plan import build_install_plan, format_install_plan
from stalker_gamma_linux.i18n import _

DEFAULT_INSTALL_TARGET = Path.home() / "Games" / "stalker-gamma"

_STATUS_LABEL = {
    Status.OK: _("[ OK ]"),
    Status.MISSING: _("[MISSING]"),
    Status.OUTDATED: _("[OUTDATED]"),
    Status.UNAVAILABLE: _("[ INFO ]"),
    Status.OPTIONAL: _("[OPTIONAL]"),
}


def build_report(target: Path | None = None) -> EnvironmentReport:
    distro = detect_distro()
    family = distro.family
    resolved_target = target if target is not None else DEFAULT_INSTALL_TARGET

    # Chaque vérification est indépendante (aucun état partagé entre elles) et
    # dominée par de l'attente I/O — sous-processus (`flatpak info`, `protontricks
    # --version`, `ldconfig -p`, `vulkaninfo --summary`) ou disque — donc le GIL est
    # relâché pendant l'essentiel de leur durée : les lancer sur des threads réduit
    # la latence totale à celle du check le plus lent au lieu de leur somme, sans
    # risque de concurrence. On soumet dans l'ordre du tuple ci-dessous et on relit
    # les `Future` dans ce même ordre (pas celui, non déterministe, de leur
    # achèvement) pour que l'ordre d'affichage du rapport reste stable.
    checks_to_run: tuple[Callable[[], Requirement], ...] = (
        lambda: checks.check_steam(family),
        lambda: checks.check_umu(family),
        lambda: checks.check_protontricks(family),
        lambda: checks.check_7z(family),
        lambda: checks.check_libunrar(family),
        lambda: checks.check_disk_space(resolved_target),
        lambda: checks.check_vulkan(family),
        lambda: checks.check_gamemode(family),
    )
    with ThreadPoolExecutor(max_workers=len(checks_to_run)) as executor:
        futures = [executor.submit(check) for check in checks_to_run]
        # `Future.result()` relève toute exception survenue dans le thread : rien
        # ne peut donc s'échapper du pool sous une forme non gérée. En pratique
        # chaque fonction de `checks` attrape déjà ses propres erreurs (`system.run`
        # renvoie un `CompletedProcess` d'échec plutôt que de lever), ce comportement
        # est simplement préservé, pas modifié, par le passage en parallèle.
        requirements = tuple(future.result() for future in futures)

    return EnvironmentReport(distro=distro, requirements=requirements)


def format_report(report: EnvironmentReport) -> str:
    lines = [
        _("Distribution: {name} ({family})").format(
            name=report.distro.pretty_name, family=report.distro.family.value
        ),
        "",
    ]
    for requirement in report.requirements:
        label = _STATUS_LABEL[requirement.status]
        lines.append(f"{label} {requirement.name} — {requirement.detail}")
    lines.append("")
    if report.is_ready:
        lines.append(_("All prerequisites are satisfied."))
    else:
        # Un seul bloc « voici la commande à lancer » plutôt qu'une ligne de
        # remède éparpillée sous chaque prérequis (cf. environment.plan).
        lines.append(_("Missing prerequisites."))
        lines.extend(format_install_plan(build_install_plan(report, report.distro.family)))
    return "\n".join(lines)


def run_doctor(target: Path | None = None) -> int:
    report = build_report(target)
    print(format_report(report))
    return 0 if report.is_ready else 1
