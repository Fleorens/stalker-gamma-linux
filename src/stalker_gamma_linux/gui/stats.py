"""Chiffres de l'accueil (mods actifs / installés, version) — indépendant de GTK.

Ce que l'accueil affiche en tuiles, à côté de l'espace disque de `space.py` :
de quoi voir d'un coup d'œil que l'installation est *réelle*, sans ouvrir le
Diagnostic. Comme `space.py`, ce module ne fait que lire — la collecte tourne
dans le thread de sondage de la fenêtre principale, jamais sur le fil GTK.

La tuile « Mods » affiche une **fraction** (« 579 / 728 ») parce qu'un seul
nombre se lisait mal : le compte des dossiers déployés est toujours supérieur
à ce qu'affiche Mod Organizer, qui ne compte que les mods **activés** dans le
profil. Les séparateurs sont exclus des *deux* nombres (voir `mo2.modlist`) :
ce ne sont pas des mods, ils ne peuvent jamais être « actifs », et les laisser
au dénominateur donnerait une fraction que le numérateur ne peut pas atteindre.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from stalker_gamma_linux.gui.format import UNKNOWN
from stalker_gamma_linux.mo2.instance import GAMMA_PROFILE
from stalker_gamma_linux.mo2.modlist import enabled_mods, modlist_path, read_modlist
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.report_bundle import DISTRIBUTION_NAME

# Suffixe des dossiers-séparateurs de MO2 (`mo2.modlist`) : de vrais dossiers
# sous `mods/`, mais des intercalaires visuels, pas des mods.
_SEPARATOR_SUFFIX = "_separator"


@dataclass(frozen=True, slots=True)
class InstallStats:
    """Ce que les tuiles de l'accueil ont besoin de savoir."""

    mod_count: int | None
    active_mod_count: int | None
    version: str

    @property
    def mods_label(self) -> str:
        """« 579 / 728 », ou le seul nombre connu, ou le marqueur d'inconnu.

        Le repli sur le nombre installé seul n'est pas théorique : entre la pose
        des mods et la première écriture du profil, `modlist.txt` n'existe pas
        encore — mieux vaut un nombre juste qu'une fraction inventée.
        """
        if self.mod_count is None:
            return UNKNOWN
        if self.active_mod_count is None:
            return str(self.mod_count)
        return f"{self.active_mod_count} / {self.mod_count}"


def count_mods(root: Path) -> int | None:
    """Nombre de mods déployés sous `<root>/gamma/mods`, ou `None` si illisible.

    Un `scandir`, pas un parcours récursif : MO2 pose un dossier par mod à plat,
    et descendre dans les quelque 400 dossiers d'une install complète coûterait
    des dizaines de milliers de `stat` pour la même réponse. Les séparateurs se
    reconnaissent au nom, sans ouvrir leur `meta.ini`.
    """
    try:
        with os.scandir(Mo2Paths.under(root).mods) as entries:
            return sum(
                1
                for entry in entries
                if entry.is_dir() and not entry.name.endswith(_SEPARATOR_SUFFIX)
            )
    except OSError:
        return None


def count_active_mods(root: Path) -> int | None:
    """Mods activés dans le profil `G.A.M.M.A`, ou `None` si le profil n'a pas de modlist.

    C'est le nombre que Mod Organizer affiche lui-même. `None` et `0` ne disent
    pas la même chose : un `modlist.txt` absent est une install qui n'a pas
    encore de profil, un modlist vide est une install que MO2 ne chargera pas —
    d'où le test d'existence plutôt que la seule lecture (`read_modlist` rend
    un tuple vide dans les deux cas).
    """
    profile = Mo2Paths.under(root).profile(GAMMA_PROFILE)
    if not modlist_path(profile).is_file():
        return None
    return len(enabled_mods(read_modlist(profile)))


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
    return InstallStats(
        mod_count=count_mods(root),
        active_mod_count=count_active_mods(root),
        version=version_label(),
    )
