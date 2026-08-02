"""stalker-gamma-linux: couche d'intégration Linux pour S.T.A.L.K.E.R. G.A.M.M.A."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Une seule source de vérité : `pyproject.toml`, via les métadonnées du
    # paquet installé. Un littéral ici aurait dérivé — c'est exactement le
    # décalage tag/version que `release.yml` refuse désormais, mais qu'il ne
    # pouvait pas voir sur un deuxième numéro codé en dur.
    __version__ = version("stalker-gamma-linux")
except PackageNotFoundError:  # exécuté depuis les sources, sans `pip install`
    __version__ = "0.0.0+unknown"
