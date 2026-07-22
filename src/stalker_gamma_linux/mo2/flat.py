"""Mode flat : fallback **sans MO2/USVFS**, accessible par flag explicite.

Uniquement si aucune version de Proton ne monte l'USVFS sur la machine. On
délègue la fusion Anomaly + mods à gamma-launcher (`usvfs-workaround`, via
`engine.build_flat_install`), puis on lance directement `AnomalyLauncher.exe` du
dossier fusionné dans le préfixe. **Perte de la flexibilité des mods** : plus
d'activation/désactivation via MO2 (docs/INSTALL-MANUAL.md annexe A).
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.mo2.errors import Mo2InstanceError
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.process import ProgressCallback

# Exécutable lancé dans l'install fusionnée (racine du dossier flat).
FLAT_LAUNCHER = "AnomalyLauncher.exe"


def flat_dir(root: Path) -> Path:
    """Dossier de l'installation fusionnée sous la racine d'installation : `<root>/flat`."""
    return root / "flat"


def launch_flat(
    final_dir: Path,
    prefix: PrefixPaths,
    proton_path: Path,
    *,
    launcher: str = FLAT_LAUNCHER,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Lance l'install flat dans le préfixe. Lève `Mo2InstanceError` si elle est absente."""
    executable = final_dir / launcher
    if not system.path_exists(executable):
        raise Mo2InstanceError(
            f"Installation flat introuvable : {executable} n'existe pas.\n"
            "Construis-la d'abord avec gamma-launcher (`usvfs-workaround`) — c'est ce "
            "que fait `play --flat` avant de lancer."
        )
    return process.run_in_prefix(
        executable,
        paths=prefix,
        proton_path=proton_path,
        log_label="flat-game",
        on_progress=on_progress,
    )
