#!/usr/bin/env python3
"""Régénère les captures d'écran de `docs/screenshots/`.

Pourquoi un script : ces images sont la première chose que voit quelqu'un qui
découvre le dépôt, et elles se démodent au premier changement d'interface. Les
refaire à la main, c'est quatre captures à recadrer, avec un chemin
d'installation personnel affiché en clair dedans.

Ce que fait le script à la place :

- il installe un **environnement de démonstration** jetable (XDG redirigé vers
  un dossier temporaire, install fictive sous `/home/stalker/Games/GAMMA`), si
  bien qu'aucune capture ne publie de chemin réel ;
- il construit chaque écran pour de vrai, puis le rend **hors écran** via
  `Gtk.WidgetPaintable` + `Gsk.CairoRenderer` — pas d'outil de capture système,
  donc le résultat est le même sous KDE, GNOME ou sur un runner CI.

La fenêtre doit tout de même être *présentée* le temps du rendu : GTK n'alloue
et ne dessine rien tant qu'un widget n'est pas mappé. Elle apparaît donc une
fraction de seconde par capture, sans décoration.

Usage : python scripts/capture_screenshots.py [dossier] [--language fr]
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from pathlib import Path

# Avant tout import de `gi` : mêmes choix que `gui/launch.py` (rendu logiciel)
# et que les tests (isolation XDG). Sans ça, le script écrirait dans la vraie
# configuration de l'utilisateur et afficherait sa vraie install.
os.environ.setdefault("GSK_RENDERER", "cairo")
_SANDBOX = tempfile.mkdtemp(prefix="sgl-screenshots-")
for _variable in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
    os.environ[_variable] = str(Path(_SANDBOX) / _variable.lower())

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")

from gi.repository import Adw, GLib, Gsk, Gtk  # noqa: E402

DEMO_ROOT = Path("/home/stalker/Games/GAMMA")
DEMO_MODS = 412
SIZE = (1060, 720)
_MAP_TIMEOUT_SECONDS = 5.0
_SETTLE_ITERATIONS = 400


def _pump(iterations: int) -> None:
    """Laisse GTK avancer : mise en page, style, dessin."""
    context = GLib.MainContext.default()
    for _ in range(iterations):
        context.iteration(False)
        time.sleep(0.002)


def _capture(window: Gtk.Window, destination: Path) -> None:
    """Présente la fenêtre, attend qu'elle soit dessinée, en écrit le rendu."""
    window.set_default_size(*SIZE)
    window.set_decorated(False)
    window.present()

    deadline = time.monotonic() + _MAP_TIMEOUT_SECONDS
    while time.monotonic() < deadline and not window.get_mapped():
        _pump(1)
    _pump(_SETTLE_ITERATIONS)

    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, *SIZE)
    node = snapshot.to_node()
    if node is None:
        raise RuntimeError(f"rien à rendre pour {destination.name}")

    renderer = Gsk.CairoRenderer.new()
    renderer.realize(None)
    texture = renderer.render_texture(node, None)
    texture.save_to_png(str(destination))
    renderer.unrealize()
    window.destroy()
    _pump(30)
    print(f"écrit : {destination}")


def _install_demo_state() -> None:
    """Une install fictive, complète et crédible — jamais celle de la machine."""
    from stalker_gamma_linux import state
    from stalker_gamma_linux.gui import prefs

    for step in state.STEPS:
        state.mark_done(DEMO_ROOT, step)
    prefs.save_preferences(prefs.Preferences(install_path=DEMO_ROOT))


def _application() -> Adw.Application:
    from stalker_gamma_linux.gui import theme

    Adw.init()
    theme.install_theme()
    application = Adw.Application(application_id="org.stalkergammalinux.Screenshots")
    # `register` émet `startup` : sans lui, chaque fenêtre créée ici déclenche
    # un Gtk-CRITICAL (« windows must be added after startup »).
    application.register(None)
    return application


def _demo_window(app: Adw.Application):  # type: ignore[no-untyped-def]
    """Fenêtre principale dont le sondage affiche l'install de démonstration."""
    from stalker_gamma_linux.gui import space, stats, summary
    from stalker_gamma_linux.gui.windows.main_window import MainWindow

    window = MainWindow(application=app)
    # Le sondage réel tourne dans un thread et lirait le disque de la machine.
    # Incrémenter la génération le périme (c'est exactement le garde-fou que la
    # fenêtre utilise quand l'utilisateur change de disque en cours de sondage),
    # puis on pousse le résultat qu'aurait donné l'install de démonstration.
    window._probe_generation += 1
    window._apply_probe(
        window._probe_generation,
        summary.SystemSummary(blocking=()),
        space.SpaceReport(free_bytes=493 * 1024**3, verdict=space.SpaceVerdict.OK),
        stats.InstallStats(mod_count=DEMO_MODS, version="0.6.0"),
    )
    return window


def _home(app: Adw.Application, destination: Path) -> None:
    _capture(_demo_window(app), destination)


def _pre_install(app: Adw.Application, destination: Path) -> None:
    from stalker_gamma_linux.gui import prefs, space
    from stalker_gamma_linux.gui.windows.install_dialog import InstallDialog

    window = _demo_window(app)
    # Le dialog interroge le vrai volume ; la cible de démonstration n'existant
    # pas, il rendrait « espace insuffisant » sur la capture de documentation.
    # On lui sert le verdict d'une machine correctement dimensionnée.
    space.assess = lambda _target: space.SpaceReport(  # type: ignore[assignment]
        free_bytes=493 * 1024**3, verdict=space.SpaceVerdict.OK
    )
    dialog = InstallDialog(
        parent_window=window,
        preferences=prefs.Preferences(install_path=DEMO_ROOT),
        on_confirmed=lambda _preferences: None,
        on_show_diagnostic=lambda: None,
    )
    dialog.present(window)
    dialog._probe_generation += 1  # périme le sondage réel, cf. `_home`
    dialog._apply_prerequisites(dialog._probe_generation, ())
    _capture(window, destination)


def _progress(app: Adw.Application, destination: Path) -> None:
    import queue
    import threading

    from stalker_gamma_linux.gui import jobs
    from stalker_gamma_linux.gui.windows.main_window import MainWindow
    from stalker_gamma_linux.gui.windows.progress_view import ProgressPage
    from stalker_gamma_linux.gui.worker import BackgroundTask, WorkerEvent

    def blocked(_events: queue.Queue[WorkerEvent], cancel: threading.Event) -> int:
        cancel.wait(timeout=30)
        return 0

    window = MainWindow(application=app)
    task = BackgroundTask(blocked)
    page = ProgressPage(
        title="Installation",
        task=task,
        cancellable=True,
        on_finished=lambda _code: None,
        phase_labels=jobs.install_phase_labels(shortcut=False),
    )
    window._nav_view.push(page)

    for event in _DEMO_PROGRESS:
        task.events.put(event)
    for _ in range(4):
        page._on_poll()
    _capture(window, destination)
    task.cancel()


def _doctor(app: Adw.Application, destination: Path) -> None:
    from stalker_gamma_linux import doctor
    from stalker_gamma_linux.gui.windows.doctor_view import DoctorPage
    from stalker_gamma_linux.gui.windows.main_window import MainWindow

    window = MainWindow(application=app)
    page = DoctorPage(
        target=DEMO_ROOT,
        show_toast=lambda _text: None,
        on_verify=lambda _repair: None,
        on_backup=lambda: None,
        on_restore=lambda _identifier: None,
    )
    window._nav_view.push(page)
    # La collecte réelle tourne dans un thread et n'aboutirait jamais sans
    # boucle GTK : on la joue ici, sur la machine courante.
    page._apply_report(doctor.build_full_report(DEMO_ROOT))
    _capture(window, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        default=Path(__file__).resolve().parent.parent / "docs" / "screenshots",
        type=Path,
    )
    parser.add_argument("--language", default="fr", help="locale gettext des captures")
    arguments = parser.parse_args()
    os.environ["LANGUAGE"] = arguments.language

    arguments.output.mkdir(parents=True, exist_ok=True)
    _install_demo_state()
    app = _application()

    for name, render in (
        ("accueil", _home),
        ("pre-installation", _pre_install),
        ("installation", _progress),
        ("diagnostic", _doctor),
    ):
        render(app, arguments.output / f"{name}.png")
    return 0


def _demo_progress() -> tuple[object, ...]:
    """Une installation crédible, figée au milieu de la deuxième étape."""
    from stalker_gamma_linux.gui.worker import ReporterEvent

    lines = (
        ReporterEvent("header", "Installation de S.T.A.L.K.E.R. G.A.M.M.A."),
        ReporterEvent("skip", "Anomaly (jeu de base)", index="1/5"),
        ReporterEvent("step", "Modpack G.A.M.M.A (mods + instance MO2)", index="2/5"),
    )
    downloads = tuple(
        ReporterEvent("progress", f"téléchargement des archives ModDB {count}/340")
        for count in (37, 74, 111, 148, 185)
    )
    return (
        *lines,
        *downloads,
        ReporterEvent("progress", "extraction : GAMMA_RC3/mods/185- Screen Space Shaders …"),
    )


if __name__ == "__main__":
    _DEMO_PROGRESS = _demo_progress()
    raise SystemExit(main())
