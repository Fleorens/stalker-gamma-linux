"""Dialog de pré-installation : cible, espace disque, raccourci — puis GO.

C'est la porte d'entrée de l'« install experience » : on ne lance plus une
installation de ~250 Go sur un simple clic aveugle. Le dialog montre où ça va
s'installer, combien d'espace est libre sur ce volume (verdict coloré), et
laisse changer de disque avant de confirmer. La cible et l'option raccourci
sont persistées dans les préférences : annuler ne change rien.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from stalker_gamma_linux.gui import prefs, space  # noqa: E402
from stalker_gamma_linux.gui.format import format_gib  # noqa: E402

_VERDICT_CHIP = {
    space.SpaceVerdict.OK: ("chip-ok", "Espace suffisant"),
    space.SpaceVerdict.TIGHT: ("chip-warn", "Espace juste"),
    space.SpaceVerdict.INSUFFICIENT: ("chip-error", "Espace insuffisant"),
    space.SpaceVerdict.UNKNOWN: ("chip-warn", "Espace libre inconnu"),
}


class InstallDialog(Adw.Dialog):
    """`on_confirmed(preferences)` n'est appelé qu'au clic « Lancer l'installation »."""

    def __init__(
        self,
        *,
        parent_window: Gtk.Window,
        preferences: prefs.Preferences,
        on_confirmed: Callable[[prefs.Preferences], None],
    ) -> None:
        super().__init__(title="Installer G.A.M.M.A.", content_width=440)
        self._parent_window = parent_window
        self._prefs = preferences
        self._on_confirmed = on_confirmed

        header = Adw.HeaderBar()
        header.add_css_class("flat")

        intro = Gtk.Label(
            label=(
                "Anomaly, le modpack complet et Mod Organizer 2 vont être\n"
                "téléchargés puis installés sous le répertoire choisi."
            ),
            justify=Gtk.Justification.CENTER,
            wrap=True,
        )
        intro.add_css_class("dim-label")

        self._target_row = Adw.ActionRow(title="Répertoire d'installation")
        self._target_row.add_css_class("property")
        choose = Gtk.Button(
            icon_name="folder-open-symbolic",
            tooltip_text="Choisir un autre répertoire",
            valign=Gtk.Align.CENTER,
        )
        choose.add_css_class("flat")
        choose.connect("clicked", self._on_choose_target)
        self._target_row.add_suffix(choose)

        self._space_row = Adw.ActionRow(title="Espace libre sur ce volume")
        self._space_row.add_css_class("property")
        self._space_chip = Gtk.Label()
        self._space_chip.set_valign(Gtk.Align.CENTER)
        self._space_row.add_suffix(self._space_chip)

        self._shortcut_row = Adw.SwitchRow(
            title="Raccourci « jouer en direct »",
            subtitle=(
                "En plus du launcher (déjà dans ton menu) — utile surtout pour "
                "Steam « Ajouter un jeu non-Steam »"
            ),
            active=preferences.create_steam_shortcut,
        )

        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class("boxed-list")
        rows.append(self._target_row)
        rows.append(self._space_row)
        rows.append(self._shortcut_row)

        self._space_note = Gtk.Label(justify=Gtk.Justification.CENTER, wrap=True)
        self._space_note.add_css_class("dim-label")

        self._confirm = Gtk.Button(label="LANCER L'INSTALLATION")
        self._confirm.add_css_class("action-play")
        self._confirm.set_size_request(-1, 52)
        self._confirm.connect("clicked", self._on_confirm)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(4)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.append(intro)
        content.append(rows)
        content.append(self._space_note)
        content.append(self._confirm)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(content)
        self.set_child(toolbar_view)

        self._refresh()

    # -- état ------------------------------------------------------------

    def _refresh(self) -> None:
        target = self._prefs.install_path
        self._target_row.set_subtitle(str(target))

        report = space.assess(target)
        verdict_class, verdict_label = _VERDICT_CHIP[report.verdict]
        self._space_chip.set_label(
            f"{report.free_label} — {verdict_label}"
            if report.free_bytes is not None
            else verdict_label
        )
        for css_class in ("chip", "chip-ok", "chip-warn", "chip-error"):
            self._space_chip.remove_css_class(css_class)
        self._space_chip.add_css_class("chip")
        self._space_chip.add_css_class(verdict_class)

        blocked = report.verdict is space.SpaceVerdict.INSUFFICIENT
        self._confirm.set_sensitive(not blocked)
        if blocked:
            self._space_note.set_label(
                f"Il faut au moins {format_gib(space.MINIMUM_FREE_BYTES)} libres "
                f"(recommandé : {format_gib(space.RECOMMENDED_FREE_BYTES)}). "
                "Choisis un autre disque."
            )
        elif report.verdict is space.SpaceVerdict.TIGHT:
            self._space_note.set_label(
                f"Ça passe, mais {format_gib(space.RECOMMENDED_FREE_BYTES)} libres "
                "sont recommandés (cache d'archives + mods extraits)."
            )
        else:
            self._space_note.set_label(
                "Téléchargement d'environ 40 Gio, installation complète "
                "d'environ 150 Gio. Interruption possible à tout moment : "
                "l'installation reprend où elle s'était arrêtée."
            )

    # -- actions -----------------------------------------------------------

    def _on_choose_target(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(
            title="Choisir le répertoire d'installation",
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
        self._prefs = self._prefs.with_install_path(Path(str(folder.get_path())))
        self._refresh()

    def _on_confirm(self, _button: Gtk.Button) -> None:
        updated = self._prefs.with_create_steam_shortcut(self._shortcut_row.get_active())
        prefs.save_preferences(updated)
        self.close()
        self._on_confirmed(updated)
