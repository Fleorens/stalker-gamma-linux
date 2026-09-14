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
from datetime import UTC, datetime
from pathlib import Path

from stalker_gamma_linux import backups, engine, output
from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.backups.errors import BackupError
from stalker_gamma_linux.desktop import install_shortcut
from stalker_gamma_linux.desktop.errors import DesktopError
from stalker_gamma_linux.engine.errors import (
    DepositMismatchError,
    EngineCancelledError,
    EngineError,
    EngineExecutionError,
)
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment.report import (
    DEFAULT_INSTALL_TARGET,
    build_report,
    format_report,
)
from stalker_gamma_linux.exit_codes import CANCELLED_EXIT_CODE
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.integrity import repair
from stalker_gamma_linux.integrity.scan import hash_file
from stalker_gamma_linux.mo2 import instance, modlist_sync
from stalker_gamma_linux.mo2.errors import Mo2Error, ModlistSyncError
from stalker_gamma_linux.mo2.modlist_merge import MergeOutcome
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.session import resolve_anomaly
from stalker_gamma_linux.prefix import provision, session
from stalker_gamma_linux.prefix.errors import PrefixBusyError, PrefixCancelledError, PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.steam.errors import NoSteamAccountError, SteamError
from stalker_gamma_linux.steam.install import add_shortcut as add_steam_shortcut

_RESUME_HINT_TEMPLATE = _(
    "Retry `stalker-gamma-linux install --target {root}`: resuming skips steps already validated."
)


class _InstallCancelledError(Exception):
    """Signal interne : `cancel_event` était déjà levé avant de démarrer une étape."""


def run_install(
    target: Path | None = None,
    *,
    shortcut: bool = False,
    steam: bool = False,
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
    raccourci bureau (si `shortcut`) → entrée Steam (si `steam`). Reprend après
    interruption : chaque étape déjà validée (état persisté sous
    `~/.config/stalker-gamma-linux/`) est sautée. Retourne 0 au succès, 1 si
    une étape échoue (message actionnable déjà affiché par l'erreur d'origine),
    `CANCELLED_EXIT_CODE` si `cancel_event` (GUI) a été levé pendant une étape
    — l'étape en cours n'est pas marquée faite, une relance la rejoue.
    `proton_release` (optionnel, préférence GUI) : voir
    `prefix.proton.ensure_proton`. `force` : démarre malgré des prérequis
    manquants (voir `EnvironmentReport.install_blockers`) — sinon on retourne 1
    sans rien télécharger ; il passe aussi outre le refus d'écrire dans Steam
    pendant que Steam tourne.

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
    # `--only <étape optionnelle>` vaut demande explicite : inutile d'exiger en
    # plus `--shortcut`/`--steam-shortcut`, qui ne servent qu'à l'ajouter à un
    # pipeline complet.
    asked = set(only or ())
    want_shortcut = shortcut or "shortcut" in asked
    want_steam = steam or "steam" in asked
    planned = state_module.planned_steps(shortcut=want_shortcut, steam=want_steam)

    def run_step(step_name: str, action: Callable[[], None]) -> None:
        nonlocal state
        label = state_module.STEP_LABELS[step_name]
        index = f"{planned.index(step_name) + 1}/{len(planned)}"
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

    def create_steam_shortcut() -> None:
        # Steam ouvert = on n'écrit pas : il réécrirait `shortcuts.vdf` en
        # quittant et effacerait l'entrée sans le moindre message. `force`
        # passe outre, comme pour le préfixe.
        if not add_steam_shortcut(root, force=force):
            # Aucun compte Steam : l'étape n'a rien à faire, mais se taire
            # laisserait croire que l'entrée est là. Un avertissement, pas une
            # erreur — le reste de l'installation est valide.
            reporter.warn(str(NoSteamAccountError()))

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
        run_step("anomaly", install_anomaly)
        run_step("gamma", install_gamma)
        run_step("reshade", remove_reshade_and_purge)
        run_step("prefix", ensure_prefix)
        run_step("mo2", configure_mo2)
        if want_shortcut:
            run_step("shortcut", create_shortcut)
        if want_steam:
            run_step("steam", create_steam_shortcut)
    except (_InstallCancelledError, EngineCancelledError, PrefixCancelledError):
        reporter.warn(_("Installation cancelled."))
        return CANCELLED_EXIT_CODE
    except EngineExecutionError as error:
        # `anomaly-install`/`full-install` n'a aucune option pour sauter un mod
        # et continuer (`launcher/commands/install.py:_install_mods` n'a pas le
        # garde-fou par-mod de `check-md5`) : un mod en échec arrête toujours
        # tout le pipeline ici, on ne prétend pas le contraire. Ce qu'on peut
        # faire, c'est le dire clairement et le mémoriser pour `--retry-failed`.
        if error.mod_name is not None:
            state_module.record_failure(root, _failure_from_error(error))
        reporter.error(str(error), hint=_RESUME_HINT_TEMPLATE.format(root=root))
        _warn_known_failures(root, reporter=reporter)
        return 1
    except (EngineError, PrefixError, Mo2Error, DesktopError, SteamError) as error:
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
            "  stalker-gamma-linux play --target {root}   # play (Anomaly via MO2, USVFS)\n"
            "\n"
            "Your first playthrough will stutter while it compiles shaders — "
            "that's normal and won't happen again (the cache lives under "
            "{root}/cache/shaders and survives prefix repairs/updates)."
        ).format(root=root)
    )
    _warn_known_failures(root, reporter=reporter)
    return 0


def _failure_from_error(error: EngineExecutionError) -> state_module.FailedMod:
    """Construit l'enregistrement d'échec à partir d'une `EngineExecutionError` déjà typée.

    N'est appelé que lorsque `error.mod_name` est connu (voir `engine.runner._install`) —
    les échecs sans mod identifié (annulation, prérequis manquant, panne du
    binaire lui-même) n'ont rien à faire dans la liste que `--retry-failed` rejoue.
    """
    assert error.mod_name is not None
    return state_module.FailedMod(
        name=error.mod_name,
        cause=error.cause.name if error.cause is not None else "unknown",
        detail=str(error),
        recorded_at=datetime.now(UTC).isoformat(),
        archive_name=error.archive_name or "",
        expected_md5=error.expected_md5 or "",
    )


def _warn_known_failures(root: Path, *, reporter: output.Reporter) -> None:
    """Rappel de fin de commande : ce qui est encore en échec, s'il y en a.

    Muet si `state.load_failures` est vide — la grande majorité des commandes,
    qui n'en ont jamais eu ou les ont déjà résolus via `--retry-failed`.
    """
    failures = state_module.load_failures(root)
    if failures:
        reporter.warn(state_module.format_failures(failures))


def run_retry_failed(
    target: Path | None = None,
    *,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
) -> int:
    """`install --retry-failed` : ne rejoue que les mods enregistrés en échec (T22).

    Réutilise tel quel le mécanisme de `integrity.repair` (T12, déjà celui de
    `verify --repair`) : retirer le dossier du mod et son archive en cache,
    puis relancer `full-install`, qui ne réinstalle que ce qui manque. Comme
    pour `verify --repair`, ce rejeu délègue à `full-install`, qui ré-extrait
    **tout** le modpack par-dessus l'existant — d'autres mods peuvent être mis
    à jour au passage, ce n'est pas une opération strictement chirurgicale
    (voir docs/ARCHITECTURE.md).

    Avant de relancer le moteur, vérifie le MD5 de chaque fichier déposé à la
    main dont on connaît le MD5 attendu (rare avec la sortie actuelle de
    gamma-launcher, voir `engine.runner._MD5_HINT_RE`) : un dépôt qui ne
    correspond pas est refusé avec un message clair plutôt que laissé au
    moteur, qui le retélécharge en silence sans jamais le dire.

    Un mod encore en échec après ce rejeu est réenregistré avec sa nouvelle
    cause ; un mod absent de la sortie (donc réinstallé avec succès, ou déjà
    présent) est retiré de la liste.
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    failures = state_module.load_failures(root)
    if not failures:
        reporter.warn(_("No failed mod recorded for {root} — nothing to retry.").format(root=root))
        return 0

    reporter.header(
        _("Retrying {count} failed mod(s) in {root}").format(count=len(failures), root=root)
    )
    reporter.progress("\n".join(f"  - {failure.name} ({failure.cause})" for failure in failures))

    try:
        session.require_free(PrefixPaths.under(root), action=_("retrying failed mods"), force=False)
    except PrefixBusyError as error:
        reporter.error(str(error))
        return 1

    mismatch = _check_deposited_files(root, failures)
    if mismatch is not None:
        reporter.error(str(mismatch))
        return 1

    names = tuple(failure.name for failure in failures)
    reporter.step("1/2", _("Removing local remnants of the failed mod(s)…"))
    repair.remove_mods(root, names, reporter=reporter)

    reporter.step("2/2", _("Reinstalling with the engine…"))
    try:
        repair.reinstall_mods(root, reporter=reporter, cancel_event=cancel_event)
    except EngineExecutionError as error:
        if error.mod_name is not None:
            state_module.record_failure(root, _failure_from_error(error))
        reporter.error(str(error))
        return 1
    except EngineCancelledError:
        reporter.warn(_("Retry cancelled."))
        return CANCELLED_EXIT_CODE
    except EngineError as error:
        reporter.error(str(error))
        return 1

    for name in names:
        state_module.clear_failure(root, name)
    reporter.success(
        _("{count} mod(s) reinstalled: {names}").format(count=len(names), names=", ".join(names))
    )
    return 0


def _check_deposited_files(
    root: Path, failures: Sequence[state_module.FailedMod]
) -> DepositMismatchError | None:
    """Vérifie le MD5 des fichiers déposés à la main dont le MD5 attendu est connu.

    Ne touche à rien : une seule incohérence bloque tout le rejeu, plutôt que
    de laisser `full-install` retélécharger silencieusement un fichier que
    l'utilisateur pensait avoir corrigé.
    """
    downloads = InstallPaths.under(root).downloads
    for failure in failures:
        if not failure.archive_name or not failure.expected_md5:
            continue
        path = downloads / failure.archive_name
        if not path.is_file():
            continue
        actual, _size = hash_file(path)
        if actual.lower() != failure.expected_md5.lower():
            return DepositMismatchError(failure.name, path, failure.expected_md5, actual)
    return None


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
