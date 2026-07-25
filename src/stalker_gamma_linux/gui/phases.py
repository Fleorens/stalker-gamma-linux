"""Modèle immuable de la timeline de phases affichée pendant install/update.

Traduit le flux d'événements `Reporter` (`step`/`skip` indexés « n/total »,
`progress`, `error`, `success`) en une suite d'états de phases rendable par la
vue progression : chaque événement produit une **nouvelle** `Timeline` (aucune
mutation), la vue ne fait que comparer et redessiner. Indépendant de GTK.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto

from stalker_gamma_linux.gui.format import parse_step_index
from stalker_gamma_linux.gui.worker import ReporterEvent


class PhaseStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    DONE = auto()
    SKIPPED = auto()  # étape déjà validée lors d'une exécution précédente (reprise)
    FAILED = auto()


# Statuts qui comptent « terminé » dans la fraction de progression globale.
_SETTLED = frozenset({PhaseStatus.DONE, PhaseStatus.SKIPPED})


@dataclass(frozen=True, slots=True)
class Phase:
    label: str
    status: PhaseStatus = PhaseStatus.PENDING
    # Dernier message `progress` du moteur pendant que la phase tourne
    # (ex. « téléchargement 12/340 ») — une seule ligne, la vue l'ellipse.
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class Timeline:
    phases: tuple[Phase, ...]

    @classmethod
    def from_labels(cls, labels: tuple[str, ...]) -> Timeline:
        return cls(phases=tuple(Phase(label=label) for label in labels))

    @property
    def fraction(self) -> float:
        """Progression globale [0,1] : phases réglées + demi-crédit pour celle en cours."""
        if not self.phases:
            return 0.0
        settled = sum(1 for phase in self.phases if phase.status in _SETTLED)
        running = sum(0.5 for phase in self.phases if phase.status is PhaseStatus.RUNNING)
        return (settled + running) / len(self.phases)

    @property
    def has_failure(self) -> bool:
        return any(phase.status is PhaseStatus.FAILED for phase in self.phases)

    def apply(self, event: ReporterEvent) -> Timeline:
        """Nouvelle timeline après `event` ; les événements non pertinents sont neutres."""
        if event.kind == "step":
            return self._enter(event.index, PhaseStatus.RUNNING)
        if event.kind == "skip":
            return self._enter(event.index, PhaseStatus.SKIPPED)
        if event.kind == "progress":
            return self._with_running_detail(event.message)
        if event.kind == "error":
            return self._fail_running()
        if event.kind == "success":
            return self.complete()
        return self

    def complete(self) -> Timeline:
        """Fin de tâche réussie : tout ce qui n'est ni sauté ni échoué est fait."""
        return Timeline(
            phases=tuple(
                replace(phase, status=PhaseStatus.DONE, detail=None)
                if phase.status in (PhaseStatus.PENDING, PhaseStatus.RUNNING)
                else phase
                for phase in self.phases
            )
        )

    # -- transitions internes ------------------------------------------------

    def _enter(self, index: str | None, status: PhaseStatus) -> Timeline:
        """La phase `n` de l'index « n/total » démarre (ou est sautée).

        Les phases précédentes encore en cours/pendantes passent à DONE : le
        moteur n'émet un nouveau `step` qu'une fois l'étape précédente finie.
        Index illisible ou hors bornes → timeline inchangée (rendu indéterminé,
        jamais une fraction fausse).
        """
        parsed = parse_step_index(index) if index is not None else None
        if parsed is None or parsed[0] > len(self.phases):
            return self
        position = parsed[0] - 1
        phases = []
        for i, phase in enumerate(self.phases):
            if i < position and phase.status in (PhaseStatus.PENDING, PhaseStatus.RUNNING):
                phases.append(replace(phase, status=PhaseStatus.DONE, detail=None))
            elif i == position:
                phases.append(replace(phase, status=status, detail=None))
            else:
                phases.append(phase)
        return Timeline(phases=tuple(phases))

    def _with_running_detail(self, message: str) -> Timeline:
        line = message.strip().splitlines()[-1] if message.strip() else ""
        return Timeline(
            phases=tuple(
                replace(phase, detail=line or None)
                if phase.status is PhaseStatus.RUNNING
                else phase
                for phase in self.phases
            )
        )

    def _fail_running(self) -> Timeline:
        return Timeline(
            phases=tuple(
                replace(phase, status=PhaseStatus.FAILED)
                if phase.status is PhaseStatus.RUNNING
                else phase
                for phase in self.phases
            )
        )
