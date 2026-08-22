"""Lecture du `modlist.txt` d'un profil MO2 (mods activés/désactivés).

Format MO2 (une ligne par entrée, priorité croissante de bas en haut) :
`+Mod` = activé, `-Mod` = désactivé, `*Mod` = non géré (toujours actif),
`#...` = commentaire (MO2 écrit un en-tête auto). Les séparateurs visuels du
panneau MO2 apparaissent comme des entrées suffixées `_separator` : ce ne sont
pas des mods, et les appelants qui comptent ou fusionnent des mods les
ignorent (comportement par défaut).

Ils correspondent pourtant à de **vrais dossiers** sous `mods/` — gamma-launcher
les crée avec un `meta.ini` (`SeparatorInstaller.install`). Qui cherche à savoir
si un dossier vient du modpack doit donc les compter : `include_separators=True`
(voir `integrity.repair.upstream_mod_names`, qui sans ça prenait les 28
séparateurs d'une install réelle pour des ajouts du joueur).
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
    is_separator: bool = False


def parse_modlist(text: str, *, include_separators: bool = False) -> tuple[ModEntry, ...]:
    """Parse le contenu d'un `modlist.txt`. Commentaires ignorés.

    `include_separators` : garde les entrées `*_separator`, qui existent bien
    en tant que dossiers sur le disque (voir l'en-tête du module). Faux par
    défaut — les appelants historiques comptent des mods, pas des intercalaires.
    """
    entries: list[ModEntry] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line[0] not in _MARKERS:
            continue
        marker, name = line[0], line[1:]
        if not name:
            continue
        is_separator = name.endswith(_SEPARATOR_SUFFIX)
        if is_separator and not include_separators:
            continue
        entries.append(ModEntry(name=name, enabled=marker != "-", is_separator=is_separator))
    return tuple(entries)


def read_modlist(profile_dir: Path) -> tuple[ModEntry, ...]:
    """Entrées du `modlist.txt` du profil, ou tuple vide si le fichier est absent."""
    text = system.read_text(profile_dir / _MODLIST_FILE)
    if text is None:
        return ()
    return parse_modlist(text)


def enabled_mods(entries: tuple[ModEntry, ...]) -> tuple[str, ...]:
    """Mods activés, hors séparateurs — ceux-ci n'ont rien à fusionner ni à charger."""
    return tuple(entry.name for entry in entries if entry.enabled and not entry.is_separator)
