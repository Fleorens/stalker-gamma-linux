"""Application GTK4/libadwaita — importé uniquement après le pré-vol de `launch.py`."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from stalker_gamma_linux.gui.windows.main_window import MainWindow  # noqa: E402

# `Gio.Application` exige syntaxiquement un id à la D-Bus (au moins un point) —
# contrainte purement technique, contrairement au `.desktop` (T06, desktop/paths.py)
# qui reste `stalker-gamma-linux` sans reverse-DNS. Même décision qu'en T06 :
# pas de segment `io.github.<compte>` (dépendrait d'un compte GitHub précis) ;
# `stalkergammalinux` est notre propre espace de noms, stable.
APPLICATION_ID = "org.stalkergammalinux.Gui"


class StalkerGammaApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APPLICATION_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self._window: MainWindow | None = None

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MainWindow(application=self)
        self._window.present()


def run_app() -> int:
    return StalkerGammaApplication().run(None)
