"""Vue progression : timeline de phases, fraction réelle, console, annulation.

Deux rendus selon la tâche :
- pipeline (install/update) : `phase_labels` fourni → timeline d'étapes avec
  états (en cours/fait/déjà fait/échec) et barre de progression déterminée,
  pilotées par le modèle immuable `gui.phases.Timeline` ;
- session (jouer/MO2) : pas de labels → barre en pulsation, console seule.

Pure wiring GTK au-dessus de `gui.worker.BackgroundTask` : ce module ne
connaît rien des opérations elles-mêmes, il rend les événements de la queue.

Le rendu obéit à deux règles, toutes deux imposées par la durée réelle d'une
installation (plusieurs heures, ~400 mods, des rafales de centaines de lignes) :
le drainage de la queue est intégral mais le **rendu** est plafonné par tick
(`_POLL_EVENT_BUDGET`), pour que le fil principal reste disponible — le bouton
« Annuler » est le seul contrôle de cet écran ; et la console est **bornée**
(`_LOG_MAX_LINES`), le journal complet restant sur disque.
"""

from __future__ import annotations

import queue
import time
from collections import deque
from collections.abc import Callable, Sequence
from itertools import islice

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

from stalker_gamma_linux.exit_codes import CANCELLED_EXIT_CODE  # noqa: E402
from stalker_gamma_linux.gui import phases  # noqa: E402
from stalker_gamma_linux.gui.format import first_url, format_duration  # noqa: E402
from stalker_gamma_linux.gui.windows.background import content_backdrop  # noqa: E402
from stalker_gamma_linux.gui.worker import (  # noqa: E402
    BackgroundTask,
    DoneEvent,
    FailedEvent,
    ReporterEvent,
    WorkerEvent,
)
from stalker_gamma_linux.i18n import _  # noqa: E402

_POLL_INTERVAL_MS = 80
_PULSE_INTERVAL_MS = 200
_CLOCK_INTERVAL_MS = 1000

# Nombre maximal d'événements *rendus* par tick de `_on_poll`.
#
# gamma-launcher sort par rafales : des centaines de lignes d'un coup, plusieurs
# fois par mod. Sans plafond, tout le paquet était rendu dans un seul tour de
# boucle principale, et pendant ce temps rien d'autre ne passait — ni le
# repeint, ni le clic sur « Annuler », seul contrôle de cet écran.
#
# 200 à 80 ms font 2500 lignes/s, très au-dessus du débit réel du moteur : en
# marche normale la queue est vidée en entier à chaque tick et rien n'est
# différé. Pendant une rafale, le tick coûte ~5 ms (mesuré, timeline de quatre
# phases repliée et redessinée à chaque événement) sur les 80 disponibles : la
# boucle principale garde 90 % de son temps pour repeindre et pour le clic. Le
# retard est repris aux ticks suivants, sans perdre un seul événement.
_POLL_EVENT_BUDGET = 200

# Plafond de la console, en lignes. Une install complète (~400 mods, plusieurs
# heures) pousse des centaines de milliers de lignes : un `Gtk.TextBuffer` non
# borné les garde toutes, avec la mise en forme de chacune. 5000 lignes font une
# cinquantaine d'écrans de défilement — bien plus que ce qu'on remonte pour
# comprendre ce qui vient d'échouer. La CLI borne déjà ses tampons de la même
# façon (`deque(maxlen=...)` dans `engine/process.py` et `prefix/process.py`).
#
# La troncature ne concerne QUE l'affichage : le journal complet reste écrit sur
# disque par `QueueReporter`, qui double chaque événement vers le journal
# applicatif sous `~/.local/state/` (cf. gui/worker.py).
_LOG_MAX_LINES = 5000
# Marge avant de couper : on supprime par blocs plutôt qu'à chaque ligne, une
# suppression dans un `TextBuffer` invalidant la géométrie du TextView.
_LOG_TRIM_CHUNK = 500

# Géométrie du rail de la timeline : largeur de la colonne d'icônes, et demi-
# hauteur d'une icône — le rail s'arrête au centre des pastilles extrêmes
# plutôt que de dépasser en haut et en bas.
_RAIL_OFFSET = 9
_RAIL_INSET = 11

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
        # Voir `doctor_view` : `Adw.Spinner` exige libadwaita 1.6, Ubuntu 24.04 a 1.5.
        self._spinner = Gtk.Spinner(spinning=True)
        self._icon = Gtk.Image()
        self._stack = Gtk.Stack()
        self._stack.add_named(self._icon, "icon")
        self._stack.add_named(self._spinner, "spinner")
        self._stack.set_valign(Gtk.Align.START)
        # La pastille est opaque : c'est elle qui « coupe » le rail vertical qui
        # passe derrière, et donne à la colonne son allure de chemin jalonné.
        self._stack.add_css_class("phase-node")
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
        self._timeline = phases.Timeline.from_labels(tuple(phase_labels)) if phase_labels else None
        self._phase_rows: list[_PhaseRow] = []
        self._error_message = ""
        self._error_url: str | None = None
        # Événements sortis de la queue mais pas encore rendus : le drainage
        # n'est pas plafonné (il ne coûte rien), le rendu l'est.
        self._backlog: deque[WorkerEvent] = deque()
        self._task_end: DoneEvent | FailedEvent | None = None
        self._scroll_pending = False

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{side}")(26)

        content.append(self._build_headline())

        # Le remède actionnable partait dans la console, mêlé à des centaines de
        # lignes de sortie moteur : personne ne le lisait. Il a maintenant sa
        # place propre, en haut, avec un bouton pour le copier.
        content.append(self._build_error_banner())

        if self._timeline is not None:
            content.append(self._section_label(_("Steps")))
            content.append(self._build_timeline_card())

        content.append(self._section_label(_("Engine log")))
        content.append(self._build_console())

        self._cancel_button = Gtk.Button(label=_("Cancel"))
        self._cancel_button.add_css_class("destructive-action")
        self._cancel_button.add_css_class("pill")
        self._cancel_button.set_visible(cancellable)
        self._cancel_button.set_halign(Gtk.Align.END)
        self._cancel_button.connect("clicked", self._on_cancel_clicked)
        content.append(self._cancel_button)

        clamp = Adw.Clamp(child=content, maximum_size=760)
        scroller = Gtk.ScrolledWindow(child=clamp, vexpand=True)

        header_bar = Adw.HeaderBar()
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(scroller)
        toolbar_view.add_css_class("over-artwork")

        super().__init__(title=title, child=content_backdrop(toolbar_view), can_pop=False)

        self._render_timeline()
        self._task.start()
        if self._timeline is None:
            GLib.timeout_add(_PULSE_INTERVAL_MS, self._on_pulse)
        GLib.timeout_add(_POLL_INTERVAL_MS, self._on_poll)
        GLib.timeout_add(_CLOCK_INTERVAL_MS, self._on_clock)

    # -- construction ------------------------------------------------------

    @staticmethod
    def _section_label(text: str) -> Gtk.Widget:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("section-label")
        label.set_margin_top(4)
        return label

    def _build_headline(self) -> Gtk.Widget:
        """Étape en cours, pourcentage, temps écoulé, barre — en un bloc.

        Ces quatre informations répondent à la même question (« où en est-on ? »)
        et étaient dispersées de part et d'autre de la timeline. Réunies, elles
        se lisent sans balayer l'écran, et le pourcentage peut enfin être écrit
        assez gros pour se voir depuis un canapé — c'est aussi une install qu'on
        surveille du coin de l'œil pendant des heures.
        """
        self._status_label = Gtk.Label(label=_("Preparing…"), xalign=0, wrap=True, hexpand=True)
        self._status_label.add_css_class("title-3")
        self._elapsed_label = Gtk.Label(label="", xalign=1)
        self._elapsed_label.add_css_class("elapsed")
        self._percent_label = Gtk.Label(xalign=1)
        self._percent_label.add_css_class("progress-percent")

        readout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.CENTER)
        readout.append(self._percent_label)
        readout.append(self._elapsed_label)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        top.append(self._status_label)
        top.append(readout)

        self._progress_bar = Gtk.ProgressBar(hexpand=True)

        headline = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        headline.append(top)
        headline.append(self._progress_bar)
        return headline

    def _build_timeline_card(self) -> Gtk.Widget:
        """Les étapes, jalonnées le long d'un rail vertical.

        Le rail est posé *sous* les rangées, dans un `Gtk.Overlay` dont l'enfant
        principal ne sert qu'à le porter : les enfants d'overlay se dessinent
        au-dessus de l'enfant principal, donc l'ordre inverse ferait passer le
        trait par-dessus les pastilles. `set_measure_overlay` est nécessaire
        pour que la hauteur vienne des rangées et non du rail, qui n'en a pas.
        """
        assert self._timeline is not None
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for phase in self._timeline.phases:
            row = _PhaseRow(phase.label)
            self._phase_rows.append(row)
            rows.append(row)

        self._rail = Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.FILL)
        self._rail.add_css_class("phase-rail")
        self._rail.set_margin_start(_RAIL_OFFSET)
        self._rail.set_margin_top(_RAIL_INSET)
        self._rail.set_margin_bottom(_RAIL_INSET)

        rail_layer = Gtk.Box()
        rail_layer.append(self._rail)

        stack = Gtk.Overlay()
        stack.set_child(rail_layer)
        stack.add_overlay(rows)
        stack.set_measure_overlay(rows, True)
        for side in ("top", "bottom", "start", "end"):
            getattr(stack, f"set_margin_{side}")(18)

        card = Gtk.Box()
        card.add_css_class("glass")
        card.append(stack)
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
        scroller = Gtk.ScrolledWindow(child=self._log_view, min_content_height=170, vexpand=True)
        scroller.add_css_class("console")
        # `scroll_to_mark` seul ne suffit pas à rester collé au bas : GTK valide
        # la hauteur des lignes par petits paquets, bien après l'insertion, et
        # `upper` continue donc de grandir une fois le défilement effectué — la
        # console s'arrêtait plusieurs dizaines de lignes trop haut (déjà le cas
        # avec le défilement par ligne, en pire : ~255 lignes de retard mesurées).
        # On recale donc la vue à chaque révision de la géométrie : c'est le même
        # comportement perçu qu'avant — la console suit la dernière ligne — mais
        # au rythme de GTK, pas à celui de la rafale.
        scroller.get_vadjustment().connect("changed", self._pin_console_to_bottom)
        return scroller

    def _pin_console_to_bottom(self, adjustment: Gtk.Adjustment) -> None:
        """Recale la console sur sa dernière ligne, à chaque révision de géométrie.

        Deux gestes, et les deux sont nécessaires :

        - `scroll_to_mark` passe par la **vue**, qui met alors son décalage
          interne et son ajustement d'accord. Sans lui, un tampon plus court que
          la fenêtre restait défilé *sous* son contenu — l'ajustement annonçait
          0, la vue affichait à partir de 96 px, et la console paraissait vide
          alors qu'elle contenait tout (constaté sur une console redimensionnée
          par la refonte : le cas ne se produisait pas tant que le tampon
          dépassait toujours la hauteur visible) ;
        - le calage exact de l'ajustement ensuite, parce que `scroll_to_mark`
          se contente de rendre la marque *visible* : sur un journal de
          plusieurs milliers de lignes, ça laisse la dernière à ras du bord.

        Rien à faire quand tout tient dans la vue : `bottom` vaut alors le bas
        de la plage, et forcer une valeur ne ferait que rouvrir le décalage.
        """
        self._log_view.scroll_to_mark(self._log_end_mark, 0.0, False, 0.0, 1.0)
        bottom = adjustment.get_upper() - adjustment.get_page_size()
        if bottom > adjustment.get_lower() and adjustment.get_value() != bottom:
            adjustment.set_value(bottom)

    # -- événements ----------------------------------------------------------

    def _on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self._status_label.set_label(_("Cancelling…"))
        self._cancel_button.set_sensitive(False)
        self._task.cancel()

    def _append_log(self, message: str) -> None:
        # Pas de `scroll_to_mark` ici : défiler à chaque ligne force GTK à
        # revalider la géométrie du TextView à chaque insertion, et une rafale
        # en compte des centaines. Le défilement a lieu une seule fois par tick,
        # après le drainage (`_scroll_console`) — la console suit donc toujours
        # la dernière ligne, en une validation au lieu de N.
        self._log_buffer.insert(self._log_buffer.get_end_iter(), f"{message}\n")
        self._scroll_pending = True
        self._trim_log()

    def _trim_log(self) -> None:
        """Borne la console : au-delà du plafond, les plus vieilles lignes partent.

        Ne concerne QUE l'affichage — le journal complet reste sur disque (cf.
        `_LOG_MAX_LINES`). Sans ça, le tampon d'une install complète atteignait
        des centaines de milliers de lignes, jamais relues et jamais libérées.
        """
        line_count = self._log_buffer.get_line_count()
        if line_count <= _LOG_MAX_LINES + _LOG_TRIM_CHUNK:
            return
        found, cut = self._log_buffer.get_iter_at_line(line_count - _LOG_MAX_LINES)
        if not found:
            return
        self._log_buffer.delete(self._log_buffer.get_start_iter(), cut)

    def _scroll_console(self) -> None:
        """Suit la dernière ligne — une fois par tick, jamais une fois par ligne."""
        if not self._scroll_pending:
            return
        self._scroll_pending = False
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
        self._drain_events()
        if self._task_end is not None:
            self._flush_final()
        else:
            # Budget : le reste du retard attend le tick suivant. Rien n'est
            # perdu, les événements non rendus restent dans `_backlog`.
            for _ in range(min(_POLL_EVENT_BUDGET, len(self._backlog))):
                self._handle_event(self._backlog.popleft())
        self._scroll_console()
        return not self._finished

    def _drain_events(self) -> None:
        """Vide la queue vers `_backlog`, sans rien afficher.

        `get_nowait` ne coûte rien (aucun travail GTK) : on prend TOUT à chaque
        tick. C'est ce qui permet de repérer un `DoneEvent`/`FailedEvent` arrivé
        derrière une rafale au tick même où il est publié, au lieu d'attendre
        les dizaines de ticks nécessaires à l'affichage du retard.
        """
        while True:
            try:
                event = self._task.events.get_nowait()
            except queue.Empty:
                return
            if isinstance(event, DoneEvent | FailedEvent):
                self._task_end = event
            else:
                self._backlog.append(event)

    def _flush_final(self) -> None:
        """Solde le retard puis clôt la tâche, dans le tick où la fin est vue.

        Plus rien n'arrivera après la fin de tâche, et la faire attendre derrière
        une rafale laisserait la fenêtre annoncer « en cours » alors que tout est
        fini. Le retard est donc soldé d'un coup, mais en deux temps pour ne pas
        payer l'affichage de milliers de lignes :

        - l'ÉTAT (timeline, statut, bandeau) est replié sur *tous* les événements
          en attente — aucun n'est ignoré, en particulier l'`error` qui porte le
          remède et qui serait sinon perdu de vue ;
        - seules les lignes encore visibles après troncature sont réellement
          insérées : les plus anciennes, `_trim_log` les supprimerait dans la
          foulée, et le journal complet est de toute façon sur disque.
        """
        assert self._task_end is not None
        for event in self._backlog:
            if isinstance(event, ReporterEvent):
                self._apply_reporter_event(event)
        self._render_timeline()
        skipped = max(0, len(self._backlog) - _LOG_MAX_LINES)
        for event in islice(self._backlog, skipped, None):
            if isinstance(event, ReporterEvent):
                self._log_reporter_event(event)
        self._backlog.clear()
        end = self._task_end
        self._task_end = None
        self._handle_event(end)

    def _handle_event(self, event: WorkerEvent) -> None:
        if isinstance(event, ReporterEvent):
            self._handle_reporter_event(event)
        elif isinstance(event, DoneEvent):
            self._handle_done(event.exit_code)
        elif isinstance(event, FailedEvent):
            message = _("Unexpected error: {error}").format(error=event.error)
            self._append_log(message)
            self._show_error(message, _("Please attach a diagnostic report to your issue."))
            self._handle_done(1)

    def _handle_reporter_event(self, event: ReporterEvent) -> None:
        self._apply_reporter_event(event)
        self._render_timeline()
        self._log_reporter_event(event)

    def _apply_reporter_event(self, event: ReporterEvent) -> None:
        """État de l'écran (timeline, titre, bandeau) — sans écrire en console.

        Séparé de l'écriture en console pour que `_flush_final` puisse replier
        l'état d'une rafale entière sans en payer le rendu ligne à ligne.
        """
        if self._timeline is not None:
            self._timeline = self._timeline.apply(event)
        if event.kind in ("step", "skip"):
            self._status_label.set_label(event.message)
        elif event.kind == "error":
            self._show_error(event.message, event.hint)

    def _log_reporter_event(self, event: ReporterEvent) -> None:
        if event.kind in ("step", "skip"):
            self._append_log(f"[{event.index}] {event.message}" if event.index else event.message)
        elif event.kind == "error":
            self._append_log(_("Error: {message}").format(message=event.message))
            if event.hint is not None:
                self._append_log(f"→ {event.hint}")
        else:
            self._append_log(event.message)

    def _build_error_banner(self) -> Gtk.Widget:
        self._error_title = Gtk.Label(xalign=0, wrap=True)
        self._error_title.add_css_class("error-banner-title")
        self._error_hint = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self._error_hint.add_css_class("error-banner-hint")

        self._error_copy = Gtk.Button(
            label=_("Copy"), valign=Gtk.Align.CENTER, halign=Gtk.Align.END
        )
        self._error_copy.add_css_class("flat")
        self._error_copy.connect("clicked", self._on_copy_error)

        # Certains remèdes commencent par « ouvre cette page » (mur ModDB :
        # télécharger le fichier à la main). Recopier une URL longue depuis un
        # bandeau, à la souris, est exactement le genre de friction qui fait
        # abandonner — d'où le bouton, affiché seulement quand il y a une URL.
        self._error_open = Gtk.Button(
            label=_("Open page"), valign=Gtk.Align.CENTER, halign=Gtk.Align.END
        )
        self._error_open.add_css_class("flat")
        self._error_open.connect("clicked", self._on_open_error_url)
        self._error_open.set_visible(False)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        text_box.append(self._error_title)
        text_box.append(self._error_hint)

        buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        buttons.append(self._error_copy)
        buttons.append(self._error_open)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(14)
        box.append(text_box)
        box.append(buttons)

        self._error_banner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._error_banner.add_css_class("error-banner")
        self._error_banner.append(box)
        self._error_banner.set_visible(False)
        return self._error_banner

    def _show_error(self, message: str, hint: str | None) -> None:
        self._error_message = message if hint is None else f"{message}\n\n{hint}"
        self._error_title.set_label(message)
        self._error_hint.set_label(hint or "")
        self._error_hint.set_visible(hint is not None)
        self._error_url = first_url(self._error_message)
        self._error_open.set_visible(self._error_url is not None)
        self._error_banner.set_visible(True)

    def _on_copy_error(self, _button: Gtk.Button) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        display.get_clipboard().set(self._error_message)
        self._error_copy.set_label(_("Copied"))

    def _on_open_error_url(self, _button: Gtk.Button) -> None:
        if self._error_url is None:
            return
        # `Gtk.UriLauncher` passe par le portail quand il y en a un et retombe
        # sur le navigateur par défaut sinon — rien à faire du résultat : si
        # l'ouverture échoue, l'URL reste lisible et copiable dans le bandeau.
        root = self.get_root()
        parent = root if isinstance(root, Gtk.Window) else None
        Gtk.UriLauncher(uri=self._error_url).launch(parent, None, None)

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
            self._status_label.set_label(_("Failed."))
        self._on_finished(exit_code)
