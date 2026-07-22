"""Arborescence de l'instance portable Mod Organizer 2 livrée par GAMMA.

L'instance vit dans `<install>/gamma/` (voir docs/ARCHITECTURE.md) : c'est une
instance **portable**, donc `ModOrganizer.ini`, `mods/`, `profiles/`, `logs/` et
`overwrite/` sont tous à la racine, à côté de `ModOrganizer.exe`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Mo2Paths:
    """Chemins de l'instance MO2 portable (racine == `<install>/gamma/`)."""

    instance: Path

    @classmethod
    def under(cls, root: Path) -> Mo2Paths:
        """Instance standard sous la racine d'installation : `<root>/gamma`."""
        return cls(instance=root / "gamma")

    @property
    def executable(self) -> Path:
        return self.instance / "ModOrganizer.exe"

    @property
    def organizer_ini(self) -> Path:
        return self.instance / "ModOrganizer.ini"

    @property
    def profiles(self) -> Path:
        return self.instance / "profiles"

    def profile(self, name: str) -> Path:
        return self.profiles / name

    @property
    def mods(self) -> Path:
        return self.instance / "mods"

    @property
    def logs(self) -> Path:
        """Répertoire où MO2/USVFS écrivent leurs journaux (`usvfs-*.log`)."""
        return self.instance / "logs"

    @property
    def overwrite(self) -> Path:
        return self.instance / "overwrite"
