"""Orchestration haut-niveau des commandes d'installation et de mise à jour (T07).

`run_install` enchaîne les étapes du moteur gamma-launcher (T03), du préfixe
partagé (T04) et de l'instance MO2 (T05) pour produire une installation
jouable sous un seul répertoire racine choisi par l'utilisateur (`--target`) :
`<target>/{anomaly,gamma,cache,prefix}`. Chaque étape est marquée dans l'état
persisté (`state.py`) : une relance après interruption saute les étapes déjà
validées. Le lancement au quotidien (MO2/USVFS) reste dans `mo2/` (commandes
`mo2`/`play`).

`run_update` fait deux choses de plus depuis T17, et l'ordre compte : il met à
l'abri ce qui ne se retélécharge pas (`backups.protect_before_update`) **avant**
de lancer le moteur, puis rejoue par-dessus la liste amont fraîchement écrite
les écarts du joueur (`mo2.modlist_sync.merge_upstream_modlist`). La sauvegarde
rend la perte réversible ; la fusion fait qu'elle n'a pas lieu.

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

from stalker_gamma_linux import backups, engine, output
from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.backups.errors import BackupError
from stalker_gamma_linux.desktop import install_shortcut
from stalker_gamma_linux.desktop.errors import DesktopError
from stalker_gamma_linux.engine.errors import EngineCancelledError, EngineError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment.report import (
    DEFAULT_INSTALL_TARGET,
    build_report,
    format_report,
)
from stalker_gamma_linux.exit_codes import CANCELLED_EXIT_CODE
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2 import instance, modlist_sync
from stalker_gamma_linux.mo2.errors import Mo2Error, ModlistSyncError
from stalker_gamma_linux.mo2.modlist_merge import MergeOutcome
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.session import resolve_anomaly
from stalker_gamma_linux.prefix import provision, session
from stalker_gamma_linux.prefix.errors import PrefixBusyError, PrefixCancelledError, PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths

_RESUME_HINT_TEMPLATE = _(
    "Retry `stalker-gamma-linux install --target {root}`: resuming skips steps already validated."
)


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
    force: bool = False,
    only: Sequence[str] | None = None,
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
    voir `prefix.proton.ensure_proton`. `force` : démarre malgré des prérequis
    manquants (voir `EnvironmentReport.install_blockers`) — sinon on retourne 1
    sans rien télécharger.

    `only` (optionnel) : ne joue que les étapes nommées, et les joue **même si
    elles sont déjà marquées faites**. Sert au dépannage — « relance juste le
    préfixe et envoie-moi le journal » — au lieu de faire rejouer un pipeline
    de 146 Gio pour reproduire un problème sur une seule étape. Les étapes non
    citées ne sont ni exécutées ni démarquées.
    """
    unknown = sorted(set(only or ()) - set(state_module.STEPS))
    if unknown:
        reporter.error(
            _("Unknown step(s): {unknown}. Valid steps: {steps}").format(
                unknown=", ".join(unknown), steps=", ".join(state_module.STEPS)
            )
        )
        return 1

    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install = InstallPaths.under(root)
    prefix_paths = PrefixPaths.under(root)
    mo2_paths = Mo2Paths.under(root)

    reporter.header(_("Installing S.T.A.L.K.E.R. G.A.M.M.A. in {root}").format(root=root))

    env_report = build_report(root)
    blockers = env_report.install_blockers
    if blockers and not force:
        # Historiquement on se contentait d'avertir puis on démarrait quand même :
        # une install de ~146 Gio partait avec 10 Gio libres et mourait des heures
        # plus tard en plein téléchargement. La GUI, elle, bloquait déjà. On
        # échoue maintenant tout de suite, avec le plan d'installation à suivre.
        reporter.error(
            _("Missing prerequisites — the install cannot succeed:\n") + format_report(env_report),
            hint=_(
                "Fix the items above, then rerun. To start anyway (at your own "
                "risk): `stalker-gamma-linux install --force`."
            ),
        )
        return 1
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
        if only is not None:
            # Rejeu ciblé : l'étape demandée tourne **même si elle est marquée
            # faite** (c'est tout l'intérêt — « relance juste le préfixe »), et
            # les autres ne sont ni jouées ni touchées.
            if step_name not in only:
                reporter.skip(index, label)
                return
        elif state.is_done(step_name):
            reporter.skip(index, label)
            return
        if cancel_event is not None and cancel_event.is_set():
            raise _InstallCancelledError
        reporter.step(index, f"{label}…")
        action()
        state = state_module.mark_done(root, step_name)

    def remove_reshade_and_purge() -> None:
        engine.remove_reshade(install, on_progress=reporter.progress, cancel_event=cancel_event)
        engine.purge_shader_cache(install, on_progress=reporter.progress, cancel_event=cancel_event)

    def ensure_prefix() -> None:
        # Le rejeu ciblé (`install --only prefix`) est l'usage de dépannage visé
        # ici, mais le garde s'applique à toute exécution de cette étape : sans
        # danger sur une install neuve, indispensable sur un rejeu. Voir
        # `prefix.session`.
        session.require_free(prefix_paths, action=_("provisioning the prefix"), force=force)
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
        # Instantané pris ici, et nulle part ailleurs : le profil vient d'être
        # écrit par le moteur, donc `modlist.txt` EST la liste amont. Le
        # prendre plus tard enregistrerait la liste du joueur comme référence
        # amont, et la première fusion ne verrait plus aucun de ses écarts.
        _record_modlist_snapshot(root, reporter=reporter)

    try:
        run_step(1, "anomaly", install_anomaly)
        run_step(2, "gamma", install_gamma)
        run_step(3, "reshade", remove_reshade_and_purge)
        run_step(4, "prefix", ensure_prefix)
        run_step(5, "mo2", configure_mo2)
        # `--only shortcut` vaut demande explicite : inutile d'exiger en plus
        # `--shortcut`, qui ne sert qu'à l'ajouter à un pipeline complet.
        if shortcut or (only is not None and "shortcut" in only):
            run_step(6, "shortcut", create_shortcut)
    except (_InstallCancelledError, EngineCancelledError, PrefixCancelledError):
        reporter.warn(_("Installation cancelled."))
        return CANCELLED_EXIT_CODE
    except (EngineError, PrefixError, Mo2Error, DesktopError) as error:
        reporter.error(str(error), hint=_RESUME_HINT_TEMPLATE.format(root=root))
        return 1

    if only is not None:
        # Pas de « installation terminée » sur un rejeu ciblé : l'installation
        # n'a pas été jouée en entier, et le dire serait mentir.
        reporter.success(_("\nStep(s) replayed: {steps}.").format(steps=", ".join(only)))
        return 0

    reporter.success(
        _(
            "\nInstallation complete. Next steps:\n"
            "  stalker-gamma-linux mo2  --target {root}   # open Mod Organizer 2\n"
            "  stalker-gamma-linux play --target {root}   # play (Anomaly via MO2, USVFS)"
        ).format(root=root)
    )
    return 0


def update_phase_labels(*, merge_modlist: bool = True) -> tuple[str, ...]:
    """Libellés des étapes de `run_update`, alignés sur sa numérotation `n/total`.

    Exposé pour que la GUI dessine sa timeline sans redériver la liste (même
    contrat que `integrity.verify_phase_labels`).
    """
    merge = (_("Reapplying your mod list"),) if merge_modlist else ()
    return (
        _("G.A.M.M.A modpack (incremental download)"),
        *merge,
        _("Removing ReShade + purging the shader cache"),
        _("Verification (MD5 of mod archives)"),
    )


def _record_modlist_snapshot(root: Path, *, reporter: output.Reporter) -> None:
    """Enregistre la liste amont de référence. Un échec n'arrête jamais le pipeline."""
    try:
        modlist_sync.record_upstream_snapshot(root)
    except ModlistSyncError as error:
        reporter.warn(str(error))


def _merge_player_modlist(
    root: Path, previous_text: str | None, *, reporter: output.Reporter
) -> MergeOutcome | None:
    """Rejoue les écarts du joueur sur la liste amont. Ne fait jamais échouer l'update.

    À ce point, la mise à jour a réussi et la sauvegarde d'avant-update est en
    place : ce qui se joue ici est un confort, pas une donnée. Une abstention
    (`merged=False`) comme une erreur d'écriture sortent donc en avertissement,
    avec de quoi agir — l'utilisateur garde l'amont et sa sauvegarde.
    """
    if previous_text is None:
        # Il n'y avait pas de liste avant (install neuve, profil absent) : rien
        # n'a été perdu, donc rien à signaler. On se contente d'enregistrer la
        # référence pour que la *prochaine* mise à jour, elle, puisse fusionner.
        _record_modlist_snapshot(root, reporter=reporter)
        return None
    try:
        outcome = modlist_sync.merge_upstream_modlist(root, previous_text)
    except ModlistSyncError as error:
        reporter.warn(str(error))
        return None
    if not outcome.merged:
        reporter.warn(
            _(
                "Mod list left as upstream wrote it: {reason}.\n"
                "Your previous list is in the backup written just before this update."
            ).format(reason=outcome.reason)
        )
        return outcome
    reporter.progress(outcome.report)
    return outcome


def run_update(
    target: Path | None = None,
    *,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
    force: bool = False,
    merge_modlist: bool = True,
) -> int:
    """Met à jour le modpack GAMMA, retire ReShade et re-vérifie l'installation.

    `full-install` (via `update_gamma`, alias documenté) ne retélécharge que ce
    qui a changé en amont ; `verify` re-contrôle l'intégrité des archives de
    mods (`check-md5`). Retourne 0 au succès, 1 si une étape échoue,
    `CANCELLED_EXIT_CODE` si `cancel_event` (GUI) a été levé. Refuse de démarrer
    si MO2 ou le jeu tournent dans le préfixe partagé (`force` passe outre) —
    voir `prefix.session`.

    `merge_modlist` (défaut) rejoue ensuite les écarts du joueur sur la liste
    amont fraîchement écrite (T17). `--no-merge` le désactive et rend le
    comportement historique — écrasement amont + sauvegarde — sans rien perdre
    de la sauvegarde ni de l'instantané : la fusion est un défaut, pas une
    obligation.
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    install = InstallPaths.under(root)

    reporter.header(_("Updating S.T.A.L.K.E.R. G.A.M.M.A. in {root}").format(root=root))

    try:
        session.require_free(PrefixPaths.under(root), action=_("updating"), force=force)
    except PrefixBusyError as error:
        reporter.error(str(error))
        return 1

    # Lu **avant** le moteur : c'est le `ours` de la fusion à trois voies, et
    # dans quelques minutes ce fichier aura été remplacé par la liste amont.
    try:
        player_modlist = modlist_sync.read_verbatim(modlist_sync.modlist_path(root))
    except ModlistSyncError as error:
        reporter.warn(str(error))
        player_modlist = None

    try:
        backups.protect_before_update(root, reporter=reporter)
    except BackupError as error:
        # Refuser d'avancer : mieux vaut ne pas mettre à jour que de perdre une
        # liste de mods — ou des parties — sans filet.
        reporter.error(
            str(error),
            hint=_("Free some space or check permissions, then try again."),
        )
        return 1

    labels = update_phase_labels(merge_modlist=merge_modlist)
    total = len(labels)
    try:
        reporter.step(f"1/{total}", _("G.A.M.M.A modpack (incremental download)…"))
        engine.update_gamma(install, on_progress=reporter.progress, cancel_event=cancel_event)
        if merge_modlist:
            reporter.step(f"2/{total}", _("Reapplying your mod list (three-way merge)…"))
            _merge_player_modlist(root, player_modlist, reporter=reporter)
        else:
            # Même sans fusion, la référence amont est mise à jour : sinon un
            # `--no-merge` isolé rendrait fausse la fusion de la fois suivante.
            _record_modlist_snapshot(root, reporter=reporter)
        reporter.step(f"{total - 1}/{total}", _("Removing ReShade + purging the shader cache…"))
        engine.remove_reshade(install, on_progress=reporter.progress, cancel_event=cancel_event)
        engine.purge_shader_cache(install, on_progress=reporter.progress, cancel_event=cancel_event)
        reporter.step(f"{total}/{total}", _("Verification (MD5 of mod archives)…"))
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
