#!/usr/bin/env python3
"""Génère les artworks de la GUI sous `src/stalker_gamma_linux/assets/`.

Procédural et déterministe (graine fixe) : la Zone à la tombée du jour —
antenne Duga, cheminée de la centrale, pylônes, brume rasante, anomalie. Aucun
asset externe : rien à créditer, rien à retélécharger, et relancer ce script
reproduit exactement les mêmes octets. Nécessite numpy + Pillow (extra `dev` ;
jamais importés par le paquet lui-même).

Deux fichiers, parce que les deux usages n'ont pas les mêmes contraintes :

- `background.jpg` (1920x1080) — l'accueil, où l'artwork est le sujet ;
- `background-blur.jpg` (960x540) — les pages de contenu (progression,
  diagnostic), où il n'est qu'une ambiance derrière du texte. Flouté et
  assombri **une fois ici** plutôt qu'à chaque affichage : la lisibilité ne
  dépend plus d'un voile CSS, et la moitié de résolution suffit puisque
  l'image est floue de toute façon — quatre fois moins de pixels à mettre à
  l'échelle à chaque redessin.

Usage : python scripts/generate_background.py [dossier_de_sortie]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageEnhance, ImageFilter  # noqa: E402

from artwork import render_zone  # noqa: E402

FULL_SIZE = (1920, 1080)
BLUR_SIZE = (960, 540)
BLUR_RADIUS = 18.0
BLUR_DIM = 0.82  # ce qui reste de luminosité sous le contenu des pages

_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "src" / "stalker_gamma_linux" / "assets"


def _blurred(full: Image.Image) -> Image.Image:
    """Variante d'ambiance : réduite, floutée, assombrie — dans cet ordre.

    Réduire d'abord n'est pas qu'une économie : un flou appliqué après la
    réduction reste identique à l'écran tout en coûtant quatre fois moins.
    """
    reduced = full.resize(BLUR_SIZE, Image.Resampling.LANCZOS)
    blurred = reduced.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    return ImageEnhance.Brightness(blurred).enhance(BLUR_DIM)


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUTPUT
    output.mkdir(parents=True, exist_ok=True)

    full = render_zone(*FULL_SIZE)
    for name, image, quality in (
        ("background.jpg", full, 88),
        ("background-blur.jpg", _blurred(full), 82),
    ):
        destination = output / name
        image.save(destination, "JPEG", quality=quality, optimize=True)
        print(f"écrit : {destination} ({destination.stat().st_size // 1024} Kio)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
