"""Réparation ciblée d'un mod abîmé : le retirer, puis laisser le moteur le reposer.

## Ce qui est réparable, et ce à quoi on ne touche jamais

Un dossier sous `gamma/mods/` n'est réparable que s'il vient du modpack : sans
source officielle, le supprimer détruirait un mod que l'utilisateur a installé
lui-même, sans aucun moyen de le retrouver.

« Venir du modpack » ne se lit **pas** dans un seul fichier. Constaté sur une
install réelle, `full-install` peuple `mods/` depuis trois sources :

1. `modpack_data/modlist.txt` — les mods téléchargés, séparateurs compris ;
2. `modpack_addons/` — 388 dossiers livrés en clair, copiés tels quels par
   `_copy_gamma_modpack`, **absents de `modlist.txt`** ;
3. les ressources Git (`gamma_large_files_v2`,
   `teivaz_anomaly_gunslinger`), dont les dossiers ne sont connus qu'après
   clonage.

On réunit 1 et 2, qui se lisent hors ligne. La 3 reste hors de portée : ses
mods tombent donc dans « source inconnue », et sont **signalés puis laissés
intacts** — le bon échec, puisque le doute doit toujours empêcher une
suppression. Le message le dit tel quel plutôt que d'affirmer à tort que le
joueur les a ajoutés.

Deuxième garde, moins évidente et tout aussi importante : un mod qui contient
des fichiers `added` n'est **pas** réparé non plus. Réparer, c'est `rmtree` sur
le dossier ; un `.ltx` que le joueur a retouché ou un patch qu'il a déposé
dedans partirait avec. La consigne « les fichiers ajoutés ne sont jamais
réparés » ne se satisfait pas d'épargner le fichier au moment du diff : elle
impose d'épargner le dossier qui le contient. Ces mods-là sont signalés, avec
la raison, et laissés intacts.

## Pourquoi une réinstallation complète et pas « juste ce mod »

gamma-launcher v3.1 n'a aucune option pour n'installer qu'un mod : `full-install`
parcourt toute la liste (`FullInstall._install_mods`). Ce qu'on contrôle, c'est
le **sous-ensemble à retélécharger** : les archives encore présentes en cache
sont réutilisées telles quelles (`use_cached=True`), donc seuls les mods dont on
vient de retirer l'archive repartent du réseau. C'est la seule granularité que
le moteur expose, et c'est celle qui compte pour l'utilisateur — l'extraction
locale du reste coûte du temps, pas 90 Gio de téléchargement.

L'archive est retirée avec le dossier, volontairement : une install abîmée dont
l'archive source serait elle-même corrompue se reconstruirait à l'identique. Le
prix est un retéléchargement du mod concerné.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux import engine, output, paths_safety, updates
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment import system
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.integrity.errors import ModpackDefinitionMissingError, RepairFailedError
from stalker_gamma_linux.integrity.report import ROOT_MOD, IntegrityReport, damaged_mods
from stalker_gamma_linux.mo2 import ini, modlist
from stalker_gamma_linux.mo2.paths import Mo2Paths

# Liste des mods du modpack, telle que le moteur la dépose dans l'install.
UPSTREAM_MODLIST_FILE = "modlist.txt"

# `meta.ini` est écrit par gamma-launcher dans chaque dossier de mod
# (`DefaultInstaller._write_ini_file`). `installationFile` y nomme l'archive
# d'origine : c'est la **seule** correspondance dossier → archive disponible
# hors ligne, le nom réel d'un téléchargement ModDB ne se connaissant qu'en
# interrogeant la page ModDB.
_META_FILE = "meta.ini"
_META_SECTION = "General"
_ARCHIVE_KEY = "installationFile"


@dataclass(frozen=True, slots=True)
class WithheldMod:
    """Un mod abîmé qu'on refuse de réparer, et la raison — affichée telle quelle."""

    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class RepairPlan:
    """Ce qui serait réparé, et ce qui est laissé intact. N'a encore rien touché."""

    repairable: tuple[str, ...] = ()
    withheld: tuple[WithheldMod, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.repairable


def upstream_mod_names(gamma_dir: Path) -> frozenset[str]:
    """Noms de dossiers que le modpack pose lui-même sous `mods/`.

    Réunion des deux sources lisibles hors ligne (voir l'en-tête du module) :
    `modlist.txt` et les dossiers de `modpack_addons/`.

    De `modlist.txt`, on garde **toutes** les entrées : activées ou non — un
    mod désactivé dans MO2 est toujours sur le disque et toujours d'origine
    officielle — séparateurs compris, puisque gamma-launcher en crée de vrais
    dossiers avec un `meta.ini` (`SeparatorInstaller.install`).

    Lève `ModpackDefinitionMissingError` si `modlist.txt` n'a pas été déposé
    (install faite à la main, hors pipeline) : sans lui, plus rien ne distingue
    un mod officiel d'un ajout du joueur.
    """
    path = updates.local_definition_dir(gamma_dir) / UPSTREAM_MODLIST_FILE
    text = system.read_text(path)
    if text is None:
        raise ModpackDefinitionMissingError(path)
    listed = {entry.name for entry in modlist.parse_modlist(text, include_separators=True)}
    return frozenset(listed | _addon_dir_names(gamma_dir))


def _addon_dir_names(gamma_dir: Path) -> set[str]:
    """Dossiers de `modpack_addons/`, vide si le dossier est absent."""
    addons = updates.local_addons_dir(gamma_dir)
    try:
        return {entry.name for entry in addons.iterdir() if entry.is_dir()}
    except OSError:
        return set()


def archive_name_for_mod(mod_dir: Path) -> str | None:
    """Nom de l'archive dont ce mod a été extrait, lu dans son `meta.ini`.

    `None` si le `meta.ini` est absent ou muet : le mod sera quand même
    supprimé et réinstallé, simplement en réutilisant l'archive du cache.
    """
    text = system.read_text(mod_dir / _META_FILE)
    if text is None:
        return None
    raw = ini.read_key(text, _META_SECTION, _ARCHIVE_KEY)
    if raw is None:
        return None
    return raw.strip() or None


def build_repair_plan(report: IntegrityReport, upstream: frozenset[str]) -> RepairPlan:
    """Trie les mods abîmés en « réparables » et « laissés intacts, avec la raison »."""
    repairable: list[str] = []
    withheld: list[WithheldMod] = []
    for finding in damaged_mods(report):
        reason = _withheld_reason(finding.name, upstream, has_user_files=finding.has_user_files)
        if reason is None:
            repairable.append(finding.name)
        else:
            withheld.append(WithheldMod(name=finding.name, reason=reason))
    return RepairPlan(repairable=tuple(repairable), withheld=tuple(withheld))


def _withheld_reason(name: str, upstream: frozenset[str], *, has_user_files: bool) -> str | None:
    if name == ROOT_MOD:
        return _("loose files directly under mods/, not part of any mod")
    if name not in upstream:
        return _(
            "not found in the local modpack definition — either a mod you added, "
            "or one installed from a Git resource. Left untouched either way"
        )
    if has_user_files:
        return _("contains files you added — repairing would delete them along with the mod")
    return None


def format_plan(plan: RepairPlan) -> str:
    lines: list[str] = []
    if plan.repairable:
        lines.append(_("To repair (removed, then reinstalled by the engine):"))
        lines.extend(f"  - {name}" for name in plan.repairable)
        lines.append("")
    if plan.withheld:
        lines.append(_("Left untouched:"))
        lines.extend(f"  - {mod.name or _('mods/')}: {mod.reason}" for mod in plan.withheld)
        lines.append("")
    return "\n".join(lines)


def remove_mod(root: Path, name: str) -> tuple[Path | None, Path | None]:
    """Retire le dossier du mod `name` et son archive en cache.

    Retourne `(dossier supprimé, archive supprimée)`, chaque terme à `None`
    quand il n'y avait rien à supprimer. Un dossier déjà absent n'est **pas**
    une erreur : c'est même un des cas qu'on répare — un mod effacé voit tous
    ses fichiers classés `removed`, et le moteur le reposera.

    Les deux chemins sont validés comme enfants **directs** de leur dossier
    parent (`paths_safety.validate_removable_child`) **avant** la moindre
    suppression : un nom venu de la liste amont ou d'un `meta.ini` ne peut ni
    faire sortir le `rmtree` de `mods/`, ni l'`unlink` de `downloads/`, et un
    `meta.ini` douteux fait tout refuser au lieu de laisser le mod à moitié
    retiré.
    """
    mods_dir = Mo2Paths.under(root).mods
    mod_dir = paths_safety.validate_removable_child(mods_dir, name)
    if mod_dir is None:
        return None, None

    # Lu **avant** la suppression : le `meta.ini` disparaît avec le dossier.
    archive_name = archive_name_for_mod(mod_dir)
    archive = (
        paths_safety.validate_removable_child(InstallPaths.under(root).downloads, archive_name)
        if archive_name is not None
        else None
    )

    try:
        shutil.rmtree(mod_dir)
        if archive is not None:
            archive.unlink()
    except OSError as error:
        raise RepairFailedError(name, str(error)) from error
    return mod_dir, archive


def remove_mods(
    root: Path,
    names: Sequence[str],
    *,
    reporter: output.Reporter = output.console_reporter,
) -> tuple[str, ...]:
    """Retire les mods visés (dossier + archive). Retourne ceux à faire reposer.

    **Toujours suivi de `reinstall_mods`** : entre les deux, l'installation est
    incomplète. Les deux sont séparés pour que l'appelant puisse annoncer les
    deux phases distinctement — le retrait dure une seconde, la réinstallation
    des dizaines de minutes.
    """
    removed: list[str] = []
    for name in names:
        mod_dir, archive = remove_mod(root, name)
        removed.append(name)
        if mod_dir is not None:
            reporter.progress(_("  removed {path}").format(path=mod_dir))
        else:
            reporter.progress(
                _("  {name}: folder already gone, it will be reinstalled").format(name=name)
            )
        if archive is not None:
            reporter.progress(_("  removed cached archive {path}").format(path=archive))
    return tuple(removed)


def reinstall_mods(
    root: Path,
    *,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
) -> None:
    """Relance `full-install` pour reposer ce qui manque (voir l'en-tête du module)."""
    engine.install_gamma(
        InstallPaths.under(root), on_progress=reporter.progress, cancel_event=cancel_event
    )
