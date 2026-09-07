"""Espace disque disponible pour une cible d'installation — indépendant de GTK.

Les seuils viennent de `sizing` (source unique, partagée avec la ligne « Espace
disque » de `doctor` via `environment.checks`) : la GUI et la CLI doivent rendre
le même verdict sur la même machine.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from stalker_gamma_linux.gui.format import UNKNOWN, format_gib
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.sizing import MINIMUM_FREE_BYTES, RECOMMENDED_FREE_BYTES

__all__ = [
    "MINIMUM_FREE_BYTES",
    "RECOMMENDED_FREE_BYTES",
    "SpaceReport",
    "SpaceVerdict",
    "assess",
    "gauge_fraction",
    "nearest_existing_parent",
    "verdict_for",
]


class SpaceVerdict(Enum):
    OK = auto()  # >= recommandé : rien à signaler
    TIGHT = auto()  # entre minimum et recommandé : possible mais juste
    INSUFFICIENT = auto()  # < minimum : l'installation échouera en cours de route
    UNKNOWN = auto()  # volume illisible (chemin réseau coupé, permission…)


@dataclass(frozen=True, slots=True)
class SpaceReport:
    free_bytes: int | None
    verdict: SpaceVerdict

    @property
    def free_size(self) -> str:
        """La taille seule (« 493 Gio ») — pour une tuile déjà étiquetée « espace libre »."""
        if self.free_bytes is None:
            return UNKNOWN
        return format_gib(self.free_bytes)

    @property
    def free_label(self) -> str:
        if self.free_bytes is None:
            return _("unknown free space")
        return _("{size} free").format(size=format_gib(self.free_bytes))


def verdict_for(free_bytes: int) -> SpaceVerdict:
    if free_bytes < MINIMUM_FREE_BYTES:
        return SpaceVerdict.INSUFFICIENT
    if free_bytes < RECOMMENDED_FREE_BYTES:
        return SpaceVerdict.TIGHT
    return SpaceVerdict.OK


def gauge_fraction(report: SpaceReport) -> float:
    """Part du recommandé déjà couverte par l'espace libre, plafonnée à 1.

    Le repère est `RECOMMENDED_FREE_BYTES` et non le minimum : une jauge pleine
    doit vouloir dire « confortable », pas « ça passe tout juste ». Un volume
    illisible rend 0 — une jauge vide dit la même chose que le libellé.
    """
    if report.free_bytes is None:
        return 0.0
    return min(1.0, report.free_bytes / RECOMMENDED_FREE_BYTES)


def nearest_existing_parent(path: Path) -> Path:
    """Premier ancêtre existant de `path` — la cible n'existe pas encore avant install."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path("/")


def assess(target: Path) -> SpaceReport:
    """Rapport d'espace libre sur le volume qui hébergera `target`."""
    try:
        free = shutil.disk_usage(nearest_existing_parent(target)).free
    except OSError:
        return SpaceReport(free_bytes=None, verdict=SpaceVerdict.UNKNOWN)
    return SpaceReport(free_bytes=free, verdict=verdict_for(free))
