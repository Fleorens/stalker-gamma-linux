"""Commandes `backup [--list]` et `restore <id>` : le seul point d'entrée.

Partagé mot pour mot par la CLI et par la vue Diagnostic de la GUI
(`output.Reporter`, comme `integrity.session`) : la GUI ne réimplémente rien,
elle fournit un reporter qui pousse vers ses widgets.

Trois invariants portés ici :

1. **Une restauration commence par une sauvegarde.** L'état courant est copié
   avant d'être écrasé, sur les mêmes ensembles que ceux qu'on remet — sinon
   une restauration sur le mauvais identifiant serait un aller simple.
2. **Rien ne bouge pendant que MO2 ou le jeu tournent.** `prefix.session.
   require_free` est déjà le verrou du projet (T13) ; `--force` passe outre,
   comme partout ailleurs.
3. **La rotation ne fait jamais échouer l'opération.** Elle est rapportée,
   pas fatale : ne pas avoir pu purger une vieille copie n'invalide pas la
   sauvegarde qu'on vient d'écrire.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux import output
from stalker_gamma_linux.backups.create import create_backup
from stalker_gamma_linux.backups.errors import BackupError, NothingToBackUpError
from stalker_gamma_linux.backups.listing import (
    describe_sets,
    find_backup,
    format_listing,
    format_size,
    list_backups,
)
from stalker_gamma_linux.backups.manifest import Manifest
from stalker_gamma_linux.backups.paths import ALL_SETS, BackupSet
from stalker_gamma_linux.backups.restore import apply_restore_plan, build_restore_plan, format_plan
from stalker_gamma_linux.backups.rotation import DEFAULT_KEEP, rotate
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.prefix.errors import PrefixBusyError
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.session import require_free

# Ce qu'on met à l'abri automatiquement avant une mise à jour. Les profils
# parce que `full-install` les réécrit — c'est le motif d'origine. Les parties
# parce que la même mise à jour appelle `purge-shader-cache`, donc un `rmtree`
# amont **dans `appdata/`**, à côté de `savedgames/` : quelques dizaines de Mio
# pour couvrir la seule donnée du joueur qui ne se retélécharge pas.
PRE_UPDATE_SETS: tuple[BackupSet, ...] = (BackupSet.PROFILES, BackupSet.SAVES)


def run_backup(
    target: Path | None = None,
    *,
    sets: tuple[BackupSet, ...] = ALL_SETS,
    list_only: bool = False,
    keep: int = DEFAULT_KEEP,
    reporter: output.Reporter = output.console_reporter,
) -> int:
    """Commande `backup`. 0 au succès, 1 si rien n'a pu être sauvegardé.

    Une sauvegarde créée ici est **explicite** : l'utilisateur l'a demandée,
    elle ne part jamais à la rotation (voir `rotation.py`).
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    if list_only:
        reporter.progress(format_listing(root, list_backups(root)))
        return 0

    reporter.header(_("Backing up what cannot be downloaded again, from {root}").format(root=root))
    try:
        directory, manifest = create_backup(root, sets=sets, explicit=True)
    except NothingToBackUpError as error:
        reporter.error(str(error))
        return 1
    except BackupError as error:
        reporter.error(str(error))
        return 1

    reporter.progress(_summary(manifest, directory))
    _report_rotation(root, keep=keep, reporter=reporter)
    reporter.success(
        _(
            "Backup complete.\n"
            "Put it back with: stalker-gamma-linux restore {identifier} --target {root}"
        ).format(identifier=manifest.identifier, root=root)
    )
    return 0


def run_restore(
    identifier: str,
    target: Path | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
    keep: int = DEFAULT_KEEP,
    reporter: output.Reporter = output.console_reporter,
) -> int:
    """Commande `restore <id>`. 0 au succès, 1 sinon."""
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    try:
        backup = find_backup(root, identifier)
        plan = build_restore_plan(root, backup)
    except BackupError as error:
        reporter.error(str(error))
        return 1

    reporter.header(
        _("Restoring backup {identifier} into {root}").format(identifier=identifier, root=root)
    )
    reporter.progress(format_plan(plan))

    if dry_run:
        reporter.success(_("\nDry run: nothing was written."))
        return 0

    try:
        require_free(PrefixPaths.under(root), action=_("restoring a backup"), force=force)
    except PrefixBusyError as error:
        reporter.error(str(error))
        return 1

    # Le filet du filet : l'état courant part dans une sauvegarde automatique
    # avant d'être remplacé. Sans elle, restaurer le mauvais identifiant
    # coûterait exactement ce que cette commande existe pour éviter.
    try:
        _snapshot_current_state(root, plan.backup.manifest.sets, reporter=reporter)
        written = apply_restore_plan(plan)
    except BackupError as error:
        reporter.error(str(error))
        return 1

    for path in written:
        reporter.progress(_("Restored: {path}").format(path=path))
    _report_rotation(root, keep=keep, reporter=reporter)
    reporter.success(
        _(
            "\nRestore complete. Open Mod Organizer 2 to check the mod list "
            "(`stalker-gamma-linux mo2 --target {root}`)."
        ).format(root=root)
    )
    return 0


def protect_before_update(
    root: Path,
    *,
    keep: int = DEFAULT_KEEP,
    reporter: output.Reporter = output.console_reporter,
) -> Manifest | None:
    """Sauvegarde automatique posée avant une mise à jour. `None` s'il n'y a rien à copier.

    Lève `BackupError` si la copie échoue : l'appelant (`orchestrator.
    run_update`) refuse alors de continuer — mieux vaut ne pas mettre à jour
    que d'écraser une liste de mods sans filet.
    """
    try:
        directory, manifest = create_backup(root, sets=PRE_UPDATE_SETS, explicit=False)
    except NothingToBackUpError:
        # Rien à protéger : première installation, ou profils absents. Ce n'est
        # pas un échec — il n'y a simplement rien qui puisse être perdu.
        return None
    reporter.progress(
        _(
            "Backed up before updating: {summary}\n"
            "(the update resets the mod list to the upstream one — this is your safety net)"
        ).format(summary=_summary(manifest, directory))
    )
    _report_rotation(root, keep=keep, reporter=reporter)
    return manifest


def _snapshot_current_state(
    root: Path, sets: tuple[BackupSet, ...], *, reporter: output.Reporter
) -> None:
    try:
        directory, manifest = create_backup(root, sets=sets, explicit=False)
    except NothingToBackUpError:
        reporter.warn(_("Nothing to save before restoring — there is no current state to keep."))
        return
    reporter.progress(
        _("Current state saved first as {identifier} ({path}).").format(
            identifier=manifest.identifier, path=directory
        )
    )


def _summary(manifest: Manifest, directory: Path) -> str:
    return _("{sets} → {path} ({files} files, {size})").format(
        sets=describe_sets(manifest.sets),
        path=directory,
        files=manifest.file_count,
        size=format_size(manifest.size_bytes),
    )


def _report_rotation(root: Path, *, keep: int, reporter: output.Reporter) -> None:
    result = rotate(root, keep=keep)
    if result.removed:
        reporter.progress(result.summary)
    for identifier, reason in result.failed:
        reporter.warn(
            _("Could not remove the old backup {identifier}: {reason}").format(
                identifier=identifier, reason=reason
            )
        )
