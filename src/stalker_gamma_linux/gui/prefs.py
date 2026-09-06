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
from stalker_gamma_linux.paths_safety import UnsafeInstallTargetError, validate_install_target

_PREFS_FILENAME = "gui-prefs.toml"


@dataclass(frozen=True, slots=True)
class Preferences:
    """`proton_release` à `None` = comportement par défaut (dernière release GE, T04).

    `create_steam_shortcut` à `False` par défaut : ce n'est PAS l'icône du menu
    applications (`install.sh` la crée déjà, une seule fois, en pointant sur la
    GUI) — c'est une entrée supplémentaire qui lance `play` en direct, utile
    uniquement comme cible pour Steam « Ajouter un jeu non-Steam ». Cochée par
    défaut, elle produisait deux icônes « Installeur GAMMA » quasi identiques
    dans le menu (constaté en VM le 2026-07-26) : une qui ouvre la GUI, une qui
    saute droit dans le jeu.
    """

    install_path: Path = DEFAULT_INSTALL_TARGET
    proton_release: str | None = None
    create_steam_shortcut: bool = False
    # `use_gamemode` à `True` par défaut : quand GameMode est installé, il n'y a
    # aucune raison de s'en priver, et quand il ne l'est pas c'est un no-op
    # (cf. `environment.gamemode`). L'interrupteur n'existe que comme échappatoire
    # (diagnostic d'un problème de perfs, machine où le daemon fait des siennes).
    use_gamemode: bool = True

    def with_install_path(self, path: Path) -> Preferences:
        return replace(self, install_path=path)

    def with_proton_release(self, release: str | None) -> Preferences:
        return replace(self, proton_release=release or None)

    def with_create_steam_shortcut(self, enabled: bool) -> Preferences:
        return replace(self, create_steam_shortcut=enabled)

    def with_use_gamemode(self, enabled: bool) -> Preferences:
        return replace(self, use_gamemode=enabled)


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
        install_path=_install_path_or_default(raw_path),
        proton_release=str(raw_release) if raw_release else None,
        create_steam_shortcut=bool(data.get("create_steam_shortcut", False)),
        use_gamemode=bool(data.get("use_gamemode", True)),
    )


def _install_path_or_default(raw_path: object) -> Path:
    """Chemin d'install du fichier, ou le défaut s'il est absent ou inutilisable.

    Le sélecteur de dossier refuse déjà les caractères de contrôle, mais ce
    fichier est du TOML éditable à la main (et a pu être écrit avant ce
    garde-fou) : sans ce filtre, un `install_path` porteur d'un `\\n` repartirait
    directement dans le `.desktop` (cf. `paths_safety.validate_install_target`).
    Repli silencieux sur le défaut, conformément au contrat « jamais
    d'exception » de `load_preferences`.
    """
    if not raw_path:
        return DEFAULT_INSTALL_TARGET
    try:
        return validate_install_target(Path(str(raw_path)))
    except UnsafeInstallTargetError:
        return DEFAULT_INSTALL_TARGET


def save_preferences(prefs: Preferences) -> None:
    directory = state.config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "install_path": str(prefs.install_path),
        "proton_release": prefs.proton_release or "",
        "create_steam_shortcut": prefs.create_steam_shortcut,
        "use_gamemode": prefs.use_gamemode,
    }
    prefs_file().write_text(tomli_w.dumps(payload), encoding="utf-8")
