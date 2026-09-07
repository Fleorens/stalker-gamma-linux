"""Rotation des sauvegardes automatiques : un plafond, et une seule règle dure.

`<root>/backups/` grossissait indéfiniment — une copie complète des profils
avant *chaque* mise à jour, jamais purgée. On plafonne donc les sauvegardes
**automatiques**, et on retire les plus anciennes au-delà.

Deux garde-fous qui ne se négocient pas :

1. **Une sauvegarde explicite n'entre jamais dans la rotation.** L'utilisateur
   qui a tapé `stalker-gamma-linux backup` avant de bricoler son ordre de
   chargement a créé un point de retour, pas un cache. Le manifeste porte ce
   drapeau (`explicit`), et c'est le seul critère.
2. **Toute suppression passe par `paths_safety`.** C'est un `rmtree` sur un
   chemin dérivé de `--target` : exactement le périmètre de T11. Le nom vient
   d'un `iterdir`, donc pas de l'utilisateur — mais un lien symbolique posé
   dans `backups/` suffirait à faire sortir la suppression du dossier, et
   `validate_removable_child` est justement ce qui ferme ça.

Les sauvegardes d'avant le manifeste comptent comme automatiques : c'est ce
qu'elles étaient (une copie posée avant chaque `update`), et ce sont
précisément celles qui se sont accumulées.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.backups.listing import Listing, StoredBackup, list_backups
from stalker_gamma_linux.backups.paths import backups_root
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.logging_setup import LOGGER_NAME
from stalker_gamma_linux.paths_safety import validate_removable_child

_logger = logging.getLogger(LOGGER_NAME)

# Cinq mises à jour de recul : assez pour revenir sur une régression repérée
# quelques sessions plus tard, assez peu pour ne pas laisser dix copies des
# profils sur un disque déjà chargé de 146 Gio de jeu.
DEFAULT_KEEP = 5


@dataclass(frozen=True, slots=True)
class RotationResult:
    """Ce que la rotation a retiré, et ce qu'elle n'a pas pu retirer."""

    removed: tuple[str, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.removed and not self.failed

    @property
    def summary(self) -> str:
        return _("Rotation: {count} old automatic backup(s) removed ({names}).").format(
            count=len(self.removed), names=", ".join(self.removed)
        )


def surplus(listing: Listing, *, keep: int = DEFAULT_KEEP) -> tuple[StoredBackup, ...]:
    """Sauvegardes automatiques au-delà du plafond, de la plus ancienne à la plus récente.

    Pure : ne touche pas au disque. `listing.automatic` est déjà trié du plus
    récent au plus ancien, donc tout ce qui suit les `keep` premiers est en
    trop.
    """
    if keep < 0:
        return ()
    return tuple(reversed(listing.automatic[keep:]))


def rotate(root: Path, *, keep: int = DEFAULT_KEEP) -> RotationResult:
    """Retire les sauvegardes automatiques excédentaires sous `<root>/backups/`.

    Ne lève pas sur une suppression impossible (permissions, montage occupé) :
    une rotation ratée ne doit jamais faire échouer la mise à jour qu'elle
    accompagne. Elle est en revanche **rapportée**, sinon le dossier
    regrossirait sans que personne ne le sache. Un refus de sûreté
    (`UnsafeWipeTargetError`), lui, remonte : ce n'est pas un aléa, c'est un
    chemin qui n'aurait jamais dû arriver là.
    """
    parent = backups_root(root)
    removed: list[str] = []
    failed: list[tuple[str, str]] = []
    for backup in surplus(list_backups(root), keep=keep):
        # Résolu et validé une seule fois, juste avant le `rmtree` : c'est
        # exactement ce chemin-là qui est supprimé (même règle qu'`uninstall`).
        target = validate_removable_child(parent, backup.identifier)
        if target is None:
            continue  # déjà parti entre le listing et ici : rien à faire
        try:
            shutil.rmtree(target)
        except OSError as error:
            _logger.warning("could not rotate backup %s: %s", target, error)
            failed.append((backup.identifier, str(error)))
            continue
        removed.append(backup.identifier)
    return RotationResult(removed=tuple(removed), failed=tuple(failed))
