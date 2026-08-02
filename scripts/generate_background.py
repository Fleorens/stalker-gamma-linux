#!/usr/bin/env python3
"""Génère l'artwork de fond de la GUI (`src/stalker_gamma_linux/assets/background.jpg`).

Procédural et déterministe (seed fixe) : brume verte de la Zone sur un dégradé
nocturne, silhouette d'horizon, halo d'anomalie, vignette et grain argentique.
Aucun asset externe — rien à créditer, rien à retélécharger ; relancer ce
script reproduit exactement la même image. Nécessite numpy + Pillow (déjà
présents dans l'environnement de dev ; jamais importés par le paquet lui-même).

Usage : python scripts/generate_background.py [sortie.jpg]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

WIDTH, HEIGHT = 1920, 1080
SEED = 1986  # année de Tchernobyl — et un rendu qu'on a validé visuellement

# Palette (RGB float 0-1) : nuit dans la Zone, vert toxique en accent.
SKY_TOP = np.array([0.020, 0.024, 0.016])
SKY_MID = np.array([0.055, 0.075, 0.038])
GROUND = np.array([0.016, 0.020, 0.012])
FOG_GREEN = np.array([0.290, 0.430, 0.150])
GLOW_GREEN = np.array([0.480, 0.750, 0.240])

_DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "stalker_gamma_linux"
    / "assets"
    / "background.jpg"
)


def _fbm(rng: np.random.Generator, shape: tuple[int, int], octaves: int = 5) -> np.ndarray:
    """Bruit fractal [0,1] : somme d'octaves de bruit blanc lissé par upscaling."""
    height, width = shape
    total = np.zeros(shape, dtype=np.float64)
    amplitude, norm = 1.0, 0.0
    for octave in range(octaves):
        cells = 2 ** (octave + 2)
        coarse = rng.random((max(2, height * cells // width), cells))
        layer = np.asarray(
            Image.fromarray((coarse * 255).astype(np.uint8)).resize(
                (width, height), Image.Resampling.BICUBIC
            ),
            dtype=np.float64,
        )
        total += amplitude * layer / 255.0
        norm += amplitude
        amplitude *= 0.55
    return total / norm


def _vertical_gradient() -> np.ndarray:
    """Dégradé ciel → brume → sol, sur toute la hauteur."""
    t = np.linspace(0.0, 1.0, HEIGHT)[:, None, None]
    upper = SKY_TOP + (SKY_MID - SKY_TOP) * np.clip(t / 0.62, 0.0, 1.0) ** 1.4
    lower_mix = np.clip((t - 0.62) / 0.38, 0.0, 1.0) ** 0.8
    return upper * (1.0 - lower_mix) + GROUND * lower_mix


def _horizon_mask(rng: np.random.Generator) -> np.ndarray:
    """Masque [0,1] de la silhouette (ruines/arbres) : 1 sous la ligne d'horizon."""
    base = HEIGHT * 0.66
    profile = _fbm(rng, (1, WIDTH), octaves=6)[0]
    spikes = (profile - 0.5) * HEIGHT * 0.16
    ys = np.arange(HEIGHT)[:, None]
    edge = base + spikes[None, :]
    return np.clip((ys - edge) / 14.0, 0.0, 1.0)


def _radial_glow(cx: float, cy: float, radius: float) -> np.ndarray:
    """Halo doux [0,1] centré en (cx, cy) — fractions de la taille de l'image."""
    xs = np.linspace(0.0, 1.0, WIDTH)[None, :]
    ys = np.linspace(0.0, 1.0, HEIGHT)[:, None]
    aspect = WIDTH / HEIGHT
    dist2 = ((xs - cx) * aspect) ** 2 + (ys - cy) ** 2
    return np.exp(-dist2 / (2.0 * radius**2))


def _vignette() -> np.ndarray:
    return 1.0 - 0.62 * (1.0 - _radial_glow(0.5, 0.52, 0.55))


def _particles(rng: np.random.Generator) -> Image.Image:
    """Poussières/spores en suspension : petits points doux, épars."""
    layer = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(layer)
    for _ in range(90):
        x, y = rng.uniform(0, WIDTH), rng.uniform(HEIGHT * 0.25, HEIGHT * 0.92)
        r = rng.uniform(0.7, 2.4)
        alpha = int(rng.uniform(30, 110))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=alpha)
    return layer.filter(ImageFilter.GaussianBlur(1.1))


def generate() -> Image.Image:
    rng = np.random.default_rng(SEED)
    image = _vertical_gradient().repeat(1, axis=1) * np.ones((HEIGHT, WIDTH, 3))

    # Brume verte : bande horizontale de fBm, plus dense près de l'horizon.
    fog = _fbm(rng, (HEIGHT, WIDTH), octaves=5)
    band = np.exp(-(((np.linspace(0.0, 1.0, HEIGHT) - 0.60) / 0.16) ** 2))[:, None]
    image += FOG_GREEN[None, None, :] * (fog * band)[:, :, None] * 0.30

    # Halo d'anomalie, décentré — la lueur qui donne sa profondeur à la scène.
    image += GLOW_GREEN[None, None, :] * _radial_glow(0.68, 0.60, 0.10)[:, :, None] * 0.16

    # Silhouette d'horizon (presque noire) par-dessus brume et halo.
    horizon = _horizon_mask(rng)[:, :, None]
    image = image * (1.0 - horizon) + GROUND[None, None, :] * 0.55 * horizon

    image *= _vignette()[:, :, None]

    # Grain argentique fin.
    image += (rng.random((HEIGHT, WIDTH, 1)) - 0.5) * 0.028

    result = Image.fromarray((np.clip(image, 0.0, 1.0) * 255).astype(np.uint8), "RGB")

    particles = _particles(rng)
    glow_tint = Image.new("RGB", (WIDTH, HEIGHT), (168, 220, 120))
    result.paste(glow_tint, (0, 0), particles)
    return result


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    generate().save(output, "JPEG", quality=87, optimize=True)
    print(f"écrit : {output} ({output.stat().st_size // 1024} Kio)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
