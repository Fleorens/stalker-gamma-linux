"""Création d'une sauvegarde : copie des ensembles choisis + manifeste.

Remplace `orchestrator.backup_mo2_profiles`, dont c'est la généralisation :
même dossier de destination, même nommage horodaté, mais plusieurs ensembles,
un manifeste, et une rotation (voir `rotation.py`). Il n'y a **pas** de seconde
implémentation en parallèle — l'orchestrateur appelle ce module.

Une sauvegarde est écrite dans un dossier neuf, jamais dans un dossier
existant : si la copie échoue en cours de route (disque plein, permissions),
le dossier partiel est retiré et l'erreur remonte. Une sauvegarde à moitié
écrite est pire que pas de sauvegarde du tout — elle donne l'illusion du filet.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from stalker_gamma_linux.backups.errors import BackupWriteError, NothingToBackUpError
from stalker_gamma_linux.backups.manifest import Manifest, ManifestEntry, write_manifest
from stalker_gamma_linux.backups.paths import (
    ALL_SETS,
    NAME_PREFIX,
    NAME_TIME_FORMAT,
    BackupSet,
    SourceEntry,
    backups_root,
    existing_sources,
)
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.report_bundle import package_version
from stalker_gamma_linux.updates import local_version_file


def backup_id(now: datetime) -> str:
    return f"{NAME_PREFIX}{now:{NAME_TIME_FORMAT}}"


def create_backup(
    root: Path,
    *,
    sets: tuple[BackupSet, ...] = ALL_SETS,
    explicit: bool = False,
    now: datetime | None = None,
) -> tuple[Path, Manifest]:
    """Copie les ensembles demandés sous `<root>/backups/<id>`. Retourne (dossier, manifeste).

    `explicit` marque une sauvegarde demandée par l'utilisateur : elle n'entre
    jamais dans la rotation. Lève `NothingToBackUpError` si aucun des ensembles
    n'existe (ou s'ils sont tous vides), `BackupWriteError` sur échec d'écriture.
    """
    sources = existing_sources(root, sets)
    if not sources:
        raise NothingToBackUpError(root, tuple(str(name) for name in sets))

    stamp = now if now is not None else datetime.now(UTC)
    directory = _unique_directory(backups_root(root), stamp)
    try:
        directory.mkdir(parents=True)
        entries = tuple(_copy_source(directory, source) for source in sources)
    except OSError as error:
        # Ne laisse pas derrière soi une sauvegarde tronquée que `--list`
        # présenterait ensuite comme utilisable.
        shutil.rmtree(directory, ignore_errors=True)
        raise BackupWriteError(directory, error) from error

    manifest = Manifest(
        identifier=directory.name,
        created_at=stamp,
        entries=entries,
        explicit=explicit,
        gamma_version=_gamma_version(root),
        tool_version=package_version(),
    )
    try:
        write_manifest(directory, manifest)
    except OSError as error:
        shutil.rmtree(directory, ignore_errors=True)
        raise BackupWriteError(directory, error) from error
    return directory, manifest


def _unique_directory(parent: Path, stamp: datetime) -> Path:
    """Dossier neuf pour l'horodatage donné, suffixé si la seconde est déjà prise."""
    base = parent / backup_id(stamp)
    if not base.exists():
        return base
    for index in range(2, 100):
        candidate = parent / f"{backup_id(stamp)}-{index}"
        if not candidate.exists():
            return candidate
    # 99 sauvegardes dans la même seconde : il se passe autre chose que ce
    # qu'on modélise, mieux vaut échouer que boucler.
    raise BackupWriteError(base, OSError("too many backups within the same second"))


def _copy_source(directory: Path, source: SourceEntry) -> ManifestEntry:
    destination = directory / source.slot
    destination.parent.mkdir(parents=True, exist_ok=True)
    # `symlinks=True` : on recopie le lien, pas ce qu'il vise. Un lien cassé ne
    # fait pas échouer la sauvegarde, et une install adoptée (`import`, qui pose
    # des liens) n'est pas dupliquée en octets.
    shutil.copytree(source.source, destination, symlinks=True)
    files, size = _measure(destination)
    return ManifestEntry(
        set_name=source.set_name,
        slot=source.slot,
        destination=source.destination,
        files=files,
        size_bytes=size,
    )


def _measure(directory: Path) -> tuple[int, int]:
    """(nombre de fichiers, octets) de l'arborescence copiée.

    Mesuré après coup plutôt que pendant la copie : `shutil.copytree` fait le
    travail délicat (permissions, dates, liens) mieux qu'une boucle maison, et
    un parcours de métadonnées sur quelques milliers d'entrées ne coûte rien
    à côté de la copie elle-même.
    """
    files = 0
    size = 0
    for path in directory.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        files += 1
        try:
            size += path.stat().st_size
        except OSError:
            continue
    return files, size


def _gamma_version(root: Path) -> str:
    """Numéro de définition GAMMA installé, ou chaîne vide s'il n'est pas lisible."""
    path = local_version_file(Mo2Paths.under(root).instance)
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
