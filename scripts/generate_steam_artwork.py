#!/usr/bin/env python3
"""Génère les capsules Steam sous `src/stalker_gamma_linux/assets/steam/`.

Même principe que `generate_background.py` : procédural, déterministe, aucun
asset externe. La Zone rendue par `artwork.render_zone`, recadrée aux formats
que Steam attend, avec le logo du paquet posé dessus. **Rien n'est téléchargé**
— ni ici ni à l'exécution : SteamGridDB et les banques d'images tierces sont
hors sujet pour ce projet (« jamais de rehosting, jamais d'asset tiers »).

Pourquoi pré-générer plutôt que composer au moment d'écrire le raccourci : la
composition demande Pillow + numpy, qui sont des dépendances de **développement**
(extra `dev`). Le paquet installé chez l'utilisateur ne les a pas, et
`steam.artwork` se contente donc de recopier des octets déjà prêts — comme
`desktop/install.py` le fait déjà pour l'icône.

Trois formats seulement : le logo (`assets/logo.png`) et l'icône
(`assets/icon.png`) partent tels quels, ils sont déjà au bon format.

Usage : python scripts/generate_steam_artwork.py [dossier_de_sortie]
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from artwork import render_zone  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_LOGO = _ROOT / "src" / "stalker_gamma_linux" / "assets" / "logo.png"
_DEFAULT_OUTPUT = _ROOT / "src" / "stalker_gamma_linux" / "assets" / "steam"

# Assombrissement : mêmes raisons qu'en carte sociale — le paysage doit rester
# lisible en vignette sans manger le logo posé dessus.
_SCRIM = 0.34

# Quantification sur palette : l'artwork est fait de dégradés et de brume, la
# perte est invisible à l'œil et divise le poids des PNG par quatre. Un dépôt
# n'a pas à porter quatre mégaoctets de capsules.
_PALETTE_COLORS = 256


@dataclass(frozen=True, slots=True)
class Capsule:
    """Un format d'artwork Steam : sa taille, et la largeur du logo posé dessus."""

    filename: str
    width: int
    height: int
    logo_ratio: float
    # Position verticale du centre du logo, en fraction de la hauteur.
    logo_center: float


# Formats attendus par Steam pour un raccourci non-Steam. La grille verticale
# est celle de la bibliothèque et du mode Gaming — c'est celle qu'on voit.
CAPSULES: tuple[Capsule, ...] = (
    Capsule("grid-vertical.png", 600, 900, logo_ratio=0.78, logo_center=0.30),
    Capsule("grid-horizontal.png", 920, 430, logo_ratio=0.62, logo_center=0.42),
    Capsule("hero.png", 1920, 620, logo_ratio=0.34, logo_center=0.40),
)


def _cropped_zone(width: int, height: int) -> Image.Image:
    """La Zone recadrée au ratio demandé, autour de l'horizon, puis assombrie."""
    zone = render_zone()
    target_ratio = width / height
    if zone.width / zone.height > target_ratio:
        crop_width = int(zone.height * target_ratio)
        left = (zone.width - crop_width) // 2
        box = (left, 0, left + crop_width, zone.height)
    else:
        crop_height = int(zone.width / target_ratio)
        # L'horizon et le halo d'anomalie sont aux deux tiers de la hauteur :
        # une bande strictement centrée n'attrape que du ciel vide.
        top = min(int((zone.height - crop_height) * 0.62), zone.height - crop_height)
        box = (0, top, zone.width, top + crop_height)
    cropped = zone.crop(box).resize((width, height), Image.Resampling.LANCZOS)
    return Image.blend(cropped, Image.new("RGB", (width, height), (0, 0, 0)), _SCRIM)


def render(capsule: Capsule) -> Image.Image:
    canvas = _cropped_zone(capsule.width, capsule.height)
    logo = Image.open(_LOGO).convert("RGBA")
    logo_width = int(capsule.width * capsule.logo_ratio)
    logo_height = logo.height * logo_width // logo.width
    logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
    top = int(capsule.height * capsule.logo_center) - logo_height // 2
    canvas.paste(logo, ((capsule.width - logo_width) // 2, top), logo)
    return canvas.quantize(colors=_PALETTE_COLORS, method=Image.Quantize.MAXCOVERAGE)


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    for capsule in CAPSULES:
        destination = output / capsule.filename
        render(capsule).save(destination, "PNG", optimize=True)
        print(f"écrit : {destination} ({destination.stat().st_size // 1024} Kio)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
