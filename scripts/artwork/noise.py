"""Bruits procéduraux de l'artwork : fBm, chaleur, poussière.

Aucune texture externe — tout vient d'un `numpy.random.Generator` à graine
fixe, donc deux exécutions donnent le même pixel. Séparé de `scene.py` pour
que la composition se lise sans le détail des octaves.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

Array = np.ndarray


def _smooth_layer(rng: np.random.Generator, shape: tuple[int, int], cells: int) -> Array:
    """Une octave : bruit blanc grossier réétiré en bicubique à la taille finale."""
    height, width = shape
    rows = max(2, round(cells * height / width))
    coarse = (rng.random((rows, cells)) * 255).astype(np.uint8)
    stretched = Image.fromarray(coarse).resize((width, height), Image.Resampling.BICUBIC)
    return np.asarray(stretched, dtype=np.float32) / 255.0


def fbm(
    rng: np.random.Generator,
    shape: tuple[int, int],
    *,
    octaves: int = 5,
    persistence: float = 0.55,
    base_cells: int = 4,
) -> Array:
    """Bruit fractal dans [0, 1] : somme d'octaves de plus en plus fines."""
    total = np.zeros(shape, dtype=np.float32)
    amplitude, norm = 1.0, 0.0
    for octave in range(octaves):
        total += amplitude * _smooth_layer(rng, shape, base_cells * 2**octave)
        norm += amplitude
        amplitude *= persistence
    return total / norm


def warped_fbm(
    rng: np.random.Generator,
    shape: tuple[int, int],
    *,
    octaves: int = 5,
    strength: float = 0.06,
) -> Array:
    """fBm dont les coordonnées sont déplacées par un autre fBm.

    C'est ce qui distingue une brume d'un simple nuage de bruit : les volutes
    s'étirent et s'enroulent au lieu de rester des taches isotropes.
    """
    height, width = shape
    field = fbm(rng, shape, octaves=octaves)
    offset_x = (fbm(rng, shape, octaves=3, base_cells=3) - 0.5) * strength * width
    offset_y = (fbm(rng, shape, octaves=3, base_cells=3) - 0.5) * strength * height

    ys, xs = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
    sample_x = np.clip((xs + offset_x).astype(np.int32), 0, width - 1)
    sample_y = np.clip((ys + offset_y).astype(np.int32), 0, height - 1)
    return field[sample_y, sample_x]


def gradient_x(width: int, height: int) -> Array:
    """Rampe horizontale 0→1, diffusée sur toute la hauteur."""
    return np.tile(np.linspace(0.0, 1.0, width, dtype=np.float32), (height, 1))


def gradient_y(width: int, height: int) -> Array:
    """Rampe verticale 0→1, diffusée sur toute la largeur."""
    return np.tile(np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None], (1, width))


def radial(width: int, height: int, cx: float, cy: float, radius: float) -> Array:
    """Halo gaussien [0, 1] centré en (cx, cy), en fractions de l'image.

    Le rayon est corrigé du rapport d'aspect : un halo demandé rond sort rond,
    pas ovale, quelle que soit la taille de l'image.
    """
    aspect = width / height
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    squared = ((xs - cx) * aspect) ** 2 + (ys - cy) ** 2
    return np.exp(-squared / (2.0 * radius**2)).astype(np.float32)


def smoothstep(edge0: float, edge1: float, values: Array) -> Array:
    """Interpolation en S entre deux seuils — transitions sans cassure visible."""
    t = np.clip((values - edge0) / (edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)
