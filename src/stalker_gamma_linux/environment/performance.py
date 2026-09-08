"""Composition des couches de performance autour du lancement du jeu.

Quatre outils, quatre modules, **une** fonction qui les emboîte :
`environment.gamemode` (gouverneur CPU), `environment.gamescope`
(compositeur), `environment.mangohud` et `environment.vkbasalt` (couches
Vulkan). Ce module ne connaît d'eux que leur signature ; il décide de l'ordre.

**L'ordre n'est pas libre.**

    gamescope … -- gamemoderun umu-run <exe> …
    ^ compositeur    ^ LD_PRELOAD      ^ conteneur steamrt → wine → le jeu
      + MANGOHUD=1, ENABLE_VKBASALT=1 dans l'environnement

1. **gamescope tout à l'extérieur** : c'est lui qui possède la fenêtre et qui
   compose ce que les autres produisent. À l'intérieur, il n'aurait rien à
   composer.
2. **gamemoderun juste dedans**, inchangé : il pose `libgamemodeauto.so.0` en
   `LD_PRELOAD` et exec la suite, donc il doit rester *au contact* du processus
   dont il veut la descendance (cf. `environment.gamemode`).
3. **MangoHud et vkBasalt nulle part dans la commande** : ce sont des couches
   Vulkan implicites, activées par une variable d'environnement que leur
   manifeste déclare (`MANGOHUD=1`, `ENABLE_VKBASALT=1`). Passer par leurs
   scripts d'enveloppe ajouterait un `LD_PRELOAD` de plus à une pile qui en
   compte déjà trop, pour un jeu qui est en Vulkan de bout en bout (DXVK).

**Chaque couche est une fonction, pas un `if` de plus.** `wrap(command) ->
list[str]` pour ce qui enveloppe, `environment(path) -> dict[str, str]` pour ce
qui s'active par variable. Aucune ne mute son entrée, aucune ne touche à
`os.environ` : `compose` part de l'environnement qu'on lui donne et en rend un
nouveau. Outil absent = la couche se retire d'elle-même, silencieusement.

**Où ça s'applique** : `launch_game` et `launch_flat`, jamais `launch_mo2` ni
les étapes d'installation — même frontière que GameMode, pour la même raison
(un overlay par-dessus le gestionnaire de mods n'a aucun sens, et un
compositeur pendant un téléchargement de 146 Gio non plus).

**Tout est opt-out par défaut**, GameMode excepté : ces trois outils changent le
rendu et les performances, et un joueur qui ouvre une issue doit pouvoir dire
« rien d'activé » sans avoir à le vérifier.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from stalker_gamma_linux import state
from stalker_gamma_linux.environment import gamemode, gamescope, mangohud, vkbasalt

# Alias de *types* : dans le corps de `Settings`, les champs `mangohud` et
# `gamescope` masquent les modules du même nom — annoter `mangohud.Preset`
# y désignerait alors un `bool`. Les fonctions de module, elles, gardent
# l'accès normal aux modules.
MangoHudPreset = mangohud.Preset
GamescopeOptions = gamescope.Options

# Liste (façon PATH) des chemins que pressure-vessel doit rendre visibles en
# lecture seule dans le conteneur steamrt. Nos fichiers de configuration vivent
# sous `~/.config/`, déjà partagé par défaut ; on les y ajoute quand même, parce
# que `XDG_CONFIG_HOME` peut pointer hors du dossier personnel et que c'est
# exactement le remède documenté par Valve pour ce cas
# (docs/steamlinuxruntime-known-issues.md, « Sharing directories with the
# container »). Sans effet hors conteneur.
CONTAINER_SHARE_VARIABLE = "PRESSURE_VESSEL_FILESYSTEMS_RO"


@dataclass(frozen=True, slots=True)
class Settings:
    """Ce que l'utilisateur a demandé. Rien de plus : la disponibilité se mesure."""

    # Seul défaut à `True` : GameMode ne change pas le rendu, il ne fait
    # qu'appliquer des priorités le temps de la partie (cf. `gui.prefs`).
    gamemode: bool = True
    mangohud: bool = False
    mangohud_preset: MangoHudPreset = MangoHudPreset.LIGHT
    gamescope: bool = False
    gamescope_options: GamescopeOptions = GamescopeOptions()
    vkbasalt: bool = False

    @classmethod
    def for_machine(cls) -> Settings:
        """Défauts adaptés à la machine : résolutions de l'écran du Deck, le cas échéant.

        Distinct du constructeur, qui reste pur : la détection matérielle n'a
        rien à faire dans une valeur par défaut de dataclass.
        """
        return cls(gamescope_options=gamescope.default_options())

    def with_gamemode(self, enabled: bool) -> Settings:
        return replace(self, gamemode=enabled)

    def with_mangohud(self, enabled: bool) -> Settings:
        return replace(self, mangohud=enabled)

    def with_mangohud_preset(self, preset: MangoHudPreset) -> Settings:
        return replace(self, mangohud_preset=preset)

    def with_gamescope(self, enabled: bool) -> Settings:
        return replace(self, gamescope=enabled)

    def with_gamescope_options(self, options: GamescopeOptions) -> Settings:
        return replace(self, gamescope_options=options)

    def with_vkbasalt(self, enabled: bool) -> Settings:
        return replace(self, vkbasalt=enabled)

    @property
    def any_layer_requested(self) -> bool:
        """Vrai dès qu'une couche de rendu est demandée (GameMode ne compte pas)."""
        return self.mangohud or self.gamescope or self.vkbasalt


class ConfigPaths(NamedTuple):
    """Fichiers que nous écrivons — les nôtres, jamais ceux des outils."""

    mangohud: Path
    vkbasalt: Path
    vkbasalt_lut: Path


@dataclass(frozen=True, slots=True)
class LaunchLayers:
    """Résultat de la composition : la commande à lancer et son environnement."""

    command: tuple[str, ...]
    environment: Mapping[str, str]


def config_dir() -> Path:
    """`~/.config/stalker-gamma-linux/` — le même dossier que l'état et les préférences."""
    return state.config_dir()


def config_paths(directory: Path) -> ConfigPaths:
    return ConfigPaths(
        mangohud=directory / mangohud.CONFIG_FILENAME,
        vkbasalt=directory / vkbasalt.CONFIG_FILENAME,
        vkbasalt_lut=directory / vkbasalt.LUT_FILENAME,
    )


def compose(
    command: Sequence[str],
    environment: Mapping[str, str],
    settings: Settings,
    *,
    directory: Path,
) -> LaunchLayers:
    """Emboîte les couches demandées **et disponibles** autour de `command`.

    Fonction pure au sens qui compte ici : ni `command` ni `environment` ne sont
    modifiés, rien n'est écrit sur le disque, et le résultat ne dépend que des
    arguments et de la présence des outils sur la machine. `directory` fournit
    l'emplacement de nos fichiers de configuration (voir `write_configs`, qui
    les produit avant le lancement).
    """
    layered = list(command)
    if settings.gamemode:
        layered = gamemode.wrap(layered)
    if settings.gamescope:
        layered = gamescope.wrap(layered, settings.gamescope_options)

    paths = config_paths(directory)
    variables: dict[str, str] = dict(environment)
    shared: list[str] = []
    if settings.mangohud and mangohud.is_available():
        variables.update(mangohud.environment(paths.mangohud))
        shared.append(str(paths.mangohud))
    if settings.vkbasalt and vkbasalt.is_available():
        variables.update(vkbasalt.environment(paths.vkbasalt))
        shared += [str(paths.vkbasalt), str(paths.vkbasalt_lut)]
    if shared:
        variables[CONTAINER_SHARE_VARIABLE] = _joined(
            environment.get(CONTAINER_SHARE_VARIABLE), shared
        )

    return LaunchLayers(command=tuple(layered), environment=variables)


def _joined(existing: str | None, additions: Sequence[str]) -> str:
    """Liste de chemins séparés par `:`, valeur de l'utilisateur en tête, sans doublon."""
    values = [entry for entry in (existing or "").split(":") if entry]
    for entry in additions:
        if entry not in values:
            values.append(entry)
    return ":".join(values)


def write_configs(settings: Settings, directory: Path) -> None:
    """Écrit les fichiers de configuration des seules couches actives.

    Réécriture à chaque lancement : c'est le réglage choisi qui fait foi, pas le
    contenu du fichier (voir les en-têtes générés, qui le disent à qui l'ouvre).
    """
    paths = config_paths(directory)
    if settings.mangohud and mangohud.is_available():
        mangohud.write_config(settings.mangohud_preset, paths.mangohud)
    if settings.vkbasalt and vkbasalt.is_available():
        vkbasalt.write_config(paths.vkbasalt, paths.vkbasalt_lut)


def prepare(
    command: Sequence[str],
    environment: Mapping[str, str],
    settings: Settings,
    *,
    directory: Path | None = None,
) -> LaunchLayers:
    """`write_configs` puis `compose` — le point d'entrée du lancement."""
    target = directory if directory is not None else config_dir()
    write_configs(settings, target)
    return compose(command, environment, settings, directory=target)


# --- Sérialisation (préférences) -------------------------------------------
#
# Conversion dictionnaire ⇄ réglages, sans dépendance à TOML ni à la GUI :
# `gui.prefs` la range sous une table `[performance]`, et rien n'interdit à un
# autre appelant de la ranger ailleurs. Aucune de ces fonctions ne lève :
# un fichier édité à la main ou écrit par une version antérieure retombe sur
# les valeurs par défaut, champ par champ (contrat de `gui.prefs`).


def as_mapping(settings: Settings) -> dict[str, object]:
    options = settings.gamescope_options
    return {
        "gamemode": settings.gamemode,
        "mangohud": settings.mangohud,
        "mangohud_preset": str(settings.mangohud_preset),
        "gamescope": settings.gamescope,
        "gamescope_render": str(options.render),
        "gamescope_output": str(options.output),
        "gamescope_fsr": options.fsr,
        "gamescope_sharpness": options.sharpness,
        "gamescope_fullscreen": options.fullscreen,
        "vkbasalt": settings.vkbasalt,
    }


def from_mapping(data: Mapping[str, object], default: Settings | None = None) -> Settings:
    """Réglages relus depuis un dictionnaire, champ manquant ou invalide = défaut."""
    base = default if default is not None else Settings()
    options = base.gamescope_options
    return Settings(
        gamemode=_flag(data, "gamemode", base.gamemode),
        mangohud=_flag(data, "mangohud", base.mangohud),
        mangohud_preset=_preset(data.get("mangohud_preset"), base.mangohud_preset),
        gamescope=_flag(data, "gamescope", base.gamescope),
        gamescope_options=gamescope.Options(
            render=_resolution(data.get("gamescope_render"), options.render),
            output=_resolution(data.get("gamescope_output"), options.output),
            fsr=_flag(data, "gamescope_fsr", options.fsr),
            sharpness=_sharpness(data.get("gamescope_sharpness"), options.sharpness),
            fullscreen=_flag(data, "gamescope_fullscreen", options.fullscreen),
        ),
        vkbasalt=_flag(data, "vkbasalt", base.vkbasalt),
    )


def _flag(data: Mapping[str, object], key: str, default: bool) -> bool:
    value = data.get(key)
    return bool(value) if isinstance(value, bool) else default


def _preset(value: object, default: mangohud.Preset) -> mangohud.Preset:
    try:
        return mangohud.Preset(str(value))
    except ValueError:
        return default


def _resolution(value: object, default: gamescope.Resolution) -> gamescope.Resolution:
    try:
        return gamescope.parse_resolution(str(value))
    except ValueError:
        return default


def _sharpness(value: object, default: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return gamescope.clamp_sharpness(value)
