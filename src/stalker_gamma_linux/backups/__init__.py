"""Sauvegarde et restauration de ce que l'utilisateur ne peut pas retélécharger (T17).

Le wiki officiel de G.A.M.M.A. le dit lui-même : « *every time you click
Install / Update GAMMA, your modlist, settings, and mod settings will reset.
This is on purpose […] remember to make backups before clicking that button* ».
Sous Windows, la réponse tient donc en un conseil que personne n'applique.

Ce paquet en fait une commande : `backup` met à l'abri les profils MO2, les
sauvegardes de partie et l'`overwrite/` de l'instance ; `backup --list` dit ce
qui existe ; `restore <id>` remet en place — après avoir sauvegardé l'état
courant. La rotation empêche `<root>/backups/` de grossir indéfiniment, et une
sauvegarde créée explicitement n'en fait jamais les frais.

La seconde moitié de T17 — la fusion à trois voies de `modlist.txt`, qui évite
la perte au lieu de la rendre réversible — vit dans `mo2/modlist_merge.py` et
`mo2/modlist_sync.py` ; seul l'instantané de la liste amont est rangé ici
(`paths.upstream_modlist_snapshot`), parce qu'il protège la même chose et doit
suivre l'installation.
"""

from stalker_gamma_linux.backups.create import backup_id, create_backup
from stalker_gamma_linux.backups.errors import (
    BackupError,
    BackupNotFoundError,
    BackupWriteError,
    ManifestError,
    NothingToBackUpError,
    RestoreError,
)
from stalker_gamma_linux.backups.listing import (
    Listing,
    StoredBackup,
    describe_sets,
    find_backup,
    format_listing,
    format_size,
    list_backups,
)
from stalker_gamma_linux.backups.manifest import (
    Manifest,
    ManifestEntry,
    legacy_manifest,
    parse_backup_name,
    read_manifest,
    write_manifest,
)
from stalker_gamma_linux.backups.paths import (
    ALL_SETS,
    SET_LABELS,
    BackupSet,
    SourceEntry,
    backups_root,
    candidate_sources,
    existing_sources,
    upstream_modlist_snapshot,
)
from stalker_gamma_linux.backups.restore import (
    RestoreAction,
    RestorePlan,
    apply_restore_plan,
    build_restore_plan,
    format_plan,
)
from stalker_gamma_linux.backups.rotation import DEFAULT_KEEP, RotationResult, rotate, surplus
from stalker_gamma_linux.backups.session import (
    PRE_UPDATE_SETS,
    protect_before_update,
    run_backup,
    run_restore,
)

__all__ = [
    "ALL_SETS",
    "DEFAULT_KEEP",
    "PRE_UPDATE_SETS",
    "SET_LABELS",
    "BackupError",
    "BackupNotFoundError",
    "BackupSet",
    "BackupWriteError",
    "Listing",
    "Manifest",
    "ManifestEntry",
    "ManifestError",
    "NothingToBackUpError",
    "RestoreAction",
    "RestoreError",
    "RestorePlan",
    "RotationResult",
    "SourceEntry",
    "StoredBackup",
    "apply_restore_plan",
    "backup_id",
    "backups_root",
    "build_restore_plan",
    "candidate_sources",
    "create_backup",
    "describe_sets",
    "existing_sources",
    "find_backup",
    "format_listing",
    "format_plan",
    "format_size",
    "legacy_manifest",
    "list_backups",
    "parse_backup_name",
    "protect_before_update",
    "read_manifest",
    "rotate",
    "run_backup",
    "run_restore",
    "surplus",
    "upstream_modlist_snapshot",
    "write_manifest",
]
