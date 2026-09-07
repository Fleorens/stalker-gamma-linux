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

from stalker_gamma_linux import backups, doctor, state  # noqa: E402
from stalker_gamma_linux.environment.models import Requirement, Status  # noqa: E402
from stalker_gamma_linux.environment.plan import (  # noqa: E402
    InstallPlan,
    build_install_plan,
)
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET  # noqa: E402
from stalker_gamma_linux.gui.summary import summarize  # noqa: E402
from stalker_gamma_linux.gui.windows.background import wrap_with_background  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402
from stalker_gamma_linux.report_bundle import build_bundle  # noqa: E402


class DoctorPage(Adw.NavigationPage):
    def __init__(
        self,
        *,
        target: Path | None,
        show_toast: Callable[[str], None],
        on_verify: Callable[[bool], None] | None = None,
        on_backup: Callable[[], None] | None = None,
        on_restore: Callable[[str], None] | None = None,
    ) -> None:
        self._target = target
        self._show_toast = show_toast
        # `on_verify(repair)` : la fenêtre principale pousse la tâche sur sa
        # vue progression. Rien de la vérification elle-même n'est décidé ici —
        # elle vit dans `integrity.run_verify`, partagée avec la CLI.
        self._on_verify = on_verify
        # Idem pour la sauvegarde/restauration : `backups.run_backup` et
        # `backups.run_restore` sont exactement les commandes CLI.
        self._on_backup = on_backup
        self._on_restore = on_restore
        self._groups: list[Adw.PreferencesGroup] = []

        # `Gtk.Spinner` et non `Adw.Spinner` : ce dernier n'existe qu'à partir de
        # libadwaita 1.6, alors qu'Ubuntu 24.04 livre 1.5. Le rendu est un peu
        # moins joli, mais la vue Diagnostic — celle qu'on ouvre justement quand
        # quelque chose ne va pas — cessait purement et simplement de s'ouvrir.
        self._spinner = Gtk.Spinner(spinning=True)
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
        # C'est ici que l'utilisateur constate qu'un prérequis cloche : c'est
        # donc ici que doit se trouver le bouton qui produit le rapport à
        # joindre à une issue, pas seulement dans la CLI.
        self._report_button = Gtk.Button(
            icon_name="document-save-symbolic",
            tooltip_text=_("Save a diagnostic report to attach to an issue"),
        )
        self._report_button.connect("clicked", lambda _b: self._save_report())
        header_bar = Adw.HeaderBar()
        header_bar.pack_end(self._refresh_button)
        header_bar.pack_end(self._report_button)

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
        if self._on_verify is not None:
            groups.append(self._build_integrity_group())
        if self._on_backup is not None:
            groups.append(self._build_backups_group())
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

    def _build_integrity_group(self) -> Adw.PreferencesGroup:
        """« Le jeu crashe depuis hier » : le seul écran où poser la question.

        Deux boutons plutôt qu'un, parce que les deux gestes n'ont pas le même
        prix : vérifier ne fait que lire, réparer retélécharge les mods abîmés.
        """
        group = Adw.PreferencesGroup(
            title=_("Installed mods"),
            description=_(
                "Compares the mod files on disk against a reference fingerprint. "
                "The first run records that reference; later runs report what "
                "changed since. Files you added yourself are never touched."
            ),
        )
        row = Adw.ActionRow(
            title=_("Check integrity"),
            subtitle=_("Reads every mod file — several minutes on a full install"),
        )
        row.set_subtitle_lines(2)
        row.add_suffix(self._verify_button(_("Repair"), repair=True))
        row.add_suffix(self._verify_button(_("Check"), repair=False))
        group.add(row)
        return group

    def _build_backups_group(self) -> Adw.PreferencesGroup:
        """« J'ai perdu ma liste de mods » : le geste, et les points de retour.

        La liste vient de `backups.list_backups`, c'est-à-dire des manifestes —
        pas d'un parcours de dossiers refait ici. Une sauvegarde illisible est
        affichée comme telle plutôt que masquée : elle occupe de la place, et
        l'utilisateur doit savoir qu'on ne sait pas la remettre.
        """
        root = self._target if self._target is not None else DEFAULT_INSTALL_TARGET
        group = Adw.PreferencesGroup(
            title=_("Backups"),
            description=_(
                "Your MO2 profiles (mod list, load order), your saved games and the "
                "overwrite folder. One is written automatically before each update; "
                "the ones you create here are never rotated away."
            ),
        )
        create_row = Adw.ActionRow(
            title=_("Back up now"),
            subtitle=_("Profiles, saved games and overwrite — kept until you delete it"),
        )
        create_row.set_subtitle_lines(2)
        button = Gtk.Button(label=_("Back up"), valign=Gtk.Align.CENTER)
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda _b: self._on_backup() if self._on_backup else None)
        create_row.add_suffix(button)
        group.add(create_row)

        listing = backups.list_backups(root)
        for stored in listing.backups:
            group.add(self._backup_row(stored))
        for path, reason in listing.unreadable:
            row = Adw.ActionRow(title=path.name, subtitle=reason)
            row.set_subtitle_lines(2)
            row.add_prefix(_status_icon(Status.MISSING))
            group.add(row)
        return group

    def _backup_row(self, stored: backups.StoredBackup) -> Adw.ActionRow:
        manifest = stored.manifest
        size = (
            _("size unknown (written before manifests)")
            if manifest.legacy
            else backups.format_size(manifest.size_bytes)
        )
        row = Adw.ActionRow(
            title=f"{manifest.created_at:%Y-%m-%d %H:%M}",
            subtitle=f"{backups.describe_sets(manifest.sets)}\n{size}",
        )
        row.set_subtitle_lines(2)
        row.add_suffix(self._restore_button(stored))
        return row

    def _restore_button(self, stored: backups.StoredBackup) -> Gtk.Button:
        button = Gtk.Button(label=_("Restore"), valign=Gtk.Align.CENTER)
        button.add_css_class("destructive-action")
        button.connect("clicked", lambda _b: self._confirm_restore(stored))
        return button

    def _confirm_restore(self, stored: backups.StoredBackup) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Restore this backup?"),
            body=_(
                "{sets} will be replaced by what this backup holds. Your current "
                "state is backed up first, so this can be undone."
            ).format(sets=backups.describe_sets(stored.manifest.sets)),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restore", _("Restore"))
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_restore_response, stored.identifier)
        dialog.present(self)

    def _on_restore_response(
        self, _dialog: Adw.AlertDialog, response: str, identifier: str
    ) -> None:
        if response == "restore" and self._on_restore is not None:
            self._on_restore(identifier)

    def _verify_button(self, label: str, *, repair: bool) -> Gtk.Button:
        button = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
        if repair:
            button.add_css_class("destructive-action")
            button.set_tooltip_text(
                _(
                    "Removes the damaged mods that come from the modpack and "
                    "reinstalls them — this re-downloads them and takes a while"
                )
            )
        else:
            button.add_css_class("suggested-action")
        button.connect("clicked", lambda _b: self._start_verify(repair=repair))
        return button

    def _start_verify(self, *, repair: bool) -> None:
        if self._on_verify is None:
            return
        if not repair:
            self._on_verify(False)
            return
        dialog = Adw.AlertDialog(
            heading=_("Repair the damaged mods?"),
            body=_(
                "The damaged mods that come from the modpack will be removed "
                "(folder + cached archive) and downloaded again. The engine then "
                "reinstalls the whole modpack over your mods folder, so other "
                "mods may be updated in passing. Nothing you added is deleted — "
                "neither your own mods, nor a file you dropped inside one."
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("repair", _("Repair"))
        dialog.set_response_appearance("repair", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_repair_response)
        dialog.present(self)

    def _on_repair_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "repair" and self._on_verify is not None:
            self._on_verify(True)

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

    def _save_report(self) -> None:
        """Écrit le rapport de diagnostic dans le home, et annonce son chemin.

        Pas de sélecteur de fichier : l'utilisateur qui clique ici a un problème
        et veut un fichier à joindre, pas une boîte de dialogue de plus. Le
        chemin est affiché dans le toast — et le rapport est anonymisé.
        """
        destination = Path.home() / "stalker-gamma-linux-report.txt"
        try:
            destination.write_text(
                build_bundle(doctor.build_full_report(self._target)), encoding="utf-8"
            )
        except OSError as error:
            self._show_toast(_("Could not write the report: {error}").format(error=error))
            return
        self._show_toast(_("Report saved to {path}").format(path=destination))


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
