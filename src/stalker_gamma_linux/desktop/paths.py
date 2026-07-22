"""Chemins XDG du raccourci bureau (spec freedesktop Desktop Entry + icon theme).

Identifiant d'application volontairement simple (`stalker-gamma-linux`, pas de
reverse-DNS type `io.github.<user>...`) : ça reste un chemin stable et lisible,
sans dépendre d'un nom de compte GitHub particulier.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_ID = "stalker-gamma-linux"
ICON_THEME_SIZE = "256x256"


@dataclass(frozen=True, slots=True)
class DesktopPaths:
    """Racine XDG (`XDG_DATA_HOME`) et fichiers dérivés (`.desktop`, icône)."""

    data_home: Path

    @classmethod
    def default(cls) -> DesktopPaths:
        """`$XDG_DATA_HOME`, ou `~/.local/share` par défaut (spec freedesktop)."""
        override = os.environ.get("XDG_DATA_HOME")
        base = Path(override) if override else Path.home() / ".local" / "share"
        return cls(data_home=base)

    @property
    def applications_dir(self) -> Path:
        return self.data_home / "applications"

    @property
    def icon_theme_root(self) -> Path:
        return self.data_home / "icons" / "hicolor"

    @property
    def icon_dir(self) -> Path:
        return self.icon_theme_root / ICON_THEME_SIZE / "apps"

    @property
    def desktop_file(self) -> Path:
        return self.applications_dir / f"{APP_ID}.desktop"

    @property
    def icon_file(self) -> Path:
        return self.icon_dir / f"{APP_ID}.png"
