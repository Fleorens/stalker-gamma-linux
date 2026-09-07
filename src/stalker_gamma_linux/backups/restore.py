"""Remise en place d'une sauvegarde : un plan, puis un échange de dossiers.

Deux règles portées ici, et une troisième dans `session.py` :

1. **Le manifeste dit où ça va.** Chaque ensemble a été copié depuis un
   emplacement précis (voir `paths.py` et le constat sur les sauvegardes de
   partie) ; c'est cet emplacement, enregistré au moment de la copie, qui est
   réécrit. Rien n'est redérivé de la configuration MO2 du jour.
2. **Jamais de mutation en place.** Chaque destination est reconstruite à
   côté (`<dest>.sgl-restore-tmp`), puis échangée par deux `rename` :
   l'ancienne arborescence est mise de côté avant que la neuve prenne sa
   place, et elle est remise si l'échange échoue. À aucun moment le dossier
   du joueur n'est vidé pour être recopié par-dessus.
3. (`session.py`) l'état courant est sauvegardé **avant** toute restauration :
   une restauration ratée ne doit pas être un aller simple.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.backups.errors import ManifestError, RestoreError
from stalker_gamma_linux.backups.listing import StoredBackup, describe_sets, format_size
from stalker_gamma_linux.backups.manifest import LEGACY_SLOT, ManifestEntry, manifest_path
from stalker_gamma_linux.backups.paths import SET_LABELS
from stalker_gamma_linux.i18n import _

_TMP_SUFFIX = ".sgl-restore-tmp"
_OLD_SUFFIX = ".sgl-restore-old"


@dataclass(frozen=True, slots=True)
class RestoreAction:
    """Un dossier à remettre en place : d'où il sort, où il va, ce qu'il remplace."""

    entry: ManifestEntry
    source: Path
    destination: Path
    replaces_existing: bool

    @property
    def label(self) -> str:
        return SET_LABELS[self.entry.set_name]


@dataclass(frozen=True, slots=True)
class RestorePlan:
    root: Path
    backup: StoredBackup
    actions: tuple[RestoreAction, ...]


def build_restore_plan(root: Path, backup: StoredBackup) -> RestorePlan:
    """Décide ce qui serait réécrit. Ne touche à rien. Lève `ManifestError` si incohérent."""
    actions: list[RestoreAction] = []
    for entry in backup.manifest.entries:
        source = backup.directory if entry.slot == LEGACY_SLOT else backup.directory / entry.slot
        if not source.is_dir():
            raise ManifestError(
                manifest_path(backup.directory),
                _("the backup announces « {slot} » but that folder is missing").format(
                    slot=entry.slot
                ),
            )
        destination = root / entry.destination
        actions.append(
            RestoreAction(
                entry=entry,
                source=source,
                destination=destination,
                replaces_existing=destination.exists() or destination.is_symlink(),
            )
        )
    return RestorePlan(root=root, backup=backup, actions=tuple(actions))


def format_plan(plan: RestorePlan) -> str:
    """Ce que la restauration écrirait — le texte de `restore --dry-run`."""
    manifest = plan.backup.manifest
    lines = [
        _("Backup {identifier} ({date})").format(
            identifier=manifest.identifier, date=f"{manifest.created_at:%Y-%m-%d %H:%M}"
        ),
        _("  holds: {sets}").format(sets=describe_sets(manifest.sets)),
    ]
    if manifest.gamma_version:
        lines.append(
            _("  G.A.M.M.A definition at backup time: {version}").format(
                version=manifest.gamma_version
            )
        )
    lines.extend(["", _("The following would be replaced:"), ""])
    for action in plan.actions:
        state = (
            _("replaces the current folder")
            if action.replaces_existing
            else _("creates it (nothing there today)")
        )
        size = "" if plan.backup.manifest.legacy else f" — {format_size(action.entry.size_bytes)}"
        lines.append(f"  - {action.label}{size}")
        lines.append(f"      {action.destination}  ({state})")
    return "\n".join(lines)


def apply_restore_plan(plan: RestorePlan) -> tuple[Path, ...]:
    """Remet chaque ensemble en place. Retourne les destinations réécrites.

    Lève `RestoreError` à la première destination qui résiste : la précédente
    est déjà en place et la sauvegarde de sécurité (voir `session.py`) permet
    de revenir en arrière — continuer à écrire par-dessus une erreur donnerait
    un état à moitié restauré sans le dire.
    """
    written: list[Path] = []
    for action in plan.actions:
        try:
            _replace_tree(action.source, action.destination)
        except OSError as error:
            raise RestoreError(action.destination, error) from error
        written.append(action.destination)
    return tuple(written)


def _replace_tree(source: Path, destination: Path) -> None:
    """Remplace l'arborescence `destination` par une copie de `source`, sans la vider.

    L'ordre compte : on construit d'abord la copie complète à côté, et
    seulement ensuite on échange. Un échec de copie (disque plein) laisse donc
    le dossier du joueur intact, et un échec du second `rename` le remet.
    """
    temporary = destination.with_name(destination.name + _TMP_SUFFIX)
    previous = destination.with_name(destination.name + _OLD_SUFFIX)
    shutil.rmtree(temporary, ignore_errors=True)
    shutil.rmtree(previous, ignore_errors=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, temporary, symlinks=True)

    replaced = destination.exists() or destination.is_symlink()
    if replaced:
        destination.rename(previous)
    try:
        temporary.rename(destination)
    except OSError:
        if replaced:
            previous.rename(destination)
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    shutil.rmtree(previous, ignore_errors=True)
