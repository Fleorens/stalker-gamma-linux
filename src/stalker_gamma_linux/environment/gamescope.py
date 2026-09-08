"""gamescope : micro-compositeur qui rend le jeu à une résolution et l'affiche à une autre.

C'est le levier qui n'existe pas sous Windows, et celui qui rend GAMMA jouable
sur un GPU modeste ou sur un Steam Deck : le moteur rend à 1024×640, gamescope
remonte l'image en 1280×800 avec FSR, et l'interface reste nette parce que le
suréchantillonnage se fait **après** le rendu, pas sur une image d'écran déjà
composée.

**Le seul de nos trois outils qui est un vrai wrapper.** MangoHud et vkBasalt
sont des couches Vulkan chargées dans le processus du jeu : elles passent par
l'environnement. gamescope, lui, est le compositeur qui possède la fenêtre :
il doit être **le plus à l'extérieur** de la commande — `gamescope … --
gamemoderun umu-run …` — pour que tout ce qui suit s'affiche dedans.

**Options retenues** (`gamescope --help`, 3.16) : `-W`/`-H` = résolution de
*sortie* (la fenêtre ou l'écran), `-w`/`-h` = résolution de *rendu* (ce que le
jeu croit avoir), `-F fsr` = filtre de remontée d'échelle, `--sharpness` de 0
(le plus net) à 20 (le plus doux), `-f` = plein écran. Rien d'autre : chaque
option ajoutée ici est une option à maintenir, et les autres relèvent de la
ligne de commande de l'utilisateur.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from stalker_gamma_linux.environment import system

GAMESCOPE = "gamescope"

# Nom DMI des deux modèles de Steam Deck (LCD puis OLED), tel que le noyau le
# rapporte. `SteamDeck=1` est posé par Steam en mode Gaming, mais pas en mode
# Bureau : les deux pistes sont nécessaires pour couvrir les deux modes.
_DECK_PRODUCTS = ("jupiter", "galileo")
_DECK_ENV = "SteamDeck"
_PRODUCT_NAME_PATH = Path("/sys/class/dmi/id/product_name")

# Écran du Steam Deck (les deux modèles ont la même définition).
DECK_OUTPUT = (1280, 800)
# Rendu par défaut sur Deck : 0,8× l'écran, remonté par FSR. C'est le réglage
# qui fait la différence sur un modpack aussi lourd que GAMMA ; l'utilisateur
# remonte à 1280×800 s'il préfère la netteté aux images par seconde.
DECK_RENDER = (1024, 640)
# Hors Deck on ne connaît pas l'écran (aucune connexion au serveur d'affichage
# ici) : 1080p comme point de départ, à ajuster dans les préférences.
DESKTOP_OUTPUT = (1920, 1080)


# Échelle de netteté du filtre FSR, telle que gamescope l'accepte : 0 = le plus
# net, 20 = le plus doux. Hors de ces bornes, il refuse la valeur.
SHARPNESS_MIN = 0
SHARPNESS_MAX = 20


def clamp_sharpness(value: int) -> int:
    """Ramène `value` dans [0, 20] — la seule plage que gamescope accepte."""
    return min(SHARPNESS_MAX, max(SHARPNESS_MIN, value))


class Resolution(NamedTuple):
    width: int
    height: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


def parse_resolution(text: str) -> Resolution:
    """« 1280x800 » → Resolution(1280, 800). Lève `ValueError` sinon (type argparse)."""
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"résolution attendue sous la forme LARGEURxHAUTEUR : {text!r}")
    try:
        width, height = (int(part) for part in parts)
    except ValueError:
        raise ValueError(f"résolution attendue sous la forme LARGEURxHAUTEUR : {text!r}") from None
    if width <= 0 or height <= 0:
        raise ValueError(f"résolution strictement positive attendue : {text!r}")
    return Resolution(width, height)


@dataclass(frozen=True, slots=True)
class Options:
    """Réglages de la fenêtre gamescope. Défauts : bureau 1080p, FSR actif."""

    render: Resolution = Resolution(*DESKTOP_OUTPUT)
    output: Resolution = Resolution(*DESKTOP_OUTPUT)
    fsr: bool = True
    # Échelle amont : 0 = netteté maximale, 20 = minimale. 2 est le défaut de
    # gamescope, et le bon compromis sur une remontée d'échelle modérée.
    sharpness: int = 2
    fullscreen: bool = True

    def with_render(self, resolution: Resolution) -> Options:
        return replace(self, render=resolution)

    def with_output(self, resolution: Resolution) -> Options:
        return replace(self, output=resolution)

    def with_fsr(self, enabled: bool) -> Options:
        return replace(self, fsr=enabled)

    def with_sharpness(self, value: int) -> Options:
        return replace(self, sharpness=value)

    def with_fullscreen(self, enabled: bool) -> Options:
        return replace(self, fullscreen=enabled)


def is_steam_deck(environ: Mapping[str, str] | None = None) -> bool:
    """Machine Steam Deck (LCD ou OLED), d'après le DMI puis la variable de Steam."""
    product = system.read_text(_PRODUCT_NAME_PATH)
    if product is not None and product.strip().lower() in _DECK_PRODUCTS:
        return True
    env = environ if environ is not None else os.environ
    return env.get(_DECK_ENV) == "1"


def default_options(environ: Mapping[str, str] | None = None) -> Options:
    """Défauts cohérents avec l'écran : 1024×640 → 1280×800 sur Deck, 1080p ailleurs."""
    if is_steam_deck(environ):
        return Options(render=Resolution(*DECK_RENDER), output=Resolution(*DECK_OUTPUT))
    return Options()


def find_gamescope() -> str | None:
    return system.which(GAMESCOPE)


def is_available() -> bool:
    return find_gamescope() is not None


def arguments(options: Options) -> list[str]:
    """Options de ligne de commande correspondant à `options`, sans le `--` final."""
    argv = [
        "-W",
        str(options.output.width),
        "-H",
        str(options.output.height),
        "-w",
        str(options.render.width),
        "-h",
        str(options.render.height),
    ]
    if options.fsr:
        argv += ["-F", "fsr", "--sharpness", str(options.sharpness)]
    if options.fullscreen:
        argv.append("-f")
    return argv


def wrap(command: Sequence[str], options: Options) -> list[str]:
    """`[gamescope, …, --, *command]` si gamescope est installé, sinon la commande inchangée.

    Même contrat que `gamemode.wrap` : toujours une nouvelle liste, jamais
    d'échec quand l'outil manque — le jeu se lance simplement sans compositeur.
    """
    binary = find_gamescope()
    if binary is None:
        return list(command)
    return [binary, *arguments(options), "--", *command]
