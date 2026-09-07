"""Composition de l'artwork : la Zone à la tombée du jour, en couches.

Ordre de lecture = ordre de profondeur. Ciel, halo voilé, brume lointaine,
puis trois plans de silhouettes de plus en plus contrastés (perspective
atmosphérique : ce qui est loin est *plus clair et plus flou*, pas plus petit),
enfin l'anomalie et les poussières. `grade.py` termine le travail.

Contrainte de mise en page, pas seulement d'esthétique : l'interface pose son
contenu en bas de l'image (logo et état à gauche, boutons à droite). Le tiers
inférieur reste donc volontairement calme et sombre — tout l'intérêt visuel est
placé au-dessus de la ligne d'horizon, là où rien ne viendra le recouvrir.
"""

from __future__ import annotations

import numpy as np

from artwork import grade, noise, silhouettes

Array = np.ndarray

SEED = 1986  # année de Tchernobyl — et un rendu validé visuellement

# Palette (RGB scène-linéaire). Le vert de la Zone n'est jamais pur : il naît
# du mélange d'un ciel froid et d'une brume jaune, ce qui lui évite le vert
# « néon » d'un simple aplat teinté.
SKY_ZENITH = np.array([0.013, 0.022, 0.028], dtype=np.float32)
SKY_UPPER = np.array([0.028, 0.046, 0.046], dtype=np.float32)
SKY_HORIZON = np.array([0.135, 0.150, 0.080], dtype=np.float32)
SUN_CORE = np.array([0.90, 0.72, 0.36], dtype=np.float32)
FOG = np.array([0.150, 0.180, 0.108], dtype=np.float32)
GROUND = np.array([0.016, 0.022, 0.017], dtype=np.float32)
ANOMALY = np.array([0.36, 0.82, 0.26], dtype=np.float32)
SHADOW_TINT = np.array([0.10, 0.26, 0.30], dtype=np.float32)
HIGHLIGHT_TINT = np.array([0.72, 0.58, 0.26], dtype=np.float32)

HORIZON = 0.615  # hauteur de la ligne d'horizon, en fraction de l'image
SUN = (0.690, 0.578)  # centre du disque voilé


def _sky(width: int, height: int) -> Array:
    """Dégradé zénith → brume d'horizon, en deux temps pour éviter la bande plate."""
    t = noise.gradient_y(width, height)
    upper = (
        SKY_ZENITH[None, None, :]
        + (SKY_UPPER - SKY_ZENITH)[None, None, :]
        * (noise.smoothstep(0.0, HORIZON, t) ** 1.5)[:, :, None]
    )
    glow = (noise.smoothstep(HORIZON - 0.42, HORIZON + 0.02, t) ** 2.2)[:, :, None]
    return upper * (1.0 - glow) + SKY_HORIZON[None, None, :] * glow


def _sun(width: int, height: int) -> Array:
    """Disque voilé + halo + rayons crépusculaires."""
    cx, cy = SUN
    disc = noise.radial(width, height, cx, cy, 0.014) ** 1.2
    halo = noise.radial(width, height, cx, cy, 0.095) * 0.30
    wide = noise.radial(width, height, cx, cy, 0.32) * 0.16

    # Rayons : bruit purement angulaire, donc des traînées droites issues du
    # disque — pas des taches. Atténués au sol, où la brume les mange.
    aspect = width / height
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    theta = np.arctan2(ys - cy, (xs - cx) * aspect)
    angular = np.random.default_rng(SEED + 7).random(96).astype(np.float32)
    ray_shape = np.interp(
        (theta + np.pi) / (2 * np.pi) * 96.0, np.arange(96), angular, period=96
    ).astype(np.float32)
    rays = noise.radial(width, height, cx, cy, 0.34) * (0.35 + 0.65 * ray_shape) * 0.20

    intensity = disc * 0.75 + halo + wide + rays
    return SUN_CORE[None, None, :] * intensity[:, :, None]


def _fog_band(
    rng: np.random.Generator,
    width: int,
    height: int,
    *,
    center: float,
    spread: float,
    depth: Array,
) -> Array:
    """Nappe de brume horizontale, texturée par un fBm déformé."""
    texture = noise.warped_fbm(rng, (height, width), octaves=5, strength=0.05)
    band = np.exp(-(((depth - center) / spread) ** 2))
    return (texture * 0.75 + 0.25) * band


def _layer(
    base: Array, mask: Array, *, haze: float, tone: Array, fog_mix: Array | None = None
) -> Array:
    """Pose une silhouette : d'autant plus délavée par la brume qu'elle est loin."""
    color = tone[None, None, :] * (1.0 - haze) + FOG[None, None, :] * haze
    if fog_mix is not None:
        color = color + FOG[None, None, :] * fog_mix[:, :, None] * haze * 0.8
    alpha = mask[:, :, None]
    return base * (1.0 - alpha) + color * alpha


def _far_plane(rng: np.random.Generator, width: int, height: int) -> Array:
    """Crête lointaine, tour de refroidissement, cheminée, et l'antenne Duga."""
    mask, draw = silhouettes.new_mask(width, height)
    silhouettes.ridge(
        draw,
        rng,
        width=width,
        height=height,
        base_y=HORIZON * height,
        amplitude=height * 0.030,
        roughness=6,
    )
    silhouettes.cooling_tower(
        draw,
        cx=width * 0.175,
        base_y=height * (HORIZON + 0.004),
        height=height * 0.125,
        waist=width * 0.026,
    )
    silhouettes.chimney(
        draw,
        cx=width * 0.262,
        base_y=height * (HORIZON + 0.004),
        height=height * 0.185,
        half_width=width * 0.0045,
    )
    silhouettes.duga(
        draw,
        left=width * 0.505,
        right=width * 0.895,
        base_y=height * (HORIZON + 0.006),
        top_y=height * 0.205,
        bays=24,
    )
    return silhouettes.resolve(mask, width, height, softness=height * 0.0018)


def _forest(rng: np.random.Generator, width: int, height: int) -> Array:
    """Bande de forêt entre l'horizon et le plan intermédiaire.

    Deux crêtes suffisaient à séparer ciel et sol ; il en fallait une troisième
    pour que la séparation soit une *distance* et pas une arête.
    """
    mask, draw = silhouettes.new_mask(width, height)
    silhouettes.ridge(
        draw,
        rng,
        width=width,
        height=height,
        base_y=height * (HORIZON - 0.004),
        amplitude=height * 0.055,
        roughness=9,
    )
    return silhouettes.resolve(mask, width, height, softness=height * 0.0014)


def _mid_plane(rng: np.random.Generator, width: int, height: int) -> Array:
    """Ligne d'arbres et pylônes qui ne portent plus rien."""
    mask, draw = silhouettes.new_mask(width, height)
    silhouettes.ridge(
        draw,
        rng,
        width=width,
        height=height,
        base_y=height * (HORIZON + 0.078),
        amplitude=height * 0.070,
        roughness=9,
    )
    positions = (0.135, 0.275, 0.415)
    tops = []
    for x in positions:
        pylon_height = height * 0.165
        silhouettes.pylon(
            draw, cx=width * x, base_y=height * (HORIZON + 0.085), height=pylon_height
        )
        tops.append((width * x, height * (HORIZON + 0.085) - pylon_height * 0.74))
    for start, end in zip(tops, tops[1:], strict=False):
        for offset in (-0.30, 0.0, 0.30):
            shift = height * 0.165 * offset
            silhouettes.cable(
                draw,
                start=(start[0] + shift, start[1]),
                end=(end[0] + shift, end[1]),
                sag=height * 0.022,
            )
    return silhouettes.resolve(mask, width, height, softness=height * 0.0009)


def _near_plane(rng: np.random.Generator, width: int, height: int) -> Array:
    """Premier plan : deux arbres morts en bord de cadre, et les herbes hautes.

    Rien au centre : c'est là que l'interface écrit. Les arbres tiennent les
    bords, l'herbe tient la lisière basse, le milieu reste lisible.
    """
    mask, draw = silhouettes.new_mask(width, height)
    for cx, tree_height in ((0.105, 0.44), (0.895, 0.36), (0.815, 0.22)):
        silhouettes.dead_tree(
            draw, rng, cx=width * cx, base_y=height * 1.02, height=height * tree_height
        )
    silhouettes.grass(
        draw, rng, width=width, base_y=height * 1.015, blades=1100, max_height=height * 0.075
    )
    return silhouettes.resolve(mask, width, height, softness=height * 0.0006)


def _horizon_line(rng: np.random.Generator, width: int, height: int) -> Array:
    """Écart vertical de la ligne d'horizon, colonne par colonne.

    Un `smoothstep` sur y seul donne une séparation ciel/sol parfaitement
    droite — une mer, pas une plaine. Le même écart sert au sol *et* aux nappes
    de brume, sinon les deux se décalent et la couture réapparaît.
    """
    profile = noise.fbm(rng, (1, width), octaves=5, base_cells=3)[0]
    return np.tile((profile - profile.mean()) * 0.055, (height, 1)).astype(np.float32)


def _clouds(rng: np.random.Generator, width: int, height: int) -> Array:
    """Voile nuageux du haut du ciel : sans lui, le tiers supérieur est un aplat noir."""
    texture = noise.warped_fbm(rng, (height, width), octaves=6, strength=0.09)
    band = 1.0 - noise.smoothstep(0.05, HORIZON - 0.06, noise.gradient_y(width, height))
    return np.clip(texture - 0.42, 0.0, None) * band


def _motes(rng: np.random.Generator, width: int, height: int) -> Array:
    """Poussières éclairées par le halo — visibles là où la lumière les prend."""
    mask, draw = silhouettes.new_mask(width, height)
    silhouettes.particles(
        draw, rng, width=width, height=height, count=220, band=(0.30, HORIZON + 0.16)
    )
    lit = noise.radial(width, height, 0.66, HORIZON - 0.01, 0.24)
    return silhouettes.resolve(mask, width, height, softness=height * 0.001) * lit


def _ground_mist(rng: np.random.Generator, width: int, height: int, depth: Array) -> Array:
    """Brume rasante qui court sur le sol — la Zone au petit matin."""
    texture = noise.warped_fbm(rng, (height, width), octaves=4, strength=0.10)
    band = np.exp(-(((depth - (HORIZON + 0.130)) / 0.115) ** 2))
    return np.clip(texture - 0.38, 0.0, None) * band


def render(width: int, height: int) -> Array:
    """L'artwork complet, en scène linéaire — `grade.to_image` finit le travail."""
    rng = np.random.default_rng(SEED)

    image = _sky(width, height)
    image = image + SKY_HORIZON[None, None, :] * _clouds(rng, width, height)[:, :, None] * 0.55
    image = image + _sun(width, height)

    # Sol : sous l'horizon, le ciel laisse place à la terre, sans couture nette.
    depth = noise.gradient_y(width, height) - _horizon_line(rng, width, height)
    ground_mask = noise.smoothstep(HORIZON - 0.01, HORIZON + 0.09, depth)
    # Assombri vers le bas du cadre : c'est là que l'interface écrit.
    ground = (
        GROUND[None, None, :] * (1.0 - 0.55 * noise.smoothstep(HORIZON, 1.0, depth))[:, :, None]
    )
    # Sans texture, la moitié basse est un aplat mort : un fBm très large donne
    # au sol un relief à peine perceptible, mais qui suffit à le faire exister.
    terrain = noise.fbm(rng, (height, width), octaves=3, base_cells=2)
    ground = ground * (0.72 + 0.55 * terrain)[:, :, None]
    image = image * (1.0 - ground_mask[:, :, None]) + ground * ground_mask[:, :, None]

    far_fog = _fog_band(rng, width, height, center=HORIZON - 0.01, spread=0.075, depth=depth)
    image = image + FOG[None, None, :] * far_fog[:, :, None] * 0.70

    image = _layer(image, _far_plane(rng, width, height), haze=0.66, tone=GROUND, fog_mix=far_fog)

    mid_fog = _fog_band(rng, width, height, center=HORIZON + 0.055, spread=0.055, depth=depth)
    image = image + FOG[None, None, :] * mid_fog[:, :, None] * 0.34

    image = _layer(image, _forest(rng, width, height), haze=0.52, tone=GROUND)
    image = _layer(image, _mid_plane(rng, width, height), haze=0.26, tone=GROUND)

    # L'anomalie : une lueur au sol, décentrée, qui justifie le vert de la palette.
    anomaly = noise.radial(width, height, 0.585, HORIZON + 0.070, 0.052)
    anomaly = anomaly * noise.smoothstep(HORIZON - 0.02, HORIZON + 0.03, depth)
    anomaly = anomaly * (0.55 + 0.45 * noise.warped_fbm(rng, (height, width), octaves=4))
    image = image + ANOMALY[None, None, :] * (anomaly**1.35)[:, :, None] * 0.30

    # La brume rasante passe DEVANT l'anomalie : elle la diffuse au lieu de la border.
    mist = _ground_mist(rng, width, height, depth)
    image = image + (FOG * 0.8 + ANOMALY * 0.2)[None, None, :] * mist[:, :, None] * 0.58

    image = _layer(image, _near_plane(rng, width, height), haze=0.06, tone=GROUND * 0.35)

    # Poussières en suspension, éclairées par la lueur : la Zone n'est jamais immobile.
    image = image + FOG[None, None, :] * _motes(rng, width, height)[:, :, None] * 1.5

    image = grade.bloom(image, threshold=0.30, radius=height * 0.024, strength=0.55)
    image = grade.split_tone(image, shadows=SHADOW_TINT, highlights=HIGHLIGHT_TINT, amount=0.12)
    image = grade.contrast_curve(image)
    image = grade.chromatic_aberration(image)
    image = grade.vignette(image, strength=0.50)
    return grade.grain(image, rng)
