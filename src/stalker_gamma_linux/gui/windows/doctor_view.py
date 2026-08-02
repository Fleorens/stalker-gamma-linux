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
from stalker_gamma_linux.environment.plan import (  # noqa: E402
    InstallPlan,
    build_install_plan,
)
from stalker_gamma_linux.gui.summary import summarize  # noqa: E402
from stalker_gamma_linux.gui.windows.background import wrap_with_background  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402


class DoctorPage(Adw.NavigationPage):
    def __init__(self, *, target: Path | None, show_toast: Callable[[str], None]) -> None:
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
            icon_name="view-refresh-symbolic", tooltip_text=_("Refresh")
        )
        self._refresh_button.connect("clicked", lambda _b: self._start_refresh())
        header_bar = Adw.HeaderBar()
        header_bar.pack_end(self._refresh_button)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(self._stack)
        toolbar_view.add_css_class("over-artwork")

        super().__init__(title=_("Diagnostic"), child=wrap_with_background(toolbar_view))

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
        plan = build_install_plan(report.environment, report.environment.distro.family)
        groups: list[Adw.PreferencesGroup] = [self._build_verdict_group(report)]
        if not plan.is_empty:
            # En tête : la seule chose à faire pour débloquer, prête à copier.
            groups.append(self._build_plan_group(plan))
        groups.extend(
            (
                self._build_requirements_group(_("Environment"), report.environment.requirements),
                self._build_requirements_group(_("Proton prefix"), report.prefix.requirements),
                self._build_install_group(report.install, report.installed_on_disk),
            )
        )
        self._groups = groups
        for group in self._groups:
            self._preferences_page.add(group)
        self._stack.set_visible_child_name("content")
        self._refresh_button.set_sensitive(True)
        return False

    def _build_verdict_group(self, report: doctor.DoctorReport) -> Adw.PreferencesGroup:
        """Verdict d'un coup d'œil en tête de page, même vocabulaire que l'accueil."""
        verdict = summarize(report.environment)
        chip = Gtk.Label(label=verdict.label, halign=Gtk.Align.START)
        chip.add_css_class("chip")
        chip.add_css_class("chip-ok" if verdict.is_ready else "chip-warn")
        group = Adw.PreferencesGroup()
        group.add(chip)
        return group

    def _build_plan_group(self, plan: InstallPlan) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title=_("To unblock"),
            description=_("Install these prerequisites, then rerun the diagnostic."),
        )
        if plan.package_command is not None:
            subtitle = plan.package_command
            for note in plan.package_notes:
                subtitle = f"{subtitle}\n({note})"
            row = Adw.ActionRow(title=_("System packages"), subtitle=subtitle)
            row.set_subtitle_lines(1 + len(plan.package_notes))
            row.add_suffix(self._copy_button(plan.package_command))
            group.add(row)
        for step in plan.manual_steps:
            row = Adw.ActionRow(title=step.name, subtitle=step.command)
            row.set_subtitle_lines(3)
            if step.name == "umu-launcher":
                # Le seul prérequis sans paquet distro : on sait l'installer
                # nous-mêmes (zipapp officiel → ~/.local/bin, sans sudo).
                row.add_suffix(self._install_umu_button())
            row.add_suffix(self._copy_button(step.command))
            group.add(row)
        return group

    def _install_umu_button(self) -> Gtk.Button:
        button = Gtk.Button(label=_("Install"), valign=Gtk.Align.CENTER)
        button.add_css_class("suggested-action")
        button.set_tooltip_text(
            _("Downloads the official zipapp (~420 KiB) into ~/.local/bin — no sudo")
        )
        button.connect("clicked", self._on_install_umu)
        return button

    def _on_install_umu(self, button: Gtk.Button) -> None:
        from stalker_gamma_linux.prefix.errors import UmuDownloadError
        from stalker_gamma_linux.prefix.umu import install_umu

        button.set_sensitive(False)
        self._show_toast(_("Downloading umu-launcher…"))

        def worker() -> None:
            try:
                target = install_umu()
            except UmuDownloadError as error:
                GLib.idle_add(self._on_umu_install_done, button, str(error))
                return
            GLib.idle_add(self._on_umu_install_done, button, None, str(target))

        threading.Thread(target=worker, daemon=True).start()

    def _on_umu_install_done(self, button: Gtk.Button, error: str | None, target: str = "") -> bool:
        if error is not None:
            button.set_sensitive(True)
            self._show_toast(_("Failed: {error}").format(error=error))
        else:
            self._show_toast(_("umu-run installed ({target})").format(target=target))
            self._start_refresh()
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
            row.add_prefix(_status_icon(requirement.status))
            if requirement.install_hint is not None:
                row.add_suffix(self._copy_button(requirement.install_hint))
            group.add(row)
        return group

    def _build_install_group(
        self, install_state: state.InstallState, installed_on_disk: bool
    ) -> Adw.PreferencesGroup:
        description = (
            _(
                "GAMMA install detected on disk (Anomaly + MO2) — playable even if "
                "the steps below aren't checked off."
            )
            if installed_on_disk
            else None
        )
        group = Adw.PreferencesGroup(title=_("Installation"), description=description)
        for step in state.STEPS:
            done = install_state.is_done(step)
            if done:
                icon_status, subtitle = Status.OK, _("Done")
            elif installed_on_disk:
                # Install présente mais posée hors pipeline : ni « fait » ni un
                # manque alarmant — un simple constat neutre (icône info).
                icon_status, subtitle = (
                    Status.UNAVAILABLE,
                    _("outside the pipeline (install already present)"),
                )
            else:
                icon_status, subtitle = Status.MISSING, _("Not done yet")
            row = Adw.ActionRow(title=state.STEP_LABELS[step], subtitle=subtitle)
            row.add_prefix(_status_icon(icon_status))
            group.add(row)
        return group

    def _copy_button(self, command: str) -> Gtk.Button:
        button = Gtk.Button(
            icon_name="edit-copy-symbolic",
            tooltip_text=_("Copy the command"),
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
        self._show_toast(_("Command copied to clipboard"))


def _status_icon(status: Status) -> Gtk.Image:
    if status is Status.OK:
        # `object-select-symbolic` : la coche toujours présente dans Adwaita —
        # `emblem-ok-symbolic` a disparu des thèmes récents (rendu « icône cassée »).
        image = Gtk.Image.new_from_icon_name("object-select-symbolic")
        image.add_css_class("success")
        return image
    if status in (Status.UNAVAILABLE, Status.OPTIONAL):
        # Constat neutre (GPU en VM, outil facultatif) : ni vert, ni alerte.
        return Gtk.Image.new_from_icon_name("dialog-information-symbolic")
    image = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
    image.add_css_class("warning")
    return image
