"""Génération procédurale de l'artwork de la GUI (outillage de dev, hors paquet).

`noise` (bruits), `silhouettes` (le vocabulaire visuel de la Zone), `scene`
(la composition) et `grade` (l'étalonnage). Deux scripts s'en servent :
`generate_background.py` (le fond de la GUI) et `generate_social_preview.py`
(la carte du dépôt) — d'où `render_zone` ici, pour que les deux montrent
exactement le même paysage.
"""

from __future__ import annotations

from PIL import Image

from artwork import grade, scene

__all__ = ["render_zone"]


def render_zone(width: int = 1920, height: int = 1080) -> Image.Image:
    """L'artwork complet : composition de la scène, puis étalonnage."""
    return grade.to_image(scene.render(width, height))
