"""Dialog de pré-installation : cible, espace disque, prérequis — puis GO.

C'est la porte d'entrée de l'« install experience » : on ne lance plus une
installation de ~146 Gio sur un simple clic aveugle. Le dialog montre où ça va
s'installer, ce que ça va prendre **rapporté à ce qui est libre** (une jauge,
pas un nombre à comparer de tête), et si les prérequis système sont là. La
cible et l'option raccourci sont persistées : annuler ne change rien.

Les deux conditions de départ — espace et prérequis — commandent la même
chose : le bouton reste inactif tant que l'une des deux n'est pas remplie, et
la raison est écrite à côté d'elle, jamais seulement dans la console.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from stalker_gamma_linux import sizing  # noqa: E402
from stalker_gamma_linux.environment.models import Requirement  # noqa: E402
from stalker_gamma_linux.environment.report import build_report  # noqa: E402
from stalker_gamma_linux.gui import prefs, space  # noqa: E402
from stalker_gamma_linux.gui.format import format_gib  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402
from stalker_gamma_linux.paths_safety import (  # noqa: E402
    UnsafeInstallTargetError,
    validate_install_target,
)

_VERDICT_CHIP = {
    space.SpaceVerdict.OK: ("chip-ok", _("Enough space")),
    space.SpaceVerdict.TIGHT: ("chip-warn", _("Tight on space")),
    space.SpaceVerdict.INSUFFICIENT: ("chip-error", _("Not enough space")),
    space.SpaceVerdict.UNKNOWN: ("chip-warn", _("Unknown free space")),
}
_VERDICT_GAUGE = {
    space.SpaceVerdict.OK: "gauge-ok",
    space.SpaceVerdict.TIGHT: "gauge-warn",
    space.SpaceVerdict.INSUFFICIENT: "gauge-error",
    space.SpaceVerdict.UNKNOWN: "gauge-warn",
}
_GAUGE_CLASSES = tuple(dict.fromkeys(_VERDICT_GAUGE.values()))
_CHIP_CLASSES = ("chip", "chip-ok", "chip-warn", "chip-error")


class InstallDialog(Adw.Dialog):
    """`on_confirmed(preferences)` n'est appelé qu'au clic « Lancer l'installation »."""

    def __init__(
        self,
        *,
        parent_window: Gtk.Window,
        preferences: prefs.Preferences,
        on_confirmed: Callable[[prefs.Preferences], None],
        on_show_diagnostic: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(title=_("Install G.A.M.M.A."), content_width=470)
        self._parent_window = parent_window
        self._prefs = preferences
        self._on_confirmed = on_confirmed
        self._on_show_diagnostic = on_show_diagnostic
        # Le sondage d'environnement tourne dans un thread (sous-process `which`,
        # `ldconfig`, `vulkaninfo`) : ce compteur ignore le résultat d'un sondage
        # devenu obsolète parce que l'utilisateur a changé de disque entre-temps.
        self._probe_generation = 0
        self._blockers: tuple[Requirement, ...] | None = None

        header = Adw.HeaderBar()
        header.add_css_class("flat")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(4)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.append(self._build_intro())
        content.append(self._build_target_row())
        content.append(self._build_gauge())
        content.append(self._build_prerequisites())
        content.append(self._build_options())
        content.append(self._build_confirm())

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(content)
        self.set_child(toolbar_view)

        self._refresh()
        self._start_prerequisites_probe()

    # -- construction ------------------------------------------------------

    @staticmethod
    def _caption(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("section-label")
        return label

    def _build_intro(self) -> Gtk.Widget:
        intro = Gtk.Label(
            label=_(
                "Anomaly, the full modpack, and Mod Organizer 2 will be\n"
                "downloaded and installed under the chosen directory."
            ),
            justify=Gtk.Justification.CENTER,
            wrap=True,
        )
        intro.add_css_class("dim-label")
        return intro

    def _build_target_row(self) -> Gtk.Widget:
        self._target_row = Adw.ActionRow(title=_("Install directory"))
        self._target_row.add_css_class("property")
        choose = Gtk.Button(
            icon_name="folder-open-symbolic",
            tooltip_text=_("Choose another directory"),
            valign=Gtk.Align.CENTER,
        )
        choose.add_css_class("flat")
        choose.connect("clicked", self._on_choose_target)
        self._target_row.add_suffix(choose)

        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class("boxed-list")
        rows.append(self._target_row)
        return rows

    def _build_gauge(self) -> Gtk.Widget:
        """L'espace libre rapporté à ce qu'il faut — une barre, pas deux nombres.

        « 143 Gio libres » et « 160 Gio requis » sur deux lignes obligent à
        faire la soustraction. La jauge la fait : ce qui manque se voit.
        """
        self._space_value = Gtk.Label(xalign=0)
        self._space_value.add_css_class("tile-value")
        self._space_chip = Gtk.Label(valign=Gtk.Align.CENTER, halign=Gtk.Align.END, hexpand=True)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top.append(self._space_value)
        top.append(self._space_chip)

        self._space_gauge = Gtk.ProgressBar(hexpand=True)
        self._space_gauge.add_css_class("gauge")

        self._space_note = Gtk.Label(xalign=0, wrap=True)
        self._space_note.add_css_class("dim-label")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self._caption(_("Disk space")))
        box.append(top)
        box.append(self._space_gauge)
        box.append(self._space_note)
        return box

    def _build_prerequisites(self) -> Gtk.Widget:
        """Les prérequis système (7z, libunrar, umu) condamnent l'installation
        aussi sûrement qu'un disque plein. Ils n'étaient vérifiés nulle part
        ici : on cliquait « Démarrer », et l'échec tombait une seconde plus
        tard sous forme de ligne noyée dans la console."""
        self._prereq_chip = Gtk.Label(label=_("Checking…"), valign=Gtk.Align.CENTER)
        self._prereq_chip.add_css_class("chip")
        self._prereq_chip.set_halign(Gtk.Align.END)
        self._prereq_chip.set_hexpand(True)

        self._diagnostic_button = Gtk.Button(
            label=_("Diagnostic"),
            valign=Gtk.Align.CENTER,
            tooltip_text=_("Opens the diagnostic, with the command to run for your distribution"),
        )
        self._diagnostic_button.add_css_class("flat")
        self._diagnostic_button.set_visible(False)
        self._diagnostic_button.connect("clicked", self._on_show_diagnostic_clicked)

        title = Gtk.Label(label=_("System prerequisites"), xalign=0)
        title.add_css_class("tile-value")

        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        line.append(title)
        line.append(self._prereq_chip)
        line.append(self._diagnostic_button)

        self._prereq_note = Gtk.Label(xalign=0, wrap=True, visible=False)
        self._prereq_note.add_css_class("dim-label")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(line)
        box.append(self._prereq_note)
        return box

    def _build_options(self) -> Gtk.Widget:
        self._shortcut_row = Adw.SwitchRow(
            title=_("« Play directly » menu entry"),
            subtitle=_("In addition to the launcher (already in your menu)"),
            active=self._prefs.create_direct_shortcut,
        )
        self._steam_row = Adw.SwitchRow(
            title=_("Add to the Steam library"),
            subtitle=_(
                "Entry + artwork, for Gaming Mode and the Steam Deck. Steam must "
                "be closed when the install reaches that step"
            ),
            active=self._prefs.add_to_steam,
        )
        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class("boxed-list")
        rows.append(self._shortcut_row)
        rows.append(self._steam_row)
        return rows

    def _build_confirm(self) -> Gtk.Widget:
        self._confirm = Gtk.Button(label=_("START INSTALLATION"))
        self._confirm.add_css_class("action-play")
        self._confirm.set_size_request(-1, 52)
        self._confirm.connect("clicked", self._on_confirm)
        return self._confirm

    # -- état ------------------------------------------------------------

    def _refresh(self) -> None:
        target = self._prefs.install_path
        self._target_row.set_subtitle(str(target))

        report = space.assess(target)
        verdict_class, verdict_label = _VERDICT_CHIP[report.verdict]
        self._space_value.set_label(report.free_label)
        self._space_chip.set_label(verdict_label)
        for css_class in _CHIP_CLASSES:
            self._space_chip.remove_css_class(css_class)
        self._space_chip.add_css_class("chip")
        self._space_chip.add_css_class(verdict_class)

        self._space_gauge.set_fraction(space.gauge_fraction(report))
        for css_class in _GAUGE_CLASSES:
            self._space_gauge.remove_css_class(css_class)
        self._space_gauge.add_css_class(_VERDICT_GAUGE[report.verdict])

        self._update_confirm_sensitivity(report)
        self._space_note.set_label(self._space_note_text(report))

    @staticmethod
    def _space_note_text(report: space.SpaceReport) -> str:
        if report.verdict is space.SpaceVerdict.INSUFFICIENT:
            return _(
                "At least {minimum} free is required (recommended: {recommended}). "
                "Choose another disk."
            ).format(
                minimum=format_gib(space.MINIMUM_FREE_BYTES),
                recommended=format_gib(space.RECOMMENDED_FREE_BYTES),
            )
        if report.verdict is space.SpaceVerdict.TIGHT:
            return _(
                "It'll fit, but {recommended} free is recommended (archive cache + extracted mods)."
            ).format(recommended=format_gib(space.RECOMMENDED_FREE_BYTES))
        return _(
            "About {cache} GiB to download, {total} GiB for the full install. "
            "Can be interrupted at any time: the install resumes where it left off."
        ).format(cache=sizing.CACHE_GIB, total=sizing.TOTAL_INSTALL_GIB)

    # -- prérequis système -------------------------------------------------

    def _start_prerequisites_probe(self) -> None:
        """Sonde l'environnement hors du fil GTK, comme la fenêtre principale."""
        self._probe_generation += 1
        generation = self._probe_generation
        target = self._prefs.install_path
        self._blockers = None
        self._prereq_chip.set_label(_("Checking…"))
        self._diagnostic_button.set_visible(False)
        self._update_confirm_sensitivity(space.assess(target))

        def worker() -> None:
            blockers = build_report(target).install_blockers
            GLib.idle_add(self._apply_prerequisites, generation, blockers)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_prerequisites(self, generation: int, blockers: tuple[Requirement, ...]) -> bool:
        if generation != self._probe_generation:
            return False  # un sondage plus récent est en route
        self._blockers = blockers
        for css_class in ("chip-ok", "chip-error"):
            self._prereq_chip.remove_css_class(css_class)
        if blockers:
            self._prereq_chip.set_label(", ".join(requirement.name for requirement in blockers))
            self._prereq_chip.add_css_class("chip-error")
            self._prereq_note.set_label(
                _("Install them before starting — the install cannot succeed without them.")
            )
            self._prereq_note.set_visible(True)
            self._diagnostic_button.set_visible(self._on_show_diagnostic is not None)
        else:
            self._prereq_chip.set_label(_("All present"))
            self._prereq_chip.add_css_class("chip-ok")
            self._prereq_note.set_visible(False)
        self._update_confirm_sensitivity(space.assess(self._prefs.install_path))
        return False

    def _update_confirm_sensitivity(self, report: space.SpaceReport) -> None:
        """On ne démarre que si l'espace **et** les prérequis le permettent.

        Tant que le sondage n'a pas rendu (`_blockers is None`), le bouton reste
        inactif : proposer de lancer 146 Gio de téléchargement avant de savoir
        si `7z` est présent serait exactement le problème qu'on corrige.
        """
        space_ok = report.verdict is not space.SpaceVerdict.INSUFFICIENT
        self._confirm.set_sensitive(space_ok and self._blockers == ())

    def _on_show_diagnostic_clicked(self, _button: Gtk.Button) -> None:
        if self._on_show_diagnostic is None:
            return
        self.close()
        self._on_show_diagnostic()

    # -- actions -----------------------------------------------------------

    def _on_choose_target(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(
            title=_("Choose the install directory"),
            initial_folder=Gio.File.new_for_path(str(self._prefs.install_path)),
        )
        dialog.select_folder(self._parent_window, None, self._on_target_selected)

    def _on_target_selected(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, *_args: object
    ) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if folder is None or folder.get_path() is None:
            return
        chosen = Path(str(folder.get_path()))
        try:
            # Même frontière que `--target` côté CLI : le chemin choisi finit
            # dans le `.desktop` et le `ModOrganizer.ini`, où un caractère de
            # contrôle ouvre une clé supplémentaire (cf. `paths_safety`).
            validate_install_target(chosen)
        except UnsafeInstallTargetError as error:
            self._alert(_("Unusable directory"), str(error))
            return
        self._prefs = self._prefs.with_install_path(chosen)
        self._refresh()
        # L'espace disque dépend du volume choisi ; les prérequis système, non —
        # mais `check_disk_space` fait partie du rapport, donc on resonde.
        self._start_prerequisites_probe()

    def _alert(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(self)

    def _on_confirm(self, _button: Gtk.Button) -> None:
        updated = self._prefs.with_create_direct_shortcut(
            self._shortcut_row.get_active()
        ).with_add_to_steam(self._steam_row.get_active())
        prefs.save_preferences(updated)
        self.close()
        self._on_confirmed(updated)
