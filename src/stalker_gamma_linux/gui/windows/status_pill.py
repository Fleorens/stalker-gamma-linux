"""Puce « état du système » de la barre de titre.

Widget d'affichage pur : la fenêtre principale lui pousse le résumé
d'environnement (`gui.summary`) et lui donne le callback d'ouverture du
Diagnostic.

Elle vivait au bas de l'accueil, sous le titre. En haut à droite, elle est là
où l'œil cherche un état — et elle libère le bas pour ce qui compte vraiment,
le nom de l'installation et le bouton qui la lance.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from stalker_gamma_linux.gui.summary import SystemSummary  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402

_TONE_CLASSES = ("chip-ok", "chip-warn")


class StatusPill(Gtk.Button):
    """Pastille + libellé, cliquable — le raccourci vers le Diagnostic."""

    def __init__(self, *, on_clicked: Callable[[], None]) -> None:
        super().__init__(valign=Gtk.Align.CENTER)
        self.add_css_class("chip")

        # `Gtk.Spinner` et non `Adw.Spinner` : ce dernier exige libadwaita 1.6,
        # or Ubuntu 24.04 livre 1.5 (même contrainte que `doctor_view`).
        self._spinner = Gtk.Spinner(spinning=True)
        self._dot = Gtk.Box(valign=Gtk.Align.CENTER)
        self._dot.add_css_class("status-dot")
        self._dot.set_visible(False)

        self._label = Gtk.Label(label=_("Analyzing system…"))

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.append(self._spinner)
        content.append(self._dot)
        content.append(self._label)
        self.set_child(content)

        self.connect("clicked", lambda _button: on_clicked())

    def show_summary(self, summary: SystemSummary) -> None:
        """Résultat de l'analyse d'environnement : la puce devient un verdict."""
        tone = "chip-ok" if summary.is_ready else "chip-warn"
        self._spinner.set_visible(False)
        self._spinner.set_spinning(False)  # un spinner caché continue d'animer
        self._dot.set_visible(True)
        self._label.set_label(summary.label)
        for css_class in _TONE_CLASSES:
            self.remove_css_class(css_class)
            self._dot.remove_css_class(css_class)
        self.add_css_class(tone)
        self._dot.add_css_class(tone)
        self.set_tooltip_text(
            _("Everything is in place. Click for details.")
            if summary.is_ready
            else _("Click to see the diagnostic and install commands.")
        )
