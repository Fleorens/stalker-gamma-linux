"""Ce qu'on sauvegarde, et **où ça vit réellement** sur une install GAMMA.

Trois ensembles, indépendamment sélectionnables, qui ont en commun d'être les
seules données qu'un joueur ne peut pas retélécharger :

- `profiles/` — la liste de mods, l'ordre de chargement, les réglages MCM ;
- les **sauvegardes de partie** ;
- `overwrite/` de l'instance MO2 — ce que les mods écrivent hors de leur
  dossier (configurations générées, journaux d'addons).

## Où vivent les sauvegardes de partie — constaté, pas supposé

Anomaly est portable : `fsgame.ltx` déclare `$game_saves$ = $app_data_root$ |
savedgames\\`, donc `<anomaly>/appdata/savedgames`. Sous MO2 l'USVFS *peut*
rediriger ces écritures ailleurs, et la question devait être tranchée sur une
install réelle avant d'être codée.

Relevé le 2026-09-07 sur l'installation de test
(`/mnt/games_samsung/Games/GAMMA`, GAMMA 920, MO2 2.5.2, parties jouées
jusqu'au 26 août) :

- `anomaly/appdata/savedgames/` contient les 29 fichiers de sauvegarde
  (39 Mio), horodatés à la minute de la dernière session de jeu ;
- `gamma/overwrite/` est **vide** — créé le 22 août, jamais écrit ;
- `profiles/G.A.M.M.A/settings.ini` porte `LocalSaves=false`, et il n'existe
  aucun `profiles/G.A.M.M.A/saves/` ;
- le `usvfs-*.log` de la dernière session ne contient **aucune** correspondance
  pour `savedgames` ; les seules entrées sous `appdata\\` concernent
  `shaders_cache`, et elles mappent le chemin réel sur lui-même.

Autrement dit : sur la configuration livrée par GAMMA, le jeu écrit ses
sauvegardes **en direct** dans `anomaly/appdata/savedgames`, sans passer par
`overwrite/`.

Les deux autres emplacements restent atteignables par configuration — MO2
redirige vers `profiles/<profil>/saves` si `LocalSaves=true`, et l'USVFS
dévierait vers `overwrite/` une écriture faite dans un dossier virtualisé. Ils
sont donc sauvegardés **aussi**, quand ils existent et ne sont pas vides : une
liste fermée de trois emplacements coûte trois `is_dir()`, alors que rater
l'emplacement réel coûte les parties du joueur.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2.paths import Mo2Paths

# Nom historique : `orchestrator.backup_mo2_profiles` écrivait déjà des dossiers
# `profiles-%Y%m%d-%H%M%S` sous `<root>/backups/`. Le conserver garde
# restaurables les sauvegardes déjà présentes sur les disques des utilisateurs
# (voir `manifest.legacy_manifest`), même si le contenu peut désormais dépasser
# les seuls profils — c'est le manifeste, pas le nom, qui dit ce qu'il y a
# dedans.
BACKUPS_DIRNAME = "backups"
NAME_PREFIX = "profiles-"
NAME_TIME_FORMAT = "%Y%m%d-%H%M%S"
MANIFEST_FILENAME = "backup.toml"

# Instantané de la liste de mods amont, base de la fusion à trois voies (T17
# partie 2). Vit à côté des sauvegardes parce qu'il protège la même chose et
# qu'il doit suivre l'installation, pas la configuration XDG de la machine.
UPSTREAM_MODLIST_FILENAME = "upstream-modlist.txt"


class BackupSet(StrEnum):
    """Les trois ensembles sauvegardables, tels que nommés par la CLI."""

    PROFILES = "profiles"
    SAVES = "saves"
    OVERWRITE = "overwrite"


ALL_SETS: tuple[BackupSet, ...] = (BackupSet.PROFILES, BackupSet.SAVES, BackupSet.OVERWRITE)

SET_LABELS: dict[BackupSet, str] = {
    BackupSet.PROFILES: _("MO2 profiles (mod list, load order, MCM settings)"),
    BackupSet.SAVES: _("saved games"),
    BackupSet.OVERWRITE: _("MO2 overwrite folder"),
}


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """Un dossier à sauvegarder : d'où il vient, et sous quel nom il est rangé."""

    set_name: BackupSet
    # Chemin absolu du dossier source, sous la racine d'installation.
    source: Path
    # Destination **relative à la racine**, telle qu'écrite dans le manifeste :
    # c'est elle qui fait foi à la restauration, jamais une redérivation.
    destination: str
    # Sous-dossier de la sauvegarde qui reçoit la copie.
    slot: str


def backups_root(root: Path) -> Path:
    return root / BACKUPS_DIRNAME


def upstream_modlist_snapshot(root: Path) -> Path:
    return backups_root(root) / UPSTREAM_MODLIST_FILENAME


def _save_sources(root: Path) -> tuple[SourceEntry, ...]:
    """Les trois emplacements possibles des sauvegardes de partie (voir l'en-tête)."""
    mo2 = Mo2Paths.under(root)
    entries = [
        SourceEntry(
            set_name=BackupSet.SAVES,
            source=root / "anomaly" / "appdata" / "savedgames",
            destination="anomaly/appdata/savedgames",
            slot="saves/anomaly-appdata",
        ),
        SourceEntry(
            set_name=BackupSet.SAVES,
            source=mo2.overwrite / "appdata" / "savedgames",
            destination="gamma/overwrite/appdata/savedgames",
            slot="saves/overwrite",
        ),
    ]
    # `LocalSaves=true` range les parties par profil. On énumère les profils
    # présents au lieu de coder « G.A.M.M.A » en dur : un joueur qui duplique le
    # profil pour tester une config a deux dossiers de parties, pas un.
    try:
        profiles = sorted(child for child in mo2.profiles.iterdir() if child.is_dir())
    except OSError:
        profiles = []
    entries.extend(
        SourceEntry(
            set_name=BackupSet.SAVES,
            source=profile / "saves",
            destination=f"gamma/profiles/{profile.name}/saves",
            slot=f"saves/profile-{profile.name}",
        )
        for profile in profiles
    )
    return tuple(entries)


def candidate_sources(root: Path, sets: tuple[BackupSet, ...]) -> tuple[SourceEntry, ...]:
    """Sources des ensembles demandés, sans doublon imbriqué. Ne touche pas au disque.

    Un ensemble peut en contenir un autre — `gamma/overwrite/appdata/savedgames`
    vit sous `gamma/overwrite`, et `gamma/profiles/<p>/saves` sous
    `gamma/profiles`. Quand les deux sont demandés, le plus large gagne : copier
    deux fois les mêmes octets doublerait la taille de la sauvegarde et donnerait
    deux vérités à la restauration.
    """
    mo2 = Mo2Paths.under(root)
    entries: list[SourceEntry] = []
    if BackupSet.PROFILES in sets:
        entries.append(
            SourceEntry(
                set_name=BackupSet.PROFILES,
                source=mo2.profiles,
                destination="gamma/profiles",
                slot="profiles",
            )
        )
    if BackupSet.OVERWRITE in sets:
        entries.append(
            SourceEntry(
                set_name=BackupSet.OVERWRITE,
                source=mo2.overwrite,
                destination="gamma/overwrite",
                slot="overwrite",
            )
        )
    if BackupSet.SAVES in sets:
        entries.extend(_save_sources(root))
    return tuple(entry for entry in entries if not _is_nested(entry, entries))


def _is_nested(entry: SourceEntry, entries: list[SourceEntry]) -> bool:
    """Vrai si `entry` vit déjà sous la destination d'une autre entrée retenue."""
    return any(
        other is not entry and entry.destination.startswith(other.destination + "/")
        for other in entries
    )


def existing_sources(root: Path, sets: tuple[BackupSet, ...]) -> tuple[SourceEntry, ...]:
    """Sources réellement présentes **et non vides**. C'est ce qu'on copie.

    Un dossier vide n'est pas sauvegardé : il ne porte aucune donnée, et
    l'inclure ferait annoncer « overwrite sauvegardé » à un joueur dont
    `overwrite/` n'a jamais rien reçu — exactement le cas mesuré sur
    l'installation de test.
    """
    return tuple(entry for entry in candidate_sources(root, sets) if _has_content(entry.source))


def _has_content(directory: Path) -> bool:
    try:
        return directory.is_dir() and any(directory.iterdir())
    except OSError:
        return False
