"""Vue progression : étape courante, barre de progression, journal repliable, annulation.

Pure wiring GTK au-dessus de `gui.worker.BackgroundTask` : ce module ne connaît
rien des opérations elles-mêmes (`orchestrator.run_install`, `mo2.session.run_play`,
…) — il ne fait que démarrer la tâche fournie et rendre les événements qu'elle
publie sur sa queue.
"""

from __future__ import annotations

import queue
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from stalker_gamma_linux.gui.worker import (  # noqa: E402
    BackgroundTask,
    DoneEvent,
    FailedEvent,
    ReporterEvent,
    WorkerEvent,
)
from stalker_gamma_linux.orchestrator import CANCELLED_EXIT_CODE  # noqa: E402

_POLL_INTERVAL_MS = 80
_PULSE_INTERVAL_MS = 200


class ProgressPage(Adw.NavigationPage):
    """Pousse une `BackgroundTask` et affiche sa progression jusqu'à ce qu'elle termine.

    `on_finished(exit_code)` est appelé une seule fois, à la fin (succès, échec
    ou annulation) — `main_window.py` s'en sert pour rafraîchir le statut affiché.
    """

    def __init__(
        self,
        *,
        title: str,
        task: BackgroundTask,
        cancellable: bool,
        on_finished: Callable[[int], None],
    ) -> None:
        self._task = task
        self._on_finished = on_finished
        self._finished = False

        self._status_label = Gtk.Label(label="Préparation…", xalign=0, wrap=True)
        self._status_label.add_css_class("title-3")

        self._progress_bar = Gtk.ProgressBar(show_text=True)

        self._log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(
            buffer=self._log_buffer,
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=6,
            bottom_margin=6,
            left_margin=6,
            right_margin=6,
        )
        log_scroller = Gtk.ScrolledWindow(
            child=log_view, min_content_height=200, vexpand=True
        )
        log_scroller.add_css_class("card")
        log_expander = Gtk.Expander(label="Journal")
        log_expander.set_child(log_scroller)

        self._cancel_button = Gtk.Button(label="Annuler")
        self._cancel_button.add_css_class("destructive-action")
        self._cancel_button.add_css_class("pill")
        self._cancel_button.set_visible(cancellable)
        self._cancel_button.set_halign(Gtk.Align.END)
        self._cancel_button.connect("clicked", self._on_cancel_clicked)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.append(self._status_label)
        content.append(self._progress_bar)
        content.append(log_expander)
        content.append(self._cancel_button)

        clamp = Adw.Clamp(child=content, maximum_size=640)
        scroller = Gtk.ScrolledWindow(child=clamp, vexpand=True)

        header_bar = Adw.HeaderBar()
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(scroller)

        super().__init__(title=title, child=toolbar_view, can_pop=False)

        self._task.start()
        GLib.timeout_add(_PULSE_INTERVAL_MS, self._on_pulse)
        GLib.timeout_add(_POLL_INTERVAL_MS, self._on_poll)

    def _on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self._status_label.set_label("Annulation en cours…")
        self._cancel_button.set_sensitive(False)
        self._task.cancel()

    def _append_log(self, message: str) -> None:
        end = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end, f"{message}\n")

    def _on_pulse(self) -> bool:
        if self._finished:
            return False
        self._progress_bar.pulse()
        return True

    def _on_poll(self) -> bool:
        if self._finished:
            return False
        while True:
            try:
                event = self._task.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        return not self._finished

    def _handle_event(self, event: WorkerEvent) -> None:
        if isinstance(event, ReporterEvent):
            self._handle_reporter_event(event)
        elif isinstance(event, DoneEvent):
            self._handle_done(event.exit_code)
        elif isinstance(event, FailedEvent):
            self._append_log(f"Erreur inattendue : {event.error}")
            self._handle_done(1)

    def _handle_reporter_event(self, event: ReporterEvent) -> None:
        if event.kind in ("step", "skip"):
            label = f"{event.index} — {event.message}" if event.index else event.message
            self._status_label.set_label(label)
            self._progress_bar.set_text(event.index or "")
            self._append_log(label)
        elif event.kind == "error":
            self._append_log(f"Erreur : {event.message}")
            if event.hint is not None:
                self._append_log(f"→ {event.hint}")
        else:
            self._append_log(event.message)

    def _handle_done(self, exit_code: int) -> None:
        self._finished = True
        self._cancel_button.set_visible(False)
        self.set_can_pop(True)
        if exit_code == 0:
            self._status_label.set_label("Terminé.")
            self._progress_bar.set_fraction(1.0)
        elif exit_code == CANCELLED_EXIT_CODE:
            self._status_label.set_label("Annulé.")
        else:
            self._status_label.set_label("Échec — voir le journal ci-dessous.")
        self._on_finished(exit_code)
