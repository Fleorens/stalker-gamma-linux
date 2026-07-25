"""Fond atmosphérique commun aux pages posées « sur l'artwork ».

Empile l'artwork (`assets/background.jpg`, recadré pour couvrir la fenêtre)
sous un voile dégradé (`.scrim`, cf. `theme.py`) qui garantit la lisibilité du
contenu. Si l'artwork manque (paquet incomplet), on retombe sur le fond uni
sombre de `window.background` — jamais d'écran cassé.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from stalker_gamma_linux.gui import theme  # noqa: E402


def _artwork() -> Gtk.Widget:
    picture = Gtk.Picture.new_for_filename(str(theme.asset("background.jpg")))
    if picture.get_paintable() is None:  # asset absent : fond uni du thème
        return Gtk.Box(hexpand=True, vexpand=True)
    picture.set_content_fit(Gtk.ContentFit.COVER)
    picture.set_hexpand(True)
    picture.set_vexpand(True)
    return picture


def wrap_with_background(content: Gtk.Widget) -> Gtk.Widget:
    """`content` rendu au-dessus de l'artwork + voile de lisibilité."""
    base = _artwork()
    base.set_can_target(False)

    scrim = Gtk.Box()
    scrim.add_css_class("scrim")
    scrim.set_can_target(False)

    overlay = Gtk.Overlay()
    overlay.set_child(base)
    overlay.add_overlay(scrim)
    overlay.add_overlay(content)
    return overlay
