"""Résumé « système prêt ? » affiché sur l'accueil — indépendant de GTK.

Compresse un `EnvironmentReport` (7 prérequis détaillés) en une seule puce
lisible d'un coup d'œil : prêt, ou N prérequis bloquants avec leurs noms.
La collecte elle-même (`environment.report.build_report`, plusieurs
sous-process) reste à la charge de l'appelant, dans un thread.
"""

from __future__ import annotations

from dataclasses import dataclass

from stalker_gamma_linux.environment.models import EnvironmentReport
from stalker_gamma_linux.i18n import _


@dataclass(frozen=True, slots=True)
class SystemSummary:
    blocking: tuple[str, ...]  # noms des prérequis MANQUANT/ANCIEN, ordre du rapport

    @property
    def is_ready(self) -> bool:
        return not self.blocking

    @property
    def label(self) -> str:
        if self.is_ready:
            return _("System ready")
        if len(self.blocking) == 1:
            return _("Missing prerequisite: {name}").format(name=self.blocking[0])
        return _("{count} missing prerequisites").format(count=len(self.blocking))


def summarize(report: EnvironmentReport) -> SystemSummary:
    return SystemSummary(
        blocking=tuple(
            requirement.name
            for requirement in report.requirements
            if requirement.status.is_blocking
        )
    )
