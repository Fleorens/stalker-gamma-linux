"""vkBasalt : post-traitement Vulkan — la réponse concrète au ReShade qu'on retire.

Le pipeline retire ReShade à chaque installation et à chaque mise à jour
(incompatible DXVK), et le README promet vkBasalt « en équivalent » depuis le
début. Cette promesse ne tenait que dans la documentation : on livre ici le
préset qui la rend vraie.

**Ce que fait le préset.** `effects = cas:lut` — d'abord le Contrast Adaptive
Sharpening d'AMD (la netteté que les joueurs vont chercher dans ReShade), puis
une table de correspondance de couleurs **que nous générons** : léger gain de
contraste et de saturation, dans l'esprit des présets ReShade livrés avec le
modpack. C'est le seul étalonnage possible ici — les effets intégrés de
vkBasalt sont `cas`, `dls`, `fxaa`, `smaa` et `lut`, et seul `lut` touche à la
couleur.

**Pourquoi une LUT générée et pas un shader ReShade `.fx`.** Les shaders `.fx`
demandent `reshadeIncludePath`/`reshadeTexturePath`, donc un dépôt de shaders
tiers installé quelque part ; et le runtime steamrt documente précisément ce
piège : « vkBasalt crashe si on lui demande des shaders introuvables », le
`/usr/share` de l'hôte n'existant pas dans le conteneur
(docs/steamlinuxruntime-known-issues.md, issue #381). Une LUT `.CUBE` est du
texte que nous écrivons sous `~/.config/stalker-gamma-linux/` — dans le dossier
personnel, donc partagé avec le conteneur par défaut — et sa génération se teste
sans lancer quoi que ce soit.

**Détection par manifeste.** vkBasalt n'installe aucun exécutable : la présence
se lit sur `vkBasalt.json` dans un `implicit_layer.d` (cf. `environment.vulkan`).
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.environment import vulkan

LAYER_STEM = "vkBasalt"
ENABLE_VARIABLE = "ENABLE_VKBASALT"
CONFIG_VARIABLE = "VKBASALT_CONFIG_FILE"
CONFIG_FILENAME = "vkBasalt.conf"
LUT_FILENAME = "gamma-reshade-like.CUBE"

# Netteté du CAS, échelle amont : 0.0 = à peine, 1.0 = maximum et artefacts.
# 0.4 est la valeur par défaut de vkBasalt — visible sans croustiller.
CAS_SHARPNESS = 0.4

# Taille du cube. 17 (et non 16) pour que le gris moyen tombe exactement sur un
# nœud (8/16 = 0.5) : le préset reste rigoureusement neutre au centre.
LUT_SIZE = 17
# Mélange vers une courbe en S (contraste) et gain de saturation. Volontairement
# discrets : c'est un étalonnage, pas un filtre Instagram.
LUT_CONTRAST = 0.18
LUT_SATURATION = 0.08

# Luminance Rec. 709 — celle du sRGB dans lequel le jeu présente ses images.
_LUMA = (0.2126, 0.7152, 0.0722)

_CONFIG_HEADER = (
    "# Généré par stalker-gamma-linux — RÉÉCRIT À CHAQUE LANCEMENT.\n"
    "# Préset « ReShade-like » : netteté CAS puis étalonnage par LUT.\n"
    "# Votre ~/.config/vkBasalt/vkBasalt.conf n'est ni lu ni modifié ici.\n"
)

_LUT_HEADER = (
    "# Généré par stalker-gamma-linux — RÉÉCRIT À CHAQUE LANCEMENT.\n"
    "# Préset « ReShade-like » : contraste +{contrast:.0%}, saturation +{saturation:.0%}.\n"
)


def layer_manifest() -> Path | None:
    """Manifeste de la couche vkBasalt sur cette machine, ou None si absente."""
    return vulkan.find_implicit_layer(LAYER_STEM)


def is_available() -> bool:
    return layer_manifest() is not None


def _contrast(value: float, amount: float) -> float:
    """Courbe en S (smoothstep) mélangée à l'identité selon `amount`.

    Monotone, et fixe en 0, 0.5 et 1 : les noirs restent noirs, les blancs
    blancs, et le gris moyen ne bouge pas — seul le contraste entre les deux
    change.
    """
    smooth = value * value * (3.0 - 2.0 * value)
    return value + amount * (smooth - value)


def lut_text(
    size: int = LUT_SIZE,
    contrast: float = LUT_CONTRAST,
    saturation: float = LUT_SATURATION,
) -> str:
    """Table de correspondance 3D au format `.CUBE` (fonction pure).

    Format attendu par vkBasalt : `LUT_3D_SIZE` **avant** les données (il
    dimensionne son tampon dessus), puis `size³` triplets RVB dans [0, 1],
    rouge variant le plus vite. Les valeurs sont toujours écrites avec un
    chiffre avant la virgule : le parseur amont ne reconnaît une ligne de
    données qu'à son premier caractère numérique.
    """
    lines = [
        _LUT_HEADER.format(contrast=contrast, saturation=saturation).rstrip("\n"),
        f"LUT_3D_SIZE {size}",
    ]
    last = size - 1
    for blue in range(size):
        for green in range(size):
            for red in range(size):
                channels = [
                    _contrast(component / last, contrast) for component in (red, green, blue)
                ]
                luma = sum(weight * value for weight, value in zip(_LUMA, channels, strict=True))
                graded = (
                    min(1.0, max(0.0, luma + (value - luma) * (1.0 + saturation)))
                    for value in channels
                )
                lines.append(" ".join(f"{value:.6f}" for value in graded))
    return "\n".join(lines) + "\n"


def config_text(lut_path: Path) -> str:
    """Contenu du `vkBasalt.conf` du préset (fonction pure).

    Le chemin de la LUT est entre guillemets : le parseur amont ignore les
    espaces hors chaîne, un dossier personnel qui en contient casserait la
    ligne sans ça. `reshadeIncludePath`/`reshadeTexturePath` restent **non
    renseignés** — aucun shader `.fx` ici, et un chemin invalide fait crasher
    la couche dans le conteneur steamrt.
    """
    return (
        _CONFIG_HEADER
        + "\n".join(
            (
                "effects = cas:lut",
                f"casSharpness = {CAS_SHARPNESS}",
                f'lutFile = "{lut_path}"',
                "# Touche Début (Home) : bascule les effets en jeu.",
                "toggleKey = Home",
                "enableOnLaunch = True",
            )
        )
        + "\n"
    )


def write_config(config_path: Path, lut_path: Path) -> Path:
    """Écrit la LUT puis la configuration qui la désigne. Retourne `config_path`."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lut_path.parent.mkdir(parents=True, exist_ok=True)
    lut_path.write_text(lut_text(), encoding="utf-8")
    config_path.write_text(config_text(lut_path), encoding="utf-8")
    return config_path


def environment(config_path: Path) -> dict[str, str]:
    """Variables qui activent la couche et lui imposent *notre* configuration."""
    return {ENABLE_VARIABLE: "1", CONFIG_VARIABLE: str(config_path)}
