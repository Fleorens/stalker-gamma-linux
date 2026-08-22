"""Arborescence d'installation pilotée par le moteur gamma-launcher."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InstallPaths:
    """Les trois répertoires d'une installation (voir docs/ARCHITECTURE.md)."""

    anomaly: Path
    gamma: Path
    cache: Path

    @classmethod
    def under(cls, root: Path) -> InstallPaths:
        """Construit l'arborescence standard `anomaly/`, `gamma/`, `cache/` sous `root`."""
        return cls(anomaly=root / "anomaly", gamma=root / "gamma", cache=root / "cache")

    @property
    def downloads(self) -> Path:
        """Dossier où `full-install` dépose les archives de mods : `<gamma>/downloads`.

        Codé en dur côté amont (`FullInstall._dl_dir = self._gamma_dir / "downloads"`).
        Peut être un vrai dossier ou un lien symbolique vers `cache/` selon
        l'historique de l'installation (voir `engine.runner.install_gamma`) —
        les deux se traversent de la même façon.
        """
        return self.gamma / "downloads"

    def ensure_directories(self) -> None:
        """Crée les répertoires manquants. Idempotent, ne touche jamais à leur contenu."""
        for path in (self.anomaly, self.gamma, self.cache):
            path.mkdir(parents=True, exist_ok=True)
