"""Fenêtre principale : un launcher — artwork, héros, gros bouton, statut live.

Toute la logique (install/update/play/mo2) reste dans `orchestrator`/
`mo2.session` ; ce module compose les vues (héros, dialog d'installation,
progression) et déclenche ces appels dans un `gui.worker.BackgroundTask`
(hors du fil GTK). L'analyse d'environnement de la puce « système » tourne
dans un thread au démarrage et à chaque retour de tâche.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Sequence

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from stalker_gamma_linux import orchestrator  # noqa: E402
from stalker_gamma_linux import state as state_module  # noqa: E402
from stalker_gamma_linux.environment.report import build_report  # noqa: E402
from stalker_gamma_linux.gui import prefs, space, summary, viewmodel  # noqa: E402
from stalker_gamma_linux.gui.windows.background import wrap_with_background  # noqa: E402
from stalker_gamma_linux.gui.windows.doctor_view import DoctorPage  # noqa: E402
from stalker_gamma_linux.gui.windows.hero import HeroBox  # noqa: E402
from stalker_gamma_linux.gui.windows.install_dialog import InstallDialog  # noqa: E402
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

# Confortable sur l'écran Steam Deck (1280x800, souvent en fenêtré bordless
# plein écran côté Gaming Mode) tout en restant raisonnable sur un bureau.
_DEFAULT_WIDTH = 1000
_DEFAULT_HEIGHT = 700
_PLAY_WIDTH, _PLAY_HEIGHT = 230, 60

# Étapes de `orchestrator.run_update`, dans l'ordre de ses événements 1/3..3/3.
_UPDATE_PHASES = (
    "Modpack G.A.M.M.A (téléchargement incrémental)",
    "Retrait de ReShade + purge du cache de shaders",
    "Vérification des archives de mods (MD5)",
)


def _install_phases(*, shortcut: bool) -> tuple[str, ...]:
    """Labels du pipeline `run_install`, alignés sur sa numérotation n/total."""
    steps = state_module.STEPS if shortcut else state_module.STEPS[:-1]
    return tuple(state_module.STEP_LABELS[step] for step in steps)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *, application: Adw.Application) -> None:
        super().__init__(
            application=application,
            title="G.A.M.M.A. pour Linux",
            default_width=_DEFAULT_WIDTH,
            default_height=_DEFAULT_HEIGHT,
        )
        self.set_size_request(720, 540)
        self._preferences = prefs.load_preferences()
        self._current_state: viewmodel.MainWindowState | None = None
        self._probe_generation = 0

        self._toast_overlay = Adw.ToastOverlay()
        self._nav_view = Adw.NavigationView()
        self._toast_overlay.set_child(self._nav_view)
        self.set_content(self._toast_overlay)

        self._update_action = self._add_action("check-update", self._on_check_update)
        self._add_action("show-doctor", self._on_show_doctor)
        self._add_action("show-preferences", self._on_show_preferences)
        self._add_action("show-about", self._on_show_about)

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
        menu.append("À propos", "win.show-about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True)

        header_bar = Adw.HeaderBar(show_title=False)
        header_bar.pack_end(menu_button)

        self._hero = HeroBox(on_chip_clicked=self._push_doctor)

        self._primary_content = Adw.ButtonContent(
            icon_name="media-playback-start-symbolic", label="JOUER"
        )
        self._primary_button = Gtk.Button(child=self._primary_content)
        self._primary_button.add_css_class("action-play")
        self._primary_button.set_size_request(_PLAY_WIDTH, _PLAY_HEIGHT)
        self._primary_button.set_receives_default(True)
        self._primary_button.connect("clicked", self._on_primary_action)

        self._mo2_button = Gtk.Button(label="Mod Organizer 2")
        self._mo2_button.add_css_class("action-secondary")
        self._mo2_button.set_size_request(-1, 40)
        self._mo2_button.connect("clicked", lambda _b: self._start_mo2())

        self._update_button = Gtk.Button(label="Mettre à jour")
        self._update_button.add_css_class("action-secondary")
        self._update_button.set_size_request(-1, 40)
        self._update_button.connect("clicked", lambda _b: self._start_update())

        secondary_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END
        )
        secondary_row.append(self._mo2_button)
        secondary_row.append(self._update_button)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.END,
            valign=Gtk.Align.END,
        )
        actions.append(self._primary_button)
        actions.append(secondary_row)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        bottom.set_margin_start(32)
        bottom.set_margin_end(32)
        bottom.set_margin_bottom(28)
        self._hero.set_hexpand(True)
        bottom.append(self._hero)
        bottom.append(actions)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(Gtk.Box(vexpand=True))  # pousse le héros vers le bas
        content.append(bottom)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(content)
        toolbar_view.add_css_class("over-artwork")

        return Adw.NavigationPage(
            title="G.A.M.M.A. pour Linux",
            tag="main",
            child=wrap_with_background(toolbar_view),
        )

    # -- état --------------------------------------------------------------

    def _refresh_status(self) -> None:
        result = viewmodel.load_main_window_state(self._preferences.install_path)
        self._current_state = result

        self._hero.show_state(result, free_label=None)
        if result.is_installed:
            self._primary_content.set_label("JOUER")
            self._primary_content.set_icon_name("media-playback-start-symbolic")
        else:
            self._primary_content.set_label("INSTALLER")
            self._primary_content.set_icon_name("folder-download-symbolic")
        self._mo2_button.set_visible(result.is_installed)
        self._update_button.set_visible(result.is_installed)
        self._update_action.set_enabled(result.is_installed)

        self.set_default_widget(self._primary_button)
        self._primary_button.grab_focus()
        self._start_environment_probe()

    def _start_environment_probe(self) -> None:
        """Analyse d'environnement + espace disque, hors du fil GTK (sous-process)."""
        self._probe_generation += 1
        generation = self._probe_generation
        target = self._preferences.install_path

        def worker() -> None:
            env_summary = summary.summarize(build_report(target))
            space_report = space.assess(target)
            GLib.idle_add(self._apply_probe, generation, env_summary, space_report)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_probe(
        self,
        generation: int,
        env_summary: summary.SystemSummary,
        space_report: space.SpaceReport,
    ) -> bool:
        if generation != self._probe_generation or self._current_state is None:
            return False  # une analyse plus récente est en route, ne pas écraser
        self._hero.show_summary(env_summary)
        self._hero.show_state(self._current_state, free_label=space_report.free_label)
        return False

    def _show_toast(self, text: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast.new(text))

    # -- actions -------------------------------------------------------

    def _on_primary_action(self, _button: Gtk.Button) -> None:
        if self._current_state is not None and self._current_state.is_installed:
            self._start_play()
        else:
            InstallDialog(
                parent_window=self,
                preferences=self._preferences,
                on_confirmed=self._on_install_confirmed,
            ).present(self)

    def _on_install_confirmed(self, updated: prefs.Preferences) -> None:
        self._preferences = updated
        self._start_install()

    def _on_check_update(self, _action: Gio.SimpleAction, _param: None) -> None:
        self._start_update()

    def _on_show_doctor(self, _action: Gio.SimpleAction, _param: None) -> None:
        self._push_doctor()

    def _push_doctor(self) -> None:
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

    def _on_show_about(self, _action: Gio.SimpleAction, _param: None) -> None:
        about = Adw.AboutDialog(
            application_name="G.A.M.M.A. pour Linux",
            developer_name="Projet communautaire, non affilié à GSC Game World",
            comments=(
                "Installe et lance le modpack S.T.A.L.K.E.R. G.A.M.M.A. de "
                "Grokitach sous Linux : Anomaly, Mod Organizer 2 sous Proton, "
                "préfixe partagé et mises à jour incrémentales."
            ),
            website="https://github.com/Fleorens/stalker-gamma-linux",
            issue_url="https://github.com/Fleorens/stalker-gamma-linux/issues",
            license_type=Gtk.License.GPL_3_0,
        )
        about.present(self)

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

        self._push_task(
            "Installation",
            job,
            cancellable=True,
            phase_labels=_install_phases(shortcut=shortcut),
        )

    def _start_update(self) -> None:
        target = self._preferences.install_path

        def job(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
            reporter = QueueReporter(events)
            return orchestrator.run_update(target, reporter=reporter, cancel_event=cancel_event)

        self._push_task("Mise à jour", job, cancellable=True, phase_labels=_UPDATE_PHASES)

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
        phase_labels: Sequence[str] | None = None,
    ) -> None:
        task = BackgroundTask(job)
        page = ProgressPage(
            title=title,
            task=task,
            cancellable=cancellable,
            on_finished=self._on_task_finished,
            phase_labels=phase_labels,
        )
        self._nav_view.push(page)

    def _on_task_finished(self, exit_code: int) -> None:
        self._refresh_status()
        if exit_code == 0:
            self._show_toast("Terminé.")
        elif exit_code == orchestrator.CANCELLED_EXIT_CODE:
            self._show_toast("Annulé — la reprise continuera où c'était arrêté.")
        else:
            self._show_toast("Échec — voir la console et le journal.")
