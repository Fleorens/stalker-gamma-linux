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


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    distro: Distro
    requirements: tuple[Requirement, ...]

    @property
    def is_ready(self) -> bool:
        return not any(requirement.status.is_blocking for requirement in self.requirements)
