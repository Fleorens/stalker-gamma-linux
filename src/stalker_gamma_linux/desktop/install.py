"""Installation/mise à jour du raccourci bureau : icône + fichier `.desktop`.

Idempotent par construction : `DesktopPaths` pointe vers des chemins fixes
(dérivés de `APP_ID`), donc relancer cette fonction écrase le fichier existant
au lieu d'en créer un doublon — pas besoin de la logique de déduplication
qu'aurait exigée un `shortcuts.vdf`.
"""

from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path

from stalker_gamma_linux.desktop.entry import render_desktop_entry
from stalker_gamma_linux.desktop.errors import DesktopWriteError
from stalker_gamma_linux.desktop.paths import DesktopPaths
from stalker_gamma_linux.environment import system

_ICON_PACKAGE = "stalker_gamma_linux"
_ICON_RESOURCE = "assets/icon.png"


def launch_command(target: Path) -> list[str]:
    """Commande de lancement du jeu, en chemin absolu (indépendant du `$PATH`)."""
    console_script = Path(sys.executable).parent / "stalker-gamma-linux"
    return [str(console_script), "play", "--target", str(target)]


def _bundled_icon_bytes() -> bytes:
    return (resources.files(_ICON_PACKAGE) / _ICON_RESOURCE).read_bytes()


def install_shortcut(target: Path, *, paths: DesktopPaths | None = None) -> DesktopPaths:
    """Écrit/actualise l'icône et le fichier `.desktop` pour `target`. Retourne les chemins."""
    resolved = paths if paths is not None else DesktopPaths.default()

    try:
        resolved.applications_dir.mkdir(parents=True, exist_ok=True)
        resolved.icon_dir.mkdir(parents=True, exist_ok=True)
        resolved.icon_file.write_bytes(_bundled_icon_bytes())

        entry = render_desktop_entry(
            command=launch_command(target),
            working_dir=target,
            icon=resolved.icon_file,
        )
        resolved.desktop_file.write_text(entry, encoding="utf-8")
        resolved.desktop_file.chmod(0o755)
    except OSError as error:
        raise DesktopWriteError(resolved.desktop_file, error) from error

    _refresh_caches(resolved)
    return resolved


def _refresh_caches(paths: DesktopPaths) -> None:
    """Rafraîchit les caches menu/icônes si les outils sont dispo ; no-op silencieux sinon."""
    if system.which("update-desktop-database") is not None:
        system.run(["update-desktop-database", str(paths.applications_dir)])
    if system.which("gtk-update-icon-cache") is not None:
        system.run(["gtk-update-icon-cache", "-f", "-t", str(paths.icon_theme_root)])
