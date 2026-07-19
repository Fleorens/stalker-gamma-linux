"""Types immuables décrivant l'état de l'environnement système."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from stalker_gamma_linux.environment.distro import Distro


class Status(StrEnum):
    OK = "ok"
    MISSING = "manquant"
    OUTDATED = "version trop ancienne"


@dataclass(frozen=True, slots=True)
class Requirement:
    name: str
    status: Status
    detail: str
    install_hint: str | None = None


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    distro: Distro
    requirements: tuple[Requirement, ...]

    @property
    def is_ready(self) -> bool:
        return all(requirement.status is Status.OK for requirement in self.requirements)
