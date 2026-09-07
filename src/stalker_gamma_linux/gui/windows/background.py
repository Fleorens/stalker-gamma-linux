"""Fond atmosphérique commun aux pages posées « sur l'artwork ».

Empile l'artwork sous un voile dégradé (cf. `theme/style.css`) qui garantit la
lisibilité du contenu. Si l'artwork manque (paquet incomplet), on retombe sur
le fond uni sombre de `window.background` — jamais d'écran cassé.

Deux fonds, parce que les deux usages n'ont pas la même contrainte :

- `hero_backdrop` — l'accueil, où l'artwork est le sujet : image nette, voile
  dégradé qui ne l'assombrit qu'à l'endroit où l'interface écrit ;
- `content_backdrop` — progression et diagnostic, où l'artwork n'est qu'une
  ambiance derrière du texte : la variante déjà floutée et assombrie à la
  génération, sous un voile plat. Le flou ne coûte donc rien à l'affichage —
  et il est deux fois plus petit à mettre à l'échelle (cf.
  `scripts/generate_background.py`).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from stalker_gamma_linux.gui import theme  # noqa: E402


def _artwork(name: str) -> Gtk.Widget:
    """Image de fond, recadrée pour couvrir la fenêtre — ou une boîte vide."""
    texture = theme.texture(name)
    if texture is None:  # asset absent : fond uni du thème
        return Gtk.Box(hexpand=True, vexpand=True)
    # `new_for_paintable` et non `new_for_filename` : la texture est décodée une
    # seule fois pour toute l'application (cf. `theme.texture`), au lieu d'une
    # copie par page ouverte.
    picture = Gtk.Picture.new_for_paintable(texture)
    picture.set_content_fit(Gtk.ContentFit.COVER)
    picture.set_hexpand(True)
    picture.set_vexpand(True)
    return picture


def _wrap(content: Gtk.Widget, *, artwork: str, scrim_class: str) -> Gtk.Widget:
    base = _artwork(artwork)
    base.set_can_target(False)

    scrim = Gtk.Box()
    scrim.add_css_class(scrim_class)
    scrim.set_can_target(False)

    overlay = Gtk.Overlay()
    overlay.set_child(base)
    overlay.add_overlay(scrim)
    overlay.add_overlay(content)
    return overlay


def hero_backdrop(content: Gtk.Widget) -> Gtk.Widget:
    """`content` au-dessus de l'artwork net — l'accueil."""
    return _wrap(content, artwork=theme.BACKGROUND, scrim_class="scrim")


def content_backdrop(content: Gtk.Widget) -> Gtk.Widget:
    """`content` au-dessus de l'ambiance floutée — les pages de texte."""
    return _wrap(content, artwork=theme.BACKGROUND_BLUR, scrim_class="scrim-content")
