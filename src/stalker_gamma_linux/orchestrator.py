"""Orchestration haut-niveau des commandes d'installation et de mise à jour (T07).

`run_install` enchaîne les étapes du moteur gamma-launcher (T03), du préfixe
partagé (T04) et de l'instance MO2 (T05) pour produire une installation
jouable sous un seul répertoire racine choisi par l'utilisateur (`--target`) :
`<target>/{anomaly,gamma,cache,prefix}`. Chaque étape est marquée dans l'état
persisté (`state.py`) : une relance après interruption saute les étapes déjà
validées. Le lancement au quotidien (MO2/USVFS) reste dans `mo2/` (commandes
`mo2`/`play`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from stalker_gamma_linux import engine, output
from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.desktop import install_shortcut
from stalker_gamma_linux.desktop.errors import DesktopError
from stalker_gamma_linux.engine.errors import EngineError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment.report import (
    DEFAULT_INSTALL_TARGET,
    build_report,
    format_report,
)
from stalker_gamma_linux.mo2 import instance
from stalker_gamma_linux.mo2.errors import Mo2Error
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.session import resolve_anomaly
from stalker_gamma_linux.prefix import provision
from stalker_gamma_linux.prefix.errors import PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths

_RESUME_HINT_TEMPLATE = (
    "Relance `stalker-gamma-linux install --target {root}` : "
    "la reprise saute les étapes déjà validées."
)


def run_install(
    target: Path | None = None,
    *,
    shortcut: bool = False,
    search_dirs: Sequence[Path] | None = None,
) -> int:
    """Installe Anomaly + le modpack GAMMA sous `target`, prêt à jouer.

    Étapes : vérification des prérequis (avertissement, non bloquant) →
    `anomaly-install` → `full-install` → retrait de ReShade + purge du cache de
    shaders → préfixe Proton partagé → configuration de l'instance MO2 →
    raccourci bureau (si `shortcut`). Reprend après interruption : chaque étape
    déjà validée (état persisté sous `~/.config/stalker-gamma-linux/`) est
    sautée. Retourne 0 au succès, 1 si une étape échoue (message actionnable
    déjà affiché par l'erreur d'origine).
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install = InstallPaths.under(root)
    prefix_paths = PrefixPaths.under(root)
    mo2_paths = Mo2Paths.under(root)

    output.header(f"Installation de S.T.A.L.K.E.R. G.A.M.M.A. dans {root}")

    env_report = build_report(root)
    if not env_report.is_ready:
        output.warn(
            "Prérequis manquants — les étapes qui en dépendent peuvent échouer :\n"
            + format_report(env_report)
        )

    install.ensure_directories()
    state = state_module.load_state(root)
    total = len(state_module.STEPS) if shortcut else len(state_module.STEPS) - 1

    def run_step(number: int, step_name: str, action: Callable[[], None]) -> None:
        nonlocal state
        label = state_module.STEP_LABELS[step_name]
        index = f"{number}/{total}"
        if state.is_done(step_name):
            output.skip(index, label)
            return
        output.step(index, f"{label}…")
        action()
        state = state_module.mark_done(root, step_name)

    def remove_reshade_and_purge() -> None:
        engine.remove_reshade(install, on_progress=output.progress)
        engine.purge_shader_cache(install, on_progress=output.progress)

    def ensure_prefix() -> None:
        provision.ensure_prefix(prefix_paths, search_dirs=search_dirs, on_progress=output.progress)

    def configure_mo2() -> None:
        anomaly_dir = resolve_anomaly(mo2_paths, install)
        instance.configure_instance(mo2_paths, anomaly_dir)

    def create_shortcut() -> None:
        install_shortcut(root)

    def install_anomaly() -> None:
        engine.install_anomaly(install, on_progress=output.progress)

    def install_gamma() -> None:
        engine.install_gamma(install, on_progress=output.progress)

    try:
        run_step(1, "anomaly", install_anomaly)
        run_step(2, "gamma", install_gamma)
        run_step(3, "reshade", remove_reshade_and_purge)
        run_step(4, "prefix", ensure_prefix)
        run_step(5, "mo2", configure_mo2)
        if shortcut:
            run_step(6, "shortcut", create_shortcut)
    except (EngineError, PrefixError, Mo2Error, DesktopError) as error:
        output.error(str(error), hint=_RESUME_HINT_TEMPLATE.format(root=root))
        return 1

    output.success(
        f"\nInstallation terminée. Étapes suivantes :\n"
        f"  stalker-gamma-linux mo2  --target {root}   # ouvrir Mod Organizer 2\n"
        f"  stalker-gamma-linux play --target {root}   # jouer (Anomaly via MO2, USVFS)"
    )
    return 0


def run_update(target: Path | None = None) -> int:
    """Met à jour le modpack GAMMA, retire ReShade et re-vérifie l'installation.

    `full-install` (via `update_gamma`, alias documenté) ne retélécharge que ce
    qui a changé en amont ; `verify` re-contrôle Anomaly (`check-anomaly`) et
    les mods (`check-md5`). Retourne 0 au succès, 1 si une étape échoue.
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install = InstallPaths.under(root)

    output.header(f"Mise à jour de S.T.A.L.K.E.R. G.A.M.M.A. dans {root}")
    try:
        output.step("1/3", "Modpack G.A.M.M.A (téléchargement incrémental)…")
        engine.update_gamma(install, on_progress=output.progress)
        output.step("2/3", "Retrait de ReShade + purge du cache de shaders…")
        engine.remove_reshade(install, on_progress=output.progress)
        engine.purge_shader_cache(install, on_progress=output.progress)
        output.step("3/3", "Vérification (Anomaly + MD5 des mods)…")
        engine.verify(install, on_progress=output.progress)
    except EngineError as error:
        output.error(str(error))
        return 1

    state_module.mark_done(root, "gamma")
    output.success(
        "\nMise à jour terminée.\nRappels : si un profil ou un exécutable "
        "personnalisé a changé en amont, relance `stalker-gamma-linux mo2 "
        f"--target {root}` pour vérifier l'instance ; si l'USVFS semble mort "
        "après la mise à jour, voir docs/MO2-PROTON-COMPAT.md."
    )
    return 0
