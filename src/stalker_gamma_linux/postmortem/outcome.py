"""Comment la session s'est terminée, et l'extrait de journal qui le prouve.

Trois fins à distinguer, parce qu'elles n'appellent pas les mêmes conseils —
plus une quatrième qui est une **absence de verdict**, et qui a toute sa place :

- `CLEAN_EXIT` : le moteur a fermé son journal lui-même. Le joueur a quitté.
- `ENGINE_CRASH` : le journal s'arrête sur un bloc fatal du moteur.
- `OUT_OF_MEMORY` : le moteur annonce explicitement un échec d'allocation.
- `INCONCLUSIVE` : ni l'un ni l'autre. Le journal est vide, tronqué, ou la
  partie est **encore en cours** — c'est le cas normal si on lance le
  post-mortem sans avoir fermé le jeu. On le dit, on n'invente pas de crash.

L'ordre de décision se lit sur les **positions** des marqueurs, pas sur leur
simple présence : un journal peut très bien contenir un crash *puis* une
fermeture propre (le moteur se rattrape et referme son journal). C'est le
dernier marqueur qui décrit la fin de la session, et lui seul.

Voir `markers` pour la provenance de chaque motif — en particulier pourquoi
chercher `[error]` ou `stack trace` sans les ancrer produit 65 faux positifs sur
une partie parfaitement normale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.postmortem import markers

# Lignes de contexte gardées **avant** le premier marqueur de fin : c'est là que
# le moteur nomme le fichier qui l'a fait tomber (relevé : la ligne
# `! error in stalker … with visual […]` précède le `stack trace:` de deux lignes).
_CONTEXT_LINES = 60

# Plafond de l'extrait conservé pour le rapport d'issue.
_MAX_EXCERPT_LINES = 80


class SessionOutcome(Enum):
    CLEAN_EXIT = auto()
    ENGINE_CRASH = auto()
    OUT_OF_MEMORY = auto()
    INCONCLUSIVE = auto()

    @property
    def is_failure(self) -> bool:
        return self in (SessionOutcome.ENGINE_CRASH, SessionOutcome.OUT_OF_MEMORY)


@dataclass(frozen=True, slots=True)
class SessionEnd:
    """Verdict de fin de session, avec de quoi le vérifier soi-même."""

    outcome: SessionOutcome
    started_at: str | None = None
    engine_build: str | None = None
    excerpt: tuple[str, ...] = ()
    # Champs du bloc fatal du moteur (`Expression`, `Description`, `Arguments`…)
    # quand il y en a un : c'est la seule partie du journal qui explique le crash
    # avec des mots plutôt qu'avec une adresse.
    fatal_fields: tuple[tuple[str, str], ...] = ()


def _last_position(pattern: re.Pattern[str], text: str) -> int:
    last = -1
    for match in pattern.finditer(text):
        last = match.start()
    return last


def classify(tail_text: str) -> SessionOutcome:
    """Fin de session lue sur la queue du journal, dernier marqueur gagnant."""
    clean = _last_position(markers.CLEAN_EXIT_RE, tail_text)
    memory = _last_position(markers.OUT_OF_MEMORY_RE, tail_text)
    crash = max(
        _last_position(markers.STACK_TRACE_RE, tail_text),
        _last_position(markers.FATAL_ERROR_RE, tail_text),
    )

    # Un manque de mémoire produit *aussi* une trace : il doit donc être examiné
    # avant elle, sinon on annoncerait un crash générique là où le moteur a
    # nommé sa cause.
    if memory > clean:
        return SessionOutcome.OUT_OF_MEMORY
    if crash > clean:
        return SessionOutcome.ENGINE_CRASH
    if clean >= 0:
        return SessionOutcome.CLEAN_EXIT
    return SessionOutcome.INCONCLUSIVE


def _first_marker_index(lines: tuple[str, ...]) -> int | None:
    for index, line in enumerate(lines):
        for pattern in (
            markers.OUT_OF_MEMORY_RE,
            markers.FATAL_ERROR_RE,
            markers.STACK_TRACE_RE,
        ):
            if pattern.match(line):
                return index
    return None


def _collapse_repeats(lines: list[str]) -> list[str]:
    """Ne garde que la première occurrence de chaque ligne, en comptant le reste.

    Sans ça l'extrait est illisible, et la mesure le montre : la session plantée
    répète la même erreur 1158 fois, et les dernières lignes avant la trace sont
    un **bloc** de six lignes qui boucle. Replier seulement les doublons
    *consécutifs* n'y changerait rien — c'est le motif entier qui se répète.
    """
    collapsed: list[str] = []
    seen: set[str] = set()
    skipped = 0
    for line in lines:
        if line in seen:
            skipped += 1
            continue
        if skipped:
            collapsed.append(_("    … ({count} repeated line(s) omitted)").format(count=skipped))
            skipped = 0
        seen.add(line)
        collapsed.append(line)
    if skipped:
        collapsed.append(_("    … ({count} repeated line(s) omitted)").format(count=skipped))
    return collapsed


def crash_excerpt(tail: tuple[str, ...]) -> tuple[str, ...]:
    """Extrait autour de la fin anormale : contexte, marqueur, et la suite.

    Vide si aucun marqueur de fin anormale n'est présent — un extrait pris au
    hasard dans une partie normale ne prouverait rien.
    """
    index = _first_marker_index(tail)
    if index is None:
        return ()
    window = list(tail[max(0, index - _CONTEXT_LINES) :])
    return tuple(_collapse_repeats(window)[:_MAX_EXCERPT_LINES])


def fatal_fields(tail_text: str) -> tuple[tuple[str, str], ...]:
    """Champs du bloc fatal (`Expression`, `File`, `Description`, `Arguments`…)."""
    return tuple(
        (match.group("field").strip(), match.group("value").strip())
        for match in markers.ERROR_FIELD_RE.finditer(tail_text)
    )


def _first_group(pattern: re.Pattern[str], text: str, group: str) -> str | None:
    match = pattern.search(text)
    return match.group(group) if match else None


def analyse(head: str, tail: tuple[str, ...]) -> SessionEnd:
    """Verdict complet : fin de session, identité du moteur, extrait de preuve."""
    tail_text = "\n".join(tail)
    outcome = classify(tail_text)
    return SessionEnd(
        outcome=outcome,
        started_at=_first_group(markers.SESSION_START_RE, head, "stamp"),
        engine_build=_first_group(markers.ENGINE_BUILD_RE, head, "build"),
        excerpt=crash_excerpt(tail) if outcome.is_failure else (),
        fatal_fields=fatal_fields(tail_text) if outcome.is_failure else (),
    )
