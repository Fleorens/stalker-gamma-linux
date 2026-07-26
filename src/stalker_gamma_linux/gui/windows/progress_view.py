"""Vue progression : timeline de phases, fraction réelle, console, annulation.

Deux rendus selon la tâche :
- pipeline (install/update) : `phase_labels` fourni → timeline d'étapes avec
  états (en cours/fait/déjà fait/échec) et barre de progression déterminée,
  pilotées par le modèle immuable `gui.phases.Timeline` ;
- session (jouer/MO2) : pas de labels → barre en pulsation, console seule.

Pure wiring GTK au-dessus de `gui.worker.BackgroundTask` : ce module ne
connaît rien des opérations elles-mêmes, il rend les événements de la queue.
"""

from __future__ import annotations

import queue
import time
from collections.abc import Callable, Sequence

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from stalker_gamma_linux.gui import phases  # noqa: E402
from stalker_gamma_linux.gui.format import format_duration  # noqa: E402
from stalker_gamma_linux.gui.windows.background import wrap_with_background  # noqa: E402
from stalker_gamma_linux.gui.worker import (  # noqa: E402
    BackgroundTask,
    DoneEvent,
    FailedEvent,
    ReporterEvent,
    WorkerEvent,
)
from stalker_gamma_linux.i18n import _  # noqa: E402
from stalker_gamma_linux.orchestrator import CANCELLED_EXIT_CODE  # noqa: E402

_POLL_INTERVAL_MS = 80
_PULSE_INTERVAL_MS = 200
_CLOCK_INTERVAL_MS = 1000

_STATUS_ICON = {
    phases.PhaseStatus.PENDING: "media-record-symbolic",
    # `object-select-symbolic` : la coche toujours présente dans Adwaita —
    # `emblem-ok-symbolic` a disparu des thèmes récents (rendu « icône cassée »).
    phases.PhaseStatus.DONE: "object-select-symbolic",
    phases.PhaseStatus.SKIPPED: "media-skip-forward-symbolic",
    phases.PhaseStatus.FAILED: "process-stop-symbolic",
}
_STATUS_CLASS = {
    phases.PhaseStatus.PENDING: "phase-pending",
    phases.PhaseStatus.RUNNING: "phase-running",
    phases.PhaseStatus.DONE: "phase-done",
    phases.PhaseStatus.SKIPPED: "phase-skipped",
    phases.PhaseStatus.FAILED: "phase-failed",
}


class _PhaseRow(Gtk.Box):
    """Une ligne de la timeline : icône d'état, label, détail (une ligne, ellipsée)."""

    def __init__(self, label: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._spinner = Adw.Spinner()
        self._icon = Gtk.Image()
        self._stack = Gtk.Stack()
        self._stack.add_named(self._icon, "icon")
        self._stack.add_named(self._spinner, "spinner")
        self._stack.set_valign(Gtk.Align.START)
        self._stack.set_margin_top(2)
        self.append(self._stack)

        self._label = Gtk.Label(label=label, xalign=0, wrap=True)
        self._detail = Gtk.Label(xalign=0, visible=False)
        self._detail.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self._detail.set_max_width_chars(56)
        self._detail.add_css_class("phase-detail")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        texts.append(self._label)
        texts.append(self._detail)
        self.append(texts)

        self._status: phases.PhaseStatus | None = None
        self.show_phase(phases.Phase(label=label))

    def show_phase(self, phase: phases.Phase) -> None:
        if phase.status is not self._status:
            self._status = phase.status
            # Sur la ligne entière : l'icône hérite ainsi de la couleur d'état
            # (le `.phase-detail` du label de détail, plus spécifique, survit).
            for css_class in _STATUS_CLASS.values():
                self.remove_css_class(css_class)
            self.add_css_class(_STATUS_CLASS[phase.status])
            if phase.status is phases.PhaseStatus.RUNNING:
                self._stack.set_visible_child_name("spinner")
            else:
                self._stack.set_visible_child_name("icon")
                self._icon.set_from_icon_name(_STATUS_ICON[phase.status])
        suffix = _(" — already done") if phase.status is phases.PhaseStatus.SKIPPED else ""
        self._label.set_label(f"{phase.label}{suffix}")
        self._detail.set_visible(phase.detail is not None)
        if phase.detail is not None:
            self._detail.set_label(phase.detail)


class ProgressPage(Adw.NavigationPage):
    """Démarre une `BackgroundTask` et affiche sa progression jusqu'au bout.

    `on_finished(exit_code)` est appelé une seule fois (succès, échec ou
    annulation) — la fenêtre principale s'en sert pour rafraîchir son statut.
    """

    def __init__(
        self,
        *,
        title: str,
        task: BackgroundTask,
        cancellable: bool,
        on_finished: Callable[[int], None],
        phase_labels: Sequence[str] | None = None,
    ) -> None:
        self._task = task
        self._on_finished = on_finished
        self._finished = False
        self._started_at = time.monotonic()
        self._timeline = (
            phases.Timeline.from_labels(tuple(phase_labels)) if phase_labels else None
        )
        self._phase_rows: list[_PhaseRow] = []

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{side}")(24)

        self._status_label = Gtk.Label(label=_("Preparing…"), xalign=0, wrap=True)
        self._status_label.add_css_class("title-3")
        self._elapsed_label = Gtk.Label(label="", xalign=1, hexpand=True)
        self._elapsed_label.add_css_class("elapsed")
        status_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_line.append(self._status_label)
        status_line.append(self._elapsed_label)
        content.append(status_line)

        if self._timeline is not None:
            content.append(self._build_timeline_card())

        self._percent_label = Gtk.Label(xalign=1)
        self._percent_label.add_css_class("progress-percent")
        self._progress_bar = Gtk.ProgressBar(hexpand=True, valign=Gtk.Align.CENTER)
        progress_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        progress_line.append(self._progress_bar)
        progress_line.append(self._percent_label)
        content.append(progress_line)

        content.append(self._build_console())

        self._cancel_button = Gtk.Button(label=_("Cancel"))
        self._cancel_button.add_css_class("destructive-action")
        self._cancel_button.add_css_class("pill")
        self._cancel_button.set_visible(cancellable)
        self._cancel_button.set_halign(Gtk.Align.END)
        self._cancel_button.connect("clicked", self._on_cancel_clicked)
        content.append(self._cancel_button)

        clamp = Adw.Clamp(child=content, maximum_size=700)
        scroller = Gtk.ScrolledWindow(child=clamp, vexpand=True)

        header_bar = Adw.HeaderBar()
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(scroller)
        toolbar_view.add_css_class("over-artwork")

        super().__init__(
            title=title, child=wrap_with_background(toolbar_view), can_pop=False
        )

        self._render_timeline()
        self._task.start()
        if self._timeline is None:
            GLib.timeout_add(_PULSE_INTERVAL_MS, self._on_pulse)
        GLib.timeout_add(_POLL_INTERVAL_MS, self._on_poll)
        GLib.timeout_add(_CLOCK_INTERVAL_MS, self._on_clock)

    # -- construction ------------------------------------------------------

    def _build_timeline_card(self) -> Gtk.Widget:
        assert self._timeline is not None
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(rows, f"set_margin_{side}")(16)
        for phase in self._timeline.phases:
            row = _PhaseRow(phase.label)
            self._phase_rows.append(row)
            rows.append(row)
        card = Gtk.Box()
        card.add_css_class("glass")
        card.append(rows)
        return card

    def _build_console(self) -> Gtk.Widget:
        self._log_buffer = Gtk.TextBuffer()
        self._log_end_mark = self._log_buffer.create_mark(
            None, self._log_buffer.get_end_iter(), False
        )
        self._log_view = Gtk.TextView(
            buffer=self._log_buffer,
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=10,
            bottom_margin=10,
            left_margin=12,
            right_margin=12,
        )
        scroller = Gtk.ScrolledWindow(
            child=self._log_view, min_content_height=140, vexpand=True
        )
        scroller.add_css_class("console")
        return scroller

    # -- événements ----------------------------------------------------------

    def _on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self._status_label.set_label(_("Cancelling…"))
        self._cancel_button.set_sensitive(False)
        self._task.cancel()

    def _append_log(self, message: str) -> None:
        self._log_buffer.insert(self._log_buffer.get_end_iter(), f"{message}\n")
        self._log_view.scroll_to_mark(self._log_end_mark, 0.0, False, 0.0, 1.0)

    def _on_pulse(self) -> bool:
        if self._finished:
            return False
        self._progress_bar.pulse()
        return True

    def _on_clock(self) -> bool:
        if self._finished:
            return False
        self._elapsed_label.set_label(format_duration(time.monotonic() - self._started_at))
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
            self._append_log(_("Unexpected error: {error}").format(error=event.error))
            self._handle_done(1)

    def _handle_reporter_event(self, event: ReporterEvent) -> None:
        if self._timeline is not None:
            self._timeline = self._timeline.apply(event)
            self._render_timeline()
        if event.kind in ("step", "skip"):
            self._status_label.set_label(event.message)
            self._append_log(
                f"[{event.index}] {event.message}" if event.index else event.message
            )
        elif event.kind == "error":
            self._append_log(_("Error: {message}").format(message=event.message))
            if event.hint is not None:
                self._append_log(f"→ {event.hint}")
        else:
            self._append_log(event.message)

    def _render_timeline(self) -> None:
        if self._timeline is None:
            return
        for row, phase in zip(self._phase_rows, self._timeline.phases, strict=True):
            row.show_phase(phase)
        fraction = self._timeline.fraction
        self._progress_bar.set_fraction(fraction)
        self._percent_label.set_label(f"{fraction:.0%}")

    def _handle_done(self, exit_code: int) -> None:
        self._finished = True
        self._cancel_button.set_visible(False)
        self.set_can_pop(True)
        self._elapsed_label.set_label(format_duration(time.monotonic() - self._started_at))
        if exit_code == 0:
            if self._timeline is not None:
                self._timeline = self._timeline.complete()
                self._render_timeline()
            self._status_label.set_label(_("Done."))
            self._progress_bar.set_fraction(1.0)
            self._percent_label.set_label("100%")
        elif exit_code == CANCELLED_EXIT_CODE:
            self._status_label.set_label(_("Cancelled — will resume where it left off."))
        else:
            self._status_label.set_label(_("Failed — see details in the console below."))
        self._on_finished(exit_code)
