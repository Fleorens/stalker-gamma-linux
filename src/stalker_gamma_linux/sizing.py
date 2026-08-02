"""Dimensionnement disque d'une installation GAMMA — **source unique** des chiffres.

Avant ce module, quatre chiffres différents circulaient pour la même exigence :
`environment.checks` exigeait 103 Gio (27 téléchargés + 76 installés),
`gui.space` bloquait sous 160 Gio, la CLI annonçait « ~146 GB » et le dialog
d'installation « ~150 GB ». Avec 120 Gio libres, `doctor` affichait donc
« [ OK ] Espace disque » pendant que la GUI refusait de lancer l'installation.

Le découpage ci-dessous est celui mesuré dans docs/INSTALL-MANUAL.md §1
(sept. 2025), seule référence propre à *notre* pipeline. Le chiffre officiel
amont (« 27 Go téléchargés / 76 Go installés », wiki Grokitach) ne s'y applique
pas : il suppose que le cache d'archives est jeté après l'installation, alors
qu'on le conserve pour rendre les mises à jour incrémentales.

Tout est exprimé en **Gio** (2³⁰ octets), l'unité que renvoie `shutil.disk_usage` :
c'est aussi ce que la CLI et la GUI affichent, pour qu'un seuil et un espace
libre soient toujours comparables à l'œil.
"""

from __future__ import annotations

GIB = 1024**3

# Découpage d'une installation complète (docs/INSTALL-MANUAL.md §1).
ANOMALY_GIB = 17  # `anomaly/` — jeu de base
MODPACK_GIB = 83  # `gamma/` — instance MO2 + mods extraits
CACHE_GIB = 46  # `cache/` — archives téléchargées, conservées pour les updates
TOTAL_INSTALL_GIB = ANOMALY_GIB + MODPACK_GIB + CACHE_GIB  # 146

# Seuil **bloquant** : le total ci-dessus plus une marge de travail pour
# l'extraction (gamma-launcher décompresse chaque archive avant de la déplacer).
# Sous ce seuil l'installation échouera en cours de route, autant le dire avant.
MINIMUM_FREE_GIB = 160

# Recommandation amont (Grokitach) pour une installation sereine : de la place
# pour les sauvegardes, les mods ajoutés à la main et les futures mises à jour.
RECOMMENDED_FREE_GIB = 250

MINIMUM_FREE_BYTES = MINIMUM_FREE_GIB * GIB
RECOMMENDED_FREE_BYTES = RECOMMENDED_FREE_GIB * GIB
