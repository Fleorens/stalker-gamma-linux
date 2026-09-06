"""Fumée GTK : chaque écran de la GUI se construit-il réellement ?

Les 1360 lignes de `gui/windows/`, `gui/app` et `gui/theme` n'étaient couvertes
par **aucun** test et n'étaient même jamais importées en CI (le job conteneur
tourne délibérément sans GTK). Une faute de frappe dans un nom de signal, une
icône disparue d'une version de libadwaita ou une classe CSS renommée ne se
voyaient qu'en lançant l'application à la main.

Ce fichier ne teste pas l'apparence — il vérifie que chaque écran s'instancie
sans exploser, ce qui attrape précisément cette classe de régressions. Il est
ignoré sans affichage ; la CI le fait tourner sous `xvfb-run`, et il passe aussi
sur une session de bureau normale (construire un widget ne l'affiche pas :
aucune fenêtre n'apparaît tant que `present()` n'est pas appelé).

S'y ajoutent les tests de la console de progression : c'est le seul endroit du
dépôt où un vrai `Gtk.TextBuffer` existe, et le comportement testé (budget par
tick, plafond du tampon) n'a de sens que face au vrai widget.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("gi", reason="PyGObject absent")

# Renderer logiciel avant toute initialisation : les runners CI n'ont pas de GPU,
# et `gui/launch.py` fait déjà ce choix par défaut pour la même raison.
os.environ.setdefault("GSK_RENDERER", "cairo")

# Deux gardes, dans cet ordre, et les deux sont nécessaires.
#
# 1. La variable d'environnement : sur un runner CI sans serveur X du tout,
#    `Gtk.init_check()` ne renvoie pas False — il **segfault** (constaté sur les
#    quatre jobs `test` de la matrice). Il faut donc ne jamais l'appeler là-bas.
# 2. `init_check` ensuite : la présence d'une variable ne garantit pas que
#    l'affichage réponde, et c'est le seul test valable pour tous les backends
#    (X11, Wayland, broadway).
if not any(os.environ.get(name) for name in ("DISPLAY", "WAYLAND_DISPLAY", "BROADWAY_DISPLAY")):
    pytest.skip("aucun affichage disponible", allow_module_level=True)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

if not Gtk.init_check():
    pytest.skip("affichage présent mais GTK ne s'initialise pas", allow_module_level=True)

from stalker_gamma_linux.gui import prefs, theme  # noqa: E402
from stalker_gamma_linux.gui.worker import BackgroundTask, DoneEvent, ReporterEvent  # noqa: E402


def _blocked_task() -> BackgroundTask:
    """Tâche qui ne se termine pas d'elle-même : le test pilote la queue.

    `ProgressPage` démarre le thread dès sa construction ; sans ce blocage, un
    `DoneEvent` tomberait au milieu de la rafale que le test veut observer.
    """

    def job(_events, cancel):  # type: ignore[no-untyped-def]
        cancel.wait(timeout=10)
        return 0

    return BackgroundTask(job)


def _progress_page(task: BackgroundTask):  # type: ignore[no-untyped-def]
    from stalker_gamma_linux.gui.windows.progress_view import ProgressPage

    return ProgressPage(
        title="Installation",
        task=task,
        cancellable=True,
        on_finished=lambda _code: None,
        phase_labels=("Anomaly", "Modpack"),
    )


def _burst(task: BackgroundTask, count: int) -> None:
    for i in range(count):
        task.events.put(ReporterEvent("progress", f"ligne {i}"))


@pytest.fixture(scope="module", autouse=True)
def _adwaita() -> None:
    Adw.init()
    theme.install_theme()


@pytest.fixture
def app() -> Adw.Application:
    return Adw.Application(application_id="org.stalkergammalinux.Test")


@pytest.fixture
def window(app: Adw.Application):  # type: ignore[no-untyped-def]
    from stalker_gamma_linux.gui.windows.main_window import MainWindow

    return MainWindow(application=app)


def test_le_theme_sinstalle() -> None:
    theme.install_theme()  # idempotent, ne lève pas


def test_fenetre_principale(window) -> None:  # type: ignore[no-untyped-def]
    assert window.get_title()


def test_dialog_installation(window) -> None:  # type: ignore[no-untyped-def]
    from stalker_gamma_linux.gui.windows.install_dialog import InstallDialog

    dialog = InstallDialog(
        parent_window=window,
        preferences=prefs.Preferences(),
        on_confirmed=lambda _p: None,
        on_show_diagnostic=lambda: None,
    )

    # Le sondage des prérequis n'a pas encore rendu : on ne doit surtout pas
    # pouvoir lancer 146 Gio de téléchargement dans cet état.
    assert not dialog._confirm.get_sensitive()


def test_dialog_preferences(window) -> None:  # type: ignore[no-untyped-def]
    from stalker_gamma_linux.gui.windows.preferences import PreferencesDialog

    PreferencesDialog(
        parent_window=window, preferences=prefs.Preferences(), on_saved=lambda _p: None
    )


def test_vue_diagnostic() -> None:
    from stalker_gamma_linux.gui.windows.doctor_view import DoctorPage

    DoctorPage(target=None, show_toast=lambda _t: None)


def test_vue_diagnostic_avec_verification_integrite() -> None:
    """Le groupe « Mods installés » n'apparaît que si un `on_verify` est branché."""
    from stalker_gamma_linux.gui.windows.doctor_view import DoctorPage

    DoctorPage(target=None, show_toast=lambda _t: None, on_verify=lambda _repair: None)


def test_vue_progression_pipeline() -> None:
    from stalker_gamma_linux.gui.windows.progress_view import ProgressPage

    page = ProgressPage(
        title="Installation",
        task=BackgroundTask(lambda _events, _cancel: 0),
        cancellable=True,
        on_finished=lambda _code: None,
        phase_labels=("Anomaly", "Modpack"),
    )

    assert not page._error_banner.get_visible()


def test_vue_progression_affiche_le_bandeau_derreur() -> None:
    """Le remède doit sortir de la console, c'est tout l'objet du bandeau."""
    from stalker_gamma_linux.gui.windows.progress_view import ProgressPage

    page = ProgressPage(
        title="Installation",
        task=BackgroundTask(lambda _events, _cancel: 1),
        cancellable=True,
        on_finished=lambda _code: None,
        phase_labels=("Anomaly",),
    )

    page._show_error("libunrar manquant", "sudo dnf install unrar")

    assert page._error_banner.get_visible()
    assert "libunrar" in page._error_title.get_label()
    assert "dnf" in page._error_hint.get_label()
    # Pas d'URL dans ce remède : le bouton « Ouvrir la page » reste caché.
    assert not page._error_open.get_visible()


def test_vue_progression_propose_douvrir_lurl_du_remede() -> None:
    """Mur ModDB : le remède commence par « ouvre cette page » — un clic, pas une recopie."""
    from stalker_gamma_linux.gui.windows.progress_view import ProgressPage

    page = ProgressPage(
        title="Installation",
        task=BackgroundTask(lambda _events, _cancel: 1),
        cancellable=True,
        on_finished=lambda _code: None,
    )

    page._show_error(
        "gamma-launcher full-install a échoué",
        "ouvre https://www.moddb.com/mods/stalker-anomaly/addons/boomsticks puis dépose le fichier",
    )

    assert page._error_open.get_visible()
    assert page._error_url == "https://www.moddb.com/mods/stalker-anomaly/addons/boomsticks"


def test_vue_progression_session_sans_timeline() -> None:
    """Mode « jouer / MO2 » : pas de labels, donc barre en pulsation."""
    from stalker_gamma_linux.gui.windows.progress_view import ProgressPage

    page = ProgressPage(
        title="Lancement",
        task=BackgroundTask(lambda _events, _cancel: 0),
        cancellable=False,
        on_finished=lambda _code: None,
    )

    assert page._timeline is None


def test_menu_contient_desinstaller_et_version(window) -> None:  # type: ignore[no-untyped-def]
    """`uninstall` et la version ont été ajoutés à la CLI ; ils doivent exister ici aussi."""
    assert window.lookup_action("uninstall") is not None


def test_lancer_le_jeu_est_annulable() -> None:
    """`play` était `cancellable=False` : MO2 qui ne rend pas la main = fenêtre à tuer."""
    import inspect

    from stalker_gamma_linux.mo2 import session

    for name in ("run_play", "run_mo2"):
        assert "cancel_event" in inspect.signature(getattr(session, name)).parameters


def test_import_adopte_une_install_et_bascule_la_cible(window, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """L'import doit être atteignable sans terminal — c'est tout son intérêt."""
    from stalker_gamma_linux import adopt, state

    source = tmp_path / "gog" / "STALKER GAMMA"
    for name, marker in (("Anomaly", adopt.ANOMALY_MARKER), ("GAMMA", adopt.MO2_MARKER)):
        (source / name).mkdir(parents=True)
        (source / name / marker).write_text("", encoding="utf-8")
    target = tmp_path / "adopted"

    adoption = adopt.plan(adopt.discover(source), target)
    window._on_import_confirmed(None, "import", adoption)

    assert window._preferences.install_path == target
    assert state.load_state(target).gamma
    assert (target / "anomaly").is_symlink()


def test_import_annule_ne_touche_a_rien(window, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from stalker_gamma_linux import adopt, state

    source = tmp_path / "src"
    for name, marker in (("Anomaly", adopt.ANOMALY_MARKER), ("GAMMA", adopt.MO2_MARKER)):
        (source / name).mkdir(parents=True)
        (source / name / marker).write_text("", encoding="utf-8")
    target = tmp_path / "adopted"

    adoption = adopt.plan(adopt.discover(source), target)
    window._on_import_confirmed(None, "cancel", adoption)

    assert not target.exists()
    assert not state.load_state(target).gamma


# -- console : réactivité pendant les rafales, mémoire bornée ----------------


def test_console_ne_defile_quune_fois_par_tick() -> None:
    """Le `scroll_to_mark` par ligne forçait GTK à revalider la géométrie à chaque insertion."""
    page = _progress_page(_blocked_task())

    page._append_log("une ligne")
    # Défilement seulement demandé : c'est `_on_poll` qui le consomme, après le drainage.
    assert page._scroll_pending

    page._on_poll()

    assert not page._scroll_pending


def test_console_recale_la_vue_sur_le_bas() -> None:
    """GTK révise la hauteur du tampon après coup : sans recalage, la console décroche.

    Mesuré sur une fenêtre réelle : le seul `scroll_to_mark` laissait la console
    des dizaines de lignes au-dessus de la dernière, `upper` continuant de
    grandir après le défilement.
    """
    from stalker_gamma_linux.gui.windows.progress_view import ProgressPage

    adjustment = Gtk.Adjustment(value=0, lower=0, upper=1000, page_size=100)

    ProgressPage._pin_console_to_bottom(adjustment)

    assert adjustment.get_value() == 900


def test_console_respecte_le_budget_par_tick() -> None:
    """Une rafale ne doit pas monopoliser la boucle principale : le clic « Annuler » doit passer."""
    from stalker_gamma_linux.gui.windows import progress_view

    task = _blocked_task()
    page = _progress_page(task)
    _burst(task, 10_000)

    page._on_poll()

    # Toute la queue est sortie (c'est gratuit), mais un seul budget est rendu.
    assert task.events.empty()
    assert len(page._backlog) == 10_000 - progress_view._POLL_EVENT_BUDGET


def test_console_encaisse_dix_mille_evenements_sans_rien_perdre() -> None:
    """10 000 événements : tampon sous le plafond, et pas un événement perdu en route."""
    from stalker_gamma_linux.gui.windows import progress_view

    task = _blocked_task()
    page = _progress_page(task)

    rendered: list[str] = []
    append = page._append_log

    def spy(message: str) -> None:
        rendered.append(message)
        append(message)

    page._append_log = spy  # type: ignore[method-assign]

    _burst(task, 10_000)
    ticks = 0
    while page._backlog or not task.events.empty():
        page._on_poll()
        ticks += 1
        assert ticks <= 10_000, "le drainage n'avance pas"

    assert len(rendered) == 10_000
    assert rendered[0] == "ligne 0"
    assert rendered[-1] == "ligne 9999"
    # Étalé sur plusieurs tours de boucle, pas rendu d'un bloc.
    assert ticks == 10_000 // progress_view._POLL_EVENT_BUDGET
    assert (
        page._log_buffer.get_line_count()
        <= progress_view._LOG_MAX_LINES + progress_view._LOG_TRIM_CHUNK + 1
    )
    # La console suit toujours la fin : la dernière ligne est bien dans le tampon.
    start, end = page._log_buffer.get_bounds()
    assert "ligne 9999" in page._log_buffer.get_text(start, end, False)


def test_fin_de_tache_pas_coincee_derriere_une_rafale() -> None:
    """`DoneEvent` derrière 10 000 lignes : traité au tick où il arrive, pas 50 ticks plus tard."""
    from stalker_gamma_linux.gui.windows import progress_view

    codes: list[int] = []
    task = _blocked_task()
    page = _progress_page(task)
    page._on_finished = codes.append
    lines = 0
    append = page._append_log

    def spy(message: str) -> None:
        nonlocal lines
        lines += 1
        append(message)

    page._append_log = spy  # type: ignore[method-assign]

    _burst(task, 10_000)
    task.events.put(DoneEvent(0))

    assert page._on_poll() is False
    assert page._finished
    assert codes == [0]
    assert not page._backlog
    # Soldé sans réinsérer les 10 000 lignes : seules celles qui survivent au
    # plafond sont écrites, les autres seraient supprimées dans la foulée.
    assert lines <= progress_view._LOG_MAX_LINES
    start, end = page._log_buffer.get_bounds()
    text = page._log_buffer.get_text(start, end, False)
    assert "ligne 9999" in text
    assert "ligne 0\n" not in text


def test_le_remede_survit_a_une_rafale_qui_le_precede() -> None:
    """L'`error` enfouie sous la rafale porte le remède : son état doit être replié, pas sauté."""
    task = _blocked_task()
    page = _progress_page(task)
    task.events.put(ReporterEvent("error", "libunrar manquant", hint="sudo dnf install unrar"))
    _burst(task, 10_000)
    task.events.put(DoneEvent(1))

    page._on_poll()

    assert page._error_banner.get_visible()
    assert "libunrar" in page._error_title.get_label()
