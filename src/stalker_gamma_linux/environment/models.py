"""Types immuables décrivant l'état de l'environnement système."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from stalker_gamma_linux.environment.distro import Distro


class Status(StrEnum):
    OK = "ok"
    MISSING = "manquant"
    OUTDATED = "version trop ancienne"
    # Détecté absent mais non actionnable dans cet environnement (ex. GPU Vulkan
    # en VM sans passthrough) : on ne propose pas de correctif et ça ne bloque
    # pas l'installation, qui n'a besoin du GPU que pour *jouer*.
    UNAVAILABLE = "non disponible ici"
    # Absent mais facultatif : le pipeline (umu) n'en a pas besoin — utile pour
    # du confort (Steam Input, mode Gaming du Deck) ou du dépannage manuel
    # (protontricks). Jamais bloquant, jamais dans le plan « à faire ».
    OPTIONAL = "recommandé, absent"

    @property
    def is_blocking(self) -> bool:
        """Un prérequis dont l'absence empêche l'install de se dérouler correctement.

        `UNAVAILABLE` et `OK` ne bloquent pas : le premier est un constat
        informatif (rien à faire ici), le second est satisfait.
        """
        return self in (Status.MISSING, Status.OUTDATED)


@dataclass(frozen=True, slots=True)
class Requirement:
    name: str
    status: Status
    detail: str
    install_hint: str | None = None
    # Clé stable dans `INSTALL_COMMANDS` (ex. "steam", "umu-launcher") permettant
    # de regrouper les remèdes en un seul plan d'installation (`environment.plan`).
    # `None` quand il n'y a pas de paquet système derrière (ex. espace disque).
    key: str | None = None
    # Faux pour ce qui n'est nécessaire qu'à l'exécution du jeu, pas à son
    # installation : un GPU Vulkan absent doit apparaître dans le diagnostic
    # sans empêcher de télécharger 146 Gio de mods sur une machine sans pilote.
    needed_to_install: bool = True

    @property
    def blocks_install(self) -> bool:
        return self.needed_to_install and self.status.is_blocking


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    distro: Distro
    requirements: tuple[Requirement, ...]

    @property
    def is_ready(self) -> bool:
        return not any(requirement.status.is_blocking for requirement in self.requirements)

    @property
    def install_blockers(self) -> tuple[Requirement, ...]:
        """Prérequis manquants qui empêchent réellement l'installation d'aboutir.

        Distinct d'`is_ready`, qui reste le verdict « tout est bon » affiché par
        `doctor` : on ne refuse de démarrer que sur ce qui condamne l'installation
        (7z, libunrar, umu, espace disque), pas sur ce qui ne servira qu'à jouer.
        """
        return tuple(requirement for requirement in self.requirements if requirement.blocks_install)
