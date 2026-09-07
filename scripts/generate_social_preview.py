#!/usr/bin/env python3
"""Génère l'image de preview sociale du dépôt (`docs/social-preview.png`).

C'est la carte affichée quand quelqu'un colle le lien du dépôt sur Discord,
Reddit ou X. Sans elle, le lien s'affiche en rectangle gris : sur les canaux
où se trouve le public de GAMMA, c'est la moitié des clics perdus.

1280×640, le format recommandé par GitHub (< 1 Mio). Déterministe et sans asset
externe, comme `generate_background.py` dont il réutilise **exactement** la même
Zone (même seed) : la carte et la fenêtre du launcher montrent le même paysage.

Le logo GAMMA est celui du modpack amont, déjà embarqué dans les assets de la
GUI. Il est donc accompagné du nom du projet et de la mention « unofficial » :
la carte doit dire « voici l'installeur Linux communautaire », jamais se faire
passer pour le projet de Grokitach.

Usage : python scripts/generate_social_preview.py [sortie.png]

L'upload, lui, reste manuel : l'API GitHub n'expose pas ce réglage.
Settings → General → Social preview → Upload an image.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from artwork import render_zone  # noqa: E402

WIDTH, HEIGHT = 1280, 640

_ROOT = Path(__file__).resolve().parent.parent
_LOGO = _ROOT / "src" / "stalker_gamma_linux" / "assets" / "logo.png"
_DEFAULT_OUTPUT = _ROOT / "docs" / "social-preview.png"

# Assombrissement de l'artwork : le paysage doit rester lisible en vignette
# tout en laissant le texte détaché. Validé à l'œil sur fond sombre et clair.
# Au-delà de ~0.45 la Zone disparaît et la carte n'est plus qu'un rectangle noir.
_SCRIM = 0.32
# Décalage du recadrage vers le bas : l'artwork met son horizon et son halo
# d'anomalie aux deux tiers de la hauteur, la bande strictement centrée n'attrape
# que du ciel vide.
_CROP_DROP = 90
_ACCENT = (168, 220, 120)
_TEXT = (238, 242, 234)
_MUTED = (150, 163, 145)

_TITLE = "stalker-gamma-linux"
_PROMISE = "Install G.A.M.M.A. on Linux with one command"
_SUBLINE = "Mod Organizer 2 under Proton — USVFS active, your mods stay flexible"
_DISTROS = "Fedora · Arch · Debian · Ubuntu · Steam Deck"
_DISCLAIMER = "unofficial community project · GPL-3.0"

# Polices : Noto (présent partout), avec repli sur DejaVu puis la police PIL.
_FONT_DIRS = ("/usr/share/fonts/google-noto", "/usr/share/fonts/dejavu-sans-fonts")
_MONO_CANDIDATES = ("NotoSansMono-Bold.ttf", "DejaVuSansMono-Bold.ttf")
_SANS_CANDIDATES = ("NotoSans-SemiBold.ttf", "DejaVuSans-Bold.ttf")
_SANS_LIGHT_CANDIDATES = ("NotoSans-Regular.ttf", "DejaVuSans.ttf")


def _load_font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    for directory in _FONT_DIRS:
        for name in candidates:
            path = Path(directory) / name
            if path.is_file():
                return ImageFont.truetype(str(path), size)
    # Repli : la carte reste générable sur une machine sans ces polices, en moins joli.
    return ImageFont.load_default(size)


def _zone_backdrop() -> Image.Image:
    """L'artwork du launcher, recadré en 2:1 et assombri."""
    zone = render_zone()
    # Recadrage par ratio : on garde la bande centrale (l'horizon et le halo),
    # pas le ciel vide du haut ni le sol du bas.
    target_height = zone.width * HEIGHT // WIDTH
    top = min((zone.height - target_height) // 2 + _CROP_DROP, zone.height - target_height)
    cropped = zone.crop((0, top, zone.width, top + target_height))
    backdrop = cropped.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    scrim = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    return Image.blend(backdrop, scrim, _SCRIM)


def _paste_logo(canvas: Image.Image, width: int, top: int) -> int:
    """Colle le logo GAMMA centré ; retourne l'ordonnée de son bas."""
    logo = Image.open(_LOGO).convert("RGBA")
    height = logo.height * width // logo.width
    logo = logo.resize((width, height), Image.Resampling.LANCZOS)
    canvas.paste(logo, ((WIDTH - width) // 2, top), logo)
    return top + height


def _centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
    fill: tuple[int, int, int],
) -> int:
    """Écrit `text` centré horizontalement ; retourne l'ordonnée du bas."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (right - left)) // 2 - left, y - top), text, font=font, fill=fill)
    return y + (bottom - top)


def generate() -> Image.Image:
    canvas = _zone_backdrop()
    logo_bottom = _paste_logo(canvas, width=440, top=48)

    draw = ImageDraw.Draw(canvas)
    y = logo_bottom + 40
    y = _centered(draw, _TITLE, _load_font(_MONO_CANDIDATES, 44), y, _ACCENT) + 40
    y = _centered(draw, _PROMISE, _load_font(_SANS_CANDIDATES, 42), y, _TEXT) + 22
    _centered(draw, _SUBLINE, _load_font(_SANS_LIGHT_CANDIDATES, 26), y, _MUTED)

    footer = _load_font(_SANS_LIGHT_CANDIDATES, 24)
    _centered(draw, _DISTROS, footer, HEIGHT - 78, _TEXT)
    _centered(draw, _DISCLAIMER, _load_font(_SANS_LIGHT_CANDIDATES, 19), HEIGHT - 40, _MUTED)
    return canvas


# GitHub refuse au-delà de 1 Mio, et un PNG vrai-couleur de cette Zone en fait
# 1,05 : le grain argentique de l'artwork est exactement ce qu'un PNG compresse
# le plus mal. Une palette de 256 couleurs avec tramage divise le poids par deux
# sans que la différence se voie en vignette — c'est du grain sur du grain.
_PALETTE_COLORS = 256


def _packed(image: Image.Image) -> Image.Image:
    return image.quantize(
        colors=_PALETTE_COLORS,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG,
    )


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    _packed(generate()).save(output, "PNG", optimize=True)
    print(f"écrit : {output} ({output.stat().st_size // 1024} Kio)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
