"""Variables d'environnement du cache de shaders DXVK/Mesa/NVIDIA (T21).

Distinct du cache X-Ray d'Anomaly (`engine.runner.purge_shader_cache`, qu'on
purge volontairement) : celui-ci est le cache de *pipelines compilés* que
DXVK, et le pilote Vulkan/OpenGL en dessous, écrivent sur disque. Personne ne
le pilotait jusqu'ici : il atterrissait où le pilote et le préfixe décidaient
(souvent `$HOME/.cache`, hors de `<root>`, ou dans le préfixe lui-même), avec
un plafond de taille par défaut bien trop bas pour un modpack qui compile des
milliers de shaders au premier lancement (Mesa : 1 Gio, cf. sources ci-dessous
— il s'évince tout seul en cours de route, en silence).

Sources des noms de variables et de leur comportement par défaut (vérifiées
2026-09-08, la doc amont a renommé certaines d'entre elles au fil des
versions — `DXVK_STATE_CACHE_PATH` par exemple n'existe plus) :
- DXVK : https://github.com/doitsujin/dxvk/blob/master/README.md
- Mesa : https://docs.mesa3d.org/envvars.html
- NVIDIA : https://download.nvidia.com/XFree86/Linux-x86_64/470.239.06/README/openglenvvariables.html
"""

from __future__ import annotations

from pathlib import Path

# Le module noyau `nvidia` crée ces deux entrées dès qu'il est chargé — que la
# carte serve réellement le rendu ou non (Optimus, carte secondaire inutilisée).
# Suffisant ici : poser les variables NVIDIA ne coûte rien si le pilote tourne
# mais ne rend pas ce jeu précis, et évite de deviner à partir du nom du GPU.
_NVIDIA_MARKERS: tuple[Path, ...] = (
    Path("/proc/driver/nvidia/version"),
    Path("/sys/module/nvidia"),
)


def nvidia_present() -> bool:
    """Le pilote propriétaire NVIDIA est-il chargé sur cette machine ?"""
    return any(marker.exists() for marker in _NVIDIA_MARKERS)


# Manifestes ICD du loader Vulkan (même piste que `environment.vulkan` pour les
# couches implicites, transposée aux pilotes) : tous les pilotes Vulkan
# open-source de Mesa (radv, anv, lvp, nouveau/nvk…) s'y déclarent, et
# « nvidia » dans le nom de fichier est le seul cas qui n'en est pas un.
_MESA_ICD_DIRS: tuple[Path, ...] = (
    Path("/usr/share/vulkan/icd.d"),
    Path("/etc/vulkan/icd.d"),
)


def mesa_present() -> bool:
    """Un pilote Vulkan Mesa (donc concerné par `MESA_SHADER_CACHE_*`) est-il installé ?"""
    for directory in _MESA_ICD_DIRS:
        try:
            entries = directory.iterdir()
        except OSError:
            continue
        for entry in entries:
            name = entry.name.lower()
            if name.endswith(".json") and "nvidia" not in name:
                return True
    return False


# Défaut Mesa documenté : 1 Gio (docs.mesa3d.org/envvars.html). Beaucoup trop
# bas pour un modpack de cette taille — relevé, pas désactivé (on veut toujours
# une purge éventuelle par le pilote, juste pas prématurée).
_MESA_CACHE_MAX_SIZE = "10G"

# NVIDIA ne documente pas de plafond par défaut explicite, seulement qu'un
# plafond implicite existe et peut être ignoré (`__GL_SHADER_DISK_CACHE_SKIP_CLEANUP`)
# ou relevé (`__GL_SHADER_DISK_CACHE_SIZE`, en octets). Même raisonnement que
# Mesa : on le relève explicitement plutôt que de le contourner.
_NVIDIA_CACHE_MAX_SIZE_BYTES = str(10 * 1024**3)


def build_env(shaders_root: Path) -> dict[str, str]:
    """Variables de cache à poser par défaut dans le préfixe (voir `prefix.process`).

    Toutes pointent sous `shaders_root` — `<root>/cache/shaders`, même volume
    que l'installation, voir `PrefixPaths.shaders` — plutôt que dans le
    préfixe ou le `$HOME` du pilote : elles survivent ainsi à une
    reconstruction du préfixe et à un changement de version de Proton-GE. Une
    variable pilote (Mesa ou NVIDIA) n'est posée que si le pilote correspondant
    est effectivement présent, pour ne pas polluer l'environnement de l'autre.
    Ce sont des défauts : l'appelant de `run_in_prefix` peut les surcharger via
    son propre `env`.
    """
    env = {
        # Sans ce chemin, DXVK écrit son cache sous $XDG_CACHE_HOME/dxvk (ou
        # $HOME/.cache/dxvk) — hors de <root>, donc invisible à
        # `uninstall --game-data` et non réutilisé par un autre préfixe.
        "DXVK_SHADER_CACHE_PATH": str(shaders_root / "dxvk"),
    }
    if mesa_present():
        # Mesa ajoute lui-même /mesa_shader_cache sous le chemin qu'on lui
        # donne (comportement documenté, pas un sous-dossier de notre cru).
        env["MESA_SHADER_CACHE_DIR"] = str(shaders_root / "mesa")
        env["MESA_SHADER_CACHE_MAX_SIZE"] = _MESA_CACHE_MAX_SIZE
    if nvidia_present():
        env["__GL_SHADER_DISK_CACHE_PATH"] = str(shaders_root / "nvidia")
        env["__GL_SHADER_DISK_CACHE_SIZE"] = _NVIDIA_CACHE_MAX_SIZE_BYTES
    return env
