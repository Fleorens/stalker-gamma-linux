"""Application GTK4/libadwaita — importé uniquement après le pré-vol de `launch.py`."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from stalker_gamma_linux.gui.windows.main_window import MainWindow  # noqa: E402

# `Gio.Application` exige syntaxiquement un id à la D-Bus (au moins un point) —
# contrainte purement technique, contrairement au `.desktop` (T06, desktop/paths.py)
# qui reste `stalker-gamma-linux` sans reverse-DNS. Même décision qu'en T06 :
# pas de segment `io.github.<compte>` (dépendrait d'un compte GitHub précis) ;
# `stalkergammalinux` est notre propre espace de noms, stable.
APPLICATION_ID = "org.stalkergammalinux.Gui"

# Ambiance S.T.A.L.K.E.R./GAMMA plutôt que le libadwaita générique : accent
# « vert toxique » (au lieu du bleu GNOME) et un fond de fenêtre plus sombre.
# L'app force aussi le thème sombre (set_color_scheme ci-dessous) — un installeur
# de modpack post-apo, c'est sombre, pas une app bureautique claire.
_STYLE = """
@define-color accent_bg_color #5f8a2b;
@define-color accent_fg_color #f4ffe6;
@define-color accent_color #a6d95b;
window.background { background-color: #17190f; }
"""


class StalkerGammaApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APPLICATION_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self._window: MainWindow | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        display = Gdk.Display.get_default()
        if display is not None:
            provider = Gtk.CssProvider()
            provider.load_from_string(_STYLE)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MainWindow(application=self)
        self._window.present()


def run_app() -> int:
    return StalkerGammaApplication().run(None)
