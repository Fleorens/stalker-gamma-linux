"""Nature du support qui porte un chemin : plateaux tournants, ou pas.

Une seule question est posée ici, et elle n'a qu'un client : `integrity.scan`,
qui doit décider combien de fils de hachage lancer. Le calcul MD5 se
parallélise très bien sur mémoire flash — `hashlib` libère le GIL, le disque
suit — mais **dégrade** un disque à plateaux : quatre lecteurs concurrents sur
quatre fichiers éloignés remplacent une lecture séquentielle à ~150 Mio/s par
un va-et-vient de têtes.

Le chemin d'accès à l'information est plus tortueux qu'il n'y paraît :

1. `os.stat(path).st_dev` ne suffit pas. Sur btrfs, ZFS, overlayfs ou NFS, le
   noyau attribue un numéro de périphérique **anonyme** (majeur 0) qui ne
   correspond à aucune entrée de `/sys/dev/block/`. Ce n'est pas un cas
   exotique : une Fedora par défaut, ou une partition de jeux btrfs, tombent
   exactement là.
2. On passe donc par `/proc/self/mountinfo`, seul endroit qui donne la
   **source** du montage (`/dev/sda1`) et pas seulement son numéro anonyme.
3. Puis par `/sys/dev/block/<majeur>:<mineur>/queue/rotational`. `queue/` vit
   au niveau du disque et non de la partition, d'où le repli sur le parent.

Chacune de ces étapes peut échouer (conteneur sans `/proc`, montage réseau,
disque virtuel, périphérique empilé) : on retourne alors `None` — « je ne sais
pas » — jamais une exception. C'est à l'appelant de décider quoi faire du doute.
"""

from __future__ import annotations

import os
from pathlib import Path

_MOUNTINFO = Path("/proc/self/mountinfo")
_SYSFS_BLOCK = Path("/sys/dev/block")

# `/proc/self/mountinfo` échappe en octal les caractères qui casseraient son
# propre découpage par espaces. Sans ce décodage, un point de montage nommé
# `/mnt/Mes jeux` ne serait jamais reconnu comme préfixe du chemin scanné.
_OCTAL_ESCAPES = {"040": " ", "011": "\t", "012": "\n", "134": "\\"}
_ESCAPE_LENGTH = 4  # `\` + trois chiffres octaux


def is_rotational(
    path: Path,
    *,
    mountinfo: Path = _MOUNTINFO,
    sysfs_block: Path = _SYSFS_BLOCK,
) -> bool | None:
    """`True` si `path` vit sur un disque mécanique, `False` sinon, `None` si indéterminable.

    Les deux paramètres de chemin n'existent que pour les tests : la suite ne
    peut pas fabriquer de vrai nœud de périphérique sans être root.
    """
    source = mount_source(path, mountinfo=mountinfo)
    if source is None:
        return None
    node = _device_node(source)
    if node is None:
        return None
    return _rotational_flag(node, sysfs_block=sysfs_block)


def mount_source(path: Path, *, mountinfo: Path = _MOUNTINFO) -> str | None:
    """Périphérique source du montage qui porte `path` (`/dev/sda1`), ou `None`.

    Le montage retenu est celui dont le point de montage est le **plus long**
    préfixe du chemin — sinon `/` gagnerait toujours contre `/mnt/jeux`. À
    longueur égale, le dernier de la liste l'emporte : un montage postérieur
    sur le même point masque le précédent, et c'est lui qu'on lit réellement.
    """
    try:
        content = mountinfo.read_text(encoding="utf-8")
    except OSError:
        return None
    target = _absolute(path)
    best_length = -1
    best_source: str | None = None
    for line in content.splitlines():
        entry = _parse_mountinfo_line(line)
        if entry is None:
            continue
        mount_point, source = entry
        if not _covers(mount_point, target) or len(mount_point) < best_length:
            continue
        best_length, best_source = len(mount_point), source
    return best_source


def _absolute(path: Path) -> str:
    """Chemin absolu et sans lien symbolique, comparable aux points de montage."""
    try:
        # `strict=False` : la racine des mods peut ne pas exister encore, le
        # montage qui la portera, lui, est déjà là.
        return str(path.resolve())
    except OSError:
        return os.path.abspath(path)


def _covers(mount_point: str, target: str) -> bool:
    """Vrai si `mount_point` est le point de montage de `target` ou d'un de ses parents."""
    if target == mount_point:
        return True
    # `rstrip` pour que la racine (`/`) ne devienne pas le préfixe `//`.
    return target.startswith(mount_point.rstrip("/") + "/")


def _parse_mountinfo_line(line: str) -> tuple[str, str] | None:
    """`(point de montage, source)` d'une ligne de `mountinfo`, ou `None`.

    Le nombre de champs optionnels avant le séparateur ` - ` est variable
    (`shared:`, `master:`…) : on découpe donc sur ce séparateur au lieu de
    compter les colonnes. Un point de montage ne peut pas contenir d'espace non
    échappée, ce qui rend ce découpage sûr.
    """
    head, separator, tail = line.partition(" - ")
    if not separator:
        return None
    head_fields = head.split(" ")
    tail_fields = tail.split(" ")
    if len(head_fields) < 5 or len(tail_fields) < 2:
        return None
    return _unescape(head_fields[4]), _unescape(tail_fields[1])


def _unescape(raw: str) -> str:
    """Décode les échappements octaux de `mountinfo` (`\\040` → espace)."""
    if "\\" not in raw:
        return raw
    decoded: list[str] = []
    index = 0
    while index < len(raw):
        code = raw[index + 1 : index + _ESCAPE_LENGTH]
        if raw[index] == "\\" and code in _OCTAL_ESCAPES:
            decoded.append(_OCTAL_ESCAPES[code])
            index += _ESCAPE_LENGTH
            continue
        decoded.append(raw[index])
        index += 1
    return "".join(decoded)


def _device_node(source: str) -> str | None:
    """`<majeur>:<mineur>` du nœud bloc `source`, ou `None` s'il n'y en a pas.

    Passer par `stat` plutôt que par le nom résout d'un coup les liens
    symboliques de `/dev/mapper/` (LUKS, LVM) et les alias `/dev/disk/by-uuid/`.
    """
    if not source.startswith("/dev/"):
        return None  # tmpfs, `serveur:/export`, overlay… : pas un bloc, rien à dire
    try:
        rdev = os.stat(source).st_rdev
    except OSError:
        return None
    if rdev == 0:
        return None  # existe mais n'est pas un périphérique bloc
    return f"{os.major(rdev)}:{os.minor(rdev)}"


def _rotational_flag(node: str, *, sysfs_block: Path) -> bool | None:
    """Lit `queue/rotational` pour `<majeur>:<mineur>`, au besoin sur le disque parent."""
    candidates = (
        sysfs_block / node / "queue" / "rotational",
        # Une partition n'a pas de `queue/` à elle : il vit sur le disque
        # parent, que le lien symbolique `/sys/dev/block/<maj>:<min>` atteint
        # par `..` — le noyau résout le lien avant de remonter d'un cran.
        sysfs_block / node / ".." / "queue" / "rotational",
    )
    for candidate in candidates:
        try:
            raw = candidate.read_text(encoding="ascii").strip()
        except OSError:
            continue
        if raw in ("0", "1"):
            return raw == "1"
    return None
