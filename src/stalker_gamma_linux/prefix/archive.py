"""Extraction d'archives tar sûre, y compris sur les Python sans `filter=`.

`TarFile.extractall(filter="data")` est la façon correcte d'extraire une archive
téléchargée : elle refuse les membres qui s'échappent du répertoire cible
(`../../etc/cron.d/…`), les liens pointant dehors et les fichiers spéciaux.
Mais ce paramètre n'existe **pas** partout dans la plage que le projet déclare
supporter (`requires-python = ">=3.11"`) : introduit en 3.12, il n'a été
rétroporté qu'en 3.11.4 (PEP 706). Debian 12 — distribution mise en avant dans
le README — livre Python **3.11.2**, où l'appel lève `TypeError` et fait échouer
aussi bien l'installation d'umu que celle de Proton-GE.

Le piège est que la CI ne pouvait pas le voir : `setup-python: "3.11"` installe
le dernier correctif de la branche (3.11.9+), qui a le filtre. Seul un vrai
conteneur Debian 12 le reproduit — d'où le job `install-script` de ci.yml.

On ne se contente donc pas de retirer le `filter=` (ce serait rétablir la faille
sur les vieux 3.11) : quand il est absent, on valide nous-mêmes chaque membre
avant extraction, avec les mêmes refus que `data_filter`.
"""

from __future__ import annotations

import os
import tarfile
from pathlib import Path

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.prefix.errors import UnsafeArchiveError

# `data_filter` et le paramètre `filter=` d'`extractall` sont arrivés ensemble :
# tester l'un renseigne sur l'autre, sans dépendre du numéro de version exact.
_HAS_DATA_FILTER = hasattr(tarfile, "data_filter")


def _is_within(base: Path, candidate: str) -> bool:
    """Vrai si `candidate` (relatif à `base`) reste sous `base`, sans toucher au disque.

    On ne résout pas les liens du système de fichiers : la cible n'existe pas
    encore au moment de la validation, et un `resolve()` suivrait des liens
    posés par l'archive elle-même.
    """
    base_str = os.path.normpath(str(base))
    resolved = os.path.normpath(os.path.join(base_str, candidate))
    return resolved == base_str or resolved.startswith(base_str + os.sep)


def _reject(member: tarfile.TarInfo, reason: str) -> None:
    raise UnsafeArchiveError(member.name, reason)


def validate_members(tar: tarfile.TarFile, dest: Path) -> None:
    """Refuse tout membre qu'un `filter="data"` refuserait. Testable seul.

    Extrait de la logique de `tarfile.data_filter` : pas de chemin absolu ni de
    sortie du répertoire cible, pas de lien qui pointe dehors, pas de fichier
    spécial (périphérique, FIFO) — rien de tout ça n'a de sens dans une release
    Proton-GE ou un zipapp umu.
    """
    for member in tar.getmembers():
        if member.name.startswith("/") or os.path.isabs(member.name):
            _reject(member, _("absolute path"))
        if not _is_within(dest, member.name):
            _reject(member, _("path escaping the destination directory"))
        if member.issym() or member.islnk():
            # Un lien symbolique est relatif à son propre répertoire ; un lien
            # physique est relatif à la racine de l'archive.
            anchor = os.path.dirname(member.name) if member.issym() else ""
            if os.path.isabs(member.linkname) or not _is_within(
                dest, os.path.join(anchor, member.linkname)
            ):
                _reject(member, _("link pointing outside the destination directory"))
        elif not (member.isfile() or member.isdir()):
            _reject(member, _("special file (device, FIFO, …)"))


def safe_extractall(tar: tarfile.TarFile, dest: Path) -> None:
    """Extrait `tar` dans `dest` en refusant les membres dangereux, sur tout Python ≥ 3.11."""
    if _HAS_DATA_FILTER:
        tar.extractall(dest, filter="data")
        return
    validate_members(tar, dest)
    tar.extractall(dest)  # noqa: S202 - membres validés juste au-dessus
