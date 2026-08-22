"""Intégrité du contenu **installé** sous `<install>/gamma/mods` (T12).

À ne pas confondre avec `engine.verify` (`check-md5`), qui vérifie les
**archives téléchargées** : « le téléchargement était-il correct ». Ce
paquet-ci répond à l'autre moitié de la question — « l'install sur le disque
est-elle encore intacte » — celle que pose un joueur dont le jeu crashe depuis
hier, après qu'un autre outil a écrasé un fichier ou qu'un disque plein en a
tronqué un.
"""

from stalker_gamma_linux.integrity.baseline import (
    BASELINE_FILENAME,
    ParsedBaseline,
    baseline_path,
    format_baseline,
    parse_baseline,
    read_baseline,
    write_baseline,
)
from stalker_gamma_linux.integrity.errors import (
    BaselineReadError,
    BaselineWriteError,
    IntegrityCancelledError,
    IntegrityError,
    ModpackDefinitionMissingError,
    ModsDirectoryMissingError,
    RepairFailedError,
)
from stalker_gamma_linux.integrity.repair import (
    RepairPlan,
    WithheldMod,
    build_repair_plan,
    upstream_mod_names,
)
from stalker_gamma_linux.integrity.report import (
    IntegrityReport,
    ModFinding,
    compare,
    damaged_mods,
    format_report,
    group_by_mod,
    mod_of,
)
from stalker_gamma_linux.integrity.scan import ScanResult, UnreadableFile, hash_file, scan_tree
from stalker_gamma_linux.integrity.session import run_verify, verify_phase_labels

__all__ = [
    "BASELINE_FILENAME",
    "BaselineReadError",
    "BaselineWriteError",
    "IntegrityCancelledError",
    "IntegrityError",
    "IntegrityReport",
    "ModFinding",
    "ModpackDefinitionMissingError",
    "ModsDirectoryMissingError",
    "ParsedBaseline",
    "RepairFailedError",
    "RepairPlan",
    "ScanResult",
    "UnreadableFile",
    "WithheldMod",
    "baseline_path",
    "build_repair_plan",
    "compare",
    "damaged_mods",
    "format_baseline",
    "format_report",
    "group_by_mod",
    "hash_file",
    "mod_of",
    "parse_baseline",
    "read_baseline",
    "run_verify",
    "scan_tree",
    "upstream_mod_names",
    "verify_phase_labels",
    "write_baseline",
]
