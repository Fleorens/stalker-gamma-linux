"""Bloc « héros » de l'accueil : logo, état de l'installation, tuiles de statut.

Widget d'affichage pur : aucune logique métier, aucun thread — la fenêtre
principale lui pousse l'état (`show_state`) puis le résultat du sondage
(`show_probe`), qui arrive plus tard, depuis un thread.

Le texte reste sobre et factuel : l'ambiance est portée par l'artwork et la
typographie, jamais par des formules d'ambiance dans l'interface.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Pango  # noqa: E402

from stalker_gamma_linux.gui import space, stats, theme, viewmodel  # noqa: E402
from stalker_gamma_linux.gui.windows.tiles import StatStrip  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402

# Le PNG source fait 720x341 : sans contrainte, Gtk.Picture le rend à taille
# naturelle et le logo avale la fenêtre. Un size_request ne pose qu'un
# *minimum* en GTK4 — c'est l'Adw.Clamp qui plafonne réellement la largeur,
# la hauteur suit le ratio (height-for-width de Gtk.Picture).
_LOGO_MAX_WIDTH = 268

# Tuiles au-dessus desquelles l'espace disque passe en avertissement.
_SPACE_TONES = {
    space.SpaceVerdict.OK: None,
    space.SpaceVerdict.TIGHT: "tile-value-warn",
    space.SpaceVerdict.INSUFFICIENT: "tile-value-warn",
    space.SpaceVerdict.UNKNOWN: None,
}


class HeroBox(Gtk.Box):
    """Colonne gauche du pont bas : identité, état, chiffres."""

    def __init__(self) -> None:
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            halign=Gtk.Align.START,
            valign=Gtk.Align.END,
        )

        texture = theme.texture("logo.png")
        if texture is not None:
            logo = Gtk.Picture.new_for_paintable(texture)
            logo.set_content_fit(Gtk.ContentFit.CONTAIN)
            logo.set_can_shrink(True)
            clamp = Adw.Clamp(child=logo, maximum_size=_LOGO_MAX_WIDTH)
            clamp.set_halign(Gtk.Align.START)
            clamp.set_margin_bottom(2)
            self.append(clamp)

        self._title = Gtk.Label(xalign=0)
        self._title.add_css_class("hero-title")
        self.append(self._title)

        self._subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE)
        self._subtitle.add_css_class("hero-subtitle")
        self.append(self._subtitle)

        self._tiles = StatStrip()
        self._tiles.set_margin_top(6)
        self.append(self._tiles)

    def show_state(self, state: viewmodel.MainWindowState) -> None:
        # Sobre et factuel — pas de flavor text (retour Florian).
        if state.is_installed:
            self._title.set_label(_("READY TO PLAY"))
        else:
            self._title.set_label(_("INSTALLATION REQUIRED"))
        self._subtitle.set_label(str(state.target))

    def show_probe(self, report: space.SpaceReport, install_stats: stats.InstallStats) -> None:
        """Chiffres du sondage : espace disque, mods déployés, version."""
        self._tiles.space.show_value(report.free_size, tone=_SPACE_TONES[report.verdict])
        self._tiles.mods.show_value(install_stats.mods_label)
        self._tiles.version.show_value(install_stats.version)
