"""Fenêtre Préférences : chemin d'installation, version Proton-GE, intégration Steam.

Persistance déléguée à `gui.prefs` (TOML, indépendant de GTK). Le raccourci
bureau lui-même reste celui de `desktop/` (T06) ; la case « Créer un raccourci
bureau » ne fait que réutiliser le flag `--shortcut` déjà exposé par
`orchestrator.run_install` — rien de nouveau côté logique d'installation.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from stalker_gamma_linux.environment import checks, gamemode  # noqa: E402
from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS  # noqa: E402
from stalker_gamma_linux.environment.distro import detect_distro  # noqa: E402
from stalker_gamma_linux.gui import prefs  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402


def _gamemode_subtitle() -> str:
    """Sous-titre de l'interrupteur : ce que ça fait, et si c'est installé.

    L'interrupteur reste actionnable même sans GameMode installé (la préférence
    est persistée, elle s'appliquera dès que le paquet sera là) — d'où le
    sous-titre qui donne la commande d'installation plutôt qu'une ligne grisée.
    """
    if gamemode.is_available():
        # Même phrase que `doctor` : l'utilisateur qui a lu l'un ne doit pas
        # découvrir un état différent dans l'autre (groupe `gamemode` compris).
        return checks.gamemode_detail()
    hint = INSTALL_COMMANDS["gamemode"].for_family(detect_distro().family)
    missing = _("Performance CPU governor and priorities — GameMode is not installed yet.")
    return f"{missing} {hint}" if hint else missing


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(
        self,
        *,
        parent_window: Gtk.Window,
        preferences: prefs.Preferences,
        on_saved: Callable[[prefs.Preferences], None],
    ) -> None:
        super().__init__(title=_("Preferences"))
        self._parent_window = parent_window
        self._prefs = preferences
        self._on_saved = on_saved

        page = Adw.PreferencesPage()
        self.add(page)

        install_group = Adw.PreferencesGroup(title=_("Installation"))
        page.add(install_group)
        self._path_row = Adw.ActionRow(
            title=_("Install directory"), subtitle=str(preferences.install_path)
        )
        choose_button = Gtk.Button(label=_("Choose…"), valign=Gtk.Align.CENTER)
        choose_button.connect("clicked", self._on_choose_path)
        self._path_row.add_suffix(choose_button)
        install_group.add(self._path_row)

        proton_group = Adw.PreferencesGroup(
            title="Proton",
            description=_(
                "Proton-GE version to use for the shared prefix. "
                "Leave empty = latest published release (recommended)."
            ),
        )
        page.add(proton_group)
        self._release_row = Adw.EntryRow(title=_("Version (e.g. GE-Proton10-8)"))
        self._release_row.set_text(preferences.proton_release or "")
        proton_group.add(self._release_row)

        performance_group = Adw.PreferencesGroup(title=_("Performance"))
        page.add(performance_group)
        self._gamemode_row = Adw.SwitchRow(
            title=_("GameMode while playing"),
            subtitle=_gamemode_subtitle(),
            active=preferences.use_gamemode,
        )
        performance_group.add(self._gamemode_row)

        steam_group = Adw.PreferencesGroup(title="Steam")
        page.add(steam_group)
        self._shortcut_row = Adw.SwitchRow(
            title=_("« Play directly » shortcut on install"),
            subtitle=_(
                "In addition to the launcher (already in your menu) — reuse it with "
                "Steam's native « Add a Non-Steam Game » button; adding it to "
                "Steam itself stays manual."
            ),
            active=preferences.create_steam_shortcut,
        )
        steam_group.add(self._shortcut_row)

        self.connect("closed", self._on_closed)

    def _on_choose_path(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(
            title=_("Choose the install directory"),
            initial_folder=Gio.File.new_for_path(str(self._prefs.install_path)),
        )
        dialog.select_folder(self._parent_window, None, self._on_folder_selected)

    def _on_folder_selected(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, *_args: object
    ) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if folder is None:
            return
        path_str = folder.get_path()
        if path_str is None:
            return
        path = Path(path_str)
        self._prefs = self._prefs.with_install_path(path)
        self._path_row.set_subtitle(str(path))

    def _on_closed(self, _dialog: Adw.PreferencesDialog) -> None:
        release = self._release_row.get_text().strip()
        updated = (
            self._prefs.with_proton_release(release)
            .with_create_steam_shortcut(self._shortcut_row.get_active())
            .with_use_gamemode(self._gamemode_row.get_active())
        )
        prefs.save_preferences(updated)
        self._on_saved(updated)
