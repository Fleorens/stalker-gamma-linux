"""Vue Diagnostic : rendu graphique de `doctor.build_full_report`, remèdes copiables.

Ne recalcule rien : `doctor.build_full_report` (T08) fait toute la collecte
(environnement, préfixe, état d'installation), déjà utilisée par la commande
CLI `doctor`. Tourne dans un thread (plusieurs sous-process — `which`,
`ldconfig`, `vulkaninfo`…) pour ne jamais geler l'UI le temps de la collecte.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from stalker_gamma_linux import doctor, state  # noqa: E402
from stalker_gamma_linux.environment.models import Requirement, Status  # noqa: E402


class DoctorPage(Adw.NavigationPage):
    def __init__(
        self, *, target: Path | None, show_toast: Callable[[str], None]
    ) -> None:
        self._target = target
        self._show_toast = show_toast
        self._groups: list[Adw.PreferencesGroup] = []

        self._spinner = Adw.Spinner()
        self._spinner.set_size_request(48, 48)
        spinner_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            vexpand=True,
        )
        spinner_box.append(self._spinner)

        self._preferences_page = Adw.PreferencesPage()

        self._stack = Gtk.Stack()
        self._stack.add_named(spinner_box, "loading")
        self._stack.add_named(self._preferences_page, "content")

        self._refresh_button = Gtk.Button(
            icon_name="view-refresh-symbolic", tooltip_text="Réactualiser"
        )
        self._refresh_button.connect("clicked", lambda _b: self._start_refresh())
        header_bar = Adw.HeaderBar()
        header_bar.pack_end(self._refresh_button)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(self._stack)

        super().__init__(title="Diagnostic", child=toolbar_view)

        self._start_refresh()

    def _start_refresh(self) -> None:
        self._stack.set_visible_child_name("loading")
        self._refresh_button.set_sensitive(False)
        target = self._target

        def worker() -> None:
            report = doctor.build_full_report(target)
            GLib.idle_add(self._apply_report, report)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_report(self, report: doctor.DoctorReport) -> bool:
        for group in self._groups:
            self._preferences_page.remove(group)
        self._groups = [
            self._build_requirements_group("Environnement", report.environment.requirements),
            self._build_requirements_group("Préfixe Proton", report.prefix.requirements),
            self._build_install_group(report.install),
        ]
        for group in self._groups:
            self._preferences_page.add(group)
        self._stack.set_visible_child_name("content")
        self._refresh_button.set_sensitive(True)
        return False

    def _build_requirements_group(
        self, title: str, requirements: tuple[Requirement, ...]
    ) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=title)
        for requirement in requirements:
            subtitle = requirement.detail
            if requirement.install_hint is not None:
                # La commande doit être lisible, pas seulement copiable à l'aveugle.
                subtitle = f"{subtitle}\n→ {requirement.install_hint}"
            row = Adw.ActionRow(title=requirement.name, subtitle=subtitle)
            row.set_subtitle_lines(2)
            row.add_prefix(_status_icon(requirement.status is Status.OK))
            if requirement.install_hint is not None:
                row.add_suffix(self._copy_button(requirement.install_hint))
            group.add(row)
        return group

    def _build_install_group(self, install_state: state.InstallState) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Installation")
        for step in state.STEPS:
            done = install_state.is_done(step)
            row = Adw.ActionRow(
                title=state.STEP_LABELS[step],
                subtitle="Fait" if done else "Pas encore fait",
            )
            row.add_prefix(_status_icon(done))
            group.add(row)
        return group

    def _copy_button(self, command: str) -> Gtk.Button:
        button = Gtk.Button(
            icon_name="edit-copy-symbolic",
            tooltip_text="Copier la commande",
            valign=Gtk.Align.CENTER,
        )
        button.add_css_class("flat")
        button.connect("clicked", lambda _b: self._copy_to_clipboard(command))
        return button

    def _copy_to_clipboard(self, text: str) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        display.get_clipboard().set(text)
        self._show_toast("Commande copiée dans le presse-papiers")


def _status_icon(ok: bool) -> Gtk.Image:
    icon_name = "emblem-ok-symbolic" if ok else "dialog-warning-symbolic"
    image = Gtk.Image.new_from_icon_name(icon_name)
    if not ok:
        image.add_css_class("warning")
    else:
        image.add_css_class("success")
    return image
