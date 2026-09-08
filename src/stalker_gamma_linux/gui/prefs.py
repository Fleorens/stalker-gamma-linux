"""Préférences de la GUI, persistées en TOML sous `~/.config/stalker-gamma-linux/`.

Fichier séparé de `state.install-state.toml` (T07) : ce ne sont pas les mêmes
données (préférences utilisateur globales vs. étapes validées par cible).
Réutilise `state.config_dir()` pour l'emplacement (XDG), seule chose commune.
Indépendant de GTK — testable sans `gi`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

from stalker_gamma_linux import state
from stalker_gamma_linux.environment import performance
from stalker_gamma_linux.environment.performance import Settings as PerformanceSettings
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.paths_safety import UnsafeInstallTargetError, validate_install_target

_PREFS_FILENAME = "gui-prefs.toml"


@dataclass(frozen=True, slots=True)
class Preferences:
    """`proton_release` à `None` = comportement par défaut (dernière release GE, T04).

    **Deux réglages Steam, à ne pas confondre** — le premier s'appelait
    `create_steam_shortcut`, un nom qui promettait le second (renommé par T19,
    l'ancienne clé du fichier reste lue) :

    - `create_direct_shortcut` — une entrée `.desktop` **du menu applications**
      qui lance `play` en direct. Steam n'y est pour rien : elle ne servait que
      de cible commode pour le bouton *Ajouter un jeu non-Steam*. `False` par
      défaut car cochée, elle produisait deux icônes « Installeur GAMMA » quasi
      identiques dans le menu (constaté en VM le 2026-07-26) : une qui ouvre la
      GUI, une qui saute droit dans le jeu.
    - `add_to_steam` — l'entrée **dans la bibliothèque Steam** elle-même
      (`shortcuts.vdf` + artwork, T19), celle qui rend GAMMA lançable depuis le
      mode Gaming. `False` par défaut : elle écrit dans un fichier qui
      appartient à Steam, et exige que Steam soit fermé — ça se demande.
    """

    install_path: Path = DEFAULT_INSTALL_TARGET
    proton_release: str | None = None
    create_direct_shortcut: bool = False
    add_to_steam: bool = False
    # Couches de performance (T20). GameMode y est actif par défaut : quand il
    # est installé, il n'y a aucune raison de s'en priver, et quand il ne l'est
    # pas c'est un no-op (cf. `environment.gamemode`) — l'interrupteur n'existe
    # que comme échappatoire (diagnostic d'un problème de perfs, machine où le
    # daemon fait des siennes). MangoHud, gamescope et vkBasalt, eux, changent
    # le rendu : ils restent éteints tant que l'utilisateur ne les demande pas.
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)

    def with_install_path(self, path: Path) -> Preferences:
        return replace(self, install_path=path)

    def with_proton_release(self, release: str | None) -> Preferences:
        return replace(self, proton_release=release or None)

    def with_create_direct_shortcut(self, enabled: bool) -> Preferences:
        return replace(self, create_direct_shortcut=enabled)

    def with_add_to_steam(self, enabled: bool) -> Preferences:
        return replace(self, add_to_steam=enabled)

    def with_performance(self, settings: PerformanceSettings) -> Preferences:
        return replace(self, performance=settings)


def prefs_file() -> Path:
    return state.config_dir() / _PREFS_FILENAME


def default_preferences() -> Preferences:
    """Défauts d'une machine neuve — dont les résolutions de l'écran du Deck, s'il y a lieu.

    Distinct de `Preferences()`, qui reste un objet pur (aucune lecture de la
    machine) : c'est ce que voit un utilisateur au tout premier lancement, et
    proposer 1920×1080 sur un écran 1280×800 serait un mauvais point de départ.
    """
    return Preferences(performance=performance.Settings.for_machine())


def load_preferences() -> Preferences:
    """État par défaut si le fichier est absent, illisible, ou corrompu (jamais d'exception)."""
    try:
        text = prefs_file().read_text(encoding="utf-8")
    except OSError:
        return default_preferences()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return default_preferences()

    raw_path = data.get("install_path")
    raw_release = data.get("proton_release")
    return Preferences(
        install_path=_install_path_or_default(raw_path),
        proton_release=str(raw_release) if raw_release else None,
        create_direct_shortcut=_direct_shortcut_flag(data),
        add_to_steam=bool(data.get("add_to_steam", False)),
        performance=_performance_or_default(data),
    )


def _direct_shortcut_flag(data: Mapping[str, object]) -> bool:
    """Le drapeau du raccourci `.desktop` direct, ancienne clé comprise.

    `create_steam_shortcut` est le nom qu'il portait avant T19, quand il n'y
    avait rien d'autre côté Steam. Un fichier de préférences écrit par une
    version précédente doit garder le choix de l'utilisateur — sans quoi le
    renommage le remettrait silencieusement à `False`.
    """
    if "create_direct_shortcut" in data:
        return bool(data["create_direct_shortcut"])
    return bool(data.get("create_steam_shortcut", False))


def _performance_or_default(data: Mapping[str, object]) -> performance.Settings:
    """Couches relues depuis la table `[performance]`, défauts de la machine sinon.

    `use_gamemode` à la racine est l'ancienne clé (avant T20, GameMode était le
    seul réglage de performance) : on la lit encore pour ne pas réactiver
    GameMode chez quelqu'un qui l'avait justement coupé, mais on ne l'écrit
    plus — la table `[performance]` est désormais la seule source de vérité.
    """
    machine = performance.Settings.for_machine()
    legacy = data.get("use_gamemode")
    base = machine.with_gamemode(legacy) if isinstance(legacy, bool) else machine
    section = data.get("performance")
    if isinstance(section, dict):
        return performance.from_mapping(section, base)
    return base


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
        "create_direct_shortcut": prefs.create_direct_shortcut,
        "add_to_steam": prefs.add_to_steam,
        # Table imbriquée en dernier : le format TOML veut les clés simples
        # avant les tables, et `tomli_w` s'y tient à condition de recevoir le
        # dictionnaire dans cet ordre.
        "performance": performance.as_mapping(prefs.performance),
    }
    prefs_file().write_text(tomli_w.dumps(payload), encoding="utf-8")
