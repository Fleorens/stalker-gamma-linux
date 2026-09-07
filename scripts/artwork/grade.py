"""Étalonnage : ce qui transforme un rendu correct en image de jeu.

Bloom, aberration chromatique, vignette, grain, virage bicolore. Ces passes
travaillent toutes sur un tableau `float32` (H, W, 3) en scène linéaire [0, 1]
et en renvoient un nouveau — rien n'est modifié en place, on peut donc les
composer dans n'importe quel ordre sans effet de bord.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

Array = np.ndarray


def _blur(channel: Array, radius: float) -> Array:
    scaled = np.clip(channel, 0.0, 1.0) * 255.0
    blurred = Image.fromarray(scaled.astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(blurred, dtype=np.float32) / 255.0


def bloom(
    image: Array, *, threshold: float = 0.55, radius: float = 26.0, strength: float = 0.5
) -> Array:
    """Diffusion lumineuse autour des zones vives — le halo d'un objectif réel."""
    luminance = image @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    excess = np.clip(luminance - threshold, 0.0, None) / max(1e-6, 1.0 - threshold)
    highlights = image * excess[:, :, None]
    spread = np.stack([_blur(highlights[:, :, c], radius) for c in range(3)], axis=2)
    return image + spread * strength


def chromatic_aberration(image: Array, *, amount: float = 0.0016) -> Array:
    """Décalage radial rouge/bleu : présent seulement dans les coins, comme en optique."""
    height, width, _ = image.shape
    ys, xs = np.meshgrid(
        np.linspace(-1.0, 1.0, height, dtype=np.float32),
        np.linspace(-1.0, 1.0, width, dtype=np.float32),
        indexing="ij",
    )
    shift_x = (xs * amount * width).astype(np.int32)
    shift_y = (ys * amount * height).astype(np.int32)
    rows, cols = np.indices((height, width))

    def sample(channel: Array, sign: int) -> Array:
        source_y = np.clip(rows + sign * shift_y, 0, height - 1)
        source_x = np.clip(cols + sign * shift_x, 0, width - 1)
        return channel[source_y, source_x]

    return np.stack([sample(image[:, :, 0], 1), image[:, :, 1], sample(image[:, :, 2], -1)], axis=2)


def vignette(image: Array, *, strength: float = 0.55, radius: float = 0.78) -> Array:
    """Assombrissement des bords : le regard tombe au centre, et le texte de
    l'interface se pose sur des coins déjà calmes."""
    height, width, _ = image.shape
    ys, xs = np.meshgrid(
        np.linspace(-1.0, 1.0, height, dtype=np.float32),
        np.linspace(-1.0, 1.0, width, dtype=np.float32),
        indexing="ij",
    )
    distance = np.sqrt(xs**2 + ys**2) / radius
    falloff = np.clip(1.0 - strength * np.clip(distance - 0.35, 0.0, None) ** 1.7, 0.0, 1.0)
    return image * falloff[:, :, None]


def split_tone(image: Array, *, shadows: Array, highlights: Array, amount: float = 0.14) -> Array:
    """Virage bicolore : ombres froides, hautes lumières chaudes.

    C'est l'étalonnage qui donne sa cohérence au tout — sans lui, brume verte,
    ciel bleuté et halo ambré cohabitent sans appartenir à la même image.
    """
    luminance = (image @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))[:, :, None]
    tint = shadows[None, None, :] * (1.0 - luminance) + highlights[None, None, :] * luminance
    return image * (1.0 - amount) + tint * amount * 2.0 * np.clip(image + 0.12, 0.0, 1.0)


def contrast_curve(image: Array, *, pivot: float = 0.34, slope: float = 1.16) -> Array:
    """Courbe en S douce autour du point gris : du noir dense, sans boucher."""
    return np.clip(pivot + (image - pivot) * slope, 0.0, 1.0)


def grain(image: Array, rng: np.random.Generator, *, amount: float = 0.026) -> Array:
    """Grain argentique, plus visible dans les basses lumières (comme une pellicule)."""
    noise = rng.standard_normal(image.shape[:2]).astype(np.float32)
    weight = (1.0 - np.clip(image.mean(axis=2), 0.0, 1.0)) * 0.7 + 0.3
    return image + (noise * weight * amount)[:, :, None]


def to_image(array: Array) -> Image.Image:
    """Tableau linéaire → image 8 bits, avec un gamma d'affichage discret."""
    clipped = np.clip(array, 0.0, 1.0) ** (1.0 / 1.06)
    return Image.fromarray((clipped * 255.0 + 0.5).astype(np.uint8), "RGB")
