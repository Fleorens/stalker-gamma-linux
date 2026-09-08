"""Écriture réelle du raccourci Steam : sauvegarde, écriture atomique, artwork.

`shortcuts.vdf` n'est pas notre fichier : il contient *les autres* raccourcis
non-Steam de l'utilisateur, que rien ne retéléchargera. Même exigence qu'en
T17 pour les profils MO2 — **rien de destructeur sans filet** :

1. une copie `.bak` horodatée avant toute écriture, à côté du fichier ;
2. une écriture atomique (fichier temporaire puis `os.replace`), jamais en
   place : une coupure au milieu laisse l'ancien fichier intact, pas un
   `shortcuts.vdf` tronqué qui coûterait à l'utilisateur tous ses raccourcis ;
3. jamais de réécriture partielle : le document est reconstruit en entier en
   mémoire, et n'atteint le disque que s'il a été reconstruit en entier.

Le choix du **multi-comptes** : on écrit pour **tous** les comptes trouvés.
Deviner « le bon » à partir de la date de modification est une heuristique qui
se trompe sur une machine partagée ; demander est impossible là où ça compte le
plus — en mode Gaming, il n'y a pas de terminal pour répondre. Et le geste est
réversible et sans effet de bord chez le voisin : une entrée de plus dans sa
bibliothèque, que `--remove` retire.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from stalker_gamma_linux.desktop.install import launch_command
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.paths_safety import validate_install_target
from stalker_gamma_linux.steam import artwork, entry, running
from stalker_gamma_linux.steam.errors import SteamError, SteamWriteError, VdfFormatError
from stalker_gamma_linux.steam.paths import MAX_SHORTCUTS_BYTES, SteamAccount, discover_accounts
from stalker_gamma_linux.steam.vdf import VdfDocument, parse, serialize

_TMP_SUFFIX = ".stalker-gamma-linux.tmp"
_BACKUP_TIMESTAMP = "%Y%m%d-%H%M%S"


class Action(Enum):
    """Ce qui a été fait (ou serait fait, en `--dry-run`) pour un compte."""

    CREATED = "created"
    UPDATED = "updated"
    REMOVED = "removed"
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class AccountResult:
    """Résultat pour un compte : de quoi rendre compte sans redériver quoi que ce soit."""

    account: SteamAccount
    action: Action
    appid: int | None = None
    backup: Path | None = None
    artwork_written: tuple[Path, ...] = ()
    artwork_removed: tuple[Path, ...] = ()
    artwork_kept: tuple[Path, ...] = ()


def read_document(path: Path) -> VdfDocument:
    """Document du fichier, ou un document vide s'il n'existe pas encore.

    Un `shortcuts.vdf` absent (ou vide) est le cas normal d'un compte qui n'a
    jamais eu de raccourci non-Steam : on part d'un document vide, on n'échoue
    pas. Ce document-là porte le terminateur `0x08` par défaut — un fichier
    qu'on crée doit se terminer comme ceux que Steam écrit, pas s'arrêter net.
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return VdfDocument.empty()
    except OSError as error:
        raise SteamWriteError(path, error) from error
    if size > MAX_SHORTCUTS_BYTES:
        raise VdfFormatError(
            path,
            0,
            _("file is {size} bytes, well beyond any real shortcuts.vdf").format(size=size),
        )
    try:
        data = path.read_bytes()
    except OSError as error:
        raise SteamWriteError(path, error) from error
    if not data:
        return VdfDocument.empty()
    return parse(data, path=path)


def backup_path(path: Path, *, moment: datetime | None = None) -> Path:
    """Nom de la copie de sauvegarde : horodaté, à côté du fichier, jamais écrasé."""
    stamp = (moment or datetime.now()).strftime(_BACKUP_TIMESTAMP)
    return path.with_name(f"{path.name}.{stamp}.bak")


def _backup(path: Path) -> Path | None:
    """Copie `.bak` horodatée du fichier existant. `None` s'il n'y a rien à sauver.

    Pas de rotation, contrairement aux sauvegardes de T17 : celles-ci pèsent
    quelques centaines d'octets, et supprimer une sauvegarde est exactement le
    geste que ce filet existe pour éviter. Elles s'accumulent donc, visiblement,
    à côté du fichier qu'elles protègent.
    """
    if not path.is_file():
        return None
    destination = backup_path(path)
    try:
        destination.write_bytes(path.read_bytes())
    except OSError as error:
        raise SteamWriteError(destination, error) from error
    return destination


def _write_atomic(path: Path, data: bytes) -> None:
    """Écrit à côté puis remplace. Jamais d'écriture en place (voir le docstring)."""
    temporary = path.with_name(path.name + _TMP_SUFFIX)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(data)
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise SteamWriteError(path, error) from error


def _apply_document(account: SteamAccount, document: VdfDocument, *, dry_run: bool) -> Path | None:
    if dry_run:
        return None
    backup = _backup(account.shortcuts_file)
    _write_atomic(account.shortcuts_file, serialize(document))
    return backup


def add_to_account(account: SteamAccount, target: Path, *, dry_run: bool = False) -> AccountResult:
    """Ajoute ou met à jour notre raccourci pour un compte, artwork compris."""
    validate_install_target(target)
    command = launch_command(target)
    exe = Path(command[0])
    document = read_document(account.shortcuts_file)

    def icon_for(appid: int) -> Path:
        # Le chemin doit être écrit dans la vue de CE Steam : un Flatpak ne voit
        # pas `~/.var/app/...`, il voit `~/.local/share/...` (cf. `paths`).
        return account.install.as_steam_sees(artwork.icon_file(account.grid_dir, appid))

    updated, appid, created = entry.add_or_update(
        document, exe=exe, target=target, arguments=command[1:], icon_for=icon_for
    )
    backup = _apply_document(account, updated, dry_run=dry_run)
    # En `--dry-run`, les chemins annoncés sont ceux qui *seraient* écrits.
    written = (
        artwork.paths(account.grid_dir, appid)
        if dry_run
        else artwork.write(account.grid_dir, appid)
    )
    return AccountResult(
        account=account,
        action=Action.CREATED if created else Action.UPDATED,
        appid=appid,
        backup=backup,
        artwork_written=written,
    )


def remove_from_account(account: SteamAccount, *, dry_run: bool = False) -> AccountResult:
    """Retire notre raccourci (et lui seul) d'un compte, ainsi que notre artwork."""
    document = read_document(account.shortcuts_file)
    updated, removed_appids = entry.remove_ours(document)
    if not removed_appids:
        return AccountResult(account=account, action=Action.ABSENT)

    appid = removed_appids[0]
    if dry_run:
        return AccountResult(
            account=account,
            action=Action.REMOVED,
            appid=appid,
            artwork_removed=artwork.paths(account.grid_dir, appid),
        )

    backup = _apply_document(account, updated, dry_run=False)
    gone: list[Path] = []
    kept: list[Path] = []
    for value in removed_appids:
        removed_files, kept_files = artwork.remove(account.grid_dir, value)
        gone.extend(removed_files)
        kept.extend(kept_files)
    return AccountResult(
        account=account,
        action=Action.REMOVED,
        appid=appid,
        backup=backup,
        artwork_removed=tuple(gone),
        artwork_kept=tuple(kept),
    )


def add_shortcut(
    target: Path,
    *,
    accounts: tuple[SteamAccount, ...] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[AccountResult, ...]:
    """Ajoute/actualise le raccourci pour tous les comptes. Lève si Steam tourne."""
    resolved = discover_accounts() if accounts is None else accounts
    if not dry_run:
        running.require_closed(force=force)
    return tuple(add_to_account(account, target, dry_run=dry_run) for account in resolved)


def _carries_our_entry(account: SteamAccount) -> bool:
    try:
        return entry.find_ours(read_document(account.shortcuts_file)) is not None
    except SteamError:
        # Fichier illisible : on ne peut pas conclure. `remove_from_account`
        # lèvera l'erreur avec son message ; inutile d'exiger d'abord que Steam
        # soit fermé pour un retrait qui n'aura probablement pas lieu.
        return False


def remove_shortcut(
    *,
    accounts: tuple[SteamAccount, ...] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[AccountResult, ...]:
    """Retire le raccourci de tous les comptes. Lève si Steam tourne.

    Le refus n'est opposé que s'il y a réellement quelque chose à retirer :
    `uninstall` appelle cette fonction à chaque désinstallation, et exiger la
    fermeture de Steam pour ne rien écrire serait un refus gratuit.
    """
    resolved = discover_accounts() if accounts is None else accounts
    if not dry_run and any(_carries_our_entry(account) for account in resolved):
        running.require_closed(force=force)
    return tuple(remove_from_account(account, dry_run=dry_run) for account in resolved)
