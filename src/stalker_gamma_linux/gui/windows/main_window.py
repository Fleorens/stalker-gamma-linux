"""Fenêtre principale : un launcher — artwork, héros, gros bouton, statut live.

Toute la logique (install/update/play/mo2) reste dans `orchestrator`/
`mo2.session`, et les sept branchements vers elle sont décrits dans
`gui.jobs` ; ce module compose les vues (héros, dialog d'installation,
progression) et pousse ces `Job` dans un `gui.worker.BackgroundTask` (hors du
fil GTK). Le sondage d'environnement, d'espace disque et de mods tourne dans
un thread au démarrage et à chaque retour de tâche.

Mise en page : l'artwork occupe tout le fond, l'état du système est en barre
de titre, et le bas de la fenêtre est un « pont » — identité et chiffres à
gauche, actions à droite, séparés de l'image par un filet lumineux. C'est la
grammaire d'un launcher de jeu, pas celle d'une fenêtre de préférences.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from stalker_gamma_linux import adopt, uninstall, updates  # noqa: E402
from stalker_gamma_linux.environment.report import build_report  # noqa: E402
from stalker_gamma_linux.exit_codes import CANCELLED_EXIT_CODE  # noqa: E402
from stalker_gamma_linux.gui import jobs, prefs, space, stats, summary, viewmodel  # noqa: E402
from stalker_gamma_linux.gui.windows.background import hero_backdrop  # noqa: E402
from stalker_gamma_linux.gui.windows.doctor_view import DoctorPage  # noqa: E402
from stalker_gamma_linux.gui.windows.hero import HeroBox  # noqa: E402
from stalker_gamma_linux.gui.windows.install_dialog import InstallDialog  # noqa: E402
from stalker_gamma_linux.gui.windows.preferences import PreferencesDialog  # noqa: E402
from stalker_gamma_linux.gui.windows.progress_view import ProgressPage  # noqa: E402
from stalker_gamma_linux.gui.windows.status_pill import StatusPill  # noqa: E402
from stalker_gamma_linux.gui.worker import BackgroundTask  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402
from stalker_gamma_linux.mo2.paths import Mo2Paths  # noqa: E402
from stalker_gamma_linux.postmortem.analysis import build_postmortem  # noqa: E402
from stalker_gamma_linux.postmortem.report import format_postmortem  # noqa: E402
from stalker_gamma_linux.postmortem.result import Postmortem  # noqa: E402
from stalker_gamma_linux.report_bundle import version_line  # noqa: E402

# Confortable sur l'écran Steam Deck (1280x800, souvent en fenêtré bordless
# plein écran côté Gaming Mode) tout en restant raisonnable sur un bureau.
_DEFAULT_WIDTH = 1060
_DEFAULT_HEIGHT = 720
_PLAY_WIDTH, _PLAY_HEIGHT = 244, 62
_SECONDARY_HEIGHT = 38


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *, application: Adw.Application) -> None:
        super().__init__(
            application=application,
            title=_("GAMMA Linux Launcher"),
            default_width=_DEFAULT_WIDTH,
            default_height=_DEFAULT_HEIGHT,
        )
        self.set_size_request(760, 560)
        self._preferences = prefs.load_preferences()
        self._current_state: viewmodel.MainWindowState | None = None
        self._probe_generation = 0
        # Le post-mortem n'a de sens qu'après une partie : le bouton n'apparaît
        # donc qu'au retour d'un `play`, là où l'utilisateur le cherche, et pas
        # en permanence comme une invitation à chercher un problème.
        self._played_this_session = False

        self._toast_overlay = Adw.ToastOverlay()
        self._nav_view = Adw.NavigationView()
        self._toast_overlay.set_child(self._nav_view)
        self.set_content(self._toast_overlay)

        self._update_action = self._add_action("check-update", self._on_check_update)
        self._add_action("import-install", self._on_import_install)
        self._add_action("show-doctor", self._on_show_doctor)
        self._add_action("show-preferences", self._on_show_preferences)
        self._add_action("show-about", self._on_show_about)
        self._add_action("uninstall", self._on_uninstall)

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

    @staticmethod
    def _wordmark() -> Gtk.Widget:
        """Signature discrète en barre de titre — deux labels, aucun markup.

        Deux `Gtk.Label` plutôt qu'un seul en Pango markup : le markup est un
        format à balises, et prendre l'habitude de l'employer pour de la
        décoration finit par le faire employer avec du texte qu'on ne contrôle
        pas (un chemin, un nom de mod). Ici, rien à échapper — il n'y a rien à
        interpréter.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        accent = Gtk.Label(label="GAMMA")
        accent.add_css_class("wordmark")
        accent.add_css_class("wordmark-accent")
        suffix = Gtk.Label(label="LINUX")
        suffix.add_css_class("wordmark")
        box.append(accent)
        box.append(suffix)
        return box

    def _build_header(self) -> Adw.HeaderBar:
        menu = Gio.Menu()
        menu.append(_("Check for updates…"), "win.check-update")
        # Le public de l'import (install GOG/Heroic bloquée, dossier partagé
        # avec un dual-boot) est précisément celui qui n'ouvre pas de terminal :
        # la commande CLI seule le laissait hors de portée.
        menu.append(_("Import an existing install…"), "win.import-install")
        menu.append(_("Diagnostic"), "win.show-doctor")
        menu.append(_("Preferences"), "win.show-preferences")
        menu.append(_("Uninstall…"), "win.uninstall")
        menu.append(_("About"), "win.show-about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True)

        self._status_pill = StatusPill(on_clicked=self._push_doctor)

        header_bar = Adw.HeaderBar(show_title=False)
        header_bar.pack_start(self._wordmark())
        header_bar.pack_end(menu_button)
        header_bar.pack_end(self._status_pill)
        return header_bar

    def _build_actions(self) -> Gtk.Widget:
        self._primary_content = Adw.ButtonContent(
            icon_name="media-playback-start-symbolic", label=_("PLAY")
        )
        self._primary_button = Gtk.Button(child=self._primary_content)
        self._primary_button.add_css_class("action-play")
        self._primary_button.set_size_request(_PLAY_WIDTH, _PLAY_HEIGHT)
        self._primary_button.set_receives_default(True)
        self._primary_button.connect("clicked", self._on_primary_action)

        self._mo2_button = self._secondary_button("Mod Organizer 2", self._start_mo2)
        self._update_button = self._secondary_button(_("Update"), self._confirm_update)
        self._postmortem_button = self._secondary_button(
            _("Did the game crash?"), self._start_postmortem
        )
        self._postmortem_button.set_visible(False)

        secondary_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END
        )
        secondary_row.append(self._postmortem_button)
        secondary_row.append(self._mo2_button)
        secondary_row.append(self._update_button)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            halign=Gtk.Align.END,
            valign=Gtk.Align.END,
        )
        actions.append(self._primary_button)
        actions.append(secondary_row)
        return actions

    def _secondary_button(self, label: str, handler: Callable[[], None]) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.add_css_class("action-secondary")
        button.set_size_request(-1, _SECONDARY_HEIGHT)
        button.connect("clicked", lambda _button: handler())
        return button

    def _build_main_page(self) -> Adw.NavigationPage:
        self._hero = HeroBox()
        self._hero.set_hexpand(True)

        deck_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=28)
        deck_row.append(self._hero)
        deck_row.append(self._build_actions())

        deck = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        deck.add_css_class("deck")
        deck.set_margin_start(30)
        deck.set_margin_end(30)
        deck.set_margin_bottom(26)
        deck_row.set_margin_top(20)
        deck.append(deck_row)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(Gtk.Box(vexpand=True))  # pousse le pont vers le bas
        content.append(deck)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._build_header())
        toolbar_view.set_content(content)
        toolbar_view.add_css_class("over-artwork")

        return Adw.NavigationPage(
            title=_("GAMMA Linux Launcher"),
            tag="main",
            child=hero_backdrop(toolbar_view),
        )

    # -- état --------------------------------------------------------------

    def _refresh_status(self) -> None:
        result = viewmodel.load_main_window_state(self._preferences.install_path)
        self._current_state = result

        self._hero.show_state(result)
        if result.is_installed:
            self._primary_content.set_label(_("PLAY"))
            self._primary_content.set_icon_name("media-playback-start-symbolic")
        else:
            self._primary_content.set_label(_("INSTALL"))
            self._primary_content.set_icon_name("folder-download-symbolic")
        self._mo2_button.set_visible(result.is_installed)
        self._update_button.set_visible(result.is_installed)
        self._postmortem_button.set_visible(result.is_installed and self._played_this_session)
        self._update_action.set_enabled(result.is_installed)

        self.set_default_widget(self._primary_button)
        self._primary_button.grab_focus()
        self._start_environment_probe()

    def _start_environment_probe(self) -> None:
        """Environnement, espace disque et mods déployés, hors du fil GTK.

        Une seule passe pour les trois : l'analyse d'environnement lance des
        sous-process (`which`, `ldconfig`, `vulkaninfo`), le décompte des mods
        touche le disque — aucun des deux n'a sa place sur le fil qui doit
        repeindre la fenêtre.
        """
        self._probe_generation += 1
        generation = self._probe_generation
        target = self._preferences.install_path

        def worker() -> None:
            env_summary = summary.summarize(build_report(target))
            space_report = space.assess(target)
            install_stats = stats.collect(target)
            GLib.idle_add(self._apply_probe, generation, env_summary, space_report, install_stats)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_probe(
        self,
        generation: int,
        env_summary: summary.SystemSummary,
        space_report: space.SpaceReport,
        install_stats: stats.InstallStats,
    ) -> bool:
        if generation != self._probe_generation or self._current_state is None:
            return False  # une analyse plus récente est en route, ne pas écraser
        self._status_pill.show_summary(env_summary)
        self._hero.show_probe(space_report, install_stats)
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
                on_show_diagnostic=self._push_doctor,
            ).present(self)

    def _on_install_confirmed(self, updated: prefs.Preferences) -> None:
        self._preferences = updated
        self._start_install()

    def _on_check_update(self, _action: Gio.SimpleAction, _param: None) -> None:
        """Vérifie, et **seulement** ça.

        Cette entrée lançait `run_update` — donc un `full-install` complet, qui
        réécrit la liste de mods MO2. Un bouton qui annonce une vérification ne
        doit rien installer : on compare les définitions du modpack à l'amont
        (quelques dizaines de Ko, aucune écriture), puis on propose la vraie
        mise à jour si elle a lieu d'être.
        """
        self._show_toast(_("Checking for updates…"))
        gamma_dir = Mo2Paths.under(self._preferences.install_path).instance

        def worker() -> None:
            result = updates.check_for_updates(gamma_dir)
            GLib.idle_add(self._present_update_check, result)

        threading.Thread(target=worker, daemon=True).start()

    def _present_update_check(self, result: updates.UpdateCheck) -> bool:
        dialog = Adw.AlertDialog(heading=_("Check for updates"), body=result.message)
        dialog.add_response("close", _("Close"))
        if result.is_available:
            dialog.add_response("update", _("Update now"))
            dialog.set_response_appearance("update", Adw.ResponseAppearance.SUGGESTED)
            dialog.connect(
                "response",
                lambda _d, response: self._confirm_update() if response == "update" else None,
            )
        dialog.present(self)
        return False

    def _confirm_update(self) -> None:
        """Prévient de ce que la mise à jour va réellement faire, puis lance.

        `full-install` remplace `profiles/G.A.M.M.A/modlist.txt` par la liste
        amont. Depuis T17 on rejoue les écarts du joueur par-dessus, et on met
        de côté profils **et** parties avant de commencer — mais la fusion peut
        s'abstenir (voir `mo2.modlist_merge`), donc la promesse annoncée reste
        celle du filet, pas celle du miracle.
        """
        dialog = Adw.AlertDialog(
            heading=_("Update the modpack?"),
            body=_(
                "Only what changed upstream is re-downloaded. Your saves and your "
                "in-game settings are preserved.\n\n"
                "The update rewrites your MO2 mod list with the upstream one, then "
                "your own changes (enabled/disabled mods, load order, mods you added) "
                "are reapplied on top. Your profiles and saved games are backed up to "
                "<target>/backups/ before anything starts — restore them from the "
                "Diagnostic view if the result is not what you expected."
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("update", _("Update"))
        dialog.set_response_appearance("update", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response", lambda _d, response: self._start_update() if response == "update" else None
        )
        dialog.present(self)

    def _on_import_install(self, _action: Gio.SimpleAction, _param: None) -> None:
        dialog = Gtk.FileDialog(title=_("Choose the folder holding your GAMMA install"))
        dialog.select_folder(self, None, self._on_import_folder_selected)

    def _on_import_folder_selected(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, *_args: object
    ) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # annulé par l'utilisateur : rien à signaler
        if folder is None or folder.get_path() is None:
            return
        self._preview_adoption(Path(str(folder.get_path())))

    def _preview_adoption(self, source: Path) -> None:
        """Montre ce qui a été trouvé et demande confirmation avant d'écrire."""
        try:
            adoption = adopt.plan(adopt.discover(source))
        except adopt.AdoptionError as error:
            self._alert(_("Nothing to import"), str(error))
            return

        confirm = Adw.AlertDialog(
            heading=_("Import this install?"),
            body=adopt.format_plan(adoption),
        )
        confirm.add_response("cancel", _("Cancel"))
        confirm.add_response("import", _("Import"))
        confirm.set_response_appearance("import", Adw.ResponseAppearance.SUGGESTED)
        confirm.set_default_response("import")
        confirm.connect("response", self._on_import_confirmed, adoption)
        confirm.present(self)

    def _on_import_confirmed(
        self, _dialog: Adw.AlertDialog, response: str, adoption: adopt.AdoptionPlan
    ) -> None:
        if response != "import":
            return
        try:
            adopt.apply(adoption, on_progress=lambda _line: None)
        except OSError as error:
            self._alert(_("Import failed"), str(error))
            return

        # La cible devient l'installation adoptée : le bouton principal enchaîne
        # alors sur ce qui manque vraiment (ReShade, préfixe, instance MO2), en
        # sautant les téléchargements que l'adoption vient de marquer faits.
        self._preferences = self._preferences.with_install_path(adoption.root)
        prefs.save_preferences(self._preferences)
        self._refresh_status()
        self._show_toast(_("Install adopted — press the main button to finish the setup."))

    def _alert(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(self)

    def _on_show_doctor(self, _action: Gio.SimpleAction, _param: None) -> None:
        self._push_doctor()

    def _push_doctor(self) -> None:
        self._nav_view.push(
            DoctorPage(
                target=self._preferences.install_path,
                show_toast=self._show_toast,
                on_verify=self._start_verify,
                on_backup=self._start_backup,
                on_restore=self._start_restore,
            )
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
            application_name=_("GAMMA Linux Launcher"),
            # Sans ça, un utilisateur qui ouvre une issue ne peut pas dire quelle
            # version il fait tourner : la GUI est son seul point de contact.
            version=version_line(),
            developer_name=_("Community project, not affiliated with GSC Game World"),
            comments=_(
                "Installs and launches Grokitach's S.T.A.L.K.E.R. G.A.M.M.A. "
                "modpack on Linux: Anomaly, Mod Organizer 2 under Proton, "
                "shared prefix, and incremental updates."
            ),
            website="https://github.com/Fleorens/stalker-gamma-linux",
            issue_url="https://github.com/Fleorens/stalker-gamma-linux/issues",
            license_type=Gtk.License.GPL_3_0,
        )
        about.present(self)

    def _on_uninstall(self, _action: Gio.SimpleAction, _param: None) -> None:
        """Confirme avant de retirer, en montrant le plan exact.

        Réutilise la séparation plan/application de `uninstall` : on affiche
        littéralement ce qui va disparaître plutôt qu'un « êtes-vous sûr ? »
        aveugle. Les données de jeu ne sont jamais concernées ici — c'est
        `stalker-gamma-linux uninstall --game-data`, et il faut le demander.
        """
        plan = uninstall.build_plan(self._preferences.install_path)
        if plan.is_empty:
            self._show_toast(_("Nothing to remove — already clean."))
            return

        dialog = Adw.AlertDialog(
            heading=_("Remove GAMMA Linux Launcher?"),
            body=uninstall.format_plan(plan)
            + "\n\n"
            + _("Your game install is NOT affected: {root}").format(
                root=self._preferences.install_path
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_uninstall_response, plan)
        dialog.present(self)

    def _on_uninstall_response(
        self, _dialog: Adw.AlertDialog, response: str, plan: uninstall.UninstallPlan
    ) -> None:
        if response != "remove":
            return
        removed = uninstall.apply_plan(plan)
        self._show_toast(
            _("{count} item(s) removed. Close the window to finish.").format(count=len(removed))
        )

    # -- tâches longues (hors fil GTK) ----------------------------------

    def _start_install(self) -> None:
        self._push_job(
            jobs.install(
                self._preferences.install_path,
                shortcut=self._preferences.create_direct_shortcut,
                steam=self._preferences.add_to_steam,
                proton_release=self._preferences.proton_release,
            )
        )

    def _start_update(self) -> None:
        self._push_job(jobs.update(self._preferences.install_path))

    def _start_verify(self, repair: bool) -> None:
        self._push_job(jobs.verify(self._preferences.install_path, repair=repair))

    def _start_backup(self) -> None:
        self._push_job(jobs.backup(self._preferences.install_path))

    def _start_restore(self, identifier: str) -> None:
        self._push_job(jobs.restore(identifier, self._preferences.install_path))

    def _start_play(self) -> None:
        self._played_this_session = True
        self._push_job(
            jobs.play(self._preferences.install_path, performance=self._preferences.performance)
        )

    def _start_mo2(self) -> None:
        self._push_job(jobs.mod_organizer(self._preferences.install_path))

    def _start_postmortem(self) -> None:
        """Analyse la dernière session, hors du fil GTK, et présente le verdict.

        Rien n'est décidé ici : `postmortem.build_postmortem` est exactement ce
        que fait `stalker-gamma-linux postmortem`. La lecture est bornée (deux
        extrémités du journal, quelques `stat` sur `mods/`), mais elle touche le
        disque — donc un thread, comme l'analyse d'environnement.
        """
        target = self._preferences.install_path

        def worker() -> None:
            result = build_postmortem(target)
            GLib.idle_add(self._present_postmortem, result)

        self._show_toast(_("Reading the last session…"))
        threading.Thread(target=worker, daemon=True).start()

    def _present_postmortem(self, postmortem: Postmortem) -> bool:
        details = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        details.get_buffer().set_text(format_postmortem(postmortem))
        # La trace fait des lignes très longues : on défile plutôt que de les
        # replier, une trace recoupée n'étant plus recopiable dans une issue.
        scroller = Gtk.ScrolledWindow(min_content_height=320, min_content_width=520)
        scroller.set_child(details)
        scroller.add_css_class("console")

        dialog = Adw.AlertDialog(heading=_("Last game session"))
        dialog.set_extra_child(scroller)
        dialog.add_response("close", _("Close"))
        dialog.present(self)
        return False

    def _push_job(self, job: jobs.Job) -> None:
        page = ProgressPage(
            title=job.title,
            task=BackgroundTask(job.run),
            cancellable=job.cancellable,
            on_finished=self._on_task_finished,
            phase_labels=job.phase_labels,
        )
        self._nav_view.push(page)

    def _on_task_finished(self, exit_code: int) -> None:
        self._refresh_status()
        if exit_code == 0:
            self._show_toast(_("Done."))
        elif exit_code == CANCELLED_EXIT_CODE:
            self._show_toast(_("Cancelled — resuming will continue where it left off."))
        else:
            self._show_toast(_("Failed — see the console and the log."))
