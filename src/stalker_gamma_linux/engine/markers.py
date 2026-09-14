"""Reconnaissance unifiée des signatures d'échec liées à ModDB.

Une seule table pour les deux chemins qui en ont besoin : `engine.runner.verify`
(qui doit dire « invérifiable en ligne », pas « corrompu ») et `engine.errors`
(qui doit donner la consigne à suivre pendant un `anomaly-install`/`full-install`).
Avant ce module, chacun maintenait sa propre liste de marqueurs, et « Download
link not found when requesting » finissait dupliqué dans les deux — un
correctif dans l'un pouvait diverger silencieusement de l'autre.

Trois causes, lues dans la source de gamma-launcher v3.1
(`launcher/mods/downloader/base.py`, `launcher/mods/downloader/moddb.py`,
`launcher/commands/check.py`) plutôt que devinées — voir `docs/ARCHITECTURE.md` :

* `NETWORK_UNREACHABLE` — `requests.exceptions.ConnectionError` non rattrapée.
  `DefaultDownloader.download` la retente 3 fois en 30 s (`tenacity`) avant de
  la relever telle quelle : à ce stade ce n'est plus un mod précis, c'est le
  réseau (ou ModDB dans son ensemble) qui ne répond pas.
* `MOD_LINK_BROKEN` — la page ModDB a répondu, mais ce qu'on y cherchait n'y
  est plus (lien de téléchargement, nom de fichier, hash), ou l'archive livrée
  n'en est pas une. Un mirroir mort, un mod déplacé/retiré en amont et un défi
  Cloudflare/403 produisent tous **le même texte** de ce côté-ci — `moddb.py`
  ne fait pas la différence, donc nous non plus (voir `_moddb_hint` dans
  `engine.errors`). L'`AttributeError` sur `unpackinfo` (py7zr) en est le
  symptôme indirect : l'archive en cache est en réalité une page d'erreur HTML
  sauvée sous le nom attendu (issues amont #283/#284).
* `LOCAL_CORRUPTION` — `Hash verification failed…` (`HashError` amont) :
  l'archive en cache ne correspond pas à son hash MD5. Seule cause où
  personne, côté ModDB, n'est en cause — supprimer et relancer suffit
  (`integrity.repair`, déjà le mécanisme de `verify --repair`).
"""

from __future__ import annotations

from enum import Enum, auto


class FailureCause(Enum):
    LOCAL_CORRUPTION = auto()
    MOD_LINK_BROKEN = auto()
    NETWORK_UNREACHABLE = auto()


# `launcher/mods/downloader/base.py` : `_check_if_exist`/`_check_if_non_exist`
# lèvent `HashError` avec ce préfixe quand l'archive du cache est absente ou ne
# correspond pas au MD5 attendu.
CORRUPTION_MARKERS: tuple[str, ...] = ("Hash verification failed",)

# `launcher/mods/downloader/moddb.py` : `ModDBDownloadError`/`HashError` levées
# quand la page ModDB répond mais que le lien, le nom de fichier ou le hash
# attendus n'y sont plus — et l'`AttributeError` de `py7zr` quand l'archive
# livrée est en fait une page d'erreur HTML (issues #283/#284).
MOD_LINK_BROKEN_MARKERS: tuple[str, ...] = (
    "ModDBDownloadError",
    "Download link not found when requesting",
    "Could not find Filename in",
    "Could not find archive hash in",
    "since ModDB info do not match download url",
    "No Info URL provided",
    "'NoneType' object has no attribute 'unpackinfo'",
    "403 Client Error",
)

# `launcher/mods/downloader/base.py` : `requests.exceptions.ConnectionError`
# relevée par `tenacity` après 3 tentatives (30 s d'intervalle) — le réseau ou
# ModDB dans son ensemble est injoignable, pas un mod en particulier.
NETWORK_UNREACHABLE_MARKERS: tuple[str, ...] = (
    "requests.exceptions.ConnectionError",
    "Max retries exceeded with url",
    "Failed to establish a new connection",
    "Name or service not known",
    "Connection refused",
    "Read timed out",
)

_MARKERS_BY_CAUSE: tuple[tuple[FailureCause, tuple[str, ...]], ...] = (
    (FailureCause.LOCAL_CORRUPTION, CORRUPTION_MARKERS),
    (FailureCause.MOD_LINK_BROKEN, MOD_LINK_BROKEN_MARKERS),
    (FailureCause.NETWORK_UNREACHABLE, NETWORK_UNREACHABLE_MARKERS),
)

# Contrat historique de `engine.runner.verify` : une archive locale n'a pas pu
# être comparée à ModDB, mais rien n'indique qu'elle est corrompue — seuls les
# marqueurs « page lue, information absente » qualifient (pas les erreurs
# réseau, absentes de ce jeu avant ce module ; les y ajouter changerait le
# comportement de `verify` sans que ça ait été demandé).
UNVERIFIABLE_MARKERS: tuple[str, ...] = MOD_LINK_BROKEN_MARKERS


def classify(output: str) -> FailureCause | None:
    """Cause reconnue dans `output`, ou `None` si rien ne correspond.

    Insensible à la casse : gamma-launcher ne garantit pas la casse exacte
    d'une trace Python d'une version à l'autre.
    """
    lowered = output.lower()
    for cause, markers in _MARKERS_BY_CAUSE:
        if any(marker.lower() in lowered for marker in markers):
            return cause
    return None
