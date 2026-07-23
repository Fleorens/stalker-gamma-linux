"""Préférences de la GUI, persistées en TOML sous `~/.config/stalker-gamma-linux/`.

Fichier séparé de `state.install-state.toml` (T07) : ce ne sont pas les mêmes
données (préférences utilisateur globales vs. étapes validées par cible).
Réutilise `state.config_dir()` pour l'emplacement (XDG), seule chose commune.
Indépendant de GTK — testable sans `gi`.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

import tomli_w

from stalker_gamma_linux import state
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET

_PREFS_FILENAME = "gui-prefs.toml"


@dataclass(frozen=True, slots=True)
class Preferences:
    """`proton_release` à `None` = comportement par défaut (dernière release GE, T04)."""

    install_path: Path = DEFAULT_INSTALL_TARGET
    proton_release: str | None = None
    create_steam_shortcut: bool = True

    def with_install_path(self, path: Path) -> Preferences:
        return replace(self, install_path=path)

    def with_proton_release(self, release: str | None) -> Preferences:
        return replace(self, proton_release=release or None)

    def with_create_steam_shortcut(self, enabled: bool) -> Preferences:
        return replace(self, create_steam_shortcut=enabled)


def prefs_file() -> Path:
    return state.config_dir() / _PREFS_FILENAME


def load_preferences() -> Preferences:
    """État par défaut si le fichier est absent, illisible, ou corrompu (jamais d'exception)."""
    try:
        text = prefs_file().read_text(encoding="utf-8")
    except OSError:
        return Preferences()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return Preferences()

    raw_path = data.get("install_path")
    raw_release = data.get("proton_release")
    return Preferences(
        install_path=Path(str(raw_path)) if raw_path else DEFAULT_INSTALL_TARGET,
        proton_release=str(raw_release) if raw_release else None,
        create_steam_shortcut=bool(data.get("create_steam_shortcut", True)),
    )


def save_preferences(prefs: Preferences) -> None:
    directory = state.config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "install_path": str(prefs.install_path),
        "proton_release": prefs.proton_release or "",
        "create_steam_shortcut": prefs.create_steam_shortcut,
    }
    prefs_file().write_text(tomli_w.dumps(payload), encoding="utf-8")
