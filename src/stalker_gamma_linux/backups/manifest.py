"""Manifeste TOML d'une sauvegarde : ce qu'elle contient, et où ça se remet.

Un petit fichier `backup.toml` à la racine de chaque sauvegarde. Il porte trois
choses qu'un `stat` du dossier ne saurait pas dire :

1. **où chaque ensemble doit être remis** — le chemin relatif à la racine
   d'installation. Redériver cette destination à la restauration reviendrait à
   deviner ce que la sauvegarde a réellement copié le jour où elle a été faite,
   alors que les emplacements dépendent de la configuration MO2 du moment ;
2. **si la sauvegarde est explicite** — celle que l'utilisateur a demandée ne
   part jamais à la rotation, contrairement à celle posée avant une mise à jour ;
3. **la version GAMMA connue** au moment de la copie : restaurer des profils
   d'une définition 890 sur une install 920 n'est pas interdit, mais il faut
   pouvoir le voir.

Les sauvegardes écrites par l'ancien `orchestrator.backup_mo2_profiles` n'ont
pas de manifeste : `legacy_manifest` en synthétise un à partir de ce qu'on sait
d'elles avec certitude (le dossier **est** une copie de `profiles/`, et son nom
porte la date). C'est de la connaissance, pas une mesure du dossier.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import tomli_w

from stalker_gamma_linux.backups.errors import ManifestError
from stalker_gamma_linux.backups.paths import (
    MANIFEST_FILENAME,
    NAME_PREFIX,
    NAME_TIME_FORMAT,
    BackupSet,
)
from stalker_gamma_linux.i18n import _

# Slot des sauvegardes historiques : le dossier de sauvegarde **est** la copie
# de `profiles/`, il n'y a pas de sous-dossier.
LEGACY_SLOT = "."


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """Un ensemble copié : son emplacement dans la sauvegarde et sa destination."""

    set_name: BackupSet
    slot: str
    # Relatif à la racine d'installation, en séparateurs POSIX.
    destination: str
    files: int = 0
    size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class Manifest:
    """Contenu d'un `backup.toml` (ou son équivalent synthétisé pour l'historique)."""

    identifier: str
    created_at: datetime
    entries: tuple[ManifestEntry, ...]
    explicit: bool = False
    gamma_version: str = ""
    tool_version: str = ""
    # Sauvegarde d'avant le manifeste : contenu déduit du nom, tailles inconnues.
    legacy: bool = False

    @property
    def sets(self) -> tuple[BackupSet, ...]:
        """Ensembles présents, dans l'ordre canonique et sans doublon."""
        seen = dict.fromkeys(entry.set_name for entry in self.entries)
        return tuple(seen)

    @property
    def size_bytes(self) -> int:
        return sum(entry.size_bytes for entry in self.entries)

    @property
    def file_count(self) -> int:
        return sum(entry.files for entry in self.entries)


def manifest_path(directory: Path) -> Path:
    return directory / MANIFEST_FILENAME


def parse_backup_name(name: str) -> datetime | None:
    """Date portée par le nom d'un dossier de sauvegarde, ou `None`.

    Tolère un suffixe après l'horodatage (`profiles-20260907-142530-2`, posé
    quand deux sauvegardes tombent dans la même seconde) : seule la partie date
    est lue.
    """
    if not name.startswith(NAME_PREFIX):
        return None
    # Découpage sur les tirets plutôt que sur une longueur calculée depuis le
    # format : `%Y%m%d-%H%M%S` fait 13 caractères mais en produit 15, et se
    # tromper d'un cran ici fait lire « 14:25:03 » là où il y a « 14:25:30 ».
    parts = name[len(NAME_PREFIX) :].split("-")
    if len(parts) < 2:
        return None
    try:
        return datetime.strptime(f"{parts[0]}-{parts[1]}", NAME_TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def write_manifest(directory: Path, manifest: Manifest) -> Path:
    """Écrit `backup.toml` dans `directory`. Retourne son chemin."""
    document = {
        "backup": {
            "id": manifest.identifier,
            "created_at": manifest.created_at.isoformat(),
            "explicit": manifest.explicit,
            "gamma_version": manifest.gamma_version,
            "tool_version": manifest.tool_version,
            "entries": [
                {
                    "set": str(entry.set_name),
                    "slot": entry.slot,
                    "destination": entry.destination,
                    "files": entry.files,
                    "size_bytes": entry.size_bytes,
                }
                for entry in manifest.entries
            ],
        }
    }
    path = manifest_path(directory)
    path.write_text(tomli_w.dumps(document), encoding="utf-8")
    return path


def read_manifest(directory: Path) -> Manifest:
    """Manifeste de `directory`, ou son équivalent historique. Lève `ManifestError`.

    Un dossier sans `backup.toml` **ni** nom horodaté reconnaissable n'est pas
    une sauvegarde : on refuse, plutôt que d'inventer une destination.
    """
    path = manifest_path(directory)
    if not path.is_file():
        legacy = legacy_manifest(directory)
        if legacy is None:
            raise ManifestError(path, _("no manifest, and the folder name carries no date"))
        return legacy
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestError(path, str(error)) from error
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(path, _("not valid TOML ({error})").format(error=error)) from error
    return _from_document(path, directory.name, data)


def legacy_manifest(directory: Path) -> Manifest | None:
    """Manifeste synthétique d'une sauvegarde d'avant T17, ou `None` si le nom ne dit rien.

    Ce qu'on sait de ces dossiers sans rien mesurer : `backup_mo2_profiles`
    faisait un `copytree(<gamma>/profiles, <root>/backups/profiles-<date>)`,
    donc le dossier **est** l'arborescence des profils, et sa date est dans son
    nom. Tailles laissées à zéro : les inventer serait un `stat` déguisé.
    """
    created_at = parse_backup_name(directory.name)
    if created_at is None:
        return None
    return Manifest(
        identifier=directory.name,
        created_at=created_at,
        entries=(
            ManifestEntry(
                set_name=BackupSet.PROFILES,
                slot=LEGACY_SLOT,
                destination="gamma/profiles",
            ),
        ),
        legacy=True,
    )


def _from_document(path: Path, identifier: str, data: dict[str, object]) -> Manifest:
    section = data.get("backup")
    if not isinstance(section, dict):
        raise ManifestError(path, _("missing [backup] section"))
    created_at = _parse_datetime(path, section.get("created_at"))
    raw_entries = section.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ManifestError(path, _("no entry: the backup does not say what it holds"))
    entries = tuple(_parse_entry(path, raw) for raw in raw_entries)
    return Manifest(
        identifier=_text(section.get("id")) or identifier,
        created_at=created_at,
        entries=entries,
        explicit=bool(section.get("explicit", False)),
        gamma_version=_text(section.get("gamma_version")),
        tool_version=_text(section.get("tool_version")),
    )


def _parse_entry(path: Path, raw: object) -> ManifestEntry:
    if not isinstance(raw, dict):
        raise ManifestError(path, _("malformed entry"))
    try:
        set_name = BackupSet(_text(raw.get("set")))
    except ValueError as error:
        raise ManifestError(
            path, _("unknown set « {set} »").format(set=_text(raw.get("set")))
        ) from error
    destination = _text(raw.get("destination"))
    reason = unsafe_destination_reason(destination)
    if reason is not None:
        raise ManifestError(path, reason)
    slot = _text(raw.get("slot"))
    if slot != LEGACY_SLOT and unsafe_destination_reason(slot) is not None:
        raise ManifestError(path, _("unusable slot « {slot} »").format(slot=slot))
    return ManifestEntry(
        set_name=set_name,
        slot=slot,
        destination=destination,
        files=_integer(raw.get("files")),
        size_bytes=_integer(raw.get("size_bytes")),
    )


def unsafe_destination_reason(destination: str) -> str | None:
    """Motif de refus d'une destination lue dans un manifeste, ou `None`.

    Le manifeste est un fichier sur le disque de l'utilisateur : il peut être
    tronqué par un disque plein, réécrit à la main, ou provenir d'une
    sauvegarde recopiée depuis ailleurs. Une destination absolue ou porteuse
    d'un `..` ferait écrire la restauration **hors** de la racine
    d'installation — même famille de risque que `paths_safety`, appliquée ici
    au chemin qui sort du fichier plutôt qu'à celui qui vient de `--target`.
    """
    if not destination:
        return _("empty destination")
    path = Path(destination)
    if path.is_absolute() or destination.startswith(("/", "\\")):
        return _("absolute destination ({path})").format(path=destination)
    if ".." in path.parts:
        return _("destination contains '..' ({path})").format(path=destination)
    if "\\" in destination or "\0" in destination:
        return _("destination contains a path separator or a NUL ({path})").format(path=destination)
    return None


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _parse_datetime(path: Path, value: object) -> datetime:
    if isinstance(value, datetime):
        # `tomllib` rend les offset date-time nativement.
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ManifestError(path, _("unreadable date « {value} »").format(value=value)) from (
                error
            )
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    raise ManifestError(path, _("missing creation date"))
