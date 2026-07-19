"""Arborescence du préfixe Proton partagé et de ses journaux."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PrefixPaths:
    """Chemins du préfixe partagé MO2 + jeu (voir docs/ARCHITECTURE.md).

    `prefix` est le répertoire passé à umu via WINEPREFIX ; umu/Proton y créent
    la vraie racine Wine dans un sous-dossier `pfx/` (layout compatdata).
    """

    prefix: Path
    logs: Path

    @classmethod
    def under(cls, root: Path) -> PrefixPaths:
        """Arborescence standard `prefix/` et `logs/` sous la racine d'installation."""
        return cls(prefix=root / "prefix", logs=root / "logs")

    @property
    def wine_root(self) -> Path:
        """Racine Wine réelle : `prefix/pfx` (layout umu/Proton) sinon `prefix/`."""
        pfx = self.prefix / "pfx"
        return pfx if pfx.exists() else self.prefix

    @property
    def winetricks_log(self) -> Path:
        """Journal des verbs installés, tenu par winetricks lui-même."""
        return self.wine_root / "winetricks.log"

    @property
    def system32(self) -> Path:
        return self.wine_root / "drive_c" / "windows" / "system32"

    @property
    def version_file(self) -> Path:
        """Fichier `version` écrit par Proton à la racine du compat data."""
        return self.prefix / "version"

    def ensure_directories(self) -> None:
        """Crée les répertoires manquants. Idempotent, ne touche jamais à leur contenu."""
        for path in (self.prefix, self.logs):
            path.mkdir(parents=True, exist_ok=True)
