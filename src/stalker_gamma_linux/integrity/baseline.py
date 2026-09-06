"""Empreinte de référence de l'install : `<install>/gamma-md5.txt`.

Une ligne par fichier de `gamma/mods/`, triée par chemin :

    <md5>  <taille>,<mtime_ns>  <chemin relatif>

C'est le format `md5sum` classique — `<md5><séparateur><chemin>` — auquel on a
ajouté une colonne. Elle porte ce qui permet de décider qu'un fichier n'a pas
bougé sans le relire (`fingerprint.FileStat`) : sans elle, chaque `verify`
rehachait les ~83 Gio de mods, même lancé deux fois de suite sans que rien ne
change entre-temps.

C'est volontairement un fichier texte à côté de l'install, et non un état sous
`~/.config` : il décrit *cette* installation-là, il doit la suivre si elle est
déplacée ou sauvegardée, et un utilisateur doit pouvoir le lire.

Quatre points structurants :

- **Parsing par découpage, jamais par offsets.** `line[:32]`/`line[34:]`
  marche tant que le fichier vient de nous et casse au premier écart (un
  fichier produit par `md5sum` en mode binaire préfixe le chemin d'un `*`, un
  éditeur peut retabuler). On découpe donc après le hash, et on vérifie que ce
  qu'on a lu *ressemble* à un md5 avant de l'accepter.
- **La colonne taille/mtime est optionnelle en lecture.** Une référence écrite
  par une version antérieure — ou par `md5sum` — n'en a pas : elle continue
  d'être relue exactement comme avant, et les fichiers qu'elle décrit sont
  alors tous rehachés. Le repli va toujours dans ce sens-là : au doute, on
  relit. On ne détache donc cette colonne que si elle a *exactement* la forme
  attendue, sinon on la rend au chemin.
- **Écriture atomique.** Un `write_text` interrompu (Ctrl-C, disque plein)
  laisserait une référence tronquée, dont le seul effet serait d'annoncer des
  centaines de fichiers « supprimés » au passage suivant. On écrit à côté puis
  on `replace()` : soit l'ancienne référence, soit la nouvelle, jamais un
  mélange.
- **Le prix de la colonne**, à dire franchement : `md5sum -c gamma-md5.txt` ne
  consomme plus le fichier tel quel, il lirait la colonne comme le début d'un
  nom. C'est le sens *entrant* qui compte ici et il est intact — on relit
  toujours ce que `md5sum` produit, donc on peut repartir d'une référence
  fabriquée à la main — et le fichier reste ce qu'il était pour un humain :
  une ligne par fichier, triée, lisible dans un éditeur.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from stalker_gamma_linux.integrity.errors import BaselineReadError, BaselineWriteError
from stalker_gamma_linux.integrity.fingerprint import FileStat, KnownFile

BASELINE_FILENAME = "gamma-md5.txt"

# Séparateur canonique de `md5sum` (deux espaces, mode texte).
_SEPARATOR = "  "
_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
# Colonne « taille,mtime_ns ». La taille est un entier positif ; `mtime_ns`,
# lui, peut être négatif — une archive de mods peut porter une date antérieure
# à 1970, et l'extraction la restitue telle quelle. Le nombre de chiffres est
# **borné**, et pas par élégance : `int()` refuse une chaîne de plus de
# 4 300 chiffres (limite CPython contre les conversions quadratiques) et lève
# `ValueError`, ce qui casserait la promesse de `parse_baseline` — ne jamais
# lever, rapporter. Vingt chiffres couvrent largement une taille et une date
# en nanosecondes ; au-delà, la ligne n'a pas la forme attendue et son
# « chemin » est rendu tel quel, donc simplement rapporté comme disparu.
_STAT_RE = re.compile(r"^(\d{1,20}),(-?\d{1,20})$")
# `md5sum` en mode binaire écrit `<hash> *<chemin>` : le `*` fait partie du
# format, pas du nom de fichier.
_BINARY_MODE_MARKER = "*"


@dataclass(frozen=True, slots=True)
class ParsedBaseline:
    """Référence relue, plus ce qu'on n'a pas su relire.

    `skipped` n'est jamais avalé en silence : l'appelant l'annonce à
    l'utilisateur. Une référence partiellement illisible produit des faux
    « supprimé », et il faut qu'on puisse le dire au lieu de le subir.

    `known` ne contient que les entrées qui portent la colonne taille/mtime :
    c'est le sous-ensemble que `scan_tree` peut court-circuiter. Il est vide
    pour une référence à l'ancien format, ce qui fait tout rehacher.
    """

    digests: Mapping[str, str] = field(default_factory=dict)
    skipped: tuple[str, ...] = ()
    known: Mapping[str, KnownFile] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.digests

    @property
    def predates_stats(self) -> bool:
        """Référence non vide dont aucune ligne ne porte taille/mtime (ancien format).

        Vaut un mot à l'utilisateur : c'est ce qui explique qu'un `verify` juste
        après une montée de version rehache tout, et que le suivant non.
        """
        return bool(self.digests) and not self.known


def baseline_path(root: Path) -> Path:
    """Emplacement de la référence pour l'installation `root`."""
    return root / BASELINE_FILENAME


def parse_baseline(text: str) -> ParsedBaseline:
    """Relit le contenu d'un `gamma-md5.txt`. Ne lève jamais : ce qui ne parse pas est rapporté."""
    digests: dict[str, str] = {}
    known: dict[str, KnownFile] = {}
    skipped: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue
        entry = _parse_line(line)
        if entry is None:
            skipped.append(line)
            continue
        digest, stat, relative = entry
        digests[relative] = digest
        if stat is not None:
            known[relative] = KnownFile(digest=digest, stat=stat)
    return ParsedBaseline(digests=digests, skipped=tuple(skipped), known=known)


def _parse_line(line: str) -> tuple[str, FileStat | None, str] | None:
    """`(md5, taille/mtime ou None, chemin relatif)`, ou None si la ligne n'a pas la bonne forme.

    Le séparateur canonique est essayé en premier : il préserve un chemin qui
    commencerait lui-même par une espace, ce qu'un découpage sur les blancs
    perdrait. Le repli sur `split` couvre les fichiers venus d'ailleurs
    (séparateur simple, tabulation).
    """
    digest, separator, remainder = line.partition(_SEPARATOR)
    if not separator:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            return None
        digest, remainder = parts[0], parts[1]
    if not _MD5_RE.match(digest):
        return None
    stat, relative = _split_stat(remainder)
    if relative.startswith(_BINARY_MODE_MARKER):
        relative = relative[len(_BINARY_MODE_MARKER) :]
    if not relative:
        return None
    return digest.lower(), stat, relative


def _split_stat(remainder: str) -> tuple[FileStat | None, str]:
    """Détache la colonne taille/mtime de ce qui suit le hash, si elle est là.

    Tout ce qui ne ressemble pas *exactement* à `<chiffres>,<chiffres>` suivi du
    séparateur canonique est rendu au chemin : une ligne d'ancien format, ou un
    chemin contenant deux espaces (`312- Mod  Name/a.ltx`), ne doit surtout pas
    perdre son début ici. Reste un cas résiduel, assumé : un chemin qui
    commencerait littéralement par `123,456` suivi de deux espaces serait lu
    comme une colonne. Nos propres chemins viennent de `Path.relative_to()` et
    ne prennent jamais cette forme ; une référence produite ailleurs le
    pourrait, en théorie.
    """
    candidate, separator, rest = remainder.partition(_SEPARATOR)
    if not separator:
        return None, remainder
    match = _STAT_RE.match(candidate)
    if match is None:
        return None, remainder
    return FileStat(size=int(match.group(1)), mtime_ns=int(match.group(2))), rest


def format_baseline(digests: Mapping[str, str], stats: Mapping[str, FileStat] | None = None) -> str:
    """Rend la référence, triée par chemin relatif (diff stable d'une version à l'autre).

    Un chemin dont on n'a pas le `FileStat` retombe sur la ligne d'origine, sans
    colonne : la référence reste écrivable même quand la provenance des
    empreintes ne fournit que des hashs.
    """
    lookup: Mapping[str, FileStat] = stats if stats is not None else {}
    return "".join(
        _format_line(relative, digest, lookup.get(relative))
        for relative, digest in sorted(digests.items())
    )


def _format_line(relative: str, digest: str, stat: FileStat | None) -> str:
    if stat is None:
        return f"{digest}{_SEPARATOR}{relative}\n"
    return f"{digest}{_SEPARATOR}{stat.size},{stat.mtime_ns}{_SEPARATOR}{relative}\n"


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


def write_baseline(
    root: Path, digests: Mapping[str, str], stats: Mapping[str, FileStat] | None = None
) -> Path:
    """Écrit la référence de façon atomique. Retourne son chemin.

    Le fichier temporaire est créé dans le **même** répertoire que la cible :
    `Path.replace` n'est atomique qu'à l'intérieur d'un système de fichiers, et
    l'install vit rarement sur le même volume que `/tmp`.
    """
    path = baseline_path(root)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(format_baseline(digests, stats), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise BaselineWriteError(path, error) from error
    return path
