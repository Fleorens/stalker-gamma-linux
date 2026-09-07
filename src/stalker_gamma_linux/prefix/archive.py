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
avant extraction, avec les mêmes refus que `data_filter` — et le même masque de
mode (`_DATA_FILTER_MODE_MASK`), parce que refuser les membres dangereux ne dit
rien des permissions de ceux qu'on accepte.
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

# Le masque que `data_filter` applique au mode de chaque membre (« Strip high
# bits & group/other write bits », `tarfile._get_filtered_attrs`). Trois familles
# de bits tombent, et chacune pour sa raison :
#
# - **setuid/setgid** (0o4000, 0o2000) : ils n'ont aucun sens dans un zipapp ou
#   une release précompilée, et deviendraient une élévation de privilèges si
#   l'archive était un jour extraite sous un autre propriétaire que celui qui a
#   posé le bit ;
# - **sticky** (0o1000) : sans objet sur un fichier ordinaire, et le poser hors
#   d'un répertoire partagé n'apporte rien qu'un comportement surprenant ;
# - **écriture groupe/autres** (0o022) : c'est le bit qui compte vraiment ici.
#   On extrait dans `compatibilitytools.d` et `~/.local/bin`, puis on exécute ce
#   qu'on vient d'y poser. Un membre en 0o777 laisserait, sur une machine
#   multi-utilisateurs, n'importe quel compte local réécrire un binaire que
#   l'utilisateur lancera ensuite.
#
# Cette branche ne tourne que sur Python < 3.11.4 (Debian 12) : ailleurs, c'est
# `data_filter` lui-même qui applique ce masque — la valeur est donc reprise de
# la bibliothèque standard, pas inventée, pour que le repli tienne la promesse
# de parité annoncée en tête de module.
_DATA_FILTER_MODE_MASK = 0o755


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
    for member in tar.getmembers():
        member.mode &= _DATA_FILTER_MODE_MASK
    tar.extractall(dest)  # noqa: S202 - membres validés juste au-dessus
