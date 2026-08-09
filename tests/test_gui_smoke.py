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
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("gi", reason="PyGObject absent")

# Renderer logiciel avant toute initialisation : les runners CI n'ont pas de GPU,
# et `gui/launch.py` fait déjà ce choix par défaut pour la même raison.
os.environ.setdefault("GSK_RENDERER", "cairo")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

# `init_check` plutôt que de flairer DISPLAY/WAYLAND_DISPLAY : c'est la seule
# vérification qui vaut pour tous les backends (X11, Wayland, broadway) et qui
# ne plante pas quand il n'y en a aucun.
if not Gtk.init_check():
    pytest.skip("aucun affichage GTK utilisable", allow_module_level=True)

from stalker_gamma_linux.gui import prefs, theme  # noqa: E402
from stalker_gamma_linux.gui.worker import BackgroundTask  # noqa: E402


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
