"""Empreinte de référence de l'install : `<install>/gamma-md5.txt`.

Une ligne par fichier de `gamma/mods/`, `<md5><séparateur><chemin relatif>`,
triée par chemin — le format `md5sum` classique, lisible et comparable à la
main. C'est volontairement un fichier texte à côté de l'install, et non un
état sous `~/.config` : il décrit *cette* installation-là, il doit la suivre si
elle est déplacée ou sauvegardée, et un utilisateur doit pouvoir le lire.

Deux points structurants :

- **Parsing par découpage, jamais par offsets.** `line[:32]`/`line[34:]`
  marche tant que le fichier vient de nous et casse au premier écart (un
  fichier produit par `md5sum` en mode binaire préfixe le chemin d'un `*`, un
  éditeur peut retabuler). On découpe donc après le hash, et on vérifie que ce
  qu'on a lu *ressemble* à un md5 avant de l'accepter.
- **Écriture atomique.** Un `write_text` interrompu (Ctrl-C, disque plein)
  laisserait une référence tronquée, dont le seul effet serait d'annoncer des
  centaines de fichiers « supprimés » au passage suivant. On écrit à côté puis
  on `replace()` : soit l'ancienne référence, soit la nouvelle, jamais un
  mélange.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from stalker_gamma_linux.integrity.errors import BaselineReadError, BaselineWriteError

BASELINE_FILENAME = "gamma-md5.txt"

# Séparateur canonique de `md5sum` (deux espaces, mode texte).
_SEPARATOR = "  "
_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
# `md5sum` en mode binaire écrit `<hash> *<chemin>` : le `*` fait partie du
# format, pas du nom de fichier.
_BINARY_MODE_MARKER = "*"


@dataclass(frozen=True, slots=True)
class ParsedBaseline:
    """Référence relue, plus ce qu'on n'a pas su relire.

    `skipped` n'est jamais avalé en silence : l'appelant l'annonce à
    l'utilisateur. Une référence partiellement illisible produit des faux
    « supprimé », et il faut qu'on puisse le dire au lieu de le subir.
    """

    digests: Mapping[str, str] = field(default_factory=dict)
    skipped: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.digests


def baseline_path(root: Path) -> Path:
    """Emplacement de la référence pour l'installation `root`."""
    return root / BASELINE_FILENAME


def parse_baseline(text: str) -> ParsedBaseline:
    """Relit le contenu d'un `gamma-md5.txt`. Ne lève jamais : ce qui ne parse pas est rapporté."""
    digests: dict[str, str] = {}
    skipped: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue
        entry = _parse_line(line)
        if entry is None:
            skipped.append(line)
            continue
        digest, relative = entry
        digests[relative] = digest
    return ParsedBaseline(digests=digests, skipped=tuple(skipped))


def _parse_line(line: str) -> tuple[str, str] | None:
    """`(md5, chemin relatif)` d'une ligne, ou None si elle n'a pas la bonne forme.

    Le séparateur canonique est essayé en premier : il préserve un chemin qui
    commencerait lui-même par une espace, ce qu'un découpage sur les blancs
    perdrait. Le repli sur `split` couvre les fichiers venus d'ailleurs
    (séparateur simple, tabulation).
    """
    digest, separator, relative = line.partition(_SEPARATOR)
    if not separator:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            return None
        digest, relative = parts[0], parts[1]
    if not _MD5_RE.match(digest):
        return None
    if relative.startswith(_BINARY_MODE_MARKER):
        relative = relative[len(_BINARY_MODE_MARKER) :]
    if not relative:
        return None
    return digest.lower(), relative


def format_baseline(digests: Mapping[str, str]) -> str:
    """Rend la référence, triée par chemin relatif (diff stable d'une version à l'autre)."""
    return "".join(
        f"{digest}{_SEPARATOR}{relative}\n" for relative, digest in sorted(digests.items())
    )


def read_baseline(root: Path) -> ParsedBaseline | None:
    """Référence de `root`, ou `None` si elle n'existe pas encore (premier passage)."""
    path = baseline_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise BaselineReadError(path, error) from error
    return parse_baseline(text)


def write_baseline(root: Path, digests: Mapping[str, str]) -> Path:
    """Écrit la référence de façon atomique. Retourne son chemin.

    Le fichier temporaire est créé dans le **même** répertoire que la cible :
    `Path.replace` n'est atomique qu'à l'intérieur d'un système de fichiers, et
    l'install vit rarement sur le même volume que `/tmp`.
    """
    path = baseline_path(root)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(format_baseline(digests), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise BaselineWriteError(path, error) from error
    return path
