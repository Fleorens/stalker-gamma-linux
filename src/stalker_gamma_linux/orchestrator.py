"""Orchestration haut-niveau des commandes d'installation et de mise à jour (T07).

`run_install` enchaîne les étapes du moteur gamma-launcher (T03), du préfixe
partagé (T04) et de l'instance MO2 (T05) pour produire une installation
jouable sous un seul répertoire racine choisi par l'utilisateur (`--target`) :
`<target>/{anomaly,gamma,cache,prefix}`. Chaque étape est marquée dans l'état
persisté (`state.py`) : une relance après interruption saute les étapes déjà
validées. Le lancement au quotidien (MO2/USVFS) reste dans `mo2/` (commandes
`mo2`/`play`).

`run_install`/`run_update` ne connaissent que `output.Reporter` (T08) : la CLI
passe `output.console_reporter` (défaut, comportement inchangé) et la GUI sa
propre implémentation qui pousse les événements vers ses widgets — aucune
étape d'installation n'est dupliquée côté GUI. `cancel_event` (optionnel) est
propagé jusqu'aux sous-process (`engine.process`/`prefix.process`) pour une
annulation propre depuis la GUI ; la CLI ne le passe jamais.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from stalker_gamma_linux import engine, output
from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.desktop import install_shortcut
from stalker_gamma_linux.desktop.errors import DesktopError
from stalker_gamma_linux.engine.errors import EngineCancelledError, EngineError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment.report import (
    DEFAULT_INSTALL_TARGET,
    build_report,
    format_report,
)
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2 import instance
from stalker_gamma_linux.mo2.errors import Mo2Error
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.session import resolve_anomaly
from stalker_gamma_linux.prefix import provision
from stalker_gamma_linux.prefix.errors import PrefixCancelledError, PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths

_RESUME_HINT_TEMPLATE = _(
    "Retry `stalker-gamma-linux install --target {root}`: "
    "resuming skips steps already validated."
)

# Convention POSIX (128 + SIGINT) : réutilisée pour toute annulation propre,
# déclenchée par la CLI (Ctrl-C, hors de ce module) ou par la GUI (`cancel_event`).
CANCELLED_EXIT_CODE = 130


class _InstallCancelledError(Exception):
    """Signal interne : `cancel_event` était déjà levé avant de démarrer une étape."""


def run_install(
    target: Path | None = None,
    *,
    shortcut: bool = False,
    search_dirs: Sequence[Path] | None = None,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
    proton_release: str | None = None,
) -> int:
    """Installe Anomaly + le modpack GAMMA sous `target`, prêt à jouer.

    Étapes : vérification des prérequis (avertissement, non bloquant) →
    `anomaly-install` → `full-install` → retrait de ReShade + purge du cache de
    shaders → préfixe Proton partagé → configuration de l'instance MO2 →
    raccourci bureau (si `shortcut`). Reprend après interruption : chaque étape
    déjà validée (état persisté sous `~/.config/stalker-gamma-linux/`) est
    sautée. Retourne 0 au succès, 1 si une étape échoue (message actionnable
    déjà affiché par l'erreur d'origine), `CANCELLED_EXIT_CODE` si `cancel_event`
    (GUI) a été levé pendant une étape — l'étape en cours n'est pas marquée
    faite, une relance la rejoue. `proton_release` (optionnel, préférence GUI) :
    voir `prefix.proton.ensure_proton`.
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install = InstallPaths.under(root)
    prefix_paths = PrefixPaths.under(root)
    mo2_paths = Mo2Paths.under(root)

    reporter.header(_("Installing S.T.A.L.K.E.R. G.A.M.M.A. in {root}").format(root=root))

    env_report = build_report(root)
    if not env_report.is_ready:
        reporter.warn(
            _("Missing prerequisites — steps depending on them may fail:\n")
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
            reporter.skip(index, label)
            return
        if cancel_event is not None and cancel_event.is_set():
            raise _InstallCancelledError
        reporter.step(index, f"{label}…")
        action()
        state = state_module.mark_done(root, step_name)

    def remove_reshade_and_purge() -> None:
        engine.remove_reshade(install, on_progress=reporter.progress, cancel_event=cancel_event)
        engine.purge_shader_cache(
            install, on_progress=reporter.progress, cancel_event=cancel_event
        )

    def ensure_prefix() -> None:
        provision.ensure_prefix(
            prefix_paths,
            search_dirs=search_dirs,
            on_progress=reporter.progress,
            cancel_event=cancel_event,
            proton_release=proton_release,
        )

    def configure_mo2() -> None:
        anomaly_dir = resolve_anomaly(mo2_paths, install)
        instance.configure_instance(mo2_paths, anomaly_dir)

    def create_shortcut() -> None:
        install_shortcut(root)

    def install_anomaly() -> None:
        engine.install_anomaly(install, on_progress=reporter.progress, cancel_event=cancel_event)

    def install_gamma() -> None:
        engine.install_gamma(install, on_progress=reporter.progress, cancel_event=cancel_event)

    try:
        run_step(1, "anomaly", install_anomaly)
        run_step(2, "gamma", install_gamma)
        run_step(3, "reshade", remove_reshade_and_purge)
        run_step(4, "prefix", ensure_prefix)
        run_step(5, "mo2", configure_mo2)
        if shortcut:
            run_step(6, "shortcut", create_shortcut)
    except (_InstallCancelledError, EngineCancelledError, PrefixCancelledError):
        reporter.warn(_("Installation cancelled."))
        return CANCELLED_EXIT_CODE
    except (EngineError, PrefixError, Mo2Error, DesktopError) as error:
        reporter.error(str(error), hint=_RESUME_HINT_TEMPLATE.format(root=root))
        return 1

    reporter.success(
        _(
            "\nInstallation complete. Next steps:\n"
            "  stalker-gamma-linux mo2  --target {root}   # open Mod Organizer 2\n"
            "  stalker-gamma-linux play --target {root}   # play (Anomaly via MO2, USVFS)"
        ).format(root=root)
    )
    return 0


def run_update(
    target: Path | None = None,
    *,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
) -> int:
    """Met à jour le modpack GAMMA, retire ReShade et re-vérifie l'installation.

    `full-install` (via `update_gamma`, alias documenté) ne retélécharge que ce
    qui a changé en amont ; `verify` re-contrôle l'intégrité des archives de
    mods (`check-md5`). Retourne 0 au succès, 1 si une étape échoue,
    `CANCELLED_EXIT_CODE` si `cancel_event` (GUI) a été levé.
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install = InstallPaths.under(root)

    reporter.header(_("Updating S.T.A.L.K.E.R. G.A.M.M.A. in {root}").format(root=root))
    try:
        reporter.step("1/3", _("G.A.M.M.A modpack (incremental download)…"))
        engine.update_gamma(install, on_progress=reporter.progress, cancel_event=cancel_event)
        reporter.step("2/3", _("Removing ReShade + purging the shader cache…"))
        engine.remove_reshade(install, on_progress=reporter.progress, cancel_event=cancel_event)
        engine.purge_shader_cache(
            install, on_progress=reporter.progress, cancel_event=cancel_event
        )
        reporter.step("3/3", _("Verification (MD5 of mod archives)…"))
        unverifiable = engine.verify(
            install, on_progress=reporter.progress, cancel_event=cancel_event
        )
    except EngineCancelledError:
        reporter.warn(_("Update cancelled."))
        return CANCELLED_EXIT_CODE
    except EngineError as error:
        reporter.error(str(error))
        return 1

    state_module.mark_done(root, "gamma")
    if unverifiable:
        # Pas un échec : toutes les archives locales vérifiables sont conformes,
        # seules ces entrées n'ont pas pu être comparées à ModDB (page modifiée
        # ou throttling Cloudflare). Voir engine.runner.verify.
        details = "\n".join(f"  - {line}" for line in unverifiable)
        reporter.warn(
            _(
                "{count} archive(s) could not be verified online "
                "(ModDB page changed or Cloudflare throttling) — no local "
                "corruption detected:\n{details}\n"
                "Run an update again later for a complete verification."
            ).format(count=len(unverifiable), details=details)
        )
    reporter.success(
        _(
            "\nUpdate complete.\nReminders: if a custom profile or executable "
            "changed upstream, retry `stalker-gamma-linux mo2 "
            "--target {root}` to check the instance; if USVFS looks dead "
            "after the update, see docs/MO2-PROTON-COMPAT.md."
        ).format(root=root)
    )
    return 0
