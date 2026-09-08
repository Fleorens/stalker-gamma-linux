"""Artwork du raccourci Steam : les capsules du paquet, posées dans `config/grid/`.

Steam nomme l'artwork d'un raccourci non-Steam d'après son `appid` **non
signé** (voir `steam.appid` pour le signé/non signé, et pour la raison qui nous
fait écrire nous-mêmes cet identifiant) :

- `<appid>p.png` — grille verticale, celle de la bibliothèque et du mode Gaming ;
- `<appid>.png` — grille horizontale ;
- `<appid>_hero.png` — bandeau de la fiche du jeu ;
- `<appid>_logo.png` — logo détouré posé sur le bandeau ;
- `<appid>_icon.png` — icône, référencée aussi par le champ `icon` de l'entrée.

**Que des assets du paquet.** Les trois capsules sont générées hors ligne par
`scripts/generate_steam_artwork.py` (procédural, déterministe) ; le logo et
l'icône sont ceux qui servent déjà à la GUI et au `.desktop`. Aucun
téléchargement, ici ou ailleurs — SteamGridDB comprise.

**Au retrait, on ne supprime que ce qu'on a écrit.** Un fichier dont les octets
ne sont plus les nôtres a été remplacé par l'utilisateur (sa propre capsule) :
il est laissé en place et signalé, pas effacé.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from stalker_gamma_linux.paths_safety import UnsafeWipeTargetError, validate_removable_child
from stalker_gamma_linux.steam.errors import SteamWriteError

_PACKAGE = "stalker_gamma_linux"

# (gabarit de nom dans `grid/`, ressource du paquet). L'ordre est celui de
# l'affichage : capsule verticale d'abord, c'est celle qu'on voit.
_ARTWORK: tuple[tuple[str, str], ...] = (
    ("{appid}p.png", "assets/steam/grid-vertical.png"),
    ("{appid}.png", "assets/steam/grid-horizontal.png"),
    ("{appid}_hero.png", "assets/steam/hero.png"),
    ("{appid}_logo.png", "assets/logo.png"),
    ("{appid}_icon.png", "assets/icon.png"),
)

_ICON_TEMPLATE = "{appid}_icon.png"


def _asset_bytes(resource: str) -> bytes:
    return (resources.files(_PACKAGE) / resource).read_bytes()


def filenames(appid: int) -> tuple[str, ...]:
    """Noms des fichiers d'artwork pour `appid` (non signé), dans `grid/`."""
    return tuple(template.format(appid=appid) for template, _resource in _ARTWORK)


def icon_file(grid_dir: Path, appid: int) -> Path:
    """Chemin de l'icône — c'est lui qu'on inscrit dans le champ `icon` de l'entrée."""
    return grid_dir / _ICON_TEMPLATE.format(appid=appid)


def paths(grid_dir: Path, appid: int) -> tuple[Path, ...]:
    return tuple(grid_dir / name for name in filenames(appid))


def write(grid_dir: Path, appid: int) -> tuple[Path, ...]:
    """Écrit les cinq fichiers d'artwork. Retourne ceux qui ont été écrits."""
    written: list[Path] = []
    try:
        grid_dir.mkdir(parents=True, exist_ok=True)
        for template, resource in _ARTWORK:
            destination = grid_dir / template.format(appid=appid)
            destination.write_bytes(_asset_bytes(resource))
            written.append(destination)
    except OSError as error:
        raise SteamWriteError(grid_dir, error) from error
    return tuple(written)


def remove(grid_dir: Path, appid: int) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Retire notre artwork. Retourne `(supprimés, laissés en place)`.

    « Laissé en place » = le fichier existe mais son contenu n'est plus celui du
    paquet : l'utilisateur y a mis sa propre capsule, ce n'est plus à nous de la
    supprimer. Les noms viennent d'un entier, donc sans surprise ; ils passent
    quand même par `paths_safety` — c'est lui qui refuse un lien symbolique posé
    en travers, pas la forme du nom.
    """
    removed: list[Path] = []
    kept: list[Path] = []
    for template, resource in _ARTWORK:
        name = template.format(appid=appid)
        try:
            target = validate_removable_child(grid_dir, name)
        except UnsafeWipeTargetError:
            kept.append(grid_dir / name)
            continue
        if target is None:
            continue
        try:
            if target.read_bytes() != _asset_bytes(resource):
                kept.append(target)
                continue
            target.unlink()
        except OSError:
            kept.append(target)
            continue
        removed.append(target)
    return tuple(removed), tuple(kept)
