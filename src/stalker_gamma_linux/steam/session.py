"""Commande utilisateur `steam-shortcut` : ajoute/retire GAMMA de la bibliothèque Steam.

Pendant du `run_shortcut` de `desktop/` : même forme (une fonction qui rend un
code de sortie, tous les messages ici et aucun dans les modules métier), mais
un puits différent — Steam plutôt que le menu applications.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux import output
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.steam import install as install_module
from stalker_gamma_linux.steam.errors import NoSteamAccountError, SteamError
from stalker_gamma_linux.steam.install import AccountResult, Action
from stalker_gamma_linux.steam.paths import discover_accounts

# Rappel affiché une fois, à la fin : ce que Steam fait du fichier qu'on vient
# d'écrire n'est pas évident (il ne le relit qu'au démarrage).
_RESTART_HINT = _("Start Steam (or restart it) to see the change in your library.")

# Steam en Flatpak lance les jeux non-Steam **dans son bac à sable**, où notre
# lanceur (un venv Python de l'hôte) n'est pas forcément joignable. L'entrée et
# son artwork sont écrits quand même — ils sont corrects, et le retrait est
# immédiat — mais l'utilisateur doit savoir d'où viendra un échec de lancement.
_FLATPAK_WARNING = _(
    "Note: this account belongs to the Flatpak Steam, which launches non-Steam "
    "games inside its sandbox — the entry and its artwork are written, but the "
    "launch itself may fail there. The native Steam package is the reliable "
    "path; `stalker-gamma-linux play` always works from outside Steam."
)


def _describe_add(result: AccountResult) -> str:
    verb = _("added to") if result.action is Action.CREATED else _("updated in")
    lines = [
        _("  {account}: {verb} the library (appid {appid})").format(
            account=result.account.label, verb=verb, appid=result.appid
        ),
        _("    artwork: {count} files in {grid}").format(
            count=len(result.artwork_written), grid=result.account.grid_dir
        ),
    ]
    if result.backup is not None:
        lines.append(_("    backup of the previous file: {backup}").format(backup=result.backup))
    return "\n".join(lines)


def _describe_remove(result: AccountResult) -> str:
    if result.action is Action.ABSENT:
        return _("  {account}: nothing of ours in there").format(account=result.account.label)
    lines = [
        _("  {account}: entry removed (appid {appid})").format(
            account=result.account.label, appid=result.appid
        )
    ]
    if result.artwork_removed:
        lines.append(
            _("    artwork removed: {count} files").format(count=len(result.artwork_removed))
        )
    if result.artwork_kept:
        lines.append(
            _("    left in place (no longer ours — you replaced them): {files}").format(
                files=", ".join(path.name for path in result.artwork_kept)
            )
        )
    if result.backup is not None:
        lines.append(_("    backup of the previous file: {backup}").format(backup=result.backup))
    return "\n".join(lines)


def _heading(*, remove: bool, dry_run: bool) -> str:
    """Titre du compte rendu — au conditionnel en `--dry-run`, où rien n'a bougé."""
    if remove:
        return (
            _("Steam shortcut that would be removed:") if dry_run else _("Steam shortcut removed:")
        )
    return _("Steam shortcut that would be written:") if dry_run else _("Steam shortcut written:")


def _flatpak_note(results: tuple[AccountResult, ...]) -> str | None:
    touched = [result for result in results if result.action is not Action.ABSENT]
    if any(result.account.install.flatpak for result in touched):
        return _FLATPAK_WARNING
    return None


def run_steam_shortcut(
    target: Path | None = None,
    *,
    remove: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Commande CLI `steam-shortcut`. 0 au succès, 1 sur refus ou erreur d'écriture."""
    root = target if target is not None else DEFAULT_INSTALL_TARGET

    accounts = discover_accounts()
    if not accounts:
        # Message actionnable, pas une exception : « aucun compte » est un état
        # normal d'une machine sans Steam, pas un bug à rapporter.
        output.error(str(NoSteamAccountError()))
        return 1

    if dry_run:
        output.header(_("Dry run — nothing will be written."))

    try:
        if remove:
            results = install_module.remove_shortcut(
                accounts=accounts, dry_run=dry_run, force=force
            )
        else:
            results = install_module.add_shortcut(
                root, accounts=accounts, dry_run=dry_run, force=force
            )
    except SteamError as error:
        output.error(str(error))
        return 1

    describe = _describe_remove if remove else _describe_add
    heading = _heading(remove=remove, dry_run=dry_run)
    output.progress(heading + "\n" + "\n".join(describe(result) for result in results))

    note = _flatpak_note(results)
    if note is not None and not remove:
        output.warn(note)
    if not dry_run:
        output.success(_RESTART_HINT)
    return 0
