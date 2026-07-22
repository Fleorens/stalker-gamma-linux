"""Orchestration haut-niveau des commandes d'installation (T07).

Enchaîne les étapes du moteur gamma-launcher (T03) pour produire une
installation jouable sous un seul répertoire racine choisi par l'utilisateur
(`--target`, sur le disque de son choix) : `<target>/{anomaly,gamma,cache}`.
Le lancement (MO2/USVFS) reste dans `mo2/` (commandes `mo2`/`play`).
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux import engine
from stalker_gamma_linux.engine.errors import EngineError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET


def run_install(target: Path | None = None) -> int:
    """Installe Anomaly + le modpack GAMMA sous `target`, prêt à jouer.

    Étapes : `anomaly-install` → `full-install` (télécharge les mods et construit
    l'instance MO2) → retrait obligatoire de ReShade + purge du cache de shaders.
    Reprend sur le cache en cas de relance (idempotent côté moteur). Retourne 0
    au succès, 1 si une étape échoue (message actionnable déjà affiché).
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install = InstallPaths.under(root)
    try:
        print(f"Installation de S.T.A.L.K.E.R. G.A.M.M.A. dans {root}")
        print("→ 1/3 Anomaly (jeu de base)…")
        engine.install_anomaly(install, on_progress=print)
        print("→ 2/3 Modpack G.A.M.M.A (téléchargement des mods + instance MO2)…")
        engine.install_gamma(install, on_progress=print)
        print("→ 3/3 Retrait de ReShade (incompatible DXVK) + purge du cache de shaders…")
        engine.remove_reshade(install, on_progress=print)
        engine.purge_shader_cache(install, on_progress=print)
    except EngineError as error:
        print(f"Erreur : {error}")
        return 1

    print(
        f"\nInstallation terminée. Étapes suivantes :\n"
        f"  stalker-gamma-linux mo2  --target {root}   # ouvrir Mod Organizer 2\n"
        f"  stalker-gamma-linux play --target {root}   # jouer (Anomaly via MO2, USVFS)"
    )
    return 0
