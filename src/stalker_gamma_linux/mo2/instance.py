"""Configuration automatique de l'instance MO2 livrée par GAMMA.

C'est l'étape que gamma-launcher ne fait pas : l'instance est construite hors
Wine, donc son `gamePath` pointe vers un chemin invalide et le profil/exécutable
ne sont pas prêts. On écrit ces valeurs directement dans `ModOrganizer.ini` pour
supprimer toute interaction au premier lancement (docs/INSTALL-MANUAL.md §7) :

- `gamePath` → dossier Anomaly en **chemin Windows** (`Z:\\...`, vu du préfixe) ;
- `selected_profile` → `G.A.M.M.A` ;
- (si le `.ini` est créé de zéro) `gameName` + `first_start=false`.

L'exécutable par défaut « Anomaly (DX11) » n'est pas épinglé ici : il est fourni
au lancement via `moshortcut://` (voir `mo2/launch.py`), ce qui est le mécanisme
fiable et ne dépend pas d'un état persistant de la barre d'outils MO2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.mo2 import ini
from stalker_gamma_linux.mo2.errors import AnomalyNotFoundError, Mo2NotInstalledError
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.winepath import to_windows_path

# Profil livré par GAMMA (dossier `profiles/G.A.M.M.A/`).
GAMMA_PROFILE = "G.A.M.M.A"

# Nom du plugin de jeu MO2 pour Anomaly. Écrit uniquement si on crée un `.ini`
# de zéro (l'instance GAMMA le fournit déjà). ⚠ À VALIDER : casse exacte du nom.
ANOMALY_GAME_NAME = "STALKER Anomaly"

# Fichier qui atteste qu'un dossier est bien une install Anomaly.
_ANOMALY_MARKER = "AnomalyLauncher.exe"

_GENERAL = "General"
_GAME_PATH_KEY = "gamePath"
_PROFILE_KEY = "selected_profile"


@dataclass(frozen=True, slots=True)
class InstanceConfig:
    """Résultat d'une configuration d'instance."""

    game_path: str
    profile: str
    changed: bool
    backup: Path | None


def _backup_path(mo2: Mo2Paths) -> Path:
    return mo2.instance / f"{mo2.organizer_ini.name}.bak"


def read_game_path(mo2: Mo2Paths) -> str | None:
    """Chemin Windows actuellement écrit dans `gamePath`, ou None si non défini."""
    text = system.read_text(mo2.organizer_ini)
    if text is None:
        return None
    return ini.read_bytearray_key(text, _GENERAL, _GAME_PATH_KEY)


def is_configured(mo2: Mo2Paths, anomaly_dir: Path, *, profile: str = GAMMA_PROFILE) -> bool:
    """Vrai si le `.ini` pointe déjà vers ce dossier Anomaly et ce profil."""
    text = system.read_text(mo2.organizer_ini)
    if text is None:
        return False
    game_ok = ini.read_bytearray_key(text, _GENERAL, _GAME_PATH_KEY) == to_windows_path(anomaly_dir)
    profile_ok = ini.read_bytearray_key(text, _GENERAL, _PROFILE_KEY) == profile
    return game_ok and profile_ok


def configure_instance(
    mo2: Mo2Paths,
    anomaly_dir: Path,
    *,
    profile: str = GAMMA_PROFILE,
    backup: bool = True,
) -> InstanceConfig:
    """Écrit `gamePath`/`selected_profile` dans `ModOrganizer.ini`. Idempotent.

    Lève `Mo2NotInstalledError` si `ModOrganizer.exe` est absent (instance non
    construite), `AnomalyNotFoundError` si `anomaly_dir` n'est pas une install
    Anomaly valide. Ne réécrit le fichier que s'il change réellement ; conserve
    une sauvegarde `ModOrganizer.ini.bak` du fichier d'origine (une seule fois).
    """
    if not system.path_exists(mo2.executable):
        raise Mo2NotInstalledError(mo2.executable)
    if not system.path_exists(anomaly_dir / _ANOMALY_MARKER):
        raise AnomalyNotFoundError(anomaly_dir)

    game_path = to_windows_path(anomaly_dir)
    original = system.read_text(mo2.organizer_ini)
    base = original if original is not None else ""

    updated = ini.set_bytearray_key(base, _GENERAL, _GAME_PATH_KEY, game_path)
    updated = ini.set_bytearray_key(updated, _GENERAL, _PROFILE_KEY, profile)
    if original is None:
        updated = ini.set_key(updated, _GENERAL, "gameName", ANOMALY_GAME_NAME)
        updated = ini.set_key(updated, _GENERAL, "first_start", "false")

    changed = updated != (original or "")
    backup_written: Path | None = None
    if changed:
        if backup and original is not None:
            backup_written = _backup_path(mo2)
            if not backup_written.exists():
                backup_written.write_text(original, encoding="utf-8")
        mo2.organizer_ini.write_text(updated, encoding="utf-8")

    return InstanceConfig(
        game_path=game_path, profile=profile, changed=changed, backup=backup_written
    )
