"""`backup --list` : ce que le manifeste dit, pas ce qu'un `stat` devinerait.

Une sauvegarde est décrite par son `backup.toml` (voir `manifest.py`). Lire à
la place la date du dossier et sa taille sur le disque donnerait une date de
copie (celle du dernier `cp`, pas de la sauvegarde) et une taille qui compte
les blocs, pas les octets sauvegardés — et surtout, ça ne dirait rien de ce
qu'il y a *dedans* ni d'où ça doit revenir.

Un dossier illisible ou incohérent n'est pas silencieusement écarté : il sort
dans `unreadable`, pour que l'utilisateur voie qu'il occupe de la place et
qu'on ne sait pas la restaurer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.backups.errors import BackupNotFoundError, ManifestError
from stalker_gamma_linux.backups.manifest import Manifest, read_manifest
from stalker_gamma_linux.backups.paths import SET_LABELS, BackupSet, backups_root
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.paths_safety import unsafe_child_name_reason

_KIB = 1024
_UNITS: tuple[tuple[int, str], ...] = ((1024**3, "GiB"), (1024**2, "MiB"), (_KIB, "KiB"))


@dataclass(frozen=True, slots=True)
class StoredBackup:
    """Une sauvegarde utilisable : son dossier et ce que son manifeste annonce."""

    directory: Path
    manifest: Manifest

    @property
    def identifier(self) -> str:
        return self.manifest.identifier


@dataclass(frozen=True, slots=True)
class Listing:
    """Inventaire de `<root>/backups/` : les utilisables, et les autres."""

    backups: tuple[StoredBackup, ...]
    unreadable: tuple[tuple[Path, str], ...] = ()

    @property
    def automatic(self) -> tuple[StoredBackup, ...]:
        return tuple(backup for backup in self.backups if not backup.manifest.explicit)

    @property
    def explicit(self) -> tuple[StoredBackup, ...]:
        return tuple(backup for backup in self.backups if backup.manifest.explicit)


def list_backups(root: Path) -> Listing:
    """Inventaire de `<root>/backups/`, du plus récent au plus ancien."""
    directory = backups_root(root)
    try:
        children = sorted(child for child in directory.iterdir() if child.is_dir())
    except OSError:
        return Listing(backups=())

    backups: list[StoredBackup] = []
    unreadable: list[tuple[Path, str]] = []
    for child in children:
        try:
            backups.append(StoredBackup(directory=child, manifest=read_manifest(child)))
        except ManifestError as error:
            unreadable.append((child, error.reason))
    backups.sort(key=lambda backup: (backup.manifest.created_at, backup.identifier), reverse=True)
    return Listing(backups=tuple(backups), unreadable=tuple(unreadable))


def find_backup(root: Path, identifier: str) -> StoredBackup:
    """Sauvegarde nommée `identifier`. Lève `BackupNotFoundError` ou `ManifestError`.

    Le nom vient de la ligne de commande : il est contrôlé comme n'importe quel
    nom d'entrée sous un dossier connu (`paths_safety`), pour qu'un
    `restore ../../etc` ne puisse pas désigner autre chose qu'un enfant direct
    de `<root>/backups/`.
    """
    if unsafe_child_name_reason(identifier) is not None:
        raise BackupNotFoundError(identifier, root)
    directory = backups_root(root) / identifier
    if not directory.is_dir() or directory.is_symlink():
        raise BackupNotFoundError(identifier, root)
    return StoredBackup(directory=directory, manifest=read_manifest(directory))


def format_size(n_bytes: int) -> str:
    """« 39.2 MiB », « 812 KiB », « 0 B » — lisible à l'échelle d'une sauvegarde."""
    for threshold, unit in _UNITS:
        if n_bytes >= threshold:
            return f"{n_bytes / threshold:.1f} {unit}"
    return f"{n_bytes} B"


def describe_sets(sets: tuple[BackupSet, ...]) -> str:
    return ", ".join(SET_LABELS[name] for name in sets)


def format_listing(root: Path, listing: Listing) -> str:
    """Rendu texte de `backup --list`, y compris ce qui n'est pas lisible."""
    if not listing.backups and not listing.unreadable:
        return _(
            "No backup under {path} yet.\n"
            "One is written automatically before each update; create one now "
            "with `stalker-gamma-linux backup`."
        ).format(path=backups_root(root))

    lines = [_("Backups under {path}:").format(path=backups_root(root)), ""]
    for backup in listing.backups:
        lines.extend(_format_entry(backup))
    if listing.unreadable:
        lines.append(_("Folders that are not usable backups:"))
        lines.extend(f"  - {path.name}: {reason}" for path, reason in listing.unreadable)
        lines.append("")
    lines.append(
        _("Restore one with: stalker-gamma-linux restore <id> --target {root}").format(root=root)
    )
    return "\n".join(lines)


def _format_entry(backup: StoredBackup) -> list[str]:
    manifest = backup.manifest
    kind = _("kept (created by you)") if manifest.explicit else _("automatic")
    lines = [
        _("  {identifier}   {date}   [{kind}]").format(
            identifier=manifest.identifier,
            date=f"{manifest.created_at:%Y-%m-%d %H:%M}",
            kind=kind,
        ),
        _("      holds: {sets}").format(sets=describe_sets(manifest.sets)),
    ]
    if manifest.legacy:
        # Sauvegarde d'avant le manifeste : dire ce qu'on sait, et seulement ça.
        lines.append(_("      (written before this tool recorded manifests — size unknown)"))
    else:
        lines.append(
            _("      {files} files, {size}").format(
                files=manifest.file_count, size=format_size(manifest.size_bytes)
            )
        )
    if manifest.gamma_version:
        lines.append(
            _("      G.A.M.M.A definition {version}").format(version=manifest.gamma_version)
        )
    lines.append("")
    return lines
