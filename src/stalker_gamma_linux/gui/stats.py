"""Chiffres de l'accueil (mods installés, version) — indépendant de GTK.

Ce que l'accueil affiche en tuiles, à côté de l'espace disque de `space.py` :
de quoi voir d'un coup d'œil que l'installation est *réelle*, sans ouvrir le
Diagnostic. Comme `space.py`, ce module ne fait que lire — la collecte tourne
dans le thread de sondage de la fenêtre principale, jamais sur le fil GTK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from stalker_gamma_linux.gui.format import UNKNOWN
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.report_bundle import DISTRIBUTION_NAME


@dataclass(frozen=True, slots=True)
class InstallStats:
    """Ce que les tuiles de l'accueil ont besoin de savoir."""

    mod_count: int | None
    version: str

    @property
    def mods_label(self) -> str:
        return UNKNOWN if self.mod_count is None else str(self.mod_count)


def count_mods(root: Path) -> int | None:
    """Nombre de mods déployés sous `<root>/gamma/mods`, ou `None` si illisible.

    Un `scandir`, pas un parcours récursif : MO2 pose un dossier par mod à plat,
    et descendre dans les quelque 400 dossiers d'une install complète coûterait
    des dizaines de milliers de `stat` pour la même réponse.
    """
    try:
        with os.scandir(Mo2Paths.under(root).mods) as entries:
            return sum(1 for entry in entries if entry.is_dir())
    except OSError:
        return None


def version_label() -> str:
    """Version courte du launcher, pour une tuile — pas la ligne de rapport.

    `report_bundle.version_line()` répond « stalker-gamma-linux 0.6.0 (rév. …) » :
    juste pour un « À propos », trop long pour une tuile.
    """
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:  # exécution depuis les sources, sans `pip install`
        return UNKNOWN


def collect(root: Path) -> InstallStats:
    """Tout ce que les tuiles affichent, en une passe."""
    return InstallStats(mod_count=count_mods(root), version=version_label())
