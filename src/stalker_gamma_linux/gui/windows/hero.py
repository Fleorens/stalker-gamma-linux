"""Bloc « héros » de l'accueil : logo, état de l'installation, puce système.

Widget d'affichage pur : aucune logique métier, aucun thread — la fenêtre
principale lui pousse l'état (`show_state`, `show_summary`) et lui fournit le
callback de la puce (ouvrir le Diagnostic).
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Pango  # noqa: E402

from stalker_gamma_linux.gui import theme, viewmodel  # noqa: E402
from stalker_gamma_linux.gui.summary import SystemSummary  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402

# Le PNG source fait 720x341 : sans contrainte, Gtk.Picture le rend à taille
# naturelle et le logo avale la fenêtre. Un size_request ne pose qu'un
# *minimum* en GTK4 — c'est l'Adw.Clamp qui plafonne réellement la largeur,
# la hauteur suit le ratio (height-for-width de Gtk.Picture).
_LOGO_MAX_WIDTH = 300


class HeroBox(Gtk.Box):
    """Colonne bas-gauche du launcher, posée sur l'artwork."""

    def __init__(self, *, on_chip_clicked: Callable[[], None]) -> None:
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            halign=Gtk.Align.START,
            valign=Gtk.Align.END,
        )

        logo = Gtk.Picture.new_for_filename(str(theme.asset("logo.png")))
        logo.set_content_fit(Gtk.ContentFit.CONTAIN)
        logo.set_can_shrink(True)
        if logo.get_paintable() is not None:
            clamp = Adw.Clamp(child=logo, maximum_size=_LOGO_MAX_WIDTH)
            clamp.set_halign(Gtk.Align.START)
            self.append(clamp)

        self._title = Gtk.Label(xalign=0)
        self._title.add_css_class("hero-title")
        self.append(self._title)

        self._subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE)
        self._subtitle.add_css_class("hero-subtitle")
        self.append(self._subtitle)

        self._chip_spinner = Adw.Spinner()
        self._chip_label = Gtk.Label(label=_("Analyzing system…"))
        chip_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chip_content.append(self._chip_spinner)
        chip_content.append(self._chip_label)

        self._chip = Gtk.Button(child=chip_content, halign=Gtk.Align.START)
        self._chip.add_css_class("chip")
        self._chip.set_margin_top(4)
        self._chip.connect("clicked", lambda _b: on_chip_clicked())
        self.append(self._chip)

    def show_state(self, state: viewmodel.MainWindowState, *, free_label: str | None) -> None:
        # Sobre et factuel — pas de flavor text (retour Florian).
        if state.is_installed:
            self._title.set_label(_("READY TO PLAY"))
        else:
            self._title.set_label(_("INSTALLATION REQUIRED"))
        subtitle = str(state.target)
        if free_label is not None:
            subtitle = f"{subtitle}  ·  {free_label}"
        self._subtitle.set_label(subtitle)

    def show_summary(self, summary: SystemSummary) -> None:
        """Résultat de l'analyse d'environnement (thread) : la puce devient un verdict."""
        self._chip_spinner.set_visible(False)
        self._chip_label.set_label(summary.label)
        self._chip.remove_css_class("chip-ok")
        self._chip.remove_css_class("chip-warn")
        self._chip.add_css_class("chip-ok" if summary.is_ready else "chip-warn")
        self._chip.set_tooltip_text(
            _("Everything is in place. Click for details.")
            if summary.is_ready
            else _("Click to see the diagnostic and install commands.")
        )
