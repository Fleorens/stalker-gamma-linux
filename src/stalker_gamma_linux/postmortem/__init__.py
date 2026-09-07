"""Post-mortem de session : attribuer un crash de GAMMA au mod fautif (T18).

Le launcher Windows ne le fait pas, et c'est pourtant l'attente n°1 après un
plantage. Ce paquet lit, **une fois le jeu fermé**, les journaux qui ont enfin
quelque chose à dire — celui du lancement, celui du moteur X-Ray, celui de
l'USVFS — et rend un diagnostic unique, avec le ou les mods à regarder en
premier quand la trace nomme un fichier.

Chaque marqueur reconnu vient d'un journal réel ou des chaînes de format du
moteur lui-même : voir `markers`, qui documente aussi pourquoi la recherche
« évidente » (`[error]`, `stack trace`) crie au crash sur une partie normale.
"""

from stalker_gamma_linux.postmortem.analysis import build_postmortem, describes_same_session
from stalker_gamma_linux.postmortem.attribution import (
    AssetReference,
    Attribution,
    Suspect,
    attribute,
    references,
)
from stalker_gamma_linux.postmortem.logfile import (
    XRAY_LOG_GLOB,
    EngineLog,
    candidate_log_dirs,
    find_engine_log,
    load_engine_log,
    read_tail,
)
from stalker_gamma_linux.postmortem.outcome import SessionEnd, SessionOutcome, analyse, classify
from stalker_gamma_linux.postmortem.report import format_postmortem, headline
from stalker_gamma_linux.postmortem.result import Finding, Postmortem
from stalker_gamma_linux.postmortem.session import run_postmortem

__all__ = [
    "XRAY_LOG_GLOB",
    "AssetReference",
    "Attribution",
    "EngineLog",
    "Finding",
    "Postmortem",
    "SessionEnd",
    "SessionOutcome",
    "Suspect",
    "analyse",
    "attribute",
    "build_postmortem",
    "candidate_log_dirs",
    "classify",
    "describes_same_session",
    "find_engine_log",
    "format_postmortem",
    "headline",
    "load_engine_log",
    "read_tail",
    "references",
    "run_postmortem",
]
