"""Lecture du `modlist.txt` d'un profil MO2 (mods activés/désactivés).

Format MO2 (une ligne par entrée, priorité croissante de bas en haut) :
`+Mod` = activé, `-Mod` = désactivé, `*Mod` = non géré (toujours actif),
`#...` = commentaire (MO2 écrit un en-tête auto). Les séparateurs visuels du
panneau MO2 apparaissent comme des entrées suffixées `_separator` : ce ne sont
pas des mods, on les ignore.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system

_MODLIST_FILE = "modlist.txt"
_SEPARATOR_SUFFIX = "_separator"
_MARKERS = "+-*"


@dataclass(frozen=True, slots=True)
class ModEntry:
    name: str
    enabled: bool


def parse_modlist(text: str) -> tuple[ModEntry, ...]:
    """Parse le contenu d'un `modlist.txt`. Séparateurs et commentaires ignorés."""
    entries: list[ModEntry] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line[0] not in _MARKERS:
            continue
        marker, name = line[0], line[1:]
        if not name or name.endswith(_SEPARATOR_SUFFIX):
            continue
        entries.append(ModEntry(name=name, enabled=marker != "-"))
    return tuple(entries)


def read_modlist(profile_dir: Path) -> tuple[ModEntry, ...]:
    """Entrées du `modlist.txt` du profil, ou tuple vide si le fichier est absent."""
    text = system.read_text(profile_dir / _MODLIST_FILE)
    if text is None:
        return ()
    return parse_modlist(text)


def enabled_mods(entries: tuple[ModEntry, ...]) -> tuple[str, ...]:
    return tuple(entry.name for entry in entries if entry.enabled)
