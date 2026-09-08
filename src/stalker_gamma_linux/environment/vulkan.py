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

**Le manifeste ne suffit pas : il faut la bibliothèque, dans la bonne ABI.**
Constaté en réel le 2026-09-08 sur la machine de dev. Fedora empaquette vkBasalt
en deux RPM distincts (`vkBasalt.x86_64` et `vkBasalt.i686`) qui partagent **un
seul** manifeste, dont le `library_path` vaut `/usr/$LIB/vkbasalt/libvkbasalt.so`.
Avec le seul paquet 32 bits installé, le manifeste est donc bien là — et `doctor`
annonçait `[ OK ]` — alors que le jeu, processus 64 bits, cherche `/usr/lib64/…`
et ne trouve rien : la couche ne se charge pas, sans le moindre message. Mesuré
dans le conteneur : `ENABLE_VKBASALT=1`, zéro occurrence de `VK_LAYER_VKBASALT`.
D'où `layer_abi_support()`, qui résout le manifeste jusqu'au fichier et lit sa
**classe ELF**.

**Pourquoi lire l'ELF plutôt que déduire du nom de dossier.** `$LIB` est un jeton
que l'éditeur de liens remplace par le répertoire de l'architecture du processus,
et sa valeur dépend de la distribution : `lib64` sur Fedora et Arch,
`lib/x86_64-linux-gnu` sur Debian multiarch. Deviner laquelle s'applique serait
faux quelque part. On essaie donc les candidats connus, et c'est l'octet de classe
du fichier trouvé qui tranche — lui ne ment pas.

**Ne pas savoir n'est pas une raison d'alarmer** (même règle que
`checks._libunrar_version`) : manifeste illisible, `library_path` absent, ou
simple soname laissé à l'éditeur de liens ⇒ `AbiSupport.UNKNOWN`, et l'appelant
se tait.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from enum import Enum, auto
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

# Valeurs possibles du jeton `$LIB` de l'éditeur de liens, toutes distributions
# confondues. On les essaie toutes : c'est la classe ELF du fichier trouvé qui
# désigne l'ABI, pas le nom du répertoire (cf. docstring du module).
_LIB_TOKEN_VALUES = ("lib64", "lib", "lib/x86_64-linux-gnu", "lib/i386-linux-gnu")

# Octet 4 de l'en-tête ELF : la classe. 1 = 32 bits, 2 = 64 bits.
_ELF_MAGIC = b"\x7fELF"
_ELF_CLASS_BITS = {1: 32, 2: 64}


class AbiSupport(Enum):
    """La couche peut-elle se charger dans un processus de l'ABI demandée ?"""

    # Une bibliothèque de cette ABI existe : la couche se chargera.
    PRESENT = auto()
    # Des bibliothèques existent, aucune dans cette ABI : elle ne se chargera
    # pas, et en silence — c'est le cas qui a motivé cette fonction.
    MISSING = auto()
    # Rien de concluant (manifeste illisible, soname sans chemin…). On ne dit
    # rien plutôt que d'alarmer à tort.
    UNKNOWN = auto()


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


def implicit_layer_manifests(
    stem: str, environ: Mapping[str, str] | None = None
) -> tuple[Path, ...]:
    """**Tous** les manifestes `<stem>*.json`, dans l'ordre de recherche du loader.

    `find_implicit_layer` n'en rend qu'un ; il en faut la liste complète pour
    juger de l'ABI, parce qu'un paquet peut livrer un manifeste **par** ABI
    (MangoHud : `MangoHud.x86.json` et `MangoHud.x86_64.json`, chacun pointant
    sur sa propre bibliothèque).
    """
    needle = stem.lower()
    found: list[Path] = []
    for directory in implicit_layer_dirs(environ):
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            name = entry.name.lower()
            if name.startswith(needle) and name.endswith(".json"):
                found.append(entry)
    return tuple(found)


def manifest_library(manifest: Path) -> str | None:
    """`library_path` déclaré par le manifeste, tel quel (jeton `$LIB` compris).

    None dès que le fichier n'est pas exploitable : absent, JSON invalide, ou
    forme inattendue. Le loader accepte `layer` (un objet) comme `layers` (une
    liste) — les deux se rencontrent.
    """
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    layer = data.get("layer")
    if layer is None:
        layers = data.get("layers")
        layer = layers[0] if isinstance(layers, list) and layers else None
    if not isinstance(layer, dict):
        return None
    library = layer.get("library_path")
    return library if isinstance(library, str) and library else None


def library_candidates(manifest: Path, library: str) -> tuple[Path, ...]:
    """Chemins absolus possibles pour `library`, jeton `$LIB` développé.

    Un `library_path` sans séparateur est un simple soname que l'éditeur de
    liens résoudra par ses propres chemins : on ne peut rien en conclure, donc
    aucun candidat. Un chemin relatif se résout depuis le dossier du manifeste,
    comme le fait le loader.
    """
    if "/" not in library:
        return ()
    if "$LIB" in library or "${LIB}" in library:
        expanded = [
            library.replace("${LIB}", value).replace("$LIB", value) for value in _LIB_TOKEN_VALUES
        ]
    else:
        expanded = [library]
    candidates: list[Path] = []
    for entry in expanded:
        if "$" in entry:
            # Un autre jeton ($PLATFORM, $ORIGIN…) : on ne sait pas résoudre.
            continue
        path = Path(entry)
        resolved = path if path.is_absolute() else manifest.parent / path
        if resolved not in candidates:
            candidates.append(resolved)
    return tuple(candidates)


def elf_bits(path: Path) -> int | None:
    """32 ou 64 d'après l'en-tête ELF du fichier, ou None s'il n'est pas lisible/ELF."""
    try:
        with path.open("rb") as handle:
            header = handle.read(5)
    except OSError:
        return None
    if len(header) < 5 or header[:4] != _ELF_MAGIC:
        return None
    return _ELF_CLASS_BITS.get(header[4])


def layer_abi_support(
    stem: str, bits: int = 64, environ: Mapping[str, str] | None = None
) -> AbiSupport:
    """La couche `stem` dispose-t-elle d'une bibliothèque en `bits` bits ?

    Parcourt tous ses manifestes, résout chacun jusqu'à un fichier réel et lit
    sa classe ELF. `MISSING` n'est retourné que si au moins une bibliothèque a
    été trouvée **et** qu'aucune n'est de la bonne ABI : sans ça, on ne saurait
    pas distinguer « mauvaise ABI » de « on n'a pas su résoudre ».
    """
    seen_any = False
    for manifest in implicit_layer_manifests(stem, environ):
        library = manifest_library(manifest)
        if library is None:
            continue
        for candidate in library_candidates(manifest, library):
            found = elf_bits(candidate)
            if found is None:
                continue
            seen_any = True
            if found == bits:
                return AbiSupport.PRESENT
    return AbiSupport.MISSING if seen_any else AbiSupport.UNKNOWN
