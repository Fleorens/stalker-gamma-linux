"""Tuiles de statut de l'accueil : une donnée par tuile, alignées.

Widgets d'affichage purs — aucune collecte, aucun thread : la fenêtre
principale leur pousse les valeurs déjà calculées (`gui.space`, `gui.stats`).

Pourquoi des tuiles plutôt qu'une phrase : l'accueil disait « /mnt/…/gamma ·
493 Gio libres » sur une seule ligne grise, et le reste (combien de mods,
quelle version) n'était nulle part. Trois blocs étiquetés se balaient d'un
coup d'œil, et laissent la place d'en ajouter un sans réécrire une phrase.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from stalker_gamma_linux.i18n import _  # noqa: E402

# Valeur affichée tant que le sondage (thread) n'a pas rendu son résultat.
PLACEHOLDER = "…"


class StatTile(Gtk.Box):
    """Un couple étiquette / valeur, dans un cadre discret."""

    def __init__(self, label: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.add_css_class("tile")

        caption = Gtk.Label(label=label, xalign=0)
        caption.add_css_class("tile-label")
        self.append(caption)

        self._value = Gtk.Label(label=PLACEHOLDER, xalign=0)
        self._value.add_css_class("tile-value")
        self.append(self._value)

    def show_value(self, value: str, *, tone: str | None = None) -> None:
        """Met la valeur à jour. `tone` = `tile-value-accent` / `-warn`, ou rien."""
        self._value.set_label(value)
        for css_class in ("tile-value-accent", "tile-value-warn"):
            self._value.remove_css_class(css_class)
        if tone is not None:
            self._value.add_css_class(tone)


class StatStrip(Gtk.Box):
    """La rangée de tuiles de l'accueil : espace disque, mods, version."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.space = StatTile(_("Free space"))
        self.mods = StatTile(_("Mods"))
        # La tuile affiche une fraction (« 579 / 728 ») : sans explication, on
        # se demande pourquoi Mod Organizer annonce un autre nombre.
        self.mods.set_tooltip_text(
            _("Enabled in the G.A.M.M.A profile / installed on disk (separators excluded)")
        )
        self.version = StatTile(_("Version"))
        for tile in (self.space, self.mods, self.version):
            self.append(tile)
