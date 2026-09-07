"""Silhouettes de la Zone : crête, Duga, cheminée, pylônes, arbres morts.

Chaque fonction rend un **masque** (mode « L », 0 = ciel, 255 = matière) que
`scene.py` teinte et fond dans la brume selon sa distance. Tout est tracé à
`SUPERSAMPLE` fois la taille finale puis réduit : c'est ce qui donne des
treillis fins nets plutôt que des escaliers de pixels.

Le vocabulaire visuel est celui de la Zone — l'antenne Duga, la cheminée de la
centrale, les pylônes qui ne portent plus rien — et il est *dessiné*, pas
photographié : aucun asset externe, donc rien à créditer ni à retélécharger.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SUPERSAMPLE = 2

Mask = Image.Image


def new_mask(width: int, height: int) -> tuple[Mask, ImageDraw.ImageDraw]:
    """Masque vide à la résolution de travail (supersamplée) et son crayon."""
    mask = Image.new("L", (width * SUPERSAMPLE, height * SUPERSAMPLE), 0)
    return mask, ImageDraw.Draw(mask)


def resolve(mask: Mask, width: int, height: int, *, softness: float = 0.0) -> np.ndarray:
    """Ramène un masque à la taille finale, en [0, 1]. `softness` = flou de distance."""
    # BOX et non LANCZOS : un noyau à lobes négatifs *dépasse* de part et
    # d'autre d'une arête franche, et une silhouette noire sur ciel clair
    # ressort alors bordée d'un liseré plus clair qu'elle. BOX moyenne
    # exactement les sous-pixels — c'est ce qu'on veut d'un supersampling.
    reduced = mask.resize((width, height), Image.Resampling.BOX)
    if softness > 0:
        reduced = reduced.filter(ImageFilter.GaussianBlur(softness))
    return np.asarray(reduced, dtype=np.float32) / 255.0


def _s(value: float) -> int:
    """Coordonnée finale → coordonnée de travail."""
    return int(round(value * SUPERSAMPLE))


def ridge(
    draw: ImageDraw.ImageDraw,
    rng: np.random.Generator,
    *,
    width: int,
    height: int,
    base_y: float,
    amplitude: float,
    roughness: int = 6,
) -> None:
    """Ligne d'horizon irrégulière, remplie jusqu'en bas de l'image."""
    from artwork.noise import fbm

    profile = fbm(rng, (1, width), octaves=roughness, base_cells=3)[0]
    line = base_y + (profile - profile.mean()) * amplitude
    points = [(_s(x), _s(float(line[x]))) for x in range(width)]
    draw.polygon(
        [(0, _s(height)), *points, (_s(width), _s(height))],
        fill=255,
    )


def duga(
    draw: ImageDraw.ImageDraw,
    *,
    left: float,
    right: float,
    base_y: float,
    top_y: float,
    bays: int = 26,
) -> None:
    """L'antenne Duga : un mur de treillis, ses haubans et ses dipôles.

    Volontairement schématique — à cette distance et sous cette brume, c'est la
    *silhouette* qui est reconnaissable, pas le détail des poutrelles.
    """
    span = right - left
    bay_width = span / bays
    post = max(1, _s(bay_width * 0.09))
    rail = max(1, _s(bay_width * 0.06))

    # Montants verticaux, de hauteur légèrement variable (le mur n'est pas droit).
    for index in range(bays + 1):
        x = left + index * bay_width
        crown = top_y + (base_y - top_y) * (0.06 if index % 4 else 0.0)
        draw.line([(_s(x), _s(base_y)), (_s(x), _s(crown))], fill=255, width=post)

    # Lisses horizontales : cinq niveaux, comme les plateformes de service.
    for level in range(5):
        y = top_y + (base_y - top_y) * (0.08 + level * 0.22)
        draw.line([(_s(left), _s(y)), (_s(right), _s(y))], fill=255, width=rail)

    # Croix de Saint-André dans une travée sur deux : la texture qui « fait » Duga.
    for index in range(bays):
        if index % 2:
            continue
        x0, x1 = left + index * bay_width, left + (index + 1) * bay_width
        for level in range(4):
            y0 = top_y + (base_y - top_y) * (0.08 + level * 0.22)
            y1 = top_y + (base_y - top_y) * (0.08 + (level + 1) * 0.22)
            draw.line([(_s(x0), _s(y0)), (_s(x1), _s(y1))], fill=255, width=rail)
            draw.line([(_s(x0), _s(y1)), (_s(x1), _s(y0))], fill=255, width=rail)

    # Dipôles en couronne : les « cornes » qui dépassent du mur.
    for index in range(0, bays + 1, 2):
        x = left + index * bay_width
        draw.line([(_s(x), _s(top_y)), (_s(x), _s(top_y - bay_width * 0.7))], fill=255, width=rail)


def cooling_tower(
    draw: ImageDraw.ImageDraw, *, cx: float, base_y: float, height: float, waist: float
) -> None:
    """Tour de refroidissement : hyperboloïde, évasée en haut et en bas."""
    steps = 40
    left_edge, right_edge = [], []
    for step in range(steps + 1):
        t = step / steps
        y = base_y - height * t
        # Profil en cosinus : large en bas, resserré à 65 %, réévasé au sommet.
        flare = 1.0 + 0.55 * (t - 0.65) ** 2 / 0.42
        half = waist * flare
        left_edge.append((_s(cx - half), _s(y)))
        right_edge.append((_s(cx + half), _s(y)))
    draw.polygon([*left_edge, *reversed(right_edge)], fill=255)


def chimney(
    draw: ImageDraw.ImageDraw, *, cx: float, base_y: float, height: float, half_width: float
) -> None:
    """Cheminée à bandes — la verticale qui donne l'échelle au reste."""
    top_y = base_y - height
    draw.polygon(
        [
            (_s(cx - half_width * 1.6), _s(base_y)),
            (_s(cx - half_width), _s(top_y)),
            (_s(cx + half_width), _s(top_y)),
            (_s(cx + half_width * 1.6), _s(base_y)),
        ],
        fill=255,
    )
    # Anneaux de la cheminée : deux plateformes, en négatif dans la silhouette.
    for ratio in (0.42, 0.72):
        y = base_y - height * ratio
        draw.line(
            [(_s(cx - half_width * 2.2), _s(y)), (_s(cx + half_width * 2.2), _s(y))],
            fill=255,
            width=max(1, _s(half_width * 0.35)),
        )


def pylon(draw: ImageDraw.ImageDraw, *, cx: float, base_y: float, height: float) -> None:
    """Pylône haute tension : fût en treillis, deux traverses, trois isolateurs."""
    half_base, half_top = height * 0.16, height * 0.045
    thickness = max(1, _s(height * 0.012))
    for side in (-1, 1):
        draw.line(
            [
                (_s(cx + side * half_base), _s(base_y)),
                (_s(cx + side * half_top), _s(base_y - height)),
            ],
            fill=255,
            width=thickness,
        )
    for level in range(6):
        t0, t1 = level / 6, (level + 1) / 6
        y0, y1 = base_y - height * t0, base_y - height * t1
        w0 = half_base + (half_top - half_base) * t0
        w1 = half_base + (half_top - half_base) * t1
        draw.line([(_s(cx - w0), _s(y0)), (_s(cx + w1), _s(y1))], fill=255, width=thickness)
        draw.line([(_s(cx + w0), _s(y0)), (_s(cx - w1), _s(y1))], fill=255, width=thickness)
    for ratio, arm in ((0.74, 0.30), (0.90, 0.22)):
        y = base_y - height * ratio
        draw.line(
            [(_s(cx - height * arm), _s(y)), (_s(cx + height * arm), _s(y))],
            fill=255,
            width=thickness,
        )


def cable(
    draw: ImageDraw.ImageDraw,
    *,
    start: tuple[float, float],
    end: tuple[float, float],
    sag: float,
) -> None:
    """Câble entre deux pylônes — une chaînette, pas un segment droit."""
    (x0, y0), (x1, y1) = start, end
    points = []
    for step in range(33):
        t = step / 32
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t + sag * 4 * t * (1 - t)
        points.append((_s(x), _s(y)))
    draw.line(points, fill=255, width=max(1, SUPERSAMPLE))


def dead_tree(
    draw: ImageDraw.ImageDraw,
    rng: np.random.Generator,
    *,
    cx: float,
    base_y: float,
    height: float,
) -> None:
    """Arbre mort : tronc et branches, par subdivision récursive."""

    def branch(x: float, y: float, angle: float, length: float, thickness: float) -> None:
        if length < height * 0.045:
            return
        end_x = x + np.sin(angle) * length
        end_y = y - np.cos(angle) * length
        draw.line(
            [(_s(x), _s(y)), (_s(end_x), _s(end_y))],
            fill=255,
            width=max(1, _s(thickness)),
        )
        for side in (-1, 1):
            spread = float(rng.uniform(0.28, 0.62)) * side
            branch(
                end_x,
                end_y,
                angle + spread,
                length * float(rng.uniform(0.58, 0.76)),
                thickness * 0.62,
            )

    branch(cx, base_y, float(rng.uniform(-0.08, 0.08)), height * 0.42, height * 0.028)


def grass(
    draw: ImageDraw.ImageDraw,
    rng: np.random.Generator,
    *,
    width: int,
    base_y: float,
    blades: int = 900,
    max_height: float,
) -> None:
    """Herbes hautes du premier plan : la bande qui ancre le regard en bas."""
    for _ in range(blades):
        x = float(rng.uniform(-0.02, 1.02)) * width
        blade_height = float(rng.uniform(0.35, 1.0)) * max_height
        lean = float(rng.uniform(-0.35, 0.35)) * blade_height
        draw.line(
            [(_s(x), _s(base_y)), (_s(x + lean), _s(base_y - blade_height))],
            fill=255,
            width=max(1, SUPERSAMPLE),
        )


def particles(
    draw: ImageDraw.ImageDraw,
    rng: np.random.Generator,
    *,
    width: int,
    height: int,
    count: int,
    band: tuple[float, float],
) -> None:
    """Poussières en suspension : des points, pas des taches.

    Tracées une à une plutôt que seuillées dans un bruit — un bruit fractal
    élevé à une grande puissance donne des *amas* de la taille de sa maille,
    ce qui se lit comme de la neige sale, pas comme de la poussière.
    """
    top, bottom = band
    for _ in range(count):
        x = float(rng.uniform(0.0, 1.0)) * width
        y = float(rng.uniform(top, bottom)) * height
        radius = float(rng.uniform(0.5, 1.9))
        brightness = int(rng.uniform(40, 190))
        draw.ellipse(
            (_s(x - radius), _s(y - radius), _s(x + radius), _s(y + radius)),
            fill=brightness,
        )
