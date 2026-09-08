"""MangoHud : overlay de performances, activé par l'environnement (couche Vulkan).

**Pourquoi les variables et pas le script `mangohud`.** Le paquet livre les
deux : un manifeste de couche Vulkan implicite activée par `MANGOHUD=1`
(`enable_environment` du JSON amont), et un script `mangohud` qui, lui, ajoute
`libMangoHud.so` au `LD_PRELOAD` pour couvrir aussi OpenGL. Le jeu est en
Vulkan (DXVK), donc le script n'apporterait rien de plus qu'un niveau de
`LD_PRELOAD` supplémentaire dans une pile qui en compte déjà trop
(gamemoderun → umu → pressure-vessel → wine). On pose donc `MANGOHUD=1` et on
s'arrête là.

**Notre fichier de configuration, jamais celui de l'utilisateur.** `MANGOHUD_CONFIGFILE`
désigne le fichier que nous écrivons sous `~/.config/stalker-gamma-linux/` ; le
`~/.config/MangoHud/MangoHud.conf` global n'est ni lu ni modifié — un joueur qui
a réglé son overlay pour tous ses jeux ne doit pas le voir changer parce qu'il a
coché une case ici. Corollaire assumé : le fichier est **réécrit à chaque
lancement** à partir du préset choisi (c'est le préset qui fait foi, pas le
fichier), d'où l'en-tête qui le dit et qui renvoie vers `MANGOHUD_CONFIG` pour
un réglage ponctuel.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from stalker_gamma_linux.environment import vulkan

# Nom du manifeste de couche implicite installé par le paquet (`MangoHud.json`,
# `MangoHud.x86.json`) : c'est lui qu'on cherche, pas un exécutable.
LAYER_STEM = "MangoHud"
ENABLE_VARIABLE = "MANGOHUD"
CONFIG_VARIABLE = "MANGOHUD_CONFIGFILE"
CONFIG_FILENAME = "mangohud.conf"

_HEADER = (
    "# Généré par stalker-gamma-linux — RÉÉCRIT À CHAQUE LANCEMENT.\n"
    "# Le préset choisi dans les préférences fait foi ; éditer ce fichier ne\n"
    "# sert donc à rien. Pour un réglage ponctuel : MANGOHUD_CONFIG=...\n"
    "# Votre ~/.config/MangoHud/MangoHud.conf n'est ni lu ni modifié ici.\n"
)

# `fps`, `frame_timing`, `cpu_stats` et `gpu_stats` sont actifs par défaut chez
# MangoHud : le préset léger doit donc *désactiver* explicitement ce qu'il ne
# veut pas, d'où les `=0`.
_LIGHT = (
    "fps",
    "frame_timing=1",
    "cpu_stats=0",
    "gpu_stats=0",
    "position=top-left",
    "font_size=20",
    "background_alpha=0.4",
)

_FULL = (
    "fps",
    "frame_timing=1",
    "cpu_stats",
    "cpu_temp",
    "gpu_stats",
    "gpu_temp",
    "vram",
    "ram",
    "resolution",
    "gpu_name",
    "vulkan_driver",
    "position=top-left",
    "font_size=20",
    "background_alpha=0.4",
)


class Preset(StrEnum):
    """Ce que l'overlay affiche. Deux niveaux : voir, ou diagnostiquer."""

    # fps + courbe de frametime : lire les à-coups sans manger l'écran.
    LIGHT = "light"
    # + CPU/GPU/VRAM/RAM/températures : ce qu'on demande à un joueur de
    # capturer quand il ouvre une issue « ça rame ».
    FULL = "full"


def layer_manifest() -> Path | None:
    """Manifeste de la couche MangoHud sur cette machine, ou None si absente."""
    return vulkan.find_implicit_layer(LAYER_STEM)


def is_available() -> bool:
    return layer_manifest() is not None


def config_text(preset: Preset) -> str:
    """Contenu du fichier de configuration pour `preset` (fonction pure)."""
    options = _FULL if preset is Preset.FULL else _LIGHT
    return _HEADER + "\n".join(options) + "\n"


def write_config(preset: Preset, path: Path) -> Path:
    """Écrit la configuration du préset dans `path` (parents créés). Retourne `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config_text(preset), encoding="utf-8")
    return path


def environment(config_path: Path) -> dict[str, str]:
    """Variables qui activent la couche et lui imposent *notre* configuration."""
    return {ENABLE_VARIABLE: "1", CONFIG_VARIABLE: str(config_path)}
