"""Fenêtre principale : statut de l'installation, bouton contextuel, Ouvrir MO2.

Toute la logique (install/update/play/mo2) reste dans `orchestrator`/
`mo2.session` ; ce module ne fait que déclencher ces appels dans un
`gui.worker.BackgroundTask` (donc hors du fil GTK) et pousser une
`ProgressPage` pour en suivre le déroulement.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk  # noqa: E402

from stalker_gamma_linux import orchestrator  # noqa: E402
from stalker_gamma_linux.gui import prefs, viewmodel  # noqa: E402
from stalker_gamma_linux.gui.windows.doctor_view import DoctorPage  # noqa: E402
from stalker_gamma_linux.gui.windows.preferences import PreferencesDialog  # noqa: E402
from stalker_gamma_linux.gui.windows.progress_view import ProgressPage  # noqa: E402
from stalker_gamma_linux.gui.worker import (  # noqa: E402
    BackgroundTask,
    QueueReporter,
    ReporterEvent,
    WorkerEvent,
)
from stalker_gamma_linux.mo2 import session as mo2_session  # noqa: E402

JobFunc = Callable[[queue.Queue[WorkerEvent], threading.Event], int]

# Confortable sur l'écran Steam Deck (1280x800, souvent en fenêtre bordless
# plein écran côté Gaming Mode) tout en restant raisonnable sur un bureau.
_DEFAULT_WIDTH = 820
_DEFAULT_HEIGHT = 620
# Cibles tactiles/manette généreuses (recommandation GNOME HIG : 44px min).
_BUTTON_HEIGHT = 56


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *, application: Adw.Application) -> None:
        super().__init__(
            application=application,
            title="S.T.A.L.K.E.R. G.A.M.M.A.",
            default_width=_DEFAULT_WIDTH,
            default_height=_DEFAULT_HEIGHT,
        )
        self._preferences = prefs.load_preferences()
        self._current_state: viewmodel.MainWindowState | None = None

        self._toast_overlay = Adw.ToastOverlay()
        self._nav_view = Adw.NavigationView()
        self._toast_overlay.set_child(self._nav_view)
        self.set_content(self._toast_overlay)

        self._install_action = self._add_action("check-update", self._on_check_update)
        self._add_action("show-doctor", self._on_show_doctor)
        self._add_action("show-preferences", self._on_show_preferences)

        self._nav_view.push(self._build_main_page())
        self._refresh_status()

    # -- construction ----------------------------------------------------

    def _add_action(
        self, name: str, handler: Callable[[Gio.SimpleAction, None], None]
    ) -> Gio.SimpleAction:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", handler)
        self.add_action(action)
        return action

    def _build_main_page(self) -> Adw.NavigationPage:
        menu = Gio.Menu()
        menu.append("Vérifier les mises à jour", "win.check-update")
        menu.append("Diagnostic", "win.show-doctor")
        menu.append("Préférences", "win.show-preferences")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True)

        header_bar = Adw.HeaderBar()
        header_bar.pack_end(menu_button)

        self._status_page = Adw.StatusPage(icon_name="applications-games-symbolic")

        self._primary_content = Adw.ButtonContent(
            icon_name="media-playback-start-symbolic", label="Installer"
        )
        self._primary_button = Gtk.Button(child=self._primary_content)
        self._primary_button.add_css_class("suggested-action")
        self._primary_button.add_css_class("pill")
        self._primary_button.set_size_request(240, _BUTTON_HEIGHT)
        self._primary_button.set_receives_default(True)
        self._primary_button.connect("clicked", self._on_primary_action)

        self._open_mo2_button = Gtk.Button(label="Ouvrir MO2")
        self._open_mo2_button.add_css_class("pill")
        self._open_mo2_button.set_size_request(180, _BUTTON_HEIGHT)
        self._open_mo2_button.connect("clicked", self._on_open_mo2)

        button_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER
        )
        button_box.append(self._primary_button)
        button_box.append(self._open_mo2_button)
        self._status_page.set_child(button_box)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(self._status_page)

        page = Adw.NavigationPage(title="S.T.A.L.K.E.R. G.A.M.M.A.", tag="main", child=toolbar_view)
        return page

    # -- état --------------------------------------------------------------

    def _refresh_status(self) -> None:
        result = viewmodel.load_main_window_state(self._preferences.install_path)
        self._current_state = result

        if result.is_installed:
            self._status_page.set_title("S.T.A.L.K.E.R. G.A.M.M.A. est installé")
            self._primary_content.set_label("Jouer")
            self._primary_content.set_icon_name("media-playback-start-symbolic")
        else:
            self._status_page.set_title("S.T.A.L.K.E.R. G.A.M.M.A. n'est pas installé")
            self._primary_content.set_label("Installer")
            self._primary_content.set_icon_name("system-software-install-symbolic")
        self._status_page.set_description(f"Cible : {result.target}")
        self._open_mo2_button.set_visible(result.is_installed)
        self._install_action.set_enabled(result.is_installed)

        self.set_default_widget(self._primary_button)
        self._primary_button.grab_focus()

    def _show_toast(self, text: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast.new(text))

    # -- actions -------------------------------------------------------

    def _on_primary_action(self, _button: Gtk.Button) -> None:
        if self._current_state is not None and self._current_state.is_installed:
            self._start_play()
        else:
            self._start_install()

    def _on_open_mo2(self, _button: Gtk.Button) -> None:
        self._start_mo2()

    def _on_check_update(self, _action: Gio.SimpleAction, _param: None) -> None:
        self._start_update()

    def _on_show_doctor(self, _action: Gio.SimpleAction, _param: None) -> None:
        self._nav_view.push(
            DoctorPage(target=self._preferences.install_path, show_toast=self._show_toast)
        )

    def _on_show_preferences(self, _action: Gio.SimpleAction, _param: None) -> None:
        PreferencesDialog(
            parent_window=self,
            preferences=self._preferences,
            on_saved=self._on_preferences_saved,
        ).present(self)

    def _on_preferences_saved(self, updated: prefs.Preferences) -> None:
        self._preferences = updated
        self._refresh_status()

    # -- tâches longues (hors fil GTK) ----------------------------------

    def _start_install(self) -> None:
        target = self._preferences.install_path
        shortcut = self._preferences.create_steam_shortcut
        proton_release = self._preferences.proton_release

        def job(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
            reporter = QueueReporter(events)
            return orchestrator.run_install(
                target,
                shortcut=shortcut,
                reporter=reporter,
                cancel_event=cancel_event,
                proton_release=proton_release,
            )

        self._push_task("Installation", job, cancellable=True)

    def _start_update(self) -> None:
        target = self._preferences.install_path

        def job(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
            reporter = QueueReporter(events)
            return orchestrator.run_update(target, reporter=reporter, cancel_event=cancel_event)

        self._push_task("Mise à jour", job, cancellable=True)

    def _start_play(self) -> None:
        target = self._preferences.install_path

        def job(events: queue.Queue[WorkerEvent], _cancel_event: threading.Event) -> int:
            return mo2_session.run_play(
                target, on_progress=lambda msg: events.put(ReporterEvent("progress", msg))
            )

        self._push_task("Lancer le jeu", job, cancellable=False)

    def _start_mo2(self) -> None:
        target = self._preferences.install_path

        def job(events: queue.Queue[WorkerEvent], _cancel_event: threading.Event) -> int:
            return mo2_session.run_mo2(
                target, on_progress=lambda msg: events.put(ReporterEvent("progress", msg))
            )

        self._push_task("Ouvrir Mod Organizer 2", job, cancellable=False)

    def _push_task(
        self,
        title: str,
        job: JobFunc,
        *,
        cancellable: bool,
    ) -> None:
        task = BackgroundTask(job)
        page = ProgressPage(
            title=title, task=task, cancellable=cancellable, on_finished=self._on_task_finished
        )
        self._nav_view.push(page)

    def _on_task_finished(self, exit_code: int) -> None:
        self._refresh_status()
        if exit_code == 0:
            self._show_toast("Terminé.")
        elif exit_code == orchestrator.CANCELLED_EXIT_CODE:
            self._show_toast("Annulé.")
        else:
            self._show_toast("Échec — voir le journal.")
