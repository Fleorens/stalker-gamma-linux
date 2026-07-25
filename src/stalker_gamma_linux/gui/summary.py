"""Résumé « système prêt ? » affiché sur l'accueil — indépendant de GTK.

Compresse un `EnvironmentReport` (7 prérequis détaillés) en une seule puce
lisible d'un coup d'œil : prêt, ou N prérequis bloquants avec leurs noms.
La collecte elle-même (`environment.report.build_report`, plusieurs
sous-process) reste à la charge de l'appelant, dans un thread.
"""

from __future__ import annotations

from dataclasses import dataclass

from stalker_gamma_linux.environment.models import EnvironmentReport


@dataclass(frozen=True, slots=True)
class SystemSummary:
    blocking: tuple[str, ...]  # noms des prérequis MANQUANT/ANCIEN, ordre du rapport

    @property
    def is_ready(self) -> bool:
        return not self.blocking

    @property
    def label(self) -> str:
        if self.is_ready:
            return "Système prêt"
        if len(self.blocking) == 1:
            return f"Prérequis manquant : {self.blocking[0]}"
        return f"{len(self.blocking)} prérequis manquants"


def summarize(report: EnvironmentReport) -> SystemSummary:
    return SystemSummary(
        blocking=tuple(
            requirement.name
            for requirement in report.requirements
            if requirement.status.is_blocking
        )
    )
