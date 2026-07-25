"""Espace disque disponible pour une cible d'installation — indépendant de GTK.

Une installation GAMMA complète pèse lourd : Anomaly (~12 Gio) + cache
d'archives (~40 Gio) + mods extraits (~100 Gio), plus la marge de travail
pendant l'extraction. Les seuils ci-dessous suivent la recommandation amont
(Grokitach) d'environ 250 Go libres pour une installation sereine.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from stalker_gamma_linux.gui.format import format_gib

MINIMUM_FREE_BYTES = 160 * 1024**3
RECOMMENDED_FREE_BYTES = 250 * 1024**3


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
    def free_label(self) -> str:
        if self.free_bytes is None:
            return "espace libre inconnu"
        return f"{format_gib(self.free_bytes)} libres"


def verdict_for(free_bytes: int) -> SpaceVerdict:
    if free_bytes < MINIMUM_FREE_BYTES:
        return SpaceVerdict.INSUFFICIENT
    if free_bytes < RECOMMENDED_FREE_BYTES:
        return SpaceVerdict.TIGHT
    return SpaceVerdict.OK


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
