"""Découverte des **couches Vulkan implicites** installées sur l'hôte.

MangoHud et vkBasalt ne sont pas des programmes qu'on lance : ce sont des
couches que le *loader* Vulkan charge dans le processus qui crée l'instance.
Une couche = un manifeste JSON dans un `vulkan/implicit_layer.d/` + la
bibliothèque qu'il désigne. D'où la détection par manifeste et pas par
`which()` : vkBasalt n'installe **aucun binaire**, et chercher un exécutable
répondrait « absent » sur une machine où la couche fonctionne parfaitement.

**Pourquoi ça compte au-delà de la détection.** C'est exactement ce fichier que
pressure-vessel importe dans le conteneur steamrt au lancement (avec la
bibliothèque associée) : si le manifeste n'est pas dans un des répertoires
standard ci-dessous, ni le loader de l'hôte ni celui du conteneur ne le
verront. `doctor` affiche donc le chemin trouvé — c'est la première chose à
regarder quand l'overlay ne s'affiche pas (cf. docs/ARCHITECTURE.md).

Les répertoires suivent la spécification du loader Vulkan (ordre de recherche
des couches implicites sous Linux) : `XDG_CONFIG_*` d'abord, puis `XDG_DATA_*`,
avec les valeurs de repli XDG usuelles. `VK_LAYER_PATH` n'est pas consulté :
elle ne concerne que les couches *explicites*.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

_IMPLICIT_LAYER_SUBDIR = ("vulkan", "implicit_layer.d")

# (variable XDG, valeur de repli, la variable désigne-t-elle une liste ?)
_XDG_SEARCH: tuple[tuple[str, str, bool], ...] = (
    ("XDG_CONFIG_HOME", "~/.config", False),
    ("XDG_CONFIG_DIRS", "/etc/xdg", True),
    ("XDG_DATA_HOME", "~/.local/share", False),
    ("XDG_DATA_DIRS", "/usr/local/share:/usr/share", True),
)
# Répertoire système hors XDG, consulté par le loader en plus des précédents.
_EXTRA_DIRS = ("/etc",)


def implicit_layer_dirs(environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    """Répertoires où le loader Vulkan cherche les manifestes de couches implicites.

    Ordre significatif (le premier manifeste trouvé gagne côté loader), doublons
    retirés. `environ` sert aux tests : par défaut `os.environ`, jamais modifié.
    """
    env = environ if environ is not None else os.environ
    roots: list[Path] = []
    for variable, fallback, is_list in _XDG_SEARCH:
        raw = env.get(variable) or fallback
        entries = raw.split(":") if is_list else [raw]
        roots.extend(Path(entry).expanduser() for entry in entries if entry)
    roots.extend(Path(entry) for entry in _EXTRA_DIRS)

    directories: list[Path] = []
    for root in roots:
        directory = root.joinpath(*_IMPLICIT_LAYER_SUBDIR)
        if directory not in directories:
            directories.append(directory)
    return tuple(directories)


def find_implicit_layer(stem: str, environ: Mapping[str, str] | None = None) -> Path | None:
    """Premier manifeste `<stem>*.json` trouvé, ou None si la couche n'est pas installée.

    Comparaison insensible à la casse et sur le *préfixe* : les paquets livrent
    un manifeste par ABI sous des noms qui varient (`MangoHud.json` et
    `MangoHud.x86.json` chez MangoHud, `vkBasalt.json` chez vkBasalt), et la
    casse du nom de fichier suit celle du projet amont, pas celle de la distro.
    """
    needle = stem.lower()
    for directory in implicit_layer_dirs(environ):
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            # Répertoire absent (le cas nominal pour la plupart) ou illisible :
            # ce n'est pas une erreur, on passe au suivant.
            continue
        for entry in entries:
            name = entry.name.lower()
            if name.startswith(needle) and name.endswith(".json"):
                return entry
    return None
