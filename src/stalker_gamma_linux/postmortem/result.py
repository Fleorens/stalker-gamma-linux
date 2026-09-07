"""Le verdict du post-mortem : une conclusion unique, et ses pièces à conviction.

**Un seul diagnostic principal.** La règle posée pour le diagnostic de lancement
vaut ici aussi : un utilisateur à qui on annonce trois problèmes n'en corrige
aucun. `Finding` est donc un choix, pas un ensemble — les autres observations
restent accessibles dans les champs, pour qui veut vérifier.

L'ordre de priorité, du plus en amont au plus en aval :

    échec de lancement > manque de mémoire > crash moteur > USVFS mort > session normale

Chaque valeur porte l'idée « à quoi l'utilisateur doit s'attaquer », pas « ce
qu'on a vu passer ».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from stalker_gamma_linux.mo2.diagnostics import UsvfsDiagnosis
from stalker_gamma_linux.postmortem.attribution import Attribution
from stalker_gamma_linux.postmortem.outcome import SessionEnd


class Finding(Enum):
    """Conclusion principale, dans l'ordre de priorité."""

    LAUNCH_FAILURE = auto()
    OUT_OF_MEMORY = auto()
    ENGINE_CRASH = auto()
    USVFS_INACTIVE = auto()
    CLEAN_SESSION = auto()
    # Le journal du moteur n'existe pas : le jeu n'a jamais démarré depuis cette
    # install, ou il écrit ailleurs.
    NO_ENGINE_LOG = auto()
    # Il existe, mais ne se termine ni proprement ni sur un crash : partie encore
    # en cours, processus tué de l'extérieur, ou journal tronqué.
    INCONCLUSIVE = auto()

    @property
    def is_problem(self) -> bool:
        return self in (
            Finding.LAUNCH_FAILURE,
            Finding.OUT_OF_MEMORY,
            Finding.ENGINE_CRASH,
            Finding.USVFS_INACTIVE,
        )


@dataclass(frozen=True, slots=True)
class Postmortem:
    """Ce que le post-mortem a conclu, et tout ce qui permet de le recouper."""

    finding: Finding
    root: Path
    engine_log: Path | None = None
    launch_log: Path | None = None
    # Message de remède de `mo2.diagnostics` quand le lancement lui-même a
    # échoué — conservé même quand il n'est pas la conclusion retenue.
    launch_failure: str | None = None
    session: SessionEnd | None = None
    attribution: Attribution = field(default_factory=Attribution)
    usvfs: UsvfsDiagnosis | None = None

    @property
    def excerpt(self) -> tuple[str, ...]:
        return self.session.excerpt if self.session is not None else ()
